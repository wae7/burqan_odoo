import logging
from datetime import datetime, timezone

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError

from .exceptions import BurqanWebhookError

_logger = logging.getLogger(__name__)

PAYMENT_METHOD_DISPLAY = {
    'cash': 'Manual Payment (Cash)',
    'deferred': 'Manual Payment (Credit)',
}
PAYMENT_JOURNAL_NAME = {
    'cash': 'Cash',
    'deferred': 'Credit',
}


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    x_burqan_order_id = fields.Char(
        string='Burqan Order ID',
        index=True,
        copy=False,
        help='Burqan Store orderId. Used for webhook idempotency.',
    )
    x_burqan_payment_type = fields.Selection(
        [
            ('cash', 'Cash'),
            ('deferred', 'Deferred'),
        ],
        string='Burqan Payment Type',
        copy=False,
        help='cash or deferred as sent by Burqan Store.',
    )
    x_burqan_source = fields.Selection(
        [
            ('store', 'Store'),
            ('external', 'External'),
        ],
        string='Burqan Source',
        copy=False,
        default='store',
        help='store = rep store sale; external = admin-recorded external sale.',
    )

    _sql_constraints = [
        (
            'x_burqan_order_id_unique',
            'UNIQUE(x_burqan_order_id)',
            'A sale order with this Burqan order ID already exists.',
        ),
    ]

    @api.model
    def _burqan_process_sale_webhook(self, payload):
        """Handle sale.completed / sale.updated / sale.cancelled from Burqan."""
        if not isinstance(payload, dict):
            raise BurqanWebhookError(400, 'Payload must be a JSON object.')
        event = payload.get('event')
        if event == 'sale.cancelled':
            return self._burqan_cancel_sale(payload)
        if event in ('sale.completed', 'sale.updated'):
            self._burqan_validate_payload(payload)
            return self._burqan_upsert_sale(payload, event=event)
        raise BurqanWebhookError(
            400,
            'event must be sale.completed, sale.updated, or sale.cancelled.',
        )

    @api.model
    def _burqan_upsert_sale(self, payload, event='sale.completed'):
        order_id = str(payload['orderId']).strip()
        existing = self.search([('x_burqan_order_id', '=', order_id)], limit=1)

        if existing and event == 'sale.completed':
            return existing, True, 'reused'

        if existing and event == 'sale.updated':
            self._burqan_assert_mutable(existing)
            return self._burqan_update_existing_sale(existing, payload)

        if not existing and event == 'sale.updated':
            # Contracted receiver; if order missing, create like completed.
            _logger.info('Burqan sale.updated for unknown orderId=%s; creating', order_id)

        lines_data, templates = self._burqan_resolve_lines(payload['lines'])
        company = self._burqan_company_for_templates(templates)
        source = self._burqan_source(payload)
        partner = self._burqan_find_or_create_partner(
            payload.get('store') or {},
            source=source,
        )
        salesperson = self.env['res.users']._burqan_find_or_create_salesperson(
            payload.get('representative') or {},
            create_if_missing=True,
        )[0]
        date_order = self._burqan_parse_occurred_at(payload.get('occurredAt'))
        payment_type = self._burqan_payment_type(payload.get('paymentType'))
        note = self._burqan_order_note(payload, salesperson, source)

        try:
            order_vals = {
                'partner_id': partner.id,
                'date_order': date_order,
                'client_order_ref': order_id,
                'x_burqan_order_id': order_id,
                'x_burqan_payment_type': payment_type,
                'x_burqan_source': source,
                'note': note,
                'company_id': company.id,
            }
            if salesperson:
                order_vals['user_id'] = salesperson.id
            order = self.with_company(company).create(order_vals)
            self._burqan_replace_lines(order, lines_data, company)
            order.action_confirm()
            self._burqan_ensure_draft_invoice(order, payment_type)
        except (UserError, ValidationError) as err:
            raced = self.search([('x_burqan_order_id', '=', order_id)], limit=1)
            if raced:
                return raced, True, 'reused'
            raise BurqanWebhookError(400, str(err)) from err

        return order, False, 'created'

    @api.model
    def _burqan_update_existing_sale(self, order, payload):
        company = order.company_id
        source = self._burqan_source(payload)
        partner = self._burqan_find_or_create_partner(
            payload.get('store') or {},
            source=source,
        )
        salesperson = self.env['res.users']._burqan_find_or_create_salesperson(
            payload.get('representative') or {},
            create_if_missing=True,
        )[0]
        payment_type = self._burqan_payment_type(payload.get('paymentType'))
        lines_data, _templates = self._burqan_resolve_lines(payload['lines'])
        note = self._burqan_order_note(payload, salesperson, source)

        # Drop draft invoices so lines can be replaced cleanly.
        draft_invoices = order.invoice_ids.filtered(lambda m: m.state == 'draft')
        if draft_invoices:
            draft_invoices.button_cancel()
            draft_invoices.unlink()

        if order.state in ('sale', 'done'):
            order._action_cancel()
        if order.state == 'cancel':
            order.action_draft()

        vals = {
            'partner_id': partner.id,
            'x_burqan_payment_type': payment_type,
            'x_burqan_source': source,
            'note': note,
            'client_order_ref': order.x_burqan_order_id,
        }
        if payload.get('occurredAt'):
            vals['date_order'] = self._burqan_parse_occurred_at(payload.get('occurredAt'))
        if salesperson:
            vals['user_id'] = salesperson.id
        order.write(vals)
        self._burqan_replace_lines(order, lines_data, company)
        order.action_confirm()
        self._burqan_ensure_draft_invoice(order, payment_type, refresh=True)
        return order, False, 'updated'

    @api.model
    def _burqan_cancel_sale(self, payload):
        order_id = payload.get('orderId')
        if order_id is None or str(order_id).strip() == '':
            raise BurqanWebhookError(400, 'orderId is required.')
        order_id = str(order_id).strip()
        order = self.search([('x_burqan_order_id', '=', order_id)], limit=1)
        if not order:
            return self.browse(), True, 'missing'
        if order.state == 'cancel':
            return order, True, 'already_cancelled'

        posted = order.invoice_ids.filtered(lambda m: m.state == 'posted')
        if posted:
            raise BurqanWebhookError(
                409,
                'Sale has posted invoice(s); cannot cancel automatically.',
                extra={
                    'saleOrderId': order.id,
                    'postedInvoiceIds': posted.ids,
                },
            )

        draft_invoices = order.invoice_ids.filtered(lambda m: m.state == 'draft')
        if draft_invoices:
            draft_invoices.button_cancel()

        if order.state != 'cancel':
            order._action_cancel()
        return order, False, 'cancelled'

    @api.model
    def _burqan_assert_mutable(self, order):
        posted = order.invoice_ids.filtered(lambda m: m.state == 'posted')
        if posted:
            raise BurqanWebhookError(
                409,
                'Sale has posted invoice(s); cannot update automatically.',
                extra={
                    'saleOrderId': order.id,
                    'postedInvoiceIds': posted.ids,
                },
            )
        if order.state == 'cancel':
            raise BurqanWebhookError(
                409,
                'Sale order is cancelled; cannot update.',
                extra={'saleOrderId': order.id},
            )

    @api.model
    def _burqan_replace_lines(self, order, lines_data, company):
        order.order_line.unlink()
        for line in lines_data:
            self.env['sale.order.line'].with_company(company).create({
                'order_id': order.id,
                'product_id': line['product_id'],
                'product_uom_qty': line['quantity'],
                'price_unit': line['unit_price'],
                'technical_price_unit': line['unit_price'],
            })

    @api.model
    def _burqan_ensure_draft_invoice(self, order, payment_type, refresh=False):
        draft = order.invoice_ids.filtered(lambda m: m.state == 'draft')
        if refresh and draft:
            draft.button_cancel()
            draft.unlink()
            draft = self.env['account.move']

        open_invoices = order.invoice_ids.filtered(lambda m: m.state in ('draft', 'posted'))
        if not open_invoices:
            invoices = order._create_invoices()
        else:
            invoices = open_invoices.filtered(lambda m: m.state == 'draft') or open_invoices

        if not invoices:
            return self.env['account.move']

        method_line = self._burqan_payment_method_line(payment_type, order.company_id)
        if method_line:
            invoices.filtered(lambda m: m.state == 'draft').write({
                'preferred_payment_method_line_id': method_line.id,
            })

        # Keep optional auto-post setting (default off = draft only).
        if self.env['ir.config_parameter'].sudo().get_param(
            'burqan.webhook_auto_invoice'
        ) in ('True', 'true', '1'):
            to_post = invoices.filtered(lambda m: m.state == 'draft')
            if to_post:
                to_post.action_post()
        return invoices

    @api.model
    def _burqan_payment_method_line(self, payment_type, company):
        """Resolve inbound Manual Payment (Cash|Credit) for the company."""
        if payment_type not in PAYMENT_METHOD_DISPLAY:
            return self.env['account.payment.method.line']

        display = PAYMENT_METHOD_DISPLAY[payment_type]
        journal_name = PAYMENT_JOURNAL_NAME[payment_type]
        Line = self.env['account.payment.method.line'].sudo()

        # Prefer exact display_name match (e.g. Manual Payment (Cash)).
        lines = Line.search([
            ('payment_type', '=', 'inbound'),
            ('journal_id.company_id', '=', company.id),
        ])
        match = lines.filtered(lambda l: (l.display_name or '') == display)[:1]
        if match:
            return match

        journal = self.env['account.journal'].sudo().search([
            ('company_id', '=', company.id),
            ('type', 'in', ('cash', 'bank')),
            ('name', '=', journal_name),
        ], limit=1)
        if not journal:
            journal = self.env['account.journal'].sudo().create({
                'name': journal_name,
                'type': 'cash',
                'company_id': company.id,
                'code': journal_name[:5].upper(),
            })

        method = self.env['account.payment.method'].sudo().search([
            ('code', '=', 'manual'),
            ('payment_type', '=', 'inbound'),
        ], limit=1)
        if not method:
            method = self.env['account.payment.method'].sudo().create({
                'name': 'Manual Payment',
                'code': 'manual',
                'payment_type': 'inbound',
            })

        line = Line.search([
            ('journal_id', '=', journal.id),
            ('payment_method_id', '=', method.id),
            ('payment_type', '=', 'inbound'),
        ], limit=1)
        if not line:
            line = Line.create({
                'name': 'Manual Payment',
                'journal_id': journal.id,
                'payment_method_id': method.id,
            })
        elif line.name != 'Manual Payment':
            line.name = 'Manual Payment'
        return line

    @api.model
    def _burqan_source(self, payload):
        raw = (payload.get('source') or 'store')
        if not isinstance(raw, str):
            raise BurqanWebhookError(400, 'source must be "store" or "external".')
        source = raw.strip().lower()
        if source not in ('store', 'external'):
            raise BurqanWebhookError(400, 'source must be "store" or "external".')
        return source

    @api.model
    def _burqan_validate_payload(self, payload):
        if payload.get('event') not in ('sale.completed', 'sale.updated'):
            raise BurqanWebhookError(400, 'event must be sale.completed or sale.updated.')
        order_id = payload.get('orderId')
        if order_id is None or str(order_id).strip() == '':
            raise BurqanWebhookError(400, 'orderId is required.')
        source = self._burqan_source(payload)
        store = payload.get('store')
        if not isinstance(store, dict):
            raise BurqanWebhookError(400, 'store is required.')
        name = (store.get('name') or '').strip() if store.get('name') is not None else ''
        if not name:
            raise BurqanWebhookError(400, 'store.name is required.')
        if source == 'store' and store.get('id') in (None, ''):
            raise BurqanWebhookError(400, 'store.id is required for store sales.')
        payment = payload.get('paymentType')
        if payment not in (None, '') and str(payment).strip().lower() not in ('cash', 'deferred'):
            raise BurqanWebhookError(400, 'paymentType must be "cash" or "deferred".')
        lines = payload.get('lines')
        if not isinstance(lines, list) or not lines:
            raise BurqanWebhookError(400, 'lines must be a non-empty array.')
        for index, line in enumerate(lines):
            if not isinstance(line, dict):
                raise BurqanWebhookError(400, 'Each line must be an object.')
            if line.get('productId') in (None, ''):
                raise BurqanWebhookError(400, f'lines[{index}].productId is required.')
            try:
                quantity = float(line.get('quantity'))
            except (TypeError, ValueError):
                raise BurqanWebhookError(400, f'lines[{index}].quantity must be a number.')
            if quantity <= 0:
                raise BurqanWebhookError(400, f'lines[{index}].quantity must be greater than 0.')
            try:
                float(line.get('unitPrice'))
            except (TypeError, ValueError):
                raise BurqanWebhookError(400, f'lines[{index}].unitPrice must be a number.')

    @api.model
    def _burqan_resolve_lines(self, lines):
        Template = self.env['product.template']
        resolved = []
        templates = Template.browse()
        missing = []
        seen_missing = set()
        for line in lines:
            integration_id = str(line['productId']).strip()
            template = Template.search(
                [('x_integration_id', '=', integration_id)],
                limit=1,
            )
            if not template or not template.product_variant_id:
                if integration_id not in seen_missing:
                    missing.append(line['productId'])
                    seen_missing.add(integration_id)
                continue
            templates |= template
            resolved.append({
                'product_id': template.product_variant_id.id,
                'quantity': float(line['quantity']),
                'unit_price': float(line['unitPrice']),
            })
        if missing:
            raise BurqanWebhookError(
                422,
                'Unknown productId values. Set product.template x_integration_id (ID).',
                extra={'missingProductIds': missing},
            )
        return resolved, templates

    @api.model
    def _burqan_company_for_templates(self, templates):
        companies = templates.mapped('company_id').filtered(lambda c: c)
        if len(companies) > 1:
            raise BurqanWebhookError(
                422,
                'Products belong to more than one company.',
            )
        return companies[:1] or self.env.company

    @api.model
    def _burqan_find_or_create_partner(self, store, source='store'):
        Partner = self.env['res.partner']
        name = (store.get('name') or '').strip()
        phone = (store.get('phone') or '').strip() or False
        store_id_raw = store.get('id')
        store_id = (
            str(store_id_raw).strip()
            if store_id_raw not in (None, '')
            else False
        )

        # Prefer registered store.id even for external sales when Burqan links them.
        if store_id:
            partner = Partner._burqan_find_store_partner(store_id, phone=phone, name=name)
            if partner:
                vals = {'x_burqan_store_id': store_id}
                if name and partner.name != name:
                    vals['name'] = name
                if phone and not partner.phone:
                    vals['phone'] = phone
                if not partner.active:
                    vals['active'] = True
                partner.write(vals)
                partner._burqan_absorb_store_duplicates(
                    store_id=store_id, phone=phone, name=name,
                )
                return partner
            partner = Partner.create({
                'name': name,
                'phone': phone,
                'x_burqan_store_id': store_id,
                'company_type': 'company',
                'is_company': True,
                'customer_rank': 1,
            })
            partner._burqan_absorb_store_duplicates(
                store_id=store_id, phone=phone, name=name,
            )
            return partner

        # Free-text external customer: match by name, never set x_burqan_store_id.
        partner = Partner.search([
            ('name', '=', name),
            ('is_company', '=', True),
            ('x_burqan_store_id', '=', False),
        ], limit=1)
        if not partner:
            partner = Partner.search([
                ('name', '=', name),
                ('x_burqan_store_id', '=', False),
            ], limit=1)
        if not partner:
            vals = {
                'name': name,
                'company_type': 'company',
                'is_company': True,
                'customer_rank': 1,
            }
            if phone:
                vals['phone'] = phone
            partner = Partner.create(vals)
        elif phone and not partner.phone:
            partner.phone = phone
        return partner

    @api.model
    def _burqan_payment_type(self, value):
        if not value:
            return False
        normalized = str(value).strip().lower()
        if normalized in ('cash', 'deferred'):
            return normalized
        return False

    @api.model
    def _burqan_parse_occurred_at(self, value):
        if not value:
            return fields.Datetime.now()
        raw = str(value).strip()
        if raw.endswith('Z'):
            raw = raw[:-1] + '+00:00'
        try:
            parsed = datetime.fromisoformat(raw)
        except ValueError as err:
            raise BurqanWebhookError(400, f'occurredAt is not a valid ISO datetime: {err}')
        if parsed.tzinfo:
            parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
        return parsed

    @api.model
    def _burqan_order_note(self, payload, salesperson, source='store'):
        store = payload.get('store') or {}
        payment = payload.get('paymentType') or ''
        store_id = store.get('id')
        store_label = store.get('name') or ''
        if store_id not in (None, ''):
            store_label = f"{store_label} (id={store_id})"
        lines = [
            f"Burqan order {payload.get('orderId')}",
            f"Source: {source}",
            f"Customer: {store_label}",
            f"Occurred (Amman): {payload.get('occurredAtAmman') or ''}",
            f"Payment: {payment}",
        ]
        if salesperson:
            lines.append(
                f"Salesperson: {salesperson.name}"
                f" ({salesperson.email or salesperson.login})"
            )
        return '\n'.join(lines)

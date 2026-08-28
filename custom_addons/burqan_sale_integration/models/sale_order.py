import logging
from datetime import datetime, timezone

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class BurqanWebhookError(Exception):
    def __init__(self, status, error, extra=None):
        super().__init__(error)
        self.status = status
        self.error = error
        self.extra = extra or {}


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

    _sql_constraints = [
        (
            'x_burqan_order_id_unique',
            'UNIQUE(x_burqan_order_id)',
            'A sale order with this Burqan order ID already exists.',
        ),
    ]

    @api.model
    def _burqan_process_sale_webhook(self, payload):
        """Create or reuse a confirmed sale order from a Burqan sale.completed payload."""
        self._burqan_validate_payload(payload)

        order_id = str(payload['orderId']).strip()
        existing = self.search([('x_burqan_order_id', '=', order_id)], limit=1)
        if existing:
            return existing, True

        lines_data, templates = self._burqan_resolve_lines(payload['lines'])
        company = self._burqan_company_for_templates(templates)
        partner = self._burqan_find_or_create_partner(payload.get('store') or {})
        salesperson, rep_note = self._burqan_match_salesperson(payload.get('representative') or {})
        date_order = self._burqan_parse_occurred_at(payload.get('occurredAt'))
        payment_type = self._burqan_payment_type(payload.get('paymentType'))
        note = self._burqan_order_note(payload, salesperson, rep_note)

        try:
            order = self.with_company(company).create({
                'partner_id': partner.id,
                'date_order': date_order,
                'client_order_ref': order_id,
                'x_burqan_order_id': order_id,
                'x_burqan_payment_type': payment_type,
                'note': note,
                'company_id': company.id,
            })
            if salesperson:
                order.user_id = salesperson

            for line in lines_data:
                self.env['sale.order.line'].with_company(company).create({
                    'order_id': order.id,
                    'product_id': line['product_id'],
                    'product_uom_qty': line['quantity'],
                    'price_unit': line['unit_price'],
                    'technical_price_unit': line['unit_price'],
                })

            order.action_confirm()

            if self.env['ir.config_parameter'].sudo().get_param(
                'burqan.webhook_auto_invoice'
            ) in ('True', 'true', '1'):
                invoices = order._create_invoices()
                if invoices:
                    invoices.action_post()
        except (UserError, ValidationError) as err:
            raced = self.search([('x_burqan_order_id', '=', order_id)], limit=1)
            if raced:
                return raced, True
            raise BurqanWebhookError(400, str(err)) from err

        return order, False

    @api.model
    def _burqan_validate_payload(self, payload):
        if not isinstance(payload, dict):
            raise BurqanWebhookError(400, 'Payload must be a JSON object.')
        if payload.get('event') != 'sale.completed':
            raise BurqanWebhookError(400, 'event must be sale.completed.')
        order_id = payload.get('orderId')
        if order_id is None or str(order_id).strip() == '':
            raise BurqanWebhookError(400, 'orderId is required.')
        store = payload.get('store')
        if not isinstance(store, dict) or store.get('id') in (None, '') or not store.get('name'):
            raise BurqanWebhookError(400, 'store.id and store.name are required.')
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
    def _burqan_find_or_create_partner(self, store):
        Partner = self.env['res.partner']
        store_id = str(store['id']).strip()
        phone = (store.get('phone') or '').strip() or False
        partner = Partner.search([('x_burqan_store_id', '=', store_id)], limit=1)
        if not partner and phone:
            partner = Partner.search([
                ('phone', '=', phone),
                '|',
                ('x_burqan_store_id', '=', False),
                ('x_burqan_store_id', '=', store_id),
            ], limit=1)
            if partner and not partner.x_burqan_store_id:
                partner.x_burqan_store_id = store_id
        if not partner:
            partner = Partner.create({
                'name': store['name'],
                'phone': phone,
                'x_burqan_store_id': store_id,
                'company_type': 'company',
                'is_company': True,
                'customer_rank': 1,
            })
        return partner

    @api.model
    def _burqan_match_salesperson(self, representative):
        Users = self.env['res.users']
        email = (representative.get('email') or '').strip()
        name = (representative.get('name') or '').strip()
        user = Users.browse()
        if email:
            user = Users.search(['|', ('login', '=', email), ('email', '=', email)], limit=1)
        if not user and name:
            user = Users.search([('name', '=', name)], limit=1)
        if user:
            return user, False
        if not representative:
            return Users.browse(), False
        parts = []
        if name:
            parts.append(name)
        if email:
            parts.append(email)
        if representative.get('id') not in (None, ''):
            parts.append(f"id={representative.get('id')}")
        return Users.browse(), ', '.join(parts) if parts else False

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
    def _burqan_order_note(self, payload, salesperson, rep_note):
        store = payload.get('store') or {}
        payment = payload.get('paymentType') or ''
        lines = [
            f"Burqan order {payload.get('orderId')}",
            f"Store: {store.get('name')} (id={store.get('id')})",
            f"Occurred (Amman): {payload.get('occurredAtAmman') or ''}",
            f"Payment: {payment}",
        ]
        if not salesperson and rep_note:
            lines.append(f"Representative: {rep_note}")
        return '\n'.join(lines)

from odoo import api, fields, models

from .exceptions import BurqanWebhookError


class ResPartner(models.Model):
    _inherit = 'res.partner'

    x_burqan_store_id = fields.Char(
        string='Burqan Store ID',
        index=True,
        copy=False,
        help='Burqan Store store.id used to match webhook customers.',
    )
    x_burqan_sales_cash = fields.Monetary(
        string='Sales Total (Cash)',
        compute='_compute_burqan_store_balances',
        currency_field='currency_id',
        help='Confirmed Burqan sale orders with payment type cash (from sales, not invoices).',
    )
    x_burqan_sales_credit = fields.Monetary(
        string='Sales Total (Credit)',
        compute='_compute_burqan_store_balances',
        currency_field='currency_id',
        help='Confirmed Burqan sale orders with payment type deferred/credit (from sales, not invoices).',
    )
    x_burqan_sales_total = fields.Monetary(
        string='Sales Total',
        compute='_compute_burqan_store_balances',
        currency_field='currency_id',
        help='Cash + credit confirmed Burqan sale order totals.',
    )
    x_burqan_amount_paid = fields.Monetary(
        string='Amount Paid',
        compute='_compute_burqan_store_balances',
        currency_field='currency_id',
        help='Cash sales (treated as paid) plus posted inbound customer payments.',
    )
    x_burqan_amount_due = fields.Monetary(
        string='Amount Due',
        compute='_compute_burqan_store_balances',
        currency_field='currency_id',
        help='Credit sales still unpaid after posted inbound payments.',
    )

    _sql_constraints = [
        (
            'x_burqan_store_id_unique',
            'UNIQUE(x_burqan_store_id)',
            'A partner with this Burqan Store ID already exists.',
        ),
    ]

    @api.depends(
        'sale_order_ids.state',
        'sale_order_ids.amount_total',
        'sale_order_ids.x_burqan_payment_type',
        'sale_order_ids.x_burqan_order_id',
    )
    def _compute_burqan_store_balances(self):
        Payment = self.env['account.payment']
        for partner in self:
            orders = self.env['sale.order'].search([
                ('partner_id', '=', partner.id),
                ('state', 'in', ('sale', 'done')),
                ('x_burqan_order_id', '!=', False),
            ])
            cash = sum(
                orders.filtered(lambda o: o.x_burqan_payment_type == 'cash').mapped('amount_total')
            )
            credit = sum(
                orders.filtered(lambda o: o.x_burqan_payment_type == 'deferred').mapped('amount_total')
            )
            # Orders without payment type still count in total.
            other = sum(
                orders.filtered(
                    lambda o: o.x_burqan_payment_type not in ('cash', 'deferred')
                ).mapped('amount_total')
            )
            payments = Payment.search([
                ('partner_id', '=', partner.id),
                ('payment_type', '=', 'inbound'),
                ('state', '=', 'paid'),
            ])
            paid_payments = sum(payments.mapped('amount'))
            paid = cash + paid_payments
            due = max(credit - paid_payments, 0.0)
            partner.x_burqan_sales_cash = cash
            partner.x_burqan_sales_credit = credit
            partner.x_burqan_sales_total = cash + credit + other
            partner.x_burqan_amount_paid = paid
            partner.x_burqan_amount_due = due

    @api.model
    def _burqan_find_store_partner(self, store_id, phone=None, name=None):
        """Find existing store partner: store id, then phone, then name."""
        Partner = self.with_context(active_test=False)
        store_id = str(store_id).strip() if store_id not in (None, '') else False
        phone = (phone or '').strip() or False
        name = (name or '').strip() or False

        partner = Partner.browse()
        if store_id:
            partner = Partner.search([('x_burqan_store_id', '=', store_id)], limit=1)
        if not partner and phone:
            partner = Partner.search([
                ('phone', '=', phone),
                '|',
                ('x_burqan_store_id', '=', False),
                ('x_burqan_store_id', '=', store_id),
            ], limit=1, order='x_burqan_store_id desc, id asc')
        if not partner and name:
            partner = Partner.search([
                ('name', '=', name),
                ('is_company', '=', True),
                '|',
                ('x_burqan_store_id', '=', False),
                ('x_burqan_store_id', '=', store_id),
            ], limit=1, order='x_burqan_store_id desc, id asc')
        return partner

    def _burqan_absorb_store_duplicates(self, store_id=None, phone=None, name=None):
        """Reassign sales/invoices from duplicate contacts onto this store partner."""
        self.ensure_one()
        Partner = self.with_context(active_test=False)
        domain = [('id', '!=', self.id), ('is_company', '=', True)]
        orphans = Partner.browse()
        phone = (phone or self.phone or '').strip() or False
        name = (name or self.name or '').strip() or False
        store_id = (
            str(store_id).strip()
            if store_id not in (None, '')
            else (self.x_burqan_store_id or False)
        )

        if phone:
            orphans |= Partner.search(domain + [('phone', '=', phone)])
        if name:
            orphans |= Partner.search(domain + [
                ('name', '=', name),
                ('x_burqan_store_id', '=', False),
            ])
        if store_id:
            # Safety: another row somehow sharing same store id (should be unique).
            orphans |= Partner.search(domain + [('x_burqan_store_id', '=', store_id)])

        for orphan in orphans:
            if orphan.x_burqan_store_id and orphan.x_burqan_store_id != store_id:
                continue
            orders = self.env['sale.order'].search([('partner_id', '=', orphan.id)])
            if orders:
                orders.write({'partner_id': self.id})
            moves = self.env['account.move'].search([
                ('partner_id', '=', orphan.id),
                ('move_type', 'in', ('out_invoice', 'out_refund', 'out_receipt')),
            ])
            if moves:
                moves.write({'partner_id': self.id})
            payments = self.env['account.payment'].search([('partner_id', '=', orphan.id)])
            if payments:
                payments.write({'partner_id': self.id})
            if orphan.active:
                orphan.active = False

    @api.model
    def _burqan_process_store_webhook(self, payload):
        """Upsert or archive a company partner from Burqan store.* webhooks."""
        if not isinstance(payload, dict):
            raise BurqanWebhookError(400, 'Payload must be a JSON object.')
        event = payload.get('event')
        if event not in (
            'store.created',
            'store.updated',
            'store.upsert',
            'store.deleted',
        ):
            raise BurqanWebhookError(
                400,
                'event must be store.created, store.updated, store.upsert, or store.deleted.',
            )
        store = payload.get('store')
        if not isinstance(store, dict):
            raise BurqanWebhookError(400, 'store is required.')
        if store.get('id') in (None, ''):
            raise BurqanWebhookError(400, 'store.id is required.')

        store_id = str(store['id']).strip()
        name = (store.get('name') or '').strip()
        phone = (store.get('phone') or '').strip() or False
        partner = self._burqan_find_store_partner(store_id, phone=phone, name=name)

        if event == 'store.deleted':
            if not partner:
                return self.browse(), False, 'missing'
            if partner.active:
                partner.active = False
            return partner, False, 'archived'

        if not name and not partner:
            raise BurqanWebhookError(400, 'store.name is required.')

        active = store.get('active')
        if active is None:
            active = True
        active = bool(active)

        vals = {
            'x_burqan_store_id': store_id,
            'company_type': 'company',
            'is_company': True,
            'customer_rank': max(partner.customer_rank if partner else 0, 1),
            'active': active,
        }
        if name:
            vals['name'] = name
        if phone:
            vals['phone'] = phone
        address = (store.get('address') or '').strip()
        if address:
            vals['street'] = address

        comment_bits = []
        owner = (store.get('ownerName') or '').strip()
        if owner:
            comment_bits.append(f'Owner: {owner}')
        rep_id = store.get('representativeId')
        if rep_id not in (None, ''):
            comment_bits.append(f'Burqan representativeId: {rep_id}')
        if comment_bits:
            vals['comment'] = '\n'.join(comment_bits)

        created = False
        if partner:
            partner.write(vals)
            action = 'updated'
        else:
            if not name:
                raise BurqanWebhookError(400, 'store.name is required.')
            partner = self.create(vals)
            created = True
            action = 'created'

        partner._burqan_absorb_store_duplicates(store_id=store_id, phone=phone, name=name)
        return partner, created, action

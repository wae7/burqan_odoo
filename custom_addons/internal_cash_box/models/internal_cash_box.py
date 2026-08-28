from odoo import _, api, fields, models


class InternalCashBox(models.Model):
    _name = 'internal.cash.box'
    _description = 'Internal Cash Box'
    _order = 'date desc, id desc'

    date = fields.Date(string='Date', required=True, default=fields.Date.context_today)
    description = fields.Char(string='Description')
    sales = fields.Float(string='Sales', digits=(16, 2), default=0.0)
    expenses = fields.Float(string='Expenses', digits=(16, 2), default=0.0)
    net_amount = fields.Float(
        string='Net Amount',
        compute='_compute_net_amount',
        store=True,
        digits=(16, 2),
    )
    state = fields.Selection(
        selection=[
            ('draft', 'Draft'),
            ('posted', 'Posted'),
        ],
        string='Status',
        default='draft',
        required=True,
        readonly=True,
        index=True,
    )

    @api.depends('sales', 'expenses')
    def _compute_net_amount(self):
        for record in self:
            record.net_amount = record.sales - record.expenses

    def action_post(self):
        """Post draft entries. Selected records, or all draft entries when none selected."""
        records = self
        if not records:
            records = self.search([('state', '=', 'draft')])
        records = records.filtered(lambda r: r.state == 'draft')
        if not records:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('ترحيل'),
                    'message': _('No draft entries to post.'),
                    'type': 'warning',
                    'sticky': False,
                },
            }
        count = len(records)
        records._post_entries()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('ترحيل'),
                'message': _('%s entry(ies) posted.') % count,
                'type': 'success',
                'sticky': False,
            },
        }

    def _post_entries(self):
        """Shared posting logic for manual and automatic posting."""
        for record in self.filtered(lambda r: r.state == 'draft'):
            record.state = 'posted'

    @api.model
    def cron_auto_post_entries(self):
        """Automatically post draft entries dated before today."""
        today = fields.Date.context_today(self)
        records = self.search([
            ('state', '=', 'draft'),
            ('date', '<', today),
        ])
        records._post_entries()

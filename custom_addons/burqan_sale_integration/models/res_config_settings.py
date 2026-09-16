from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    burqan_webhook_secret = fields.Char(
        string='Burqan Webhook Secret',
        config_parameter='burqan.webhook_secret',
        help='Must match Burqan API env ODOO_WEBHOOK_SECRET. '
             'Sent as Authorization: Bearer <secret>.',
    )
    burqan_webhook_auto_invoice = fields.Boolean(
        string='Auto-post Burqan webhook invoices',
        config_parameter='burqan.webhook_auto_invoice',
        help='Webhook orders always create a draft invoice. '
             'If enabled, that invoice is also posted. Default off (draft only).',
    )

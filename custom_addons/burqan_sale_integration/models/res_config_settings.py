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
        string='Auto-create invoices from Burqan webhook',
        config_parameter='burqan.webhook_auto_invoice',
        help='If enabled, confirmed webhook orders also create and post an invoice. Default off.',
    )

from odoo import models


class AccountMove(models.Model):
    _inherit = 'account.move'

    def _get_name_invoice_report(self):
        self.ensure_one()
        if self.move_type in ('out_invoice', 'out_refund'):
            return 'burqan_invoice_report.report_invoice_document_burqan'
        return super()._get_name_invoice_report()

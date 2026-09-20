from odoo import api, models


class AccountMoveSendWizard(models.TransientModel):
    _inherit = 'account.move.send.wizard'

    @api.depends('move_id')
    def _compute_sending_method_checkboxes(self):
        super()._compute_sending_method_checkboxes()
        for wizard in self:
            checkboxes = wizard.sending_method_checkboxes
            if not checkboxes or 'email' not in checkboxes:
                continue
            email_vals = dict(checkboxes.get('email') or {})
            if not email_vals.get('checked'):
                continue
            wizard.sending_method_checkboxes = {
                **checkboxes,
                'email': {**email_vals, 'checked': False},
            }

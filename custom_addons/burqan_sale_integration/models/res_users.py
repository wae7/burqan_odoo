from odoo import api, fields, models

from .exceptions import BurqanWebhookError


class ResUsers(models.Model):
    _inherit = 'res.users'

    x_burqan_representative_id = fields.Char(
        string='Burqan Representative ID',
        index=True,
        copy=False,
        help='Burqan Store representatives.id used to match webhook salespeople.',
    )

    _sql_constraints = [
        (
            'x_burqan_representative_id_unique',
            'UNIQUE(x_burqan_representative_id)',
            'A user with this Burqan representative ID already exists.',
        ),
    ]

    @api.model
    def _burqan_find_or_create_salesperson(self, representative, create_if_missing=True):
        """Match or create an Odoo sales user from a Burqan representative payload.

        Returns (user, created_bool). user may be empty if create_if_missing is False
        and no match exists.
        """
        if not isinstance(representative, dict) or not representative:
            return self.browse(), False

        rep_id = representative.get('id')
        rep_id_str = str(rep_id).strip() if rep_id not in (None, '') else False
        email = (representative.get('email') or '').strip()
        name = (representative.get('name') or '').strip() or (email or f'Burqan Rep {rep_id_str or ""}').strip()

        user = self.browse()
        if rep_id_str:
            user = self.search([('x_burqan_representative_id', '=', rep_id_str)], limit=1)
        if not user and email:
            user = self.search(
                ['|', ('login', '=ilike', email), ('email', '=ilike', email)],
                limit=1,
            )
        if not user and name:
            user = self.search([('name', '=ilike', name)], limit=1)

        if user:
            vals = {}
            if rep_id_str and user.x_burqan_representative_id != rep_id_str:
                vals['x_burqan_representative_id'] = rep_id_str
            if name and user.name != name:
                vals['name'] = name
            if email and (user.email or '').lower() != email.lower():
                vals['email'] = email
            if vals:
                user.write(vals)
            self._burqan_ensure_sales_group(user)
            return user, False

        if not create_if_missing:
            return self.browse(), False

        if not email and not rep_id_str:
            raise BurqanWebhookError(
                400,
                'representative.id or representative.email is required to create a salesperson.',
            )

        login = email.lower() if email else f'burqan.rep.{rep_id_str}@burqan.local'
        if self.search_count([('login', '=', login)]):
            login = f'burqan.rep.{rep_id_str or "x"}@{login.split("@")[-1]}'

        salesman = self.env.ref('sales_team.group_sale_salesman', raise_if_not_found=False)
        group_cmds = [(4, salesman.id)] if salesman else []

        user = self.with_context(no_reset_password=True).create({
            'name': name,
            'login': login,
            'email': email or login,
            'x_burqan_representative_id': rep_id_str or False,
            'groups_id': group_cmds,
        })
        return user, True

    @api.model
    def _burqan_ensure_sales_group(self, user):
        salesman = self.env.ref('sales_team.group_sale_salesman', raise_if_not_found=False)
        if salesman and salesman not in user.groups_id:
            user.write({'groups_id': [(4, salesman.id)]})

    @api.model
    def _burqan_process_representative_webhook(self, payload):
        """Create/update an Odoo salesperson from representative.upsert / representative.updated."""
        if not isinstance(payload, dict):
            raise BurqanWebhookError(400, 'Payload must be a JSON object.')
        event = payload.get('event')
        if event not in ('representative.upsert', 'representative.created', 'representative.updated'):
            raise BurqanWebhookError(
                400,
                'event must be representative.upsert, representative.created, or representative.updated.',
            )
        rep = payload.get('representative')
        if not isinstance(rep, dict):
            # Allow flat payload: {event, id, name, email}
            rep = {
                'id': payload.get('id'),
                'name': payload.get('name'),
                'email': payload.get('email'),
            }
        if rep.get('id') in (None, '') and not (rep.get('email') or '').strip():
            raise BurqanWebhookError(400, 'representative.id or representative.email is required.')
        if not (rep.get('name') or '').strip() and not (rep.get('email') or '').strip():
            raise BurqanWebhookError(400, 'representative.name or representative.email is required.')

        user, created = self._burqan_find_or_create_salesperson(rep, create_if_missing=True)
        return user, created

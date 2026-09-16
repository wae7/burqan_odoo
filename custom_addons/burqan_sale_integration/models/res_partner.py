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

    _sql_constraints = [
        (
            'x_burqan_store_id_unique',
            'UNIQUE(x_burqan_store_id)',
            'A partner with this Burqan Store ID already exists.',
        ),
    ]

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
        partner = self.with_context(active_test=False).search(
            [('x_burqan_store_id', '=', store_id)],
            limit=1,
        )

        if event == 'store.deleted':
            if not partner:
                return self.browse(), False, 'missing'
            if partner.active:
                partner.active = False
            return partner, False, 'archived'

        name = (store.get('name') or '').strip()
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
        phone = (store.get('phone') or '').strip()
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

        if partner:
            partner.write(vals)
            return partner, False, 'updated'

        if not name:
            raise BurqanWebhookError(400, 'store.name is required.')
        partner = self.create(vals)
        return partner, True, 'created'

from odoo import api, models

from .exceptions import BurqanWebhookError


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    @api.model
    def _burqan_process_product_webhook(self, payload):
        """Upsert or archive a product from Burqan product.* webhooks."""
        if not isinstance(payload, dict):
            raise BurqanWebhookError(400, 'Payload must be a JSON object.')
        event = payload.get('event')
        if event not in ('product.created', 'product.updated', 'product.deleted'):
            raise BurqanWebhookError(
                400,
                'event must be product.created, product.updated, or product.deleted.',
            )
        product = payload.get('product')
        if not isinstance(product, dict):
            raise BurqanWebhookError(400, 'product is required.')
        if product.get('id') in (None, ''):
            raise BurqanWebhookError(400, 'product.id is required.')

        integration_id = str(product['id']).strip()
        template = self.with_context(active_test=False).search(
            [('x_integration_id', '=', integration_id)],
            limit=1,
        )

        if event == 'product.deleted':
            if not template:
                return self.browse(), False, 'missing'
            if template.active:
                template.active = False
            return template, False, 'archived'

        name = (product.get('name') or '').strip()
        if not name and not template:
            raise BurqanWebhookError(400, 'product.name is required.')

        active = product.get('active')
        if active is None:
            active = True
        active = bool(active)

        vals = {
            'x_integration_id': integration_id,
            'active': active,
            'sale_ok': True,
            'type': 'consu',
        }
        if name:
            vals['name'] = name
        if product.get('unitPrice') is not None:
            try:
                vals['list_price'] = float(product.get('unitPrice'))
            except (TypeError, ValueError):
                raise BurqanWebhookError(400, 'product.unitPrice must be a number.')
        sku = product.get('sku')
        if sku not in (None, ''):
            vals['default_code'] = str(sku).strip()
        barcode = product.get('barcode')
        if barcode not in (None, ''):
            vals['barcode'] = str(barcode).strip()

        if template:
            template.write(vals)
            return template, False, 'updated'

        if not name:
            raise BurqanWebhookError(400, 'product.name is required.')
        template = self.create(vals)
        return template, True, 'created'

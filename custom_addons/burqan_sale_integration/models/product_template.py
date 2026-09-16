import base64
import logging
import urllib.error
import urllib.request

from odoo import api, models

from .exceptions import BurqanWebhookError

_logger = logging.getLogger(__name__)


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

        image_b64 = self._burqan_product_image_b64(product)
        if image_b64:
            vals['image_1920'] = image_b64

        if template:
            template.write(vals)
            return template, False, 'updated'

        if not name:
            raise BurqanWebhookError(400, 'product.name is required.')
        template = self.create(vals)
        return template, True, 'created'

    @api.model
    def _burqan_product_image_b64(self, product):
        """Accept imageBase64 / image, or download imageUrl / image_url."""
        raw_b64 = product.get('imageBase64') or product.get('image')
        if isinstance(raw_b64, str) and raw_b64.strip():
            data = raw_b64.strip()
            if data.startswith('data:') and 'base64,' in data:
                data = data.split('base64,', 1)[1]
            try:
                base64.b64decode(data, validate=True)
            except Exception as err:
                raise BurqanWebhookError(400, f'product image base64 is invalid: {err}') from err
            return data

        url = product.get('imageUrl') or product.get('image_url')
        if not isinstance(url, str) or not url.strip():
            return False
        url = url.strip()
        if not url.startswith(('http://', 'https://')):
            raise BurqanWebhookError(400, 'product.imageUrl must be an absolute http(s) URL.')
        try:
            req = urllib.request.Request(
                url,
                headers={'User-Agent': 'BurqanOdooWebhook/1.0'},
            )
            with urllib.request.urlopen(req, timeout=20) as resp:
                content_type = (resp.headers.get('Content-Type') or '').lower()
                blob = resp.read(5_000_000 + 1)
            if len(blob) > 5_000_000:
                raise BurqanWebhookError(400, 'product image is larger than 5MB.')
            if content_type and not content_type.startswith('image/') and 'octet-stream' not in content_type:
                _logger.warning('Burqan product image unexpected content-type=%s url=%s', content_type, url)
            return base64.b64encode(blob)
        except BurqanWebhookError:
            raise
        except (urllib.error.URLError, TimeoutError, ValueError) as err:
            _logger.warning('Burqan product image download failed url=%s err=%s', url, err)
            # Do not fail the whole product upsert if image fetch fails.
            return False

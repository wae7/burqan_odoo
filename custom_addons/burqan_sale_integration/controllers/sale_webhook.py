import hmac
import json
import logging

from odoo import SUPERUSER_ID, http
from odoo.exceptions import UserError, ValidationError
from odoo.http import request

from odoo.addons.burqan_sale_integration.models.exceptions import BurqanWebhookError

_logger = logging.getLogger(__name__)


class BurqanSaleWebhook(http.Controller):

    @http.route(
        '/burqan/webhook/sale',
        type='http',
        auth='none',
        csrf=False,
        methods=['POST'],
        save_session=False,
    )
    def sale_webhook(self, **kwargs):
        order_id = None
        event = None
        if not self._bearer_ok():
            return request.make_json_response(
                {'ok': False, 'error': 'Unauthorized'},
                status=401,
            )

        env = request.env(user=SUPERUSER_ID)
        try:
            payload = self._read_json_body()
            if isinstance(payload, dict):
                order_id = payload.get('orderId')
                event = payload.get('event')
            with env.cr.savepoint():
                order, reused, action = env['sale.order']._burqan_process_sale_webhook(payload)
            _logger.info(
                'Burqan sale webhook event=%s action=%s reused=%s orderId=%s sale.order=%s',
                event,
                action,
                reused,
                order_id,
                order.id if order else False,
            )
            body = {
                'ok': True,
                'event': event,
                'action': action,
                'saleOrderId': order.id if order else False,
                'salespersonId': order.user_id.id if order else False,
            }
            return request.make_json_response(body, status=200)
        except BurqanWebhookError as err:
            env.cr.rollback()
            _logger.warning(
                'Burqan sale webhook rejected orderId=%s status=%s error=%s',
                order_id,
                err.status,
                err.error,
            )
            body = {'ok': False, 'error': err.error}
            body.update(err.extra)
            return request.make_json_response(body, status=err.status)
        except (UserError, ValidationError) as err:
            env.cr.rollback()
            _logger.warning(
                'Burqan sale webhook validation failed orderId=%s error=%s',
                order_id,
                err,
            )
            return request.make_json_response(
                {'ok': False, 'error': str(err)},
                status=400,
            )
        except Exception:
            env.cr.rollback()
            _logger.exception('Burqan sale webhook failed orderId=%s', order_id)
            return request.make_json_response(
                {'ok': False, 'error': 'Internal server error'},
                status=500,
            )

    @http.route(
        '/burqan/webhook/product',
        type='http',
        auth='none',
        csrf=False,
        methods=['POST'],
        save_session=False,
    )
    def product_webhook(self, **kwargs):
        product_id = None
        event = None
        if not self._bearer_ok():
            return request.make_json_response(
                {'ok': False, 'error': 'Unauthorized'},
                status=401,
            )

        env = request.env(user=SUPERUSER_ID)
        try:
            payload = self._read_json_body()
            if isinstance(payload, dict):
                event = payload.get('event')
                product = payload.get('product') if isinstance(payload.get('product'), dict) else {}
                product_id = product.get('id')
            with env.cr.savepoint():
                template, created, action = env['product.template']._burqan_process_product_webhook(
                    payload
                )
            _logger.info(
                'Burqan product webhook event=%s action=%s burqanId=%s product.template=%s',
                event,
                action,
                product_id,
                template.id if template else False,
            )
            return request.make_json_response(
                {
                    'ok': True,
                    'event': event,
                    'action': action,
                    'productTemplateId': template.id if template else False,
                    'created': created,
                    'integrationId': template.x_integration_id if template else False,
                    'active': template.active if template else False,
                },
                status=201 if created else 200,
            )
        except BurqanWebhookError as err:
            env.cr.rollback()
            body = {'ok': False, 'error': err.error}
            body.update(err.extra)
            return request.make_json_response(body, status=err.status)
        except (UserError, ValidationError) as err:
            env.cr.rollback()
            return request.make_json_response({'ok': False, 'error': str(err)}, status=400)
        except Exception:
            env.cr.rollback()
            _logger.exception('Burqan product webhook failed burqanId=%s', product_id)
            return request.make_json_response(
                {'ok': False, 'error': 'Internal server error'},
                status=500,
            )

    @http.route(
        '/burqan/webhook/store',
        type='http',
        auth='none',
        csrf=False,
        methods=['POST'],
        save_session=False,
    )
    def store_webhook(self, **kwargs):
        store_id = None
        event = None
        if not self._bearer_ok():
            return request.make_json_response(
                {'ok': False, 'error': 'Unauthorized'},
                status=401,
            )

        env = request.env(user=SUPERUSER_ID)
        try:
            payload = self._read_json_body()
            if isinstance(payload, dict):
                event = payload.get('event')
                store = payload.get('store') if isinstance(payload.get('store'), dict) else {}
                store_id = store.get('id')
            with env.cr.savepoint():
                partner, created, action = env['res.partner']._burqan_process_store_webhook(payload)
            _logger.info(
                'Burqan store webhook event=%s action=%s burqanId=%s res.partner=%s',
                event,
                action,
                store_id,
                partner.id if partner else False,
            )
            return request.make_json_response(
                {
                    'ok': True,
                    'event': event,
                    'action': action,
                    'partnerId': partner.id if partner else False,
                    'created': created,
                    'burqanStoreId': partner.x_burqan_store_id if partner else False,
                    'active': partner.active if partner else False,
                },
                status=201 if created else 200,
            )
        except BurqanWebhookError as err:
            env.cr.rollback()
            body = {'ok': False, 'error': err.error}
            body.update(err.extra)
            return request.make_json_response(body, status=err.status)
        except (UserError, ValidationError) as err:
            env.cr.rollback()
            return request.make_json_response({'ok': False, 'error': str(err)}, status=400)
        except Exception:
            env.cr.rollback()
            _logger.exception('Burqan store webhook failed burqanId=%s', store_id)
            return request.make_json_response(
                {'ok': False, 'error': 'Internal server error'},
                status=500,
            )

    @http.route(
        '/burqan/webhook/representative',
        type='http',
        auth='none',
        csrf=False,
        methods=['POST'],
        save_session=False,
    )
    def representative_upsert(self, **kwargs):
        rep_id = None
        event = None
        if not self._bearer_ok():
            return request.make_json_response(
                {'ok': False, 'error': 'Unauthorized'},
                status=401,
            )

        env = request.env(user=SUPERUSER_ID)
        try:
            payload = self._read_json_body()
            if isinstance(payload, dict):
                event = payload.get('event')
                rep = (
                    payload.get('representative')
                    if isinstance(payload.get('representative'), dict)
                    else payload
                )
                rep_id = (rep or {}).get('id')
            with env.cr.savepoint():
                user, created, action = env['res.users']._burqan_process_representative_webhook(
                    payload
                )
            _logger.info(
                'Burqan representative webhook event=%s action=%s burqanId=%s res.users=%s',
                event,
                action,
                rep_id,
                user.id if user else False,
            )
            return request.make_json_response(
                {
                    'ok': True,
                    'event': event,
                    'action': action,
                    'userId': user.id if user else False,
                    'created': created,
                    'login': user.login if user else False,
                    'active': user.active if user else False,
                },
                status=200,
            )
        except BurqanWebhookError as err:
            env.cr.rollback()
            _logger.warning(
                'Burqan representative webhook rejected burqanId=%s status=%s error=%s',
                rep_id,
                err.status,
                err.error,
            )
            body = {'ok': False, 'error': err.error}
            body.update(err.extra)
            return request.make_json_response(body, status=err.status)
        except (UserError, ValidationError) as err:
            env.cr.rollback()
            _logger.warning(
                'Burqan representative webhook validation failed burqanId=%s error=%s',
                rep_id,
                err,
            )
            return request.make_json_response(
                {'ok': False, 'error': str(err)},
                status=400,
            )
        except Exception:
            env.cr.rollback()
            _logger.exception('Burqan representative webhook failed burqanId=%s', rep_id)
            return request.make_json_response(
                {'ok': False, 'error': 'Internal server error'},
                status=500,
            )

    def _bearer_ok(self):
        secret = request.env['ir.config_parameter'].sudo().get_param(
            'burqan.webhook_secret'
        ) or ''
        header = request.httprequest.headers.get('Authorization') or ''
        if not secret or not header.startswith('Bearer '):
            return False
        token = header[7:]
        try:
            return hmac.compare_digest(token, secret)
        except (TypeError, ValueError):
            return False

    def _read_json_body(self):
        raw = request.httprequest.get_data(as_text=True) or ''
        if not raw.strip():
            raise BurqanWebhookError(400, 'Empty request body.')
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            raise BurqanWebhookError(400, 'Body must be valid JSON.')

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
    def sale_completed(self, **kwargs):
        order_id = None
        if not self._bearer_ok():
            return request.make_json_response(
                {'ok': False, 'error': 'Unauthorized'},
                status=401,
            )

        env = request.env(user=SUPERUSER_ID)
        try:
            payload = self._read_json_body()
            order_id = payload.get('orderId') if isinstance(payload, dict) else None
            with env.cr.savepoint():
                order, reused = env['sale.order']._burqan_process_sale_webhook(payload)
            _logger.info(
                'Burqan webhook %s orderId=%s sale.order=%s user_id=%s',
                'reused' if reused else 'created',
                order_id,
                order.id,
                order.user_id.id,
            )
            return request.make_json_response(
                {
                    'ok': True,
                    'saleOrderId': order.id,
                    'salespersonId': order.user_id.id or False,
                },
                status=200,
            )
        except BurqanWebhookError as err:
            env.cr.rollback()
            _logger.warning(
                'Burqan webhook rejected orderId=%s status=%s error=%s',
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
                'Burqan webhook validation failed orderId=%s error=%s',
                order_id,
                err,
            )
            return request.make_json_response(
                {'ok': False, 'error': str(err)},
                status=400,
            )
        except Exception:
            env.cr.rollback()
            _logger.exception('Burqan webhook failed orderId=%s', order_id)
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
        if not self._bearer_ok():
            return request.make_json_response(
                {'ok': False, 'error': 'Unauthorized'},
                status=401,
            )

        env = request.env(user=SUPERUSER_ID)
        try:
            payload = self._read_json_body()
            if isinstance(payload, dict):
                rep = payload.get('representative') if isinstance(payload.get('representative'), dict) else payload
                rep_id = (rep or {}).get('id')
            with env.cr.savepoint():
                user, created = env['res.users']._burqan_process_representative_webhook(payload)
            _logger.info(
                'Burqan representative webhook %s burqanId=%s res.users=%s',
                'created' if created else 'updated',
                rep_id,
                user.id,
            )
            return request.make_json_response(
                {
                    'ok': True,
                    'userId': user.id,
                    'created': created,
                    'login': user.login,
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

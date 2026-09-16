# Burqan Sale Integration

Syncs Burqan Store into Odoo 18: products, stores, representatives, and sales.

## Endpoints

| Method | URL |
| --- | --- |
| POST | `https://erp.burqan.tech/burqan/webhook/sale` |
| POST | `https://erp.burqan.tech/burqan/webhook/product` |
| POST | `https://erp.burqan.tech/burqan/webhook/store` |
| POST | `https://erp.burqan.tech/burqan/webhook/representative` |

| Header | Value |
| --- | --- |
| `Content-Type` | `application/json` |
| `Authorization` | `Bearer <secret>` |

Body is raw JSON (not JSON-RPC). Shared secret = Odoo `burqan.webhook_secret` = Burqan `ODOO_WEBHOOK_SECRET`.

## Sales (`/burqan/webhook/sale`)

Events: `sale.completed`, `sale.updated`, `sale.cancelled`

- `orderId` is the idempotency key (`sale.order.x_burqan_order_id`)
- Confirmed sales create a **draft** invoice
- `paymentType`:
  - `cash` → preferred payment method **Manual Payment (Cash)**
  - `deferred` → preferred payment method **Manual Payment (Credit)**
- Missing `source` → `store`
- External with `store.id` links partner via `x_burqan_store_id`
- Cancel cancels SO + draft invoices; posted invoices return **409**

## Products (`/burqan/webhook/product`)

Events: `product.created`, `product.updated`, `product.deleted`  
Key: `product.id` → `product.template.x_integration_id` (archive on delete / `active: false`)

## Stores (`/burqan/webhook/store`)

Events: `store.created`, `store.updated`, `store.upsert`, `store.deleted`  
Key: `store.id` → `res.partner.x_burqan_store_id` (archive on delete)

## Representatives (`/burqan/webhook/representative`)

Events: `representative.upsert`, `created`, `updated`, `deleted`  
Key: `representative.id` → `res.users.x_burqan_representative_id` (deactivate on delete)

## Optional setting

**Auto-post Burqan webhook invoices** — if enabled, draft invoices are also posted (default off).

# Burqan Sale Integration

Creates and confirms Odoo 18 sale orders from Burqan Store webhooks, and syncs representatives as Odoo salespeople.

## Endpoints

| Method | URL |
| --- | --- |
| POST | `https://erp.burqan.tech/burqan/webhook/sale` |
| POST | `https://erp.burqan.tech/burqan/webhook/representative` |

| Header | Value |
| --- | --- |
| `Content-Type` | `application/json` |
| `Authorization` | `Bearer <secret>` |

Body is a raw JSON object (not JSON-RPC). Shared secret = Odoo `burqan.webhook_secret` = Burqan `ODOO_WEBHOOK_SECRET`.

## Set the shared secret

1. **Settings → Sales** → Burqan Store webhook, or
2. Developer mode → **Settings → Technical → System Parameters** → `burqan.webhook_secret`

## Product mapping

Each Burqan `lines[].productId` must match `product.template` **ID** (`x_integration_id`) as a string.

## Representative / salesperson sync

On every sale, Odoo finds or **creates** an Odoo user from `representative` and sets `sale.order.user_id`.

Matching order:
1. `res.users.x_burqan_representative_id` = `representative.id`
2. login/email = `representative.email`
3. name = `representative.name`
4. else create a Sales user

Optional dedicated sync when a rep is created/updated in Burqan:

```bash
curl -sS -X POST 'https://erp.burqan.tech/burqan/webhook/representative' \
  -H 'Content-Type: application/json' \
  -H 'Authorization: Bearer CHANGE_ME' \
  -d '{
    "event": "representative.upsert",
    "representative": {
      "id": 8,
      "name": "Ahmad Gonar",
      "email": "ahmad-gonar@gmail.com"
    }
  }'
```

Success: `{"ok": true, "userId": 5, "created": true, "login": "ahmad-gonar@gmail.com"}`

## Sale example

```bash
curl -sS -X POST 'https://erp.burqan.tech/burqan/webhook/sale' \
  -H 'Content-Type: application/json' \
  -H 'Authorization: Bearer CHANGE_ME' \
  -d '{
    "event": "sale.completed",
    "orderId": "1842",
    "occurredAt": "2026-08-28T14:22:11.000Z",
    "occurredAtAmman": "2026-08-28 17:22:11",
    "paymentType": "cash",
    "store": { "id": 45, "name": "سوبر ماركت النور", "phone": "0791234567" },
    "representative": { "id": 3, "name": "محمد سعيد", "email": "rep@burqan.store" },
    "lines": [
      {
        "productId": 12,
        "productName": "ماء 330مل",
        "quantity": 4,
        "unitPrice": 0.25,
        "lineTotal": 1.0
      }
    ],
    "totalAmount": 1.0
  }'
```

Success: `{"ok": true, "saleOrderId": 15, "salespersonId": 5}`

## External sales (`source: "external"`)

Admin-recorded sales without a Burqan store id:

- `source`: `"store"` (default if missing) or `"external"`
- For `external`: `store.id` may be null; `store.name` is required; partner is matched/created by name and **no** `x_burqan_store_id` is set
- For `store`: current behaviour (require `store.id` + name, match `x_burqan_store_id`)

```bash
curl -sS -X POST 'https://erp.burqan.tech/burqan/webhook/sale' \
  -H 'Content-Type: application/json' \
  -H 'Authorization: Bearer CHANGE_ME' \
  -d '{
    "event": "sale.completed",
    "source": "external",
    "orderId": "ext-42",
    "occurredAt": "2026-09-04T21:00:00.000Z",
    "occurredAtAmman": "2026-09-05 00:00:00",
    "paymentType": "cash",
    "store": { "id": null, "name": "سوق الحي", "phone": null },
    "representative": { "id": 3, "name": "محمد", "email": "rep@burqan.store" },
    "lines": [{ "productId": 31, "productName": "Choco Beurre Lots", "quantity": 2, "unitPrice": 1.9, "lineTotal": 3.8 }],
    "totalAmount": 3.8
  }'
```

## Behaviour

- Customer: partner with `x_burqan_store_id` = `store.id`, else phone, else create company partner (store sales); external sales use name only.
- Line prices come from Burqan `unitPrice`.
- Salesperson is auto-created if missing (Sales / Own Documents group).
- Orders are confirmed. Invoices optional via **Auto-invoice Burqan webhook orders** (default off).

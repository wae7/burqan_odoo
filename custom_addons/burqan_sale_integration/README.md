# Burqan Sale Integration

Creates and confirms Odoo 18 sale orders from Burqan Store `sale.completed` webhooks.

## Endpoint

`POST https://erp.burqan.tech/burqan/webhook/sale`

| Header | Value |
| --- | --- |
| `Content-Type` | `application/json` |
| `Authorization` | `Bearer <secret>` |

The body is a raw JSON object (not JSON-RPC).

## Set the shared secret

Use the **same** value as Burqan API env `ODOO_WEBHOOK_SECRET`.

1. **Settings → Sales** → Burqan Store webhook, or
2. Enable developer mode → **Settings → Technical → System Parameters** → create/edit `burqan.webhook_secret`

If the parameter is empty, every request returns `401`.

## Product mapping

Each Burqan `lines[].productId` must match `product.template` field **ID** (`x_integration_id`) as a string, e.g. Burqan product `12` → product ID `12`.

If any line has no match, the webhook returns `422` with `missingProductIds` and creates **no** sale order.

## Example curl

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

Success: `{"ok": true, "saleOrderId": 15}`  
Repeat of the same `orderId`: `200` with the existing sale order id (no duplicate).

## Behaviour

- Customer: partner with `x_burqan_store_id` = `store.id`, else phone, else a new company partner.
- Line prices come from Burqan `unitPrice`, not the Odoo list price.
- Salesperson is set only when a `res.users` matches representative email/login/name; otherwise the representative is written on the SO note.
- Orders are confirmed. Invoices/payments are not created unless **Auto-invoice Burqan webhook orders** is enabled (default off).

# Batch Claims API

This is the **B2** execution-plan slice: bulk claim intake over the existing async queue.

## Endpoint

`POST /v1/claims/batch`

- tenant-auth only (`X-API-Key`)
- multipart form upload
- fans each item into the same queue path used by `POST /v1/claims/async`

## Request shape

- repeated `images` file fields
- one `items_json` form field containing a JSON array with the same length as `images`

Example `items_json`:

```json
[
  {
    "order_id": "ORD-B1",
    "product_sku": "SKU-1",
    "claim_reason": "scratched",
    "listing_image_urls": ["https://example.com/listing-1.jpg"],
    "webhook_url": "https://example.com/webhook-1"
  },
  {
    "order_id": "ORD-B2",
    "product_sku": "SKU-2",
    "claim_reason": "broken",
    "listing_image_urls": [],
    "webhook_url": ""
  }
]
```

## Response

Returns:

- `count`
- `claims`: array of `ClaimQueueStatus`

Each queued claim is then polled through the existing `GET /v1/claims/{claim_id}/status`
endpoint.

## Notes

- Per-tenant rate limits still apply at the request level through the existing auth layer.
- Validation remains per image: unsupported content type, oversize images, or malformed
  `items_json` fail the request.

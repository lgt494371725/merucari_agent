# Mercari Search API Fields

Last checked: 2026-07-04

This note documents the fields observed from Mercari JP's search API endpoint used by `MercariApiClient`:

```text
POST https://api.mercari.jp/v2/entities:search
```

The sample request used keyword `Nintendo Switch` with `pageSize = 30`. Mercari can return fewer than the requested number of items, so callers should not assume the response always contains exactly `pageSize` items.

The web UI search currently sends one direct search request without a `status` filter. This is faster than making separate status-specific requests, but in observed tests it mostly returned `ITEM_STATUS_ON_SALE` and occasionally `ITEM_STATUS_TRADING`, not `ITEM_STATUS_SOLD_OUT`.

## Current App Mapping

`mercari_api_client.py` currently converts each search result item into this smaller shape for the web UI:

| UI field | Source field | Notes |
| --- | --- | --- |
| `id` | `id` | Mercari item id, for example `m88472655145`. |
| `title` | `name` | Cleaned with `_clean`. The observed raw `title` field was empty. |
| `price` | `price` | Converted from string to `int` with `_to_int`. |
| `thumbnail` | `thumbnails` or `photos` | `_first_thumbnail` prefers `thumbnails[0]`, then falls back to `photos[0].url/src/uri`. |
| `status` | `status` | Used by the UI to mark sold-out items. |

Search results do not include full item description or readable category path. Those still require the detail endpoint.

## Observed Raw Item Fields

| Field | Observed type | Example / observed values | Notes |
| --- | --- | --- | --- |
| `attributes` | list | `[]` | Empty in the observed sample. |
| `auction` | null | `null` | Empty in the observed sample. |
| `buyerId` | string | `""` | Empty for on-sale search results. |
| `categoryId` | string | `"702"`, `"701"` | Category id only, not a readable category path. |
| `created` | string | `"1783148442"` | Timestamp-like numeric string. |
| `id` | string | `"m88472655145"` | Item id. |
| `isLiked` | boolean | `false` | Always `false` in the anonymous observed sample. |
| `isNoPrice` | boolean | `false` | Indicates items without a normal price. |
| `itemBrand` | object or null | `null`, object | Some results include a brand object. |
| `itemConditionId` | string | `"1"`, `"2"`, `"3"`, `"4"` | Condition id only, not readable condition text. |
| `itemPromotions` | list | `[]` | Empty in the observed sample. |
| `itemSize` | null | `null` | Empty in the observed sample. |
| `itemSizes` | list | `[]` | Empty in the observed sample. |
| `itemType` | string | `"ITEM_TYPE_MERCARI"` | Dataset/type marker. |
| `name` | string | `"スーパーマリオ 3Dコレクション Nintendo Switch"` | Primary display title used by the app. |
| `photos` | list | list length 1 | Contains detail photo objects, observed with `uri`. |
| `price` | string | `"6888"`, `"2000"`, `"4280"` | Returned as a string in the observed sample. |
| `sellerId` | string | `"952876992"` | Seller id. |
| `shippingMethodId` | string | `"14"`, `"17"`, `"1"` | Shipping method id only, not readable shipping method text. |
| `shippingPayerId` | string | `"2"`, `"1"` | Shipping payer id only. |
| `shop` | null | `null` | Empty in the observed sample. |
| `shopName` | string | `""` | Empty in the observed sample. |
| `status` | string | `"ITEM_STATUS_ON_SALE"`, `"ITEM_STATUS_TRADING"`, `"ITEM_STATUS_SOLD_OUT"` | Used to distinguish available, trading, and sold-out search results when returned. Direct unfiltered search did not return sold-out items in the observed sample. |
| `thumbnails` | list | list length 1 | Contains thumbnail URLs. |
| `title` | string | `""` | Empty in the observed sample; use `name` instead. |
| `updated` | string | `"1783148554"` | Timestamp-like numeric string. |

## Observed Top-Level Response Fields

The search response also contained these top-level keys:

```text
components
items
meta
searchCondition
searchConditionId
```

The app currently reads only `items`.

## Practical Notes

- Requesting `pageSize = 30` can return fewer than 30 items.
- To reliably include sold-out items, request `STATUS_SOLD_OUT` separately. Passing `STATUS_ON_SALE` and `STATUS_SOLD_OUT` together may still return only on-sale results first. The current app does not do the extra sold-out request because it noticeably slows search.
- Search result fields include useful ids such as `categoryId`, `itemConditionId`, `shippingMethodId`, and `shippingPayerId`, but the search API response does not directly provide the readable labels this app needs for autofill.
- For listing drafts, `description`, readable category names, and richer item information should continue to come from item detail fetching.

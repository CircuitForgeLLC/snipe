# Community Blocklist

The blocklist is a shared database of sellers flagged by Snipe users. When a blocklisted seller appears in search results, their listing card is marked with an `established_bad_actor` flag.

## Viewing the blocklist

Navigate to **Blocklist** in the sidebar to see all reported sellers, with usernames, platforms, and optional reasons.

## Reporting a seller

On any listing card, click the **Block** button (shield icon) to report the seller. You can optionally add a reason (e.g. "sent counterfeit item", "never shipped").

!!! note
    In cloud mode, blocking requires a signed-in account. Anonymous users can view the blocklist but cannot report sellers.

## Importing a blocklist

The Blocklist view has an **Import CSV** button. The accepted format:

```csv
platform,platform_seller_id,username,reason
ebay,seller123,seller123,counterfeit item
ebay,badactor99,badactor99,
```

The `reason` column is optional. `platform` defaults to `ebay` if omitted.

## Exporting the blocklist

Click **Export CSV** in the Blocklist view to download the current blocklist. Use this to back up, share with others, or import into another Snipe instance.

## Blocklist sync (roadmap)

Batch reporting to eBay's Trust & Safety team is on the roadmap (issue #4). This would allow community-flagged sellers to be reported directly to eBay from within Snipe.

# eBay API Keys (Optional)

Snipe works without any credentials using its Playwright scraper fallback. Adding eBay API credentials unlocks faster searches and higher rate limits.

## What API keys enable

| Feature | Without keys | With keys |
|---------|-------------|-----------|
| Listing search | Playwright scraper | eBay Browse API (faster, higher limits) |
| Market comps (completed sales) | Not available | eBay Marketplace Insights API |
| Seller account data | BTF scraper (Xvfb) | BTF scraper (same — eBay API doesn't expose join date) |

## Getting credentials

1. Create a developer account at [developer.ebay.com](https://developer.ebay.com/my/keys)
2. Create a new application (choose **Production**)
3. Copy your **App ID (Client ID)** and **Cert ID (Client Secret)**

## Configuration

Add your credentials to `.env`:

```bash
EBAY_APP_ID=YourAppID-...
EBAY_CERT_ID=YourCertID-...
```

Then restart:

```bash
./manage.sh restart
```

## Verifying

After restart, the search bar shows **API** as available in the data source selector. The auto mode will use the API by default.

!!! note
    The Marketplace Insights API (for completed sales comps) requires an approved eBay developer account. New accounts may not have access. Snipe gracefully falls back to Browse API results when Insights returns 403 or 404.

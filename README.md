# Snipe — Auction Sniping & Bid Management

> *Part of the Circuit Forge LLC "AI for the tasks you hate most" suite.*

**Status:** Backlog — not yet started. Peregrine must prove the model first.

## What it does

Snipe manages online auction participation: monitoring listings across platforms, scheduling last-second bids, tracking price history to avoid overpaying, and managing the post-win logistics (payment, shipping coordination, provenance documentation for antiques).

The name is the origin of the word "sniping" — common snipes are notoriously elusive birds, secretive and camouflaged, that flush suddenly from cover. Shooting one required extreme patience, stillness, and a precise last-second shot. That's the auction strategy.

## Primary platforms

- **CT Bids** — Connecticut state surplus and municipal auctions
- **GovPlanet / IronPlanet** — government surplus equipment
- **AuctionZip** — antique auction house aggregator (1,000+ houses)
- **Invaluable / LiveAuctioneers** — fine art and antiques
- **Bidsquare** — antiques and collectibles
- **eBay** — general + collectibles
- **HiBid** — estate auctions
- **Proxibid** — industrial and collector auctions

## Why it's hard

Online auctions are frustrating because:
- Winning requires being present at the exact closing moment — sometimes 2 AM
- Platforms vary wildly: some allow proxy bids, some don't; closing times extend on activity
- Price history is hidden — you don't know if an item is underpriced or a trap
- Shipping logistics for large / fragile antiques require coordination with auction house
- Provenance documentation is inconsistent across auction houses

## Core pipeline

```
Configure search (categories, keywords, platforms, max price, location)
→ Monitor listings → Alert on matching items
→ Human review: approve or skip
→ Price research: comparable sales history, condition assessment via photos
→ Schedule snipe bid (configurable: X seconds before close, Y% above current)
→ Execute bid → Monitor for counter-bid (soft-close extension handling)
→ Win notification → Payment + shipping coordination workflow
→ Provenance documentation for antiques
```

## Bidding strategy engine

- **Hard snipe**: submit bid N seconds before close (default: 8s)
- **Soft-close handling**: detect if platform extends on last-minute bids; adjust strategy
- **Proxy ladder**: set max and let the engine bid in increments, reserve snipe for final window
- **Reserve detection**: identify likely reserve price from bid history patterns
- **Comparable sales**: pull recent auction results for same/similar items across platforms

## Post-win workflow

1. Payment method routing (platform-specific: CC, wire, check)
2. Shipping quote requests to approved carriers (for freight / large items)
3. Condition report request from auction house
4. Provenance packet generation (for antiques / fine art resale or insurance)
5. Add to inventory (for dealers / collectors tracking portfolio value)

## Product code (license key)

`CFG-SNPE-XXXX-XXXX-XXXX`

## Tech notes

- Shared `circuitforge-core` scaffold
- Platform adapters: AuctionZip, Invaluable, HiBid, eBay, CT Bids (Playwright + API where available)
- Bid execution: Playwright automation with precise timing (NTP-synchronized)
- Soft-close detection: platform-specific rules engine
- Comparable sales: scrape completed auctions, normalize by condition/provenance
- Vision module: condition assessment from listing photos (moondream2 / Claude vision)
- Shipping quote integration: uShip API for freight, FedEx / UPS for parcel

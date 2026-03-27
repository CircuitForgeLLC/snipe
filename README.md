# Snipe — Auction Sniping & Listing Intelligence

> *Part of the Circuit Forge LLC "AI for the tasks you hate most" suite.*

**Status:** Active — eBay listing search + seller trust scoring MVP complete. Auction sniping engine and multi-platform support are next.

## What it does

Snipe has two layers that work together:

**Layer 1 — Listing intelligence (MVP, implemented)**
Before you bid, Snipe tells you whether a listing is worth your time. It fetches eBay listings, scores each seller's trustworthiness across five signals, flags suspicious pricing relative to completed sales, and surfaces red flags like new accounts, cosmetic damage buried in titles, and listings that have been sitting unsold for weeks.

**Layer 2 — Auction sniping (roadmap)**
Snipe manages the bid itself: monitors listings across platforms, schedules last-second bids, handles soft-close extensions, and guides you through the post-win logistics (payment routing, shipping coordination, provenance documentation for antiques).

The name is the origin of the word "sniping" — common snipes are notoriously elusive birds, secretive and camouflaged, that flush suddenly from cover. Shooting one required extreme patience, stillness, and a precise last-second shot. That's the auction strategy.

---

## Implemented: eBay Listing Intelligence

### Search & filtering
- Full-text eBay search via Browse API (with Playwright scraper fallback when no API credentials configured)
- Price range, must-include keywords (AND / ANY / OR-groups mode), must-exclude terms, eBay category filter
- OR-group mode expands keyword combinations into multiple targeted queries and deduplicates results — eBay relevance won't silently drop variants
- Pages-to-fetch control: each Browse API page returns up to 200 listings
- Saved searches with one-click re-run that restores all filter settings

### Seller trust scoring
Five signals, each scored 0–20, composited to 0–100:

| Signal | What it measures |
|--------|-----------------|
| `account_age` | Days since eBay account registration |
| `feedback_count` | Total feedback received |
| `feedback_ratio` | Positive feedback percentage |
| `price_vs_market` | Listing price vs. median of recent completed sales |
| `category_history` | Whether seller has history selling in this category |

Scores are marked **partial** when signals are unavailable (e.g. account age not yet enriched). Partial scores are displayed with a visual indicator rather than penalizing the seller for missing data.

### Red flags
Hard filters that override the composite score:
- `new_account` — account registered within 7 days
- `established_bad_actor` — feedback ratio < 80% with 20+ reviews

Soft flags surfaced as warnings:
- `account_under_30_days` — account under 30 days old
- `low_feedback_count` — fewer than 10 reviews
- `suspicious_price` — listing price below 50% of market median *(suppressed automatically when the search returns a heterogeneous price distribution — e.g. mixed laptop generations — to prevent false positives)*
- `duplicate_photo` — same image found on another listing (perceptual hash)
- `scratch_dent_mentioned` — title keywords indicating cosmetic damage, functional problems, or evasive language (see below)
- `long_on_market` — listing has been seen 5+ times over 14+ days without selling
- `significant_price_drop` — current price more than 20% below first-seen price

### Scratch & dent title detection
Scans listing titles for signals the item may have undisclosed damage or problems:
- **Explicit damage**: scratch, scuff, dent, crack, chip, blemish, worn
- **Condition catch-alls**: as is, for parts, parts only, spares or repair
- **Evasive redirects**: "see description", "read description", "see photos for" (seller hiding damage detail in listing body)
- **Functional problems**: "not working", "stopped working", "no power", "dead on arrival", "powers on but", "faulty", "broken screen/hinge/port"
- **DIY/repair listings**: "needs repair", "needs tlc", "project laptop", "for repair", "sold as is"

### Seller enrichment
- **Inline (API adapter)**: account age filled from Browse API `registrationDate` field
- **Background (scraper)**: `/itm/` listing pages scraped for seller "Joined" date via Playwright + Xvfb (Kasada-safe headed Chromium)
- **On-demand**: ↻ button on any listing card triggers `POST /api/enrich` — runs enrichment and re-scores without waiting for a second search
- **Category history**: derived from the seller's accumulated listing data (Browse API `categories` field); improves with every search, no extra API calls

### Market price comparison
Completed sales fetched via eBay Marketplace Insights API (with Browse API fallback for app tiers that don't have Insights access). Median stored per query hash, used to score `price_vs_market` across all listings in a search.

### Adapters
| Adapter | When used | Signals available |
|---------|-----------|-------------------|
| Browse API (`api`) | eBay API credentials configured | All signals; account age inline |
| Playwright scraper (`scraper`) | No credentials / forced | All signals except account age (async BTF enrichment) |
| `auto` (default) | — | API if credentials present, scraper otherwise |

---

## Stack

| Layer | Tech | Port |
|-------|------|------|
| Frontend | Vue 3 + Pinia + UnoCSS + Vite (nginx) | 8509 |
| API | FastAPI (uvicorn) | 8510 |
| Scraper | Playwright + playwright-stealth + Xvfb | — |
| DB | SQLite (`data/snipe.db`) | — |
| Core | circuitforge-core (editable install) | — |

## Running

```bash
./manage.sh start         # start all services
./manage.sh stop          # stop
./manage.sh logs          # tail logs
./manage.sh open          # open in browser
```

Cloud stack (shared DB, multi-user):
```bash
docker compose -f compose.cloud.yml -p snipe-cloud up -d
docker compose -f compose.cloud.yml -p snipe-cloud build api  # after Python changes
```

---

## Roadmap

### Near-term (eBay)

| Issue | Feature |
|-------|---------|
| [#1](https://git.opensourcesolarpunk.com/Circuit-Forge/snipe/issues/1) | SSE/WebSocket live score push — enriched data appears without re-search |
| [#2](https://git.opensourcesolarpunk.com/Circuit-Forge/snipe/issues/2) | eBay OAuth (Connect eBay Account) for full trust score access via Trading API |
| [#4](https://git.opensourcesolarpunk.com/Circuit-Forge/snipe/issues/4) | Scammer database: community blocklist + batch eBay Trust & Safety reporting |
| [#5](https://git.opensourcesolarpunk.com/Circuit-Forge/snipe/issues/5) | UPC/product lookup → LLM-crafted search terms (paid tier) |
| [#8](https://git.opensourcesolarpunk.com/Circuit-Forge/snipe/issues/8) | "Triple Red" easter egg: CSS animation when all hard flags fire simultaneously |
| [#11](https://git.opensourcesolarpunk.com/Circuit-Forge/snipe/issues/11) | Vision-based photo condition assessment — moondream2 (local) / Claude vision (cloud, paid) |
| [#12](https://git.opensourcesolarpunk.com/Circuit-Forge/snipe/issues/12) | Background saved-search monitoring with configurable alerts |

### Cloud / infrastructure

| Issue | Feature |
|-------|---------|
| [#6](https://git.opensourcesolarpunk.com/Circuit-Forge/snipe/issues/6) | Shared seller/scammer/comps DB across cloud users (public data, no re-scraping) |
| [#7](https://git.opensourcesolarpunk.com/Circuit-Forge/snipe/issues/7) | Shared image hash DB — requires explicit opt-in consent (CF privacy-by-architecture) |

### Auction sniping engine

| Issue | Feature |
|-------|---------|
| [#9](https://git.opensourcesolarpunk.com/Circuit-Forge/snipe/issues/9) | Bid scheduling + snipe execution (NTP-synchronized, soft-close handling, human approval gate) |
| [#13](https://git.opensourcesolarpunk.com/Circuit-Forge/snipe/issues/13) | Post-win workflow: payment routing, shipping coordination, provenance documentation |

### Multi-platform expansion

| Issue | Feature |
|-------|---------|
| [#10](https://git.opensourcesolarpunk.com/Circuit-Forge/snipe/issues/10) | CT Bids, HiBid, AuctionZip, Invaluable, GovPlanet, Bidsquare, Proxibid |

---

## Primary platforms (full vision)

- **eBay** — general + collectibles *(search + trust scoring: implemented)*
- **CT Bids** — Connecticut state surplus and municipal auctions
- **GovPlanet / IronPlanet** — government surplus equipment
- **AuctionZip** — antique auction house aggregator (1,000+ houses)
- **Invaluable / LiveAuctioneers** — fine art and antiques
- **Bidsquare** — antiques and collectibles
- **HiBid** — estate auctions
- **Proxibid** — industrial and collector auctions

## Why auctions are hard

Online auctions are frustrating because:
- Winning requires being present at the exact closing moment — sometimes 2 AM
- Platforms vary wildly: some allow proxy bids, some don't; closing times extend on activity
- Price history is hidden — you don't know if an item is underpriced or a trap
- Sellers hide damage in descriptions rather than titles to avoid automated filters
- Shipping logistics for large / fragile antiques require coordination with the auction house
- Provenance documentation is inconsistent across auction houses

## Bidding strategy engine (planned)

- **Hard snipe**: submit bid N seconds before close (default: 8s)
- **Soft-close handling**: detect if platform extends on last-minute bids; adjust strategy
- **Proxy ladder**: set max and let the engine bid in increments, reserve snipe for final window
- **Reserve detection**: identify likely reserve price from bid history patterns
- **Comparable sales**: pull recent auction results for same/similar items across platforms

## Post-win workflow (planned)

1. Payment method routing (platform-specific: CC, wire, check)
2. Shipping quote requests to approved carriers (freight / large items via uShip; parcel via FedEx/UPS)
3. Condition report request from auction house
4. Provenance packet generation (for antiques / fine art resale or insurance)
5. Add to inventory (for dealers / collectors tracking portfolio value)

## Product code (license key)

`CFG-SNPE-XXXX-XXXX-XXXX`

## Tech notes

- Shared `circuitforge-core` scaffold (DB, LLM router, tier system, config)
- Platform adapters: currently eBay only; AuctionZip, Invaluable, HiBid, CT Bids planned (Playwright + API where available)
- Bid execution: Playwright automation with precise timing (NTP-synchronized)
- Soft-close detection: platform-specific rules engine
- Comparable sales: eBay completed listings via Marketplace Insights API + Browse API fallback
- Vision module: condition assessment from listing photos — moondream2 / Claude vision (paid tier stub in `app/trust/photo.py`)
- **Kasada bypass**: headed Chromium via Xvfb; all scraping uses this path — headless and `requests`-based approaches are blocked by eBay

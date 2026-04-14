# Snipe

**eBay trust scoring before you bid.**

![Snipe landing hero](screenshots/01-hero.png)

Snipe scores eBay listings and sellers for trustworthiness before you place a bid. Paste a search query, get results with trust scores, and know exactly which listings are worth your time.

## What it catches

- **New accounts** selling high-value items with no track record
- **Suspicious prices** — listings priced far below completed sales
- **Duplicate photos** — images copy-pasted from other listings (perceptual hash deduplication)
- **Damage buried in titles** — scratch, dent, untested, for parts, and similar
- **Known bad actors** — sellers on the community blocklist

## How it works

![Search results with trust scores](screenshots/02-results.png)

Each listing gets a composite trust score from 0–100 based on five seller signals: account age, feedback count, feedback ratio, price vs. market, and category history. Red flags are surfaced alongside the score, not buried in it.

## Free, no account required

Search and scoring work without creating an account. Community features (reporting sellers, importing blocklists) require a free account.

## Quick links

- [Installation](getting-started/installation.md)
- [Understanding trust scores](user-guide/trust-scores.md)
- [Red flags reference](user-guide/red-flags.md)
- [Cloud demo](https://menagerie.circuitforge.tech/snipe)
- [Source code](https://git.opensourcesolarpunk.com/Circuit-Forge/snipe)

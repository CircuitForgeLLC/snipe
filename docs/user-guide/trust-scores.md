# Trust Scores

## How scoring works

Each listing gets a composite trust score from 0–100, built from five signals:

| Signal | Max points | What it measures |
|--------|-----------|-----------------|
| `account_age` | 20 | Days since the seller's eBay account was registered |
| `feedback_count` | 20 | Total feedback received (volume proxy for experience) |
| `feedback_ratio` | 20 | Percentage of positive feedback |
| `price_vs_market` | 20 | How the listing price compares to recent completed sales |
| `category_history` | 20 | Whether the seller has a history in this item category |

The composite score is the sum of available signals divided by the maximum possible from available signals. Missing signals don't penalize the seller — they reduce the max rather than adding a zero.

## Score bands

| Score | Label | Meaning |
|-------|-------|---------|
| 70–100 | Green | Established seller, no major concerns |
| 40–69 | Yellow | Some signals marginal or missing |
| 0–39 | Red | Multiple red flags — proceed carefully |

## Zero-feedback cap

A seller with zero feedback is hard-capped at a composite score of **35**, regardless of other signals. Zero feedback is the single strongest indicator of a fraudulent or new account, and it would be misleading to allow such a seller to score higher based on price alignment alone.

## Partial scores

When account age hasn't yet been enriched (the BTF scraper is still running), the score is marked **partial** and shown with a spinning indicator. Partial scores are based on available signals only and update automatically when enrichment completes — typically within 30–60 seconds per seller.

## STEAL badge

The **STEAL** badge appears when a listing's price is significantly below the market median from recently completed sales. This is a useful signal for buyers, but it can also indicate a scam — always cross-reference with the trust score and red flags.

## Market comps

Market price data comes from eBay's Marketplace Insights API (completed sales). When this API is unavailable (requires an approved eBay developer account), Snipe falls back to listing prices from the Browse API, which is less accurate. The market price shown in search results reflects whichever source was available.

# Trust Score Algorithm

## Signal scoring

Each signal contributes 0–20 points to the composite score.

### account_age

| Days old | Score |
|----------|-------|
| < 7 | 0 (triggers `new_account` hard flag) |
| 7–30 | 5 |
| 30–90 | 10 |
| 90–365 | 15 |
| > 365 | 20 |

Data source: eBay profile page (BTF scraper via headed Chromium + Xvfb — eBay API does not expose account registration date).

### feedback_count

| Count | Score |
|-------|-------|
| 0 | 0 (triggers `zero_feedback` hard flag, score capped at 35) |
| 1–9 | 5 |
| 10–49 | 10 |
| 50–199 | 15 |
| 200+ | 20 |

### feedback_ratio

| Ratio | Score |
|-------|-------|
| < 80% (with 20+ reviews) | 0 (triggers `established_bad_actor`) |
| < 90% | 5 |
| 90–94% | 10 |
| 95–98% | 15 |
| 99–100% | 20 |

### price_vs_market

Compares listing price to the median of recent completed sales from eBay Marketplace Insights API.

| Price vs. median | Score |
|-----------------|-------|
| < 40% | 0 (triggers `suspicious_price` flag) |
| 40–59% | 5 |
| 60–79% | 10 |
| 80–120% | 20 (normal range) |
| 121–149% | 15 |
| 150%+ | 10 |

`suspicious_price` flag is suppressed when the market price distribution is too wide (standard deviation > 50% of median) — this prevents false positives on heterogeneous search results.

When no market data is available, this signal returns `None` and is excluded from the composite.

### category_history

Derived from the seller's recent listing history (categories of their sold items):

| Result | Score |
|--------|-------|
| Seller has history in this category | 20 |
| Seller sells cross-category (generalist) | 10 |
| No category history available | None (excluded from composite) |

## Composite calculation

```
composite = (sum of available signal scores) / (20 × count of available signals) × 100
```

This ensures missing signals don't penalize a seller — only available signals count toward the denominator.

## Zero-feedback cap

When `feedback_count == 0`, the composite is hard-capped at **35** after the standard calculation. A 0-feedback seller cannot score above 35 regardless of other signals.

## Partial scores

A score is marked **partial** when one or more signals are `None` (not yet available). The score is recalculated and the partial flag is cleared when enrichment completes.

## Red flag override

Red flags are evaluated independently of the composite score. A seller can have a high composite score and still trigger red flags — for example, a long-established seller with a suspicious-priced listing and duplicate photos.

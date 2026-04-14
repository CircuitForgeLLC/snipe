# Searching

## Basic search

Type a query and press **Search**. Snipe fetches listings from eBay and scores each seller in parallel.

Result count depends on the **Pages to fetch** setting (1 page = up to 200 listings). More pages means a more complete picture but a longer wait.

## Keyword modes

The must-include field has three modes:

| Mode | Behavior |
|------|---------|
| **All** | Every term must appear in results (eBay AND search) |
| **Any** | At least one term must appear (eBay OR search) |
| **Groups** | Comma-separated groups, each searched separately and merged |

Groups mode is the most powerful. Use it to search for variations that eBay's relevance ranking might drop:

```
16gb, 32gb
RTX 4090, 4090 founders
```

This sends two separate eBay queries and deduplicates the results by listing ID.

## Must-exclude

Terms in the must-exclude field are forwarded to eBay on re-search. Common uses:

```
broken, parts only, for parts, untested, cracked
```

!!! note
    Must-exclude applies on re-search (it goes to eBay). The **Hide listings: Scratch/dent mentioned** sidebar filter applies instantly to current results using Snipe's own detection logic, which is more comprehensive than eBay's keyword exclusion.

## Filters sidebar

The sidebar has two sections:

**eBay Search** — settings forwarded to eBay on re-search:
- Category filter
- Price range (min/max)
- Pages to fetch
- Data source (Auto / API / Scraper)

**Filter Results** — applied instantly to current results:
- Min trust score slider
- Min account age / Min feedback count
- Hide listings checkboxes

## Saved searches

Click the bookmark icon next to the Search button to save a search with its current filter settings. Saved searches appear in the **Saved** view and can be re-run with one click, restoring all filters.

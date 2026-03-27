"""
Build eBay-compatible boolean search queries from OR groups.

eBay honors parenthetical OR groups in the _nkw search parameter:
  (term1,term2,term3)  → must contain at least one of these terms
  -term / -"phrase"    → must NOT contain this term / phrase
  space between groups → implicit AND

expand_queries() generates one eBay query per term in the smallest OR group,
using eBay's OR syntax for all remaining groups. This guarantees coverage even
if eBay's relevance ranking would suppress some matches in a single combined query.

Example:
  base = "GPU"
  or_groups = [["16gb","24gb","40gb","48gb"], ["nvidia","quadro","rtx","geforce","titan"]]
  → 4 queries (one per memory size, brand group as eBay OR):
      "GPU 16gb (nvidia,quadro,rtx,geforce,titan)"
      "GPU 24gb (nvidia,quadro,rtx,geforce,titan)"
      "GPU 40gb (nvidia,quadro,rtx,geforce,titan)"
      "GPU 48gb (nvidia,quadro,rtx,geforce,titan)"
"""
from __future__ import annotations


def _group_to_ebay(group: list[str]) -> str:
    """Convert a list of alternatives to an eBay OR clause."""
    clean = [t.strip() for t in group if t.strip()]
    if not clean:
        return ""
    if len(clean) == 1:
        return clean[0]
    return f"({','.join(clean)})"


def build_ebay_query(base_query: str, or_groups: list[list[str]]) -> str:
    """
    Build a single eBay _nkw query string using eBay's parenthetical OR syntax.
    Exclusions are handled separately via SearchFilters.must_exclude.
    """
    parts = [base_query.strip()]
    for group in or_groups:
        clause = _group_to_ebay(group)
        if clause:
            parts.append(clause)
    return " ".join(p for p in parts if p)


def expand_queries(base_query: str, or_groups: list[list[str]]) -> list[str]:
    """
    Expand OR groups into one eBay query per term in the smallest group,
    using eBay's OR syntax for all remaining groups.

    This guarantees every term in the pivot group is explicitly searched,
    which prevents eBay's relevance engine from silently skipping rare variants.
    Falls back to a single query when there are no OR groups.
    """
    if not or_groups:
        return [base_query.strip()]

    # Pivot on the smallest group to minimise the number of Playwright calls
    smallest_idx = min(range(len(or_groups)), key=lambda i: len(or_groups[i]))
    pivot = or_groups[smallest_idx]
    rest = [g for i, g in enumerate(or_groups) if i != smallest_idx]

    queries = []
    for term in pivot:
        q = build_ebay_query(base_query, [[term]] + rest)
        queries.append(q)
    return queries


def parse_groups(raw: str) -> list[list[str]]:
    """
    Parse a Groups-mode must_include string into nested OR groups.

    Format: comma separates groups (AND), pipe separates alternatives within a group (OR).
    "16gb|24gb|48gb, nvidia|rtx|geforce"
    → [["16gb","24gb","48gb"], ["nvidia","rtx","geforce"]]
    """
    groups = []
    for chunk in raw.split(","):
        alts = [t.strip().lower() for t in chunk.split("|") if t.strip()]
        if alts:
            groups.append(alts)
    return groups

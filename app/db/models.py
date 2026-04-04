"""Dataclasses for all Snipe domain objects."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Seller:
    platform: str
    platform_seller_id: str
    username: str
    account_age_days: Optional[int]   # None = not yet fetched (scraper tier)
    feedback_count: int
    feedback_ratio: float           # 0.0–1.0
    category_history_json: str      # JSON blob of past category sales
    id: Optional[int] = None
    fetched_at: Optional[str] = None


@dataclass
class Listing:
    platform: str
    platform_listing_id: str
    title: str
    price: float
    currency: str
    condition: str
    seller_platform_id: str
    url: str
    photo_urls: list[str] = field(default_factory=list)
    listing_age_days: int = 0
    buying_format: str = "fixed_price"   # "fixed_price", "auction", "best_offer"
    ends_at: Optional[str] = None        # ISO8601 auction end time; None for fixed-price
    id: Optional[int] = None
    fetched_at: Optional[str] = None
    trust_score_id: Optional[int] = None
    category_name: Optional[str] = None          # leaf category from eBay API (e.g. "Graphics/Video Cards")
    # Staging DB fields — populated from DB after upsert
    first_seen_at: Optional[str] = None
    last_seen_at: Optional[str] = None
    times_seen: int = 1
    price_at_first_seen: Optional[float] = None


@dataclass
class TrustScore:
    listing_id: int
    composite_score: int            # 0–100
    account_age_score: int          # 0–20
    feedback_count_score: int       # 0–20
    feedback_ratio_score: int       # 0–20
    price_vs_market_score: int      # 0–20
    category_history_score: int     # 0–20
    photo_hash_duplicate: bool = False
    photo_analysis_json: Optional[str] = None
    red_flags_json: str = "[]"
    score_is_partial: bool = False
    id: Optional[int] = None
    scored_at: Optional[str] = None


@dataclass
class MarketComp:
    platform: str
    query_hash: str
    median_price: float
    sample_count: int
    expires_at: str                 # ISO8601 — checked against current time
    id: Optional[int] = None
    fetched_at: Optional[str] = None


@dataclass
class SavedSearch:
    """Schema scaffolded in v0.1; background monitoring wired in v0.2."""
    name: str
    query: str
    platform: str
    filters_json: str = "{}"
    id: Optional[int] = None
    created_at: Optional[str] = None
    last_run_at: Optional[str] = None


@dataclass
class ScammerEntry:
    """A seller manually or community-flagged as a known scammer."""
    platform: str
    platform_seller_id: str
    username: str
    reason: Optional[str] = None
    source: str = "manual"          # "manual" | "csv_import" | "community"
    id: Optional[int] = None
    created_at: Optional[str] = None


@dataclass
class PhotoHash:
    """Perceptual hash store for cross-search dedup (v0.2+). Schema scaffolded in v0.1."""
    listing_id: int
    photo_url: str
    phash: str              # hex string from imagehash
    id: Optional[int] = None
    first_seen_at: Optional[str] = None

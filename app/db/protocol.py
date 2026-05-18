"""Protocol (duck-type interface) for shared table backends (SQLite and Postgres)."""
from __future__ import annotations

from typing import Optional, Protocol, runtime_checkable

from app.db.models import MarketComp, Seller


@runtime_checkable
class SharedTableProtocol(Protocol):
    """Protocol that both Store (SQLite) and SnipeSharedStore (Postgres) must satisfy.

    This enables code that reads/writes shared tables (sellers, market_comps, reported_sellers)
    to remain agnostic to the underlying backend.
    """

    def save_seller(self, seller: Seller) -> None:
        """Persist a single seller record."""
        ...

    def save_sellers(self, sellers: list[Seller]) -> None:
        """Persist multiple seller records (batch upsert)."""
        ...

    def get_seller(self, platform: str, platform_seller_id: str) -> Optional[Seller]:
        """Fetch a single seller by platform and platform_seller_id."""
        ...

    def save_market_comp(self, comp: MarketComp) -> None:
        """Persist a market comparison record."""
        ...

    def get_market_comp(self, platform: str, query_hash: str) -> Optional[MarketComp]:
        """Fetch a market comparison by platform and query_hash."""
        ...

    def mark_reported(
        self,
        platform: str,
        platform_seller_id: str,
        username: Optional[str] = None,
        reported_by: str = "user",
    ) -> None:
        """Record that a seller has been reported to the platform."""
        ...

    def list_reported(self, platform: str = "ebay") -> list[str]:
        """Return all platform_seller_ids that have been reported."""
        ...

    def delete_seller_data(self, platform: str, platform_seller_id: str) -> None:
        """Permanently erase a seller and all related data (GDPR/eBay compliance)."""
        ...

    def clone(self) -> SharedTableProtocol:
        """Create a new independent instance pointing to the same backend."""
        ...

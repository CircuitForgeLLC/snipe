"""PlatformAdapter abstract base and shared types."""
from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional
from app.db.models import Listing, Seller


@dataclass
class SearchFilters:
    max_price: Optional[float] = None
    min_price: Optional[float] = None
    condition: Optional[list[str]] = field(default_factory=list)
    location_radius_km: Optional[int] = None
    pages: int = 1          # number of result pages to fetch (48 listings/page)
    must_include: list[str] = field(default_factory=list)  # client-side title filter
    must_exclude: list[str] = field(default_factory=list)  # forwarded to eBay -term AND client-side


class PlatformAdapter(ABC):
    @abstractmethod
    def search(self, query: str, filters: SearchFilters) -> list[Listing]: ...

    @abstractmethod
    def get_seller(self, seller_platform_id: str) -> Optional[Seller]: ...

    @abstractmethod
    def get_completed_sales(self, query: str) -> list[Listing]:
        """Fetch recently completed/sold listings for price comp data."""
        ...

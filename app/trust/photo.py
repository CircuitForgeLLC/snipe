"""Perceptual hash deduplication within a result set (free tier, v0.1)."""
from __future__ import annotations
from typing import Optional
import io
import requests

try:
    import imagehash
    from PIL import Image
    _IMAGEHASH_AVAILABLE = True
except ImportError:
    _IMAGEHASH_AVAILABLE = False


class PhotoScorer:
    """
    check_duplicates: compare images within a single result set.
    Cross-session dedup (PhotoHash table) is v0.2.
    Vision analysis (real/marketing/EM bag) is v0.2 paid tier.
    """

    def check_duplicates(self, photo_urls_per_listing: list[list[str]]) -> list[bool]:
        """
        Returns a list of booleans parallel to photo_urls_per_listing.
        True = this listing's primary photo is a duplicate of another listing in the set.
        Falls back to URL-equality check if imagehash is unavailable or fetch fails.
        """
        if not _IMAGEHASH_AVAILABLE:
            return self._url_dedup(photo_urls_per_listing)

        primary_urls = [urls[0] if urls else "" for urls in photo_urls_per_listing]

        # Fast path: URL equality is a trivial duplicate signal (no fetch needed)
        url_results = self._url_dedup([[u] for u in primary_urls])

        hashes: list[Optional[str]] = []
        for url in primary_urls:
            hashes.append(self._fetch_hash(url))

        results = list(url_results)  # start from URL-equality results
        seen: dict[str, int] = {}
        for i, h in enumerate(hashes):
            if h is None:
                continue
            if h in seen:
                results[i] = True
                results[seen[h]] = True
            else:
                seen[h] = i
        return results

    def _fetch_hash(self, url: str) -> Optional[str]:
        if not url:
            return None
        try:
            resp = requests.get(url, timeout=5, stream=True)
            resp.raise_for_status()
            img = Image.open(io.BytesIO(resp.content))
            return str(imagehash.phash(img))
        except Exception:
            return None

    def _url_dedup(self, photo_urls_per_listing: list[list[str]]) -> list[bool]:
        seen: set[str] = set()
        results = []
        for urls in photo_urls_per_listing:
            primary = urls[0] if urls else ""
            if primary and primary in seen:
                results.append(True)
            else:
                if primary:
                    seen.add(primary)
                results.append(False)
        return results

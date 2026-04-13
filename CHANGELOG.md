# Changelog

All notable changes to `snipe` are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
Versions follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [0.2.0] — 2026-04-12

### Added

**Trust signal UI** — community feedback on seller trust scores (MIT component layer)

- `web/src/components/TrustFeedbackButtons.vue`: "This score looks right / This score is wrong" button pair displayed below the trust badge on each listing card. Shows "Thanks, noted." on submission with no countdown or urgency.
- `web/src/composables/useTrustFeedback.ts`: `FeedbackState` machine (`idle | sending | confirmed | disputed`). Fail-soft: any network error still transitions to confirmed state — the UI never surfaces signal pipeline failures.
- Slotted into `ListingCard.vue` after the trust badge, inside `.card__score-col`.
- WCAG (Web Content Accessibility Guidelines) 2.1 compliance: `aria-live="polite"` on confirmation message, `aria-busy` during send, keyboard-focusable buttons with `focus-visible` styles, `prefers-reduced-motion` guard on transitions.
- Uses `--trust-high` / `--trust-low` theme CSS custom properties for color consistency.

_Note: The backend signal endpoint (`POST /api/community/signal`) and seller signal store are gated on cf-orch community postgres landing. The UI degrades gracefully when the endpoint is absent._

**Forgejo feedback FAB** (floating action button)

- `FeedbackButton.vue`: floating "Feedback" button in the corner of every view. Opens a two-step modal (type + description → attribution + confirm) that files a Forgejo issue against `Circuit-Forge/snipe`. Hidden when `FORGEJO_API_TOKEN` is unset or in demo mode.
- `GET /api/feedback/status` — returns `{"enabled": bool}` so the button never flashes before checking.
- `POST /api/feedback` — files the issue; returns `issue_number` and `issue_url`.

**Live SSE score push** (closes #1)

- Background enrichment results pushed to the browser via Server-Sent Events as trust scores complete.

---

## [0.1.0] — 2026-03-25

### Added

Initial beta release of Snipe — eBay listing intelligence and trust scoring.

- Listing search via eBay scraper (Kasada bypass with headed Chromium + Xvfb).
- Trust score composite: feedback rate, negative feedback ratio, member age, zero-feedback penalty.
- `TrustScore` dataclass with red flags, partial score flag, composite score (0-100).
- Vue 3 SPA frontend: search view, listing card grid, listing detail view, blocklist management.
- FastAPI backend: `/api/search`, `/api/enrich`, `/api/blocklist`.
- Keyword filtering for search queries.
- SQLite persistence via cf-core `db` module.

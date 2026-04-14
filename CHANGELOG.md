# Changelog

All notable changes to `snipe` are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
Versions follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [0.4.0] — 2026-04-14

### Added

**Search with AI** — natural language to eBay search filters (closes #29, Paid+ tier)

- `QueryTranslator`: sends a free-text prompt to a local LLM (via cf-orch, defaulting to `llama3.1:8b`) with a domain-aware system prompt and eBay Taxonomy category hints. Returns structured `SearchParamsResponse` (keywords, price range, condition, category, sort order, pages).
- `EbayCategoryCache`: bootstraps from a seed list; refreshes from the eBay Browse API Taxonomy endpoint on a 7-day TTL. `get_relevant(query)` injects the 10 closest categories into the system prompt to reduce hallucinated filter values.
- `POST /api/search/build` — tier-gated endpoint (paid+) that accepts `{"prompt": "..."}` and returns populated `SearchParamsResponse`. Wired to `LLMRouter` via the Peregrine-style shim.
- `LLMQueryPanel.vue`: collapsible panel above the search form with a text area, a "Search with AI" button, and an auto-run toggle. A11y (accessibility): `aria-expanded`, `aria-controls`, `aria-live="polite"` on status, keyboard-navigable, `prefers-reduced-motion` guard on collapse animation.
- `useLLMQueryBuilder` composable: manages `buildQuery()` state machine (`idle | loading | done | error`), exposes `autoRun` flag, calls `populateFromLLM()` on the search store.
- `SettingsView`: new "Search with AI" section with the auto-run toggle persisted to user preferences.
- `search.ts`: `populateFromLLM()` merges LLM-returned filters into the store; guards `v-model.number` empty-string edge case (cleared price inputs sent `NaN` to the API).

**Preferences system**

- `Store.get_user_preference` / `set_user_preference` / `get_all_preferences`: dot-path read/write over a singleton `user_preferences` JSON row (immutable update pattern via `circuitforge_core.preferences.paths`).
- `Store.save_community_signal`: persists trust feedback signals to `community_signals` table.
- `preferencesStore` (Pinia): loaded after session bootstrap; `load()` / `set()` / `get()` surface preferences to Vue components.

**Community module** (closes #31 #32 #33)

- `corrections` router wired: `POST /api/community/signal` now lands in SQLite `community_signals`.
- `COMMUNITY_DB_URL` env var documented in `.env.example`.

### Fixed

- `useTrustFeedback`: prefixes fetch URL with `VITE_API_BASE` so feedback signals route correctly under menagerie reverse proxy.
- `App.vue`: skip-to-main link moved before `<AppNav>` so keyboard users reach it as the first focusable element (WCAG 2.4.1 bypass-blocks compliance).
- `@/` path alias removed from Vue components (Vite config had no alias configured; replaced with relative imports to fix production build).
- `search.ts`: LLM-populated filters now sync back into `SearchView` local state so the form reflects the AI-generated values immediately.
- Python import ordering pass (isort) across adapters, trust modules, tasks, and test files.

### Closed

- `#29` LLM query builder — shipped.
- `#31` `#32` `#33` Community corrections router — shipped.

---

## [0.3.0] — 2026-04-14

### Added

**Infrastructure and DevOps**

- `.forgejo/workflows/ci.yml` — Python lint (ruff) + pytest + Vue typecheck + vitest on every PR/push to main. Installs circuitforge-core from GitHub mirror so the CI runner doesn't need the sibling directory.
- `.forgejo/workflows/release.yml` — Docker build and push (api + web images) to Forgejo container registry on `v*` tags. Builds both images multi-arch (amd64 + arm64). Creates a Forgejo release with git-cliff changelog notes.
- `.forgejo/workflows/mirror.yml` — Mirror push to GitHub and Codeberg on main/tags.
- `install.sh` — Full rewrite following the CircuitForge installer pattern: colored output, `--docker` / `--bare-metal` / `--help` flags, auto-detection of Docker/conda/Python/Node/Chromium/Xvfb, license key prompting, structured named functions.
- `docs/nginx-self-hosted.conf` — Sample nginx config for bare-metal self-hosted deployments (SPA fallback, SSE proxy settings, long-term asset caching).
- `docs/getting-started/installation.md` — No-Docker install section: bare-metal instructions, nginx setup, Chromium/Xvfb note.
- `compose.override.yml` — `cf-orch-agent` sidecar service for routing vision tasks to a cf-orch GPU coordinator (`--profile orch` opt-in). `CF_ORCH_COORDINATOR_URL` env var documented.
- `.env.example` — `CF_ORCH_URL` and `CF_ORCH_COORDINATOR_URL` comments expanded with self-hosted coordinator guidance.

**Screenshots** (post CSS fix)

- Retook all docs screenshots (`01-hero`, `02-results`, `03-steal-badge`, `hero`) after the color-mix token fix so tints match the theme in both dark and light mode.

### Closed

- `#1` SSE live score push — already fully implemented in 0.2.0; closed.
- `#22` Forgejo Actions CI/CD — shipped.
- `#24` nginx config for no-Docker self-hosting — shipped.
- `#25` Self-hosted installer script — shipped.
- `#15` cf-orch agent in compose stack — shipped.
- `#27` MCP server — already shipped in 0.2.0; closed.

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

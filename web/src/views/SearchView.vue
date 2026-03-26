<template>
  <div class="search-view">
    <!-- Search bar -->
    <header class="search-header">
      <form class="search-form" @submit.prevent="onSearch" role="search">
        <label for="search-input" class="sr-only">Search listings</label>
        <input
          id="search-input"
          v-model="queryInput"
          type="search"
          class="search-input"
          placeholder="RTX 4090, vintage camera, rare vinyl…"
          autocomplete="off"
          :disabled="store.loading"
        />
        <button type="submit" class="search-btn" :disabled="store.loading || !queryInput.trim()">
          <MagnifyingGlassIcon class="search-btn-icon" aria-hidden="true" />
          <span>{{ store.loading ? 'Searching…' : 'Search' }}</span>
        </button>
      </form>
    </header>

    <div class="search-body">
      <!-- Filter sidebar -->
      <aside class="filter-sidebar" aria-label="Search filters">
        <h2 class="filter-heading">Filters</h2>

        <fieldset class="filter-group">
          <legend class="filter-label">Min Trust Score</legend>
          <input
            v-model.number="filters.minTrustScore"
            type="range"
            min="0"
            max="100"
            step="5"
            class="filter-range"
            aria-valuemin="0"
            aria-valuemax="100"
            :aria-valuenow="filters.minTrustScore"
          />
          <span class="filter-range-val">{{ filters.minTrustScore ?? 0 }}</span>
        </fieldset>

        <fieldset class="filter-group">
          <legend class="filter-label">Pages to fetch</legend>
          <div class="filter-pages" role="group" aria-label="Number of result pages">
            <button
              v-for="p in [1, 2, 3, 5]"
              :key="p"
              type="button"
              class="filter-pages-btn"
              :class="{ 'filter-pages-btn--active': filters.pages === p }"
              @click="filters.pages = p"
            >{{ p }}</button>
          </div>
          <p class="filter-pages-hint">{{ (filters.pages ?? 1) * 48 }} listings · {{ (filters.pages ?? 1) * 2 }} Playwright calls</p>
        </fieldset>

        <fieldset class="filter-group">
          <legend class="filter-label">Price</legend>
          <div class="filter-row">
            <input v-model.number="filters.minPrice" type="number" min="0" class="filter-input" placeholder="Min $" />
            <input v-model.number="filters.maxPrice" type="number" min="0" class="filter-input" placeholder="Max $" />
          </div>
        </fieldset>

        <fieldset class="filter-group">
          <legend class="filter-label">Condition</legend>
          <label v-for="cond in CONDITIONS" :key="cond.value" class="filter-check">
            <input
              type="checkbox"
              :value="cond.value"
              v-model="filters.conditions"
            />
            {{ cond.label }}
          </label>
        </fieldset>

        <fieldset class="filter-group">
          <legend class="filter-label">Seller</legend>
          <div class="filter-row">
            <label class="filter-label-sm" for="f-age">Min account age (days)</label>
            <input id="f-age" v-model.number="filters.minAccountAgeDays" type="number" min="0" class="filter-input" placeholder="0" />
          </div>
          <div class="filter-row">
            <label class="filter-label-sm" for="f-fb">Min feedback count</label>
            <input id="f-fb" v-model.number="filters.minFeedbackCount" type="number" min="0" class="filter-input" placeholder="0" />
          </div>
        </fieldset>

        <fieldset class="filter-group">
          <legend class="filter-label">Hide listings</legend>
          <label class="filter-check">
            <input type="checkbox" v-model="filters.hideNewAccounts" />
            New accounts (&lt;30d)
          </label>
          <label class="filter-check">
            <input type="checkbox" v-model="filters.hideSuspiciousPrice" />
            Suspicious price
          </label>
          <label class="filter-check">
            <input type="checkbox" v-model="filters.hideDuplicatePhotos" />
            Duplicate photos
          </label>
        </fieldset>
      </aside>

      <!-- Results area -->
      <section class="results-area" aria-live="polite" aria-label="Search results">
        <!-- Error -->
        <div v-if="store.error" class="results-error" role="alert">
          <ExclamationTriangleIcon class="results-error-icon" aria-hidden="true" />
          {{ store.error }}
        </div>

        <!-- Empty state (before first search) -->
        <div v-else-if="!store.results.length && !store.loading && !store.query" class="results-empty">
          <span class="results-empty-icon" aria-hidden="true">🎯</span>
          <p>Enter a search term to find listings.</p>
        </div>

        <!-- No results -->
        <div v-else-if="!store.results.length && !store.loading && store.query" class="results-empty">
          <p>No listings found for <strong>{{ store.query }}</strong>.</p>
        </div>

        <!-- Results -->
        <template v-else-if="store.results.length">
          <!-- Sort + count bar -->
          <div class="results-toolbar">
            <p class="results-count">
              {{ visibleListings.length }} results
              <span v-if="hiddenCount > 0" class="results-hidden">
                · {{ hiddenCount }} hidden by filters
              </span>
            </p>
            <label for="sort-select" class="sr-only">Sort by</label>
            <select id="sort-select" v-model="sortBy" class="sort-select">
              <option v-for="opt in SORT_OPTIONS" :key="opt.value" :value="opt.value">
                {{ opt.label }}
              </option>
            </select>
          </div>

          <!-- Cards -->
          <div class="results-list">
            <ListingCard
              v-for="listing in visibleListings"
              :key="`${listing.platform}-${listing.platform_listing_id}`"
              :listing="listing"
              :trust="store.trustScores.get(listing.platform_listing_id) ?? null"
              :seller="store.sellers.get(listing.seller_platform_id) ?? null"
              :market-price="store.marketPrice"
            />
          </div>
        </template>
      </section>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, reactive } from 'vue'
import { MagnifyingGlassIcon, ExclamationTriangleIcon } from '@heroicons/vue/24/outline'
import { useSearchStore } from '../stores/search'
import type { Listing, TrustScore, SearchFilters } from '../stores/search'
import ListingCard from '../components/ListingCard.vue'

const store = useSearchStore()
const queryInput = ref('')

// ── Filters ──────────────────────────────────────────────────────────────────

const filters = reactive<SearchFilters>({
  minTrustScore: 0,
  minPrice: undefined,
  maxPrice: undefined,
  conditions: [],
  minAccountAgeDays: 0,
  minFeedbackCount: 0,
  hideNewAccounts: false,
  hideSuspiciousPrice: false,
  hideDuplicatePhotos: false,
  pages: 1,
})

const CONDITIONS = [
  { value: 'new',       label: 'New' },
  { value: 'like_new',  label: 'Like New' },
  { value: 'very_good', label: 'Very Good' },
  { value: 'good',      label: 'Good' },
  { value: 'acceptable',label: 'Acceptable' },
  { value: 'for_parts', label: 'For Parts' },
]

// ── Sort ─────────────────────────────────────────────────────────────────────

const SORT_OPTIONS = [
  { value: 'trust',       label: 'Trust score' },
  { value: 'price_asc',   label: 'Price ↑' },
  { value: 'price_desc',  label: 'Price ↓' },
  { value: 'ending_soon', label: 'Ending soon' },
]

const sortBy = ref('trust')

function hoursRemaining(listing: Listing): number | null {
  if (!listing.ends_at) return null
  const ms = new Date(listing.ends_at).getTime() - Date.now()
  return ms > 0 ? ms / 3_600_000 : 0
}

function sortedListings(list: Listing[]): Listing[] {
  return [...list].sort((a, b) => {
    const ta = store.trustScores.get(a.platform_listing_id)
    const tb = store.trustScores.get(b.platform_listing_id)
    switch (sortBy.value) {
      case 'trust':
        return (tb?.composite_score ?? 0) - (ta?.composite_score ?? 0)
      case 'price_asc':
        return a.price - b.price
      case 'price_desc':
        return b.price - a.price
      case 'ending_soon': {
        const ha = hoursRemaining(a) ?? Infinity
        const hb = hoursRemaining(b) ?? Infinity
        return ha - hb
      }
      default:
        return 0
    }
  })
}

function passesFilter(listing: Listing): boolean {
  const trust = store.trustScores.get(listing.platform_listing_id)
  const seller = store.sellers.get(listing.seller_platform_id)

  if (filters.minTrustScore && trust && trust.composite_score < filters.minTrustScore) return false
  if (filters.minPrice != null && listing.price < filters.minPrice) return false
  if (filters.maxPrice != null && listing.price > filters.maxPrice) return false
  if (filters.conditions?.length && !filters.conditions.includes(listing.condition)) return false

  if (seller) {
    if (filters.minAccountAgeDays && seller.account_age_days < filters.minAccountAgeDays) return false
    if (filters.minFeedbackCount && seller.feedback_count < filters.minFeedbackCount) return false
  }

  if (trust) {
    let flags: string[] = []
    try { flags = JSON.parse(trust.red_flags_json ?? '[]') } catch { /* empty */ }
    if (filters.hideNewAccounts && flags.includes('account_under_30_days')) return false
    if (filters.hideSuspiciousPrice && flags.includes('suspicious_price')) return false
    if (filters.hideDuplicatePhotos && flags.includes('duplicate_photo')) return false
  }

  return true
}

const sortedAll = computed(() => sortedListings(store.results))
const visibleListings = computed(() => sortedAll.value.filter(passesFilter))
const hiddenCount = computed(() => store.results.length - visibleListings.value.length)

// ── Actions ──────────────────────────────────────────────────────────────────

async function onSearch() {
  if (!queryInput.value.trim()) return
  await store.search(queryInput.value.trim(), filters)
}
</script>

<style scoped>
.search-view {
  display: flex;
  flex-direction: column;
  min-height: 100dvh;
}

/* Search bar header */
.search-header {
  padding: var(--space-6) var(--space-6) var(--space-4);
  border-bottom: 1px solid var(--color-border);
  background: var(--color-surface-2);
  position: sticky;
  top: 0;
  z-index: 10;
}

.search-form {
  display: flex;
  gap: var(--space-3);
  max-width: 760px;
}

.search-input {
  flex: 1;
  padding: var(--space-3) var(--space-4);
  background: var(--color-surface-raised);
  border: 1.5px solid var(--color-border);
  border-radius: var(--radius-md);
  color: var(--color-text);
  font-family: var(--font-body);
  font-size: 1rem;
  transition: border-color 150ms ease;
}

.search-input:focus {
  outline: none;
  border-color: var(--app-primary);
}

.search-input::placeholder { color: var(--color-text-muted); }

.search-btn {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-3) var(--space-6);
  background: var(--app-primary);
  color: var(--color-text-inverse);
  border: none;
  border-radius: var(--radius-md);
  font-family: var(--font-body);
  font-size: 1rem;
  font-weight: 600;
  cursor: pointer;
  transition: background 150ms ease;
  white-space: nowrap;
}

.search-btn:hover:not(:disabled) { background: var(--app-primary-hover); }
.search-btn:disabled { opacity: 0.55; cursor: not-allowed; }
.search-btn-icon { width: 1.1rem; height: 1.1rem; }

/* Two-column layout */
.search-body {
  display: flex;
  flex: 1;
  min-height: 0;
}

/* Filter sidebar */
.filter-sidebar {
  width: 220px;
  flex-shrink: 0;
  padding: var(--space-6) var(--space-4);
  border-right: 1px solid var(--color-border);
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

.filter-heading {
  font-size: 0.8125rem;
  font-weight: 700;
  color: var(--color-text-muted);
  text-transform: uppercase;
  letter-spacing: 0.06em;
  margin-bottom: var(--space-2);
}

.filter-group {
  border: none;
  padding: 0;
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.filter-label {
  font-size: 0.8125rem;
  font-weight: 600;
  color: var(--color-text-muted);
}

.filter-label-sm {
  font-size: 0.75rem;
  color: var(--color-text-muted);
}

.filter-range {
  accent-color: var(--app-primary);
  width: 100%;
}

.filter-range-val {
  font-family: var(--font-mono);
  font-size: 0.8125rem;
  color: var(--app-primary);
}

.filter-row {
  display: flex;
  gap: var(--space-2);
  flex-direction: column;
}

.filter-input {
  padding: var(--space-2) var(--space-3);
  background: var(--color-surface-raised);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  color: var(--color-text);
  font-family: var(--font-body);
  font-size: 0.875rem;
  width: 100%;
}

.filter-check {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  font-size: 0.8125rem;
  color: var(--color-text-muted);
  cursor: pointer;
}

.filter-check input[type="checkbox"] {
  accent-color: var(--app-primary);
  width: 14px;
  height: 14px;
}

.filter-pages {
  display: flex;
  gap: var(--space-1);
}

.filter-pages-btn {
  flex: 1;
  padding: var(--space-1) 0;
  background: var(--color-surface-raised);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  color: var(--color-text-muted);
  font-family: var(--font-body);
  font-size: 0.8125rem;
  font-weight: 600;
  cursor: pointer;
  transition: background 120ms ease, color 120ms ease, border-color 120ms ease;
}

.filter-pages-btn:hover:not(.filter-pages-btn--active) {
  border-color: var(--app-primary);
  color: var(--app-primary);
}

.filter-pages-btn--active {
  background: var(--app-primary);
  border-color: var(--app-primary);
  color: var(--color-text-inverse);
}

.filter-pages-hint {
  font-size: 0.6875rem;
  color: var(--color-text-muted);
  margin: 0;
  opacity: 0.75;
}

/* Results area */
.results-area {
  flex: 1;
  padding: var(--space-6);
  overflow-y: auto;
  min-width: 0;
}

.results-error {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-4);
  background: rgba(248, 81, 73, 0.1);
  border: 1px solid rgba(248, 81, 73, 0.3);
  border-radius: var(--radius-md);
  color: var(--color-error);
  font-size: 0.9375rem;
}

.results-error-icon { width: 1.25rem; height: 1.25rem; flex-shrink: 0; }

.results-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-4);
  padding: var(--space-16) var(--space-4);
  color: var(--color-text-muted);
  text-align: center;
}

.results-empty-icon { font-size: 3rem; }

.results-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: var(--space-4);
  gap: var(--space-4);
}

.results-count {
  font-size: 0.875rem;
  color: var(--color-text-muted);
  margin: 0;
}

.results-hidden { color: var(--color-warning); }

.sort-select {
  padding: var(--space-2) var(--space-3);
  background: var(--color-surface-raised);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  color: var(--color-text);
  font-family: var(--font-body);
  font-size: 0.875rem;
  cursor: pointer;
}

.results-list {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

/* Mobile: collapse filter sidebar */
@media (max-width: 767px) {
  .filter-sidebar {
    display: none;
  }

  .search-header { padding: var(--space-4); }
  .results-area  { padding: var(--space-4); }
}
</style>

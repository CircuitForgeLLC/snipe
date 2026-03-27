<template>
  <div class="search-view">
    <!-- Search bar -->
    <header class="search-header">
      <form class="search-form" @submit.prevent="onSearch" role="search">
        <label for="cat-select" class="sr-only">Category</label>
        <select
          id="cat-select"
          v-model="filters.categoryId"
          class="search-category-select"
          :class="{ 'search-category-select--active': filters.categoryId }"
          :disabled="store.loading"
          title="Filter by category"
        >
          <option value="">All</option>
          <optgroup v-for="group in CATEGORY_GROUPS" :key="group.label" :label="group.label">
            <option v-for="cat in group.cats" :key="cat.id" :value="cat.id">
              {{ cat.name }}
            </option>
          </optgroup>
        </select>
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
        <button
          v-if="store.loading"
          type="button"
          class="cancel-btn"
          @click="store.cancelSearch()"
          title="Cancel search"
        >✕ Cancel</button>
        <button
          v-else
          type="button"
          class="save-bookmark-btn"
          :disabled="!queryInput.trim()"
          :title="showSaveForm ? 'Cancel' : 'Save this search'"
          @click="showSaveForm = !showSaveForm; if (showSaveForm) saveName = queryInput.trim()"
        >
          <BookmarkIcon class="search-btn-icon" aria-hidden="true" />
        </button>
      </form>
      <form v-if="showSaveForm" class="save-inline-form" @submit.prevent="onSave">
        <input
          v-model="saveName"
          class="save-name-input"
          placeholder="Name this search…"
          autocomplete="off"
          autofocus
        />
        <button type="submit" class="save-confirm-btn">Save</button>
        <button type="button" class="save-cancel-btn" @click="showSaveForm = false">✕</button>
        <span v-if="saveSuccess" class="save-success">Saved!</span>
        <span v-if="saveError" class="save-error">{{ saveError }}</span>
      </form>
    </header>

    <div class="search-body">
      <!-- Filter sidebar -->
      <aside class="filter-sidebar" aria-label="Search filters">

        <!-- ── eBay Search Parameters ─────────────────────────────────────── -->
        <!-- These are sent to eBay. Changes require a new search to take effect. -->
        <h2 class="filter-section-heading filter-section-heading--search">
          eBay Search
        </h2>
        <p class="filter-section-hint">Re-search to apply changes below</p>

        <fieldset class="filter-group">
          <legend class="filter-label">
            Data source
            <span
              v-if="store.adapterUsed"
              class="adapter-badge"
              :class="store.adapterUsed === 'api' ? 'adapter-badge--api' : 'adapter-badge--scraper'"
            >{{ store.adapterUsed === 'api' ? 'eBay API' : 'Scraper' }}</span>
          </legend>
          <div class="filter-pages" role="group" aria-label="Data source adapter">
            <button
              v-for="m in ADAPTER_MODES"
              :key="m.value"
              type="button"
              class="filter-pages-btn"
              :class="{ 'filter-pages-btn--active': filters.adapter === m.value }"
              @click="filters.adapter = m.value"
            >{{ m.label }}</button>
          </div>
          <p class="filter-pages-hint">Auto uses API when credentials are set</p>
        </fieldset>

        <fieldset class="filter-group">
          <legend class="filter-label">Pages to fetch</legend>
          <div class="filter-pages" role="group" aria-label="Number of result pages">
            <button
              v-for="p in [1, 2, 3, 5]"
              :key="p"
              type="button"
              class="filter-pages-btn"
              :class="{
                'filter-pages-btn--active': filters.pages === p,
                'filter-pages-btn--locked': p > session.features.max_pages,
              }"
              :disabled="p > session.features.max_pages"
              :title="p > session.features.max_pages ? 'Upgrade to fetch more pages' : undefined"
              @click="p <= session.features.max_pages && (filters.pages = p)"
            >{{ p }}</button>
          </div>
          <p class="filter-pages-hint">{{ pagesHint }}</p>
        </fieldset>

        <fieldset class="filter-group">
          <legend class="filter-label">Price range</legend>
          <div class="filter-row">
            <input v-model.number="filters.minPrice" type="number" min="0" class="filter-input" placeholder="Min $" />
            <input v-model.number="filters.maxPrice" type="number" min="0" class="filter-input" placeholder="Max $" />
          </div>
          <p class="filter-pages-hint">Forwarded to eBay API</p>
        </fieldset>

        <fieldset class="filter-group">
          <legend class="filter-label">Keywords</legend>
          <div class="filter-row">
            <label class="filter-label-sm" for="f-include">Must include</label>
            <div class="filter-mode-row">
              <button
                v-for="m in INCLUDE_MODES"
                :key="m.value"
                type="button"
                class="filter-pages-btn"
                :class="{ 'filter-pages-btn--active': filters.mustIncludeMode === m.value }"
                @click="filters.mustIncludeMode = m.value"
              >{{ m.label }}</button>
            </div>
            <input
              id="f-include"
              v-model="filters.mustInclude"
              type="text"
              class="filter-input filter-input--keyword"
              :placeholder="filters.mustIncludeMode === 'groups' ? 'founders|fe, 16gb\u2026' : '16gb, founders\u2026'"
              autocomplete="off"
              spellcheck="false"
            />
            <p class="filter-pages-hint">{{ includeHint }}</p>
          </div>
          <div class="filter-row">
            <label class="filter-label-sm" for="f-exclude">Must exclude</label>
            <input
              id="f-exclude"
              v-model="filters.mustExclude"
              type="text"
              class="filter-input filter-input--keyword filter-input--exclude"
              placeholder="broken, parts\u2026"
              autocomplete="off"
              spellcheck="false"
            />
            <p class="filter-pages-hint">Excludes forwarded to eBay on re-search</p>
          </div>
        </fieldset>

        <!-- ── Post-search Filters ────────────────────────────────────────── -->
        <!-- Applied locally to current results — no re-search needed. -->
        <div class="filter-section-divider" role="separator"></div>
        <h2 class="filter-section-heading filter-section-heading--filter">
          Filter Results
        </h2>
        <p class="filter-section-hint">Applied instantly to current results</p>

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

        <details class="filter-group filter-collapsible">
          <summary class="filter-collapsible-summary">Condition</summary>
          <div class="filter-collapsible-body">
            <label v-for="cond in CONDITIONS" :key="cond.value" class="filter-check">
              <input
                type="checkbox"
                :value="cond.value"
                v-model="filters.conditions"
              />
              {{ cond.label }}
            </label>
          </div>
        </details>

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
          <label class="filter-check">
            <input type="checkbox" v-model="filters.hideScratchDent" />
            Scratch / dent mentioned
          </label>
          <label class="filter-check">
            <input type="checkbox" v-model="filters.hideLongOnMarket" />
            Long on market (≥5 sightings, 14d+)
          </label>
          <label class="filter-check">
            <input type="checkbox" v-model="filters.hidePriceDrop" />
            Significant price drop (≥20%)
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
            <div class="toolbar-actions">
              <label for="sort-select" class="sr-only">Sort by</label>
              <select id="sort-select" v-model="sortBy" class="sort-select">
                <option v-for="opt in SORT_OPTIONS" :key="opt.value" :value="opt.value">
                  {{ opt.label }}
                </option>
              </select>
            </div>
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
import { ref, computed, reactive, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { MagnifyingGlassIcon, ExclamationTriangleIcon, BookmarkIcon } from '@heroicons/vue/24/outline'
import { useSearchStore } from '../stores/search'
import type { Listing, TrustScore, SearchFilters, MustIncludeMode } from '../stores/search'
import { useSavedSearchesStore } from '../stores/savedSearches'
import { useSessionStore } from '../stores/session'
import ListingCard from '../components/ListingCard.vue'

const route = useRoute()
const store = useSearchStore()
const savedStore = useSavedSearchesStore()
const session = useSessionStore()
const queryInput = ref('')

// Save search UI state
const showSaveForm = ref(false)
const saveName = ref('')
const saveError = ref<string | null>(null)
const saveSuccess = ref(false)

async function onSave() {
  if (!saveName.value.trim()) return
  saveError.value = null
  try {
    await savedStore.create(saveName.value.trim(), store.query, { ...filters })
    saveSuccess.value = true
    showSaveForm.value = false
    saveName.value = ''
    setTimeout(() => { saveSuccess.value = false }, 2500)
  } catch (e) {
    saveError.value = e instanceof Error ? e.message : 'Save failed'
  }
}

// Auto-run if ?q= param present (e.g. launched from Saved Searches)
onMounted(() => {
  const q = route.query.q
  if (typeof q === 'string' && q.trim()) {
    queryInput.value = q.trim()
    // Restore saved filters (e.g. category, price range, trust threshold)
    const f = route.query.filters
    if (typeof f === 'string') {
      try {
        const restored = JSON.parse(f) as Partial<SearchFilters>
        Object.assign(filters, restored)
      } catch { /* malformed — ignore */ }
    }
    onSearch()
  }
})

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
  hideScratchDent: false,
  hideLongOnMarket: false,
  hidePriceDrop: false,
  pages: 1,
  mustInclude: '',
  mustIncludeMode: 'all',
  mustExclude: '',
  categoryId: '',
  adapter: 'auto' as 'auto' | 'api' | 'scraper',
})

// Parse comma-separated keyword strings into trimmed, lowercase, non-empty term arrays
const parsedMustInclude = computed(() =>
  (filters.mustInclude ?? '').split(',').map(t => t.trim().toLowerCase()).filter(Boolean)
)
const parsedMustExclude = computed(() =>
  (filters.mustExclude ?? '').split(',').map(t => t.trim().toLowerCase()).filter(Boolean)
)
// Groups mode: comma = group separator, pipe = OR within group → string[][]
// e.g. "founders|fe, 16gb" → [["founders","fe"], ["16gb"]]
const parsedMustIncludeGroups = computed(() =>
  (filters.mustInclude ?? '').split(',')
    .map(group => group.split('|').map(t => t.trim().toLowerCase()).filter(Boolean))
    .filter(g => g.length > 0)
)

const INCLUDE_MODES: { value: MustIncludeMode; label: string }[] = [
  { value: 'all',    label: 'All' },
  { value: 'any',    label: 'Any' },
  { value: 'groups', label: 'Groups' },
]

const includeHint = computed(() => {
  switch (filters.mustIncludeMode) {
    case 'any':    return 'At least one term must appear'
    case 'groups': return 'Comma = AND · pipe | = OR within group'
    default:       return 'Every term must appear'
  }
})

const ADAPTER_MODES: { value: 'auto' | 'api' | 'scraper'; label: string }[] = [
  { value: 'auto',    label: 'Auto' },
  { value: 'api',     label: 'API' },
  { value: 'scraper', label: 'Scraper' },
]

const pagesHint = computed(() => {
  const p = filters.pages ?? 1
  const effective = filters.adapter === 'scraper' ? 'scraper'
    : filters.adapter === 'api' ? 'api'
    : store.adapterUsed ?? 'api'  // assume API until first search
  if (effective === 'scraper') {
    return `${p * 48} listings · ${p} Playwright calls`
  }
  return `Up to ${p * 200} listings · ${p} Browse API call${p > 1 ? 's' : ''}`
})

const CATEGORY_GROUPS = [
  { label: 'Computers', cats: [
    { id: '175673', name: 'Computer Components & Parts' },
    { id: '27386',  name: 'Graphics / Video Cards' },
    { id: '164',    name: 'CPUs / Processors' },
    { id: '1244',   name: 'Motherboards' },
    { id: '170083', name: 'Memory (RAM)' },
    { id: '56083',  name: 'Hard Drives & SSDs' },
    { id: '42017',  name: 'Power Supplies' },
    { id: '42014',  name: 'Computer Cases' },
    { id: '11176',  name: 'Networking Equipment' },
    { id: '80053',  name: 'Monitors' },
    { id: '177',    name: 'Laptops' },
    { id: '179',    name: 'Desktop Computers' },
  ]},
  { label: 'Mobile', cats: [
    { id: '9355',   name: 'Smartphones' },
    { id: '171485', name: 'Tablets & eReaders' },
  ]},
  { label: 'Gaming', cats: [
    { id: '139971', name: 'Game Consoles' },
    { id: '1249',   name: 'Video Games' },
  ]},
  { label: 'Audio & Video', cats: [
    { id: '14969',  name: 'Home Audio' },
    { id: '32852',  name: 'TVs' },
  ]},
  { label: 'Cameras', cats: [
    { id: '625',    name: 'Cameras & Photo' },
  ]},
  { label: 'Collectibles', cats: [
    { id: '183454', name: 'Trading Cards' },
    { id: '64482',  name: 'Sports Memorabilia' },
    { id: '11116',  name: 'Coins & Currency' },
    { id: '20081',  name: 'Antiques' },
  ]},
]

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

  // Keyword filtering — substring match on lowercased title
  const title = listing.title.toLowerCase()
  if (parsedMustInclude.value.length) {
    const mode = filters.mustIncludeMode ?? 'all'
    if (mode === 'any') {
      if (!parsedMustInclude.value.some(term => title.includes(term))) return false
    } else if (mode === 'groups') {
      // CNF: must match at least one alternative from every group
      if (!parsedMustIncludeGroups.value.every(group => group.some(alt => title.includes(alt)))) return false
    } else {
      // 'all': every term must appear
      if (parsedMustInclude.value.some(term => !title.includes(term))) return false
    }
  }
  if (parsedMustExclude.value.some(term => title.includes(term))) return false

  if (filters.minTrustScore && trust && trust.composite_score < filters.minTrustScore) return false
  if (filters.minPrice != null && listing.price < filters.minPrice) return false
  if (filters.maxPrice != null && listing.price > filters.maxPrice) return false
  if (filters.conditions?.length && !filters.conditions.includes(listing.condition)) return false

  if (seller) {
    if (filters.minAccountAgeDays && seller.account_age_days != null && seller.account_age_days < filters.minAccountAgeDays) return false
    if (filters.minFeedbackCount && seller.feedback_count < filters.minFeedbackCount) return false
  }

  if (trust) {
    let flags: string[] = []
    try { flags = JSON.parse(trust.red_flags_json ?? '[]') } catch { /* empty */ }
    if (filters.hideNewAccounts && flags.includes('account_under_30_days')) return false
    if (filters.hideSuspiciousPrice && flags.includes('suspicious_price')) return false
    if (filters.hideDuplicatePhotos && flags.includes('duplicate_photo')) return false
    if (filters.hideScratchDent && flags.includes('scratch_dent_mentioned')) return false
    if (filters.hideLongOnMarket && flags.includes('long_on_market')) return false
    if (filters.hidePriceDrop && flags.includes('significant_price_drop')) return false
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

.search-category-select {
  padding: var(--space-3) var(--space-3);
  background: var(--color-surface-raised);
  border: 1.5px solid var(--color-border);
  border-radius: var(--radius-md);
  color: var(--color-text-muted);
  font-family: var(--font-body);
  font-size: 0.875rem;
  cursor: pointer;
  white-space: nowrap;
  flex-shrink: 0;
  max-width: 160px;
  transition: border-color 150ms ease, color 150ms ease;
}
.search-category-select--active {
  border-color: var(--app-primary);
  color: var(--color-text);
  font-weight: 500;
}
.search-category-select:focus {
  outline: none;
  border-color: var(--app-primary);
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

.cancel-btn {
  padding: var(--space-3) var(--space-4);
  background: transparent;
  border: 1.5px solid var(--color-error);
  border-radius: var(--radius-md);
  color: var(--color-error);
  font-family: var(--font-body);
  font-size: 0.875rem;
  font-weight: 600;
  cursor: pointer;
  white-space: nowrap;
  flex-shrink: 0;
  transition: background 150ms ease;
}
.cancel-btn:hover { background: rgba(248, 81, 73, 0.1); }

.save-bookmark-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: var(--space-3);
  background: var(--color-surface-raised);
  border: 1.5px solid var(--color-border);
  border-radius: var(--radius-md);
  color: var(--color-text-muted);
  cursor: pointer;
  transition: border-color 150ms ease, color 150ms ease;
  flex-shrink: 0;
}
.save-bookmark-btn:hover:not(:disabled) {
  border-color: var(--app-primary);
  color: var(--app-primary);
}
.save-bookmark-btn:disabled { opacity: 0.4; cursor: not-allowed; }

.save-inline-form {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-2) 0 0;
  max-width: 760px;
}

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

/* Section headings that separate eBay Search params from local filters */
.filter-section-heading {
  font-size: 0.6875rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  padding: var(--space-1) var(--space-2);
  border-radius: var(--radius-sm);
  margin-top: var(--space-1);
}
.filter-section-heading--search {
  color: var(--app-primary);
  background: color-mix(in srgb, var(--app-primary) 10%, transparent);
}
.filter-section-heading--filter {
  color: var(--color-text-muted);
  background: color-mix(in srgb, var(--color-text-muted) 8%, transparent);
}

.filter-section-hint {
  font-size: 0.6875rem;
  color: var(--color-text-muted);
  opacity: 0.75;
  margin-top: calc(-1 * var(--space-2));
}

.filter-section-divider {
  height: 1px;
  background: var(--color-border);
  margin: var(--space-2) 0;
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

.filter-input--keyword {
  font-family: var(--font-mono);
  font-size: 0.75rem;
}

.adapter-badge {
  display: inline-block;
  margin-left: var(--space-2);
  padding: 1px var(--space-2);
  border-radius: var(--radius-sm);
  font-size: 0.625rem;
  font-weight: 700;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  vertical-align: middle;
}
.adapter-badge--api     { background: color-mix(in srgb, var(--app-primary) 15%, transparent); color: var(--app-primary); }
.adapter-badge--scraper { background: color-mix(in srgb, var(--color-warning) 15%, transparent); color: var(--color-warning); }

.filter-category-select {
  cursor: pointer;
  appearance: auto;
}

.filter-input--exclude {
  border-color: color-mix(in srgb, var(--color-error) 40%, var(--color-border));
}

.filter-input--exclude:focus {
  outline: none;
  border-color: var(--color-error);
}

/* Mode toggle row — same pill style as pages buttons */
.filter-mode-row {
  display: flex;
  gap: var(--space-1);
}

/* Collapsible condition picker */
.filter-collapsible {
  border: none;
  padding: 0;
  margin: 0;
}

.filter-collapsible-summary {
  font-size: 0.8125rem;
  font-weight: 600;
  color: var(--color-text-muted);
  cursor: pointer;
  list-style: none;
  display: flex;
  align-items: center;
  gap: var(--space-2);
  user-select: none;
}

.filter-collapsible-summary::after {
  content: '›';
  font-size: 1rem;
  line-height: 1;
  transition: transform 150ms ease;
}

.filter-collapsible[open] .filter-collapsible-summary::after {
  transform: rotate(90deg);
}

.filter-collapsible-summary::-webkit-details-marker { display: none; }

.filter-collapsible-body {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  padding-top: var(--space-2);
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

.filter-pages-btn--locked,
.filter-pages-btn:disabled {
  opacity: 0.35;
  cursor: not-allowed;
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

.toolbar-actions {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  flex-wrap: wrap;
}

.save-btn {
  display: flex;
  align-items: center;
  gap: var(--space-1);
  padding: var(--space-2) var(--space-3);
  background: transparent;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  color: var(--color-text-muted);
  font-family: var(--font-body);
  font-size: 0.8125rem;
  cursor: pointer;
  transition: border-color 150ms ease, color 150ms ease;
}
.save-btn:hover { border-color: var(--app-primary); color: var(--app-primary); }
.save-btn-icon { width: 0.9rem; height: 0.9rem; }

.save-form {
  display: flex;
  align-items: center;
  gap: var(--space-1);
}
.save-name-input {
  padding: var(--space-1) var(--space-2);
  background: var(--color-surface-raised);
  border: 1px solid var(--app-primary);
  border-radius: var(--radius-sm);
  color: var(--color-text);
  font-family: var(--font-body);
  font-size: 0.8125rem;
  width: 160px;
}
.save-name-input:focus { outline: none; }
.save-confirm-btn {
  padding: var(--space-1) var(--space-3);
  background: var(--app-primary);
  border: none;
  border-radius: var(--radius-sm);
  color: var(--color-text-inverse);
  font-size: 0.8125rem;
  font-weight: 600;
  cursor: pointer;
}
.save-cancel-btn {
  padding: var(--space-1) var(--space-2);
  background: transparent;
  border: none;
  color: var(--color-text-muted);
  font-size: 0.875rem;
  cursor: pointer;
  line-height: 1;
}
.save-success {
  font-size: 0.8125rem;
  color: var(--color-success);
  font-weight: 600;
}
.save-error {
  font-size: 0.75rem;
  color: var(--color-error);
  margin: 0;
}

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

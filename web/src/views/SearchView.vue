<template>
  <div class="search-view">
    <!-- Search bar -->
    <header class="search-header">
      <div class="platform-tabs" role="tablist" aria-label="Search platform">
        <button
          v-for="p in PLATFORMS"
          :key="p.value"
          type="button"
          role="tab"
          class="platform-tab"
          :class="{
            'platform-tab--active': filters.platform === p.value,
            'platform-tab--soon': !p.available,
          }"
          :aria-selected="filters.platform === p.value"
          :disabled="!p.available"
          :title="p.available ? p.label : `${p.label} — coming soon`"
          @click="p.available && (filters.platform = p.value)"
        >
          {{ p.label }}
          <span v-if="!p.available" class="platform-tab__soon">soon</span>
        </button>
      </div>
      <form class="search-form" @submit.prevent="onSearch" role="search">
        <div class="search-form-row1">
          <template v-if="filters.platform === 'ebay' || !filters.platform">
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
          </template>
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
        </div>
        <div class="search-form-row2">
          <button type="submit" class="search-btn" :disabled="store.loading || !queryInput.trim()">
            <MagnifyingGlassIcon class="search-btn-icon" aria-hidden="true" />
            <span>{{ store.loading ? 'Searching…' : 'Search' }}</span>
          </button>
          <button
            v-if="store.loading"
            type="button"
            class="cancel-btn"
            aria-label="Cancel search"
            @click="store.cancelSearch()"
          >✕ Cancel</button>
          <a
            v-else-if="session.isCloud && !session.isLoggedIn"
            href="https://circuitforge.tech/login"
            class="save-bookmark-btn"
            aria-label="Sign in to save searches"
          >
            <BookmarkIcon class="search-btn-icon" aria-hidden="true" />
          </a>
          <button
            v-else
            type="button"
            class="save-bookmark-btn"
            :disabled="!queryInput.trim()"
            :aria-label="showSaveForm ? 'Cancel saving search' : 'Save this search'"
            :aria-pressed="showSaveForm"
            @click="showSaveForm = !showSaveForm; if (showSaveForm) saveName = queryInput.trim()"
          >
            <BookmarkIcon class="search-btn-icon" aria-hidden="true" />
          </button>
        </div>
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
        <button type="button" class="save-cancel-btn" aria-label="Cancel save" @click="showSaveForm = false">✕</button>
        <span v-if="saveSuccess" class="save-success">Saved!</span>
        <span v-if="saveError" class="save-error">{{ saveError }}</span>
      </form>
    </header>

    <!-- LLM query builder panel — only shown when feature flag is active -->
    <LLMQueryPanel v-if="session.features.llm_query_builder" />

    <div class="search-body">
      <!-- Mobile filter toggle -->
      <button
        type="button"
        class="filter-drawer-toggle"
        :class="{ 'filter-drawer-toggle--active': showFilters }"
        aria-controls="filter-sidebar"
        :aria-expanded="showFilters"
        @click="showFilters = !showFilters"
      >
        ⚙ Filters<span v-if="activeFilterCount > 0" class="filter-badge">{{ activeFilterCount }}</span>
      </button>

      <!-- Filter sidebar / drawer -->
      <aside
        id="filter-sidebar"
        class="filter-sidebar"
        :class="{ 'filter-sidebar--open': showFilters }"
        aria-label="Search filters"
      >

        <!-- Clear all filters — only shown when at least one filter is active -->
        <button
          v-if="activeFilterCount > 0"
          type="button"
          class="filter-clear-btn"
          @click="resetFilters"
          aria-label="Clear all filters"
        >
          ✕ Clear filters ({{ activeFilterCount }})
        </button>

        <!-- ── eBay Search Parameters ─────────────────────────────────────── -->
        <!-- These are sent to eBay. Changes require a new search to take effect. -->
        <template v-if="filters.platform === 'ebay' || !filters.platform">
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
              :aria-pressed="filters.adapter === m.value"
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
              :aria-pressed="filters.pages === p"
              :aria-label="p > session.features.max_pages ? `${p} pages — upgrade required` : `${p} page${p > 1 ? 's' : ''}`"
              @click="p <= session.features.max_pages && (filters.pages = p)"
            >{{ p }}</button>
          </div>
          <p class="filter-pages-hint">{{ pagesHint }}</p>
        </fieldset>

        <fieldset class="filter-group">
          <legend class="filter-label">Price range</legend>
          <div class="filter-row">
            <label class="sr-only" for="f-min-price">Minimum price</label>
            <input id="f-min-price" v-model.number="filters.minPrice" type="number" min="0" class="filter-input" placeholder="Min $" aria-label="Minimum price in dollars" />
            <label class="sr-only" for="f-max-price">Maximum price</label>
            <input id="f-max-price" v-model.number="filters.maxPrice" type="number" min="0" class="filter-input" placeholder="Max $" aria-label="Maximum price in dollars" />
          </div>
          <p class="filter-pages-hint">Forwarded to eBay API</p>
        </fieldset>

        <fieldset class="filter-group">
          <legend class="filter-label">Keywords</legend>
          <div class="filter-row">
            <label class="filter-label-sm" for="f-include">Must include</label>
            <div class="filter-mode-row" role="group" aria-label="Keyword match mode">
              <button
                v-for="m in INCLUDE_MODES"
                :key="m.value"
                type="button"
                class="filter-pages-btn"
                :class="{ 'filter-pages-btn--active': filters.mustIncludeMode === m.value }"
                :aria-pressed="filters.mustIncludeMode === m.value"
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
        </template>

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
            aria-label="Minimum trust score"
            aria-valuemin="0"
            aria-valuemax="100"
            :aria-valuenow="filters.minTrustScore"
            :aria-valuetext="`${filters.minTrustScore ?? 0} out of 100`"
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

        <!-- Landing hero (before first search) -->
        <div v-else-if="!store.results.length && !store.loading && !store.query" class="landing-hero">
          <div class="landing-hero__eyebrow" aria-hidden="true">🎯 Snipe</div>
          <h1 class="landing-hero__headline">Bid with confidence.</h1>
          <p class="landing-hero__sub">
            Seen a listing that looks almost too good to pass up? Snipe tells you if it's safe
            to bid: seller account age, feedback history, price vs. completed sales, and red flag
            detection — one trust score before you commit. Free. No account required.
          </p>

          <!-- Timely callout: eBay cancellation policy change -->
          <div v-if="showEbayCallout" class="landing-hero__callout" role="note">
            <span class="landing-hero__callout-icon" aria-hidden="true">⚠</span>
            <p>
              <strong>Starting May 13, 2026, eBay removes the option for buyers to cancel winning bids.</strong>
              Auction sales become final. Search above to score listings before you commit.
            </p>
          </div>

          <!-- Signal tiles -->
          <div class="landing-hero__tiles" role="list">
            <div class="landing-hero__tile" role="listitem">
              <span class="landing-hero__tile-icon" aria-hidden="true">🛡</span>
              <strong class="landing-hero__tile-title">Seller trust score</strong>
              <p class="landing-hero__tile-desc">Account age, feedback count and ratio, and category history — does this seller actually know what they're selling? Scored 0–100.</p>
            </div>
            <div class="landing-hero__tile" role="listitem">
              <span class="landing-hero__tile-icon" aria-hidden="true">📊</span>
              <strong class="landing-hero__tile-title">Price vs. market</strong>
              <p class="landing-hero__tile-desc">Checked against recent completed eBay sales. If the price is 40% below median, you'll see it flagged before you bid.</p>
            </div>
            <div class="landing-hero__tile" role="listitem">
              <span class="landing-hero__tile-icon" aria-hidden="true">🚩</span>
              <strong class="landing-hero__tile-title">Red flag detection</strong>
              <p class="landing-hero__tile-desc">Duplicate listing photos, "scratch and dent" buried in the description, zero-feedback sellers, and known bad actors — flagged automatically.</p>
            </div>
          </div>

          <!-- Sign-in unlock strip (cloud, unauthenticated only) -->
          <div v-if="session.isCloud && !session.isLoggedIn" class="landing-hero__signin-strip">
            <p class="landing-hero__signin-text">
              Free account unlocks saved searches, up to 5 pages of results, and the community-maintained scammer blocklist.
            </p>
            <a href="https://circuitforge.tech/login" class="landing-hero__signin-cta">
              Create a free account →
            </a>
          </div>
        </div>

        <!-- Loading (scraping in progress, no results yet) -->
        <SearchProgress v-else-if="store.loading && !store.results.length" :query="store.query" :platform="filters.platform ?? 'ebay'" />

        <!-- No results -->
        <div v-else-if="!store.results.length && !store.loading && store.query" class="results-empty">
          <p>No listings found for <strong>{{ store.query }}</strong>.</p>
          <p class="results-empty__hint">Try a broader search term, or check spelling.</p>
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
              <span v-if="store.affiliateActive" class="affiliate-disclosure">
                · Links may include an affiliate code
              </span>
            </p>
            <div class="toolbar-actions">
              <!-- Re-search indicator — loading while stale results are still visible -->
              <span v-if="store.loading && store.results.length" class="enriching-badge enriching-badge--searching" aria-live="polite" title="Fetching new results…">
                <span class="enriching-dot" aria-hidden="true"></span>
                Re-searching…
              </span>
              <!-- Live enrichment indicator — visible while SSE stream is open -->
              <span v-else-if="store.enriching" class="enriching-badge" aria-live="polite" title="Scores updating as seller data arrives">
                <span class="enriching-dot" aria-hidden="true"></span>
                Updating scores…
              </span>
              <label for="sort-select" class="sr-only">Sort by</label>
              <select id="sort-select" v-model="sortBy" class="sort-select">
                <option v-for="opt in SORT_OPTIONS" :key="opt.value" :value="opt.value">
                  {{ opt.label }}
                </option>
              </select>
            </div>
          </div>

          <!-- Guest prompt — sign-in CTA for gated bulk actions -->
          <Transition name="bulk-bar">
            <div v-if="guestPrompt" class="guest-prompt" role="alert">
              <span>{{ guestPrompt }}</span>
              <a href="https://circuitforge.tech/login" class="guest-prompt__link">Sign in free →</a>
              <button class="guest-prompt__dismiss" @click="guestPrompt = null" aria-label="Dismiss">✕</button>
            </div>
          </Transition>

          <!-- Bulk action bar — appears when any cards are selected -->
          <Transition name="bulk-bar">
            <div v-if="selectMode" class="bulk-bar" role="toolbar" aria-label="Bulk actions">
              <span class="bulk-bar__count">{{ selectedIds.size }} selected</span>
              <button class="bulk-bar__btn bulk-bar__btn--ghost" @click="selectAll">Select all</button>
              <button class="bulk-bar__btn bulk-bar__btn--ghost" @click="clearSelection">Deselect</button>
              <div class="bulk-bar__sep" role="separator" />
              <button
                class="bulk-bar__btn bulk-bar__btn--danger"
                :disabled="bulkBlocking"
                @click="blockSelected"
                :title="session.isLoggedIn ? 'Block all selected sellers' : 'Sign in to block sellers'"
              >
                {{ bulkBlocking ? `Blocking… (${bulkBlockDone})` : session.isLoggedIn ? '⚑ Block sellers' : '⚑ Sign in to block' }}
              </button>
              <button
                class="bulk-bar__btn bulk-bar__btn--report"
                @click="reportSelected"
                title="Report selected sellers to eBay"
              >
                ⚐ Report to eBay
              </button>
            </div>
          </Transition>

          <!-- Cards -->
          <div class="results-list">
            <ListingCard
              v-for="listing in visibleListings"
              :key="`${listing.platform}-${listing.platform_listing_id}`"
              :listing="listing"
              :trust="store.trustScores.get(listing.platform_listing_id) ?? null"
              :seller="store.sellers.get(listing.seller_platform_id) ?? null"
              :market-price="store.marketPrice"
              :selected="selectedIds.has(listing.platform_listing_id)"
              :select-mode="selectMode"
              :seller-reported="reported.isReported(listing.seller_platform_id)"
              @toggle="toggleSelect(listing.platform_listing_id)"
            />
          </div>
        </template>
      </section>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, reactive, watch, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { MagnifyingGlassIcon, ExclamationTriangleIcon, BookmarkIcon } from '@heroicons/vue/24/outline'
import { useSearchStore } from '../stores/search'
import type { Listing, TrustScore, SearchFilters, MustIncludeMode } from '../stores/search'
import { useSavedSearchesStore } from '../stores/savedSearches'
import { useSessionStore } from '../stores/session'
import { useBlocklistStore } from '../stores/blocklist'
import { useReportedStore } from '../stores/reported'
import ListingCard from '../components/ListingCard.vue'
import LLMQueryPanel from '../components/LLMQueryPanel.vue'
import SearchProgress from '../components/SearchProgress.vue'

const route = useRoute()
const store = useSearchStore()
const savedStore = useSavedSearchesStore()
const session = useSessionStore()
const blocklist = useBlocklistStore()
const reported = useReportedStore()
const queryInput = ref('')

// ── Multi-select + bulk actions ───────────────────────────────────────────────
const selectedIds = ref<Set<string>>(new Set())
const selectMode = computed(() => selectedIds.value.size > 0)

function toggleSelect(platformListingId: string) {
  const next = new Set(selectedIds.value)
  if (next.has(platformListingId)) {
    next.delete(platformListingId)
  } else {
    next.add(platformListingId)
  }
  selectedIds.value = next
}

function selectAll() {
  selectedIds.value = new Set(visibleListings.value.map(l => l.platform_listing_id))
}

function clearSelection() {
  selectedIds.value = new Set()
}

const bulkBlocking = ref(false)
const bulkBlockDone = ref(0)
const guestPrompt = ref<string | null>(null)  // sign-in CTA message for guest/anon

async function blockSelected() {
  if (!session.isLoggedIn) {
    guestPrompt.value = 'Sign in to add sellers to the community blocklist.'
    return
  }
  guestPrompt.value = null
  bulkBlocking.value = true
  bulkBlockDone.value = 0
  const toBlock = visibleListings.value.filter(l => selectedIds.value.has(l.platform_listing_id))
  const uniqueSellers = new Map<string, string>() // seller_id → username
  for (const l of toBlock) {
    if (l.seller_platform_id && !uniqueSellers.has(l.seller_platform_id)) {
      const seller = store.sellers.get(l.seller_platform_id)
      uniqueSellers.set(l.seller_platform_id, seller?.username ?? l.seller_platform_id)
    }
  }
  for (const [sellerId, username] of uniqueSellers) {
    if (!blocklist.isBlocklisted(sellerId)) {
      try {
        await blocklist.addSeller(sellerId, username, 'Bulk block from search results')
        bulkBlockDone.value++
      } catch { /* continue */ }
    }
  }
  bulkBlocking.value = false
  clearSelection()
}

function reportSelected() {
  const toReport = visibleListings.value.filter(l => selectedIds.value.has(l.platform_listing_id))
  // De-duplicate by seller — one report per seller covers all their listings
  const reportedEntries: Array<{ platform_seller_id: string; username: string | null }> = []
  const seenSellers = new Set<string>()
  for (const l of toReport) {
    if (l.seller_platform_id && !seenSellers.has(l.seller_platform_id)) {
      seenSellers.add(l.seller_platform_id)
      const seller = store.sellers.get(l.seller_platform_id)
      const username = seller?.username ?? l.seller_platform_id
      window.open(
        `https://contact.ebay.com/ws/eBayISAPI.dll?ReportUser&userid=${encodeURIComponent(username)}`,
        '_blank',
        'noopener,noreferrer',
      )
      reportedEntries.push({ platform_seller_id: l.seller_platform_id, username: seller?.username ?? null })
    }
  }
  if (reportedEntries.length) {
    reported.markReported(reportedEntries)
  }
  clearSelection()
}

// Save search UI state
const showSaveForm = ref(false)
const showFilters = ref(false)
const saveName = ref('')
const saveError = ref<string | null>(null)
const saveSuccess = ref(false)

// Show the eBay cancellation policy callout until the policy takes effect
const showEbayCallout = computed(() => new Date() < new Date('2026-05-13T00:00:00'))

// Count active non-default filters for the mobile badge
const activeFilterCount = computed(() => {
  let n = 0
  if (filters.categoryId) n++
  if (filters.minPrice !== null && filters.minPrice > 0) n++
  if (filters.maxPrice !== null && filters.maxPrice > 0) n++
  if (filters.minTrust > 0) n++
  if (filters.hideRedFlags) n++
  if (filters.hidePartial) n++
  if (filters.hideLongOnMarket) n++
  if (filters.hidePriceDrop) n++
  if (filters.mustInclude) n++
  if (filters.mustExclude) n++
  if (filters.pages > 1) n++
  return n
})

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
    const f = route.query.filters
    if (typeof f === 'string') {
      try {
        const restored = JSON.parse(f) as Partial<SearchFilters>
        Object.assign(filters, restored)
      } catch { /* malformed — ignore */ }
    }
    if (route.query.autorun === '1') {
      // Strip the autorun flag from the URL before searching
      router.replace({ query: { ...route.query, autorun: undefined } })
      onSearch()
    }
    // Otherwise: URL params just restore the form (e.g. on page refresh).
    // Results are restored from sessionStorage by the search store.
  }
})

// ── Filters ──────────────────────────────────────────────────────────────────

const DEFAULT_FILTERS: SearchFilters = {
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
  platform: 'ebay',
}

const filters = reactive<SearchFilters>({ ...DEFAULT_FILTERS })

// Sync LLM-populated store state into the sidebar reactive and search bar.
// One-way only: store → view. User edits in the sidebar stay local.
watch(
  () => store.filters,
  (newFilters) => { Object.assign(filters, newFilters) },
  { deep: true },
)
watch(
  () => store.query,
  (q) => { if (q) queryInput.value = q },
)

function resetFilters() {
  Object.assign(filters, DEFAULT_FILTERS)
}

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

const PLATFORMS: { value: string; label: string; available: boolean }[] = [
  { value: 'ebay',     label: 'eBay',     available: true },
  { value: 'mercari',  label: 'Mercari',  available: true },
  { value: 'poshmark', label: 'Poshmark', available: false },
]

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
  showFilters.value = false   // close drawer on mobile when search runs
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
.search-btn:focus-visible { outline: 2px solid var(--app-primary); outline-offset: 2px; }
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
.cancel-btn:hover { background: color-mix(in srgb, var(--color-error) 10%, transparent); }
.cancel-btn:focus-visible { outline: 2px solid var(--color-error); outline-offset: 2px; }

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

/* Clear all filters button */
.filter-clear-btn {
  display: flex;
  align-items: center;
  gap: var(--space-1);
  width: 100%;
  padding: var(--space-1) var(--space-2);
  margin-bottom: var(--space-2);
  background: color-mix(in srgb, var(--color-red, #ef4444) 12%, transparent);
  color: var(--color-red, #ef4444);
  border: 1px solid color-mix(in srgb, var(--color-red, #ef4444) 30%, transparent);
  border-radius: var(--radius-sm);
  font-size: 0.75rem;
  font-weight: 600;
  cursor: pointer;
  transition: background 0.15s, color 0.15s;
}
.filter-clear-btn:hover {
  background: color-mix(in srgb, var(--color-red, #ef4444) 22%, transparent);
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

.filter-pages-btn:focus-visible {
  outline: 2px solid var(--app-primary);
  outline-offset: 2px;
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
  background: color-mix(in srgb, var(--color-error) 10%, transparent);
  border: 1px solid color-mix(in srgb, var(--color-error) 30%, transparent);
  border-radius: var(--radius-md);
  color: var(--color-error);
  font-size: 0.9375rem;
}

.results-error-icon { width: 1.25rem; height: 1.25rem; flex-shrink: 0; }

/* ── Landing hero ────────────────────────────────────────────────────── */
.landing-hero {
  max-width: 760px;
  margin: var(--space-12) auto;
  padding: 0 var(--space-4);
  display: flex;
  flex-direction: column;
  gap: var(--space-6);
}

.landing-hero__eyebrow {
  font-family: var(--font-mono);
  font-size: 0.8125rem;
  color: var(--app-primary);
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.landing-hero__headline {
  font-family: var(--font-display);
  font-size: clamp(2rem, 5vw, 3rem);
  font-weight: 700;
  line-height: 1.15;
  color: var(--color-text);
  margin: 0;
}

.landing-hero__sub {
  font-size: 1.0625rem;
  line-height: 1.65;
  color: var(--color-text-muted);
  max-width: 600px;
  margin: 0;
}

.landing-hero__callout {
  display: flex;
  gap: var(--space-3);
  align-items: flex-start;
  background: color-mix(in srgb, var(--color-error) 8%, transparent);
  border: 1px solid color-mix(in srgb, var(--color-error) 35%, transparent);
  border-radius: var(--radius-lg);
  padding: var(--space-4) var(--space-5);
  font-size: 0.9375rem;
  line-height: 1.55;
  color: var(--color-text);
}

.landing-hero__callout-icon {
  font-size: 1.1rem;
  flex-shrink: 0;
  margin-top: 2px;
}

.landing-hero__callout p { margin: 0; }

.landing-hero__tiles {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: var(--space-4);
  margin-top: var(--space-2);
}

.landing-hero__tile {
  background: var(--color-surface-2);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  padding: var(--space-5);
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.landing-hero__tile-icon { font-size: 1.5rem; line-height: 1; }

.landing-hero__tile-title {
  font-size: 0.9375rem;
  font-weight: 600;
  color: var(--color-text);
}

.landing-hero__tile-desc {
  font-size: 0.8125rem;
  line-height: 1.55;
  color: var(--color-text-muted);
  margin: 0;
}

.landing-hero__signin-strip {
  display: flex;
  align-items: center;
  justify-content: center;
  flex-wrap: wrap;
  gap: var(--space-3) var(--space-6);
  margin-top: var(--space-8);
  padding: var(--space-4) var(--space-6);
  background: color-mix(in srgb, var(--app-primary) 8%, transparent);
  border: 1px solid color-mix(in srgb, var(--app-primary) 20%, transparent);
  border-radius: var(--radius-md);
}

.landing-hero__signin-text {
  margin: 0;
  font-size: 0.875rem;
  color: var(--color-text-muted);
}

.landing-hero__signin-cta {
  font-size: 0.875rem;
  font-weight: 600;
  color: var(--app-primary);
  text-decoration: none;
  white-space: nowrap;
}

.landing-hero__signin-cta:hover {
  text-decoration: underline;
}

@media (max-width: 720px) {
  .landing-hero { margin: var(--space-8) auto; }
  .landing-hero__tiles { grid-template-columns: 1fr; }
  .landing-hero__signin-strip { flex-direction: column; text-align: center; }
}

@media (max-width: 480px) {
  .landing-hero__headline { font-size: 1.75rem; }
}

/* ── Results empty (post-search, no matches) ─────────────────────────── */
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

.results-empty__hint {
  font-size: 0.875rem;
  margin: 0;
  color: var(--color-text-muted);
}

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
.affiliate-disclosure { color: var(--color-text-muted, #8b949e); font-size: 0.8em; }

.toolbar-actions {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  flex-wrap: wrap;
}

.enriching-badge {
  display: inline-flex;
  align-items: center;
  gap: var(--space-1);
  padding: var(--space-1) var(--space-2);
  background: color-mix(in srgb, var(--app-primary) 10%, transparent);
  border: 1px solid color-mix(in srgb, var(--app-primary) 30%, transparent);
  border-radius: var(--radius-full, 9999px);
  color: var(--app-primary);
  font-size: 0.75rem;
  font-weight: 500;
  white-space: nowrap;
}

.enriching-badge--searching {
  background: color-mix(in srgb, var(--color-info) 10%, transparent);
  border-color: color-mix(in srgb, var(--color-info) 30%, transparent);
  color: var(--color-info);
}

.enriching-badge--searching .enriching-dot {
  background: var(--color-info);
}

.enriching-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--app-primary);
  animation: enriching-pulse 1.2s ease-in-out infinite;
}

@keyframes enriching-pulse {
  0%, 100% { opacity: 1; transform: scale(1); }
  50%       { opacity: 0.4; transform: scale(0.7); }
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

/* ── Bulk action bar ────────────────────────────────────────────────────── */
.bulk-bar {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  flex-wrap: wrap;
  padding: var(--space-2) var(--space-3);
  background: color-mix(in srgb, var(--app-primary) 10%, var(--color-surface-2));
  border: 1px solid color-mix(in srgb, var(--app-primary) 30%, transparent);
  border-radius: var(--radius-md);
}

.bulk-bar__count {
  font-size: 0.8125rem;
  font-weight: 600;
  color: var(--app-primary);
  margin-right: var(--space-1);
}

.bulk-bar__sep {
  width: 1px;
  height: 18px;
  background: var(--color-border);
  margin: 0 var(--space-1);
}

.bulk-bar__btn {
  padding: 4px var(--space-3);
  border-radius: var(--radius-sm);
  font-size: 0.8125rem;
  font-weight: 500;
  cursor: pointer;
  font-family: var(--font-body);
  transition: background 120ms ease, color 120ms ease, opacity 120ms ease;
}
.bulk-bar__btn:disabled { opacity: 0.5; cursor: not-allowed; }

.bulk-bar__btn--ghost {
  background: transparent;
  border: 1px solid var(--color-border);
  color: var(--color-text-muted);
}
.bulk-bar__btn--ghost:hover:not(:disabled) {
  background: var(--color-surface-raised);
  color: var(--color-text);
}

.bulk-bar__btn--danger {
  background: transparent;
  border: 1px solid var(--color-error);
  color: var(--color-error);
}
.bulk-bar__btn--danger:hover:not(:disabled) {
  background: color-mix(in srgb, var(--color-error) 12%, transparent);
}

.bulk-bar__btn--report {
  background: transparent;
  border: 1px solid var(--color-text-muted);
  color: var(--color-text-muted);
}
.bulk-bar__btn--report:hover:not(:disabled) {
  background: var(--color-surface-raised);
  color: var(--color-text);
  border-color: var(--color-text);
}

/* Slide-in transition (shared by bulk-bar and guest-prompt) */
.bulk-bar-enter-active, .bulk-bar-leave-active { transition: opacity 0.18s ease, transform 0.18s ease; }
.bulk-bar-enter-from, .bulk-bar-leave-to { opacity: 0; transform: translateY(-6px); }

/* Guest sign-in prompt */
.guest-prompt {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-2) var(--space-4);
  background: color-mix(in srgb, var(--app-primary) 12%, var(--color-surface-2));
  border: 1px solid color-mix(in srgb, var(--app-primary) 30%, transparent);
  border-radius: var(--radius-md);
  font-size: 0.875rem;
  color: var(--color-text);
  margin-bottom: var(--space-2);
}
.guest-prompt__link {
  color: var(--app-primary);
  font-weight: 600;
  text-decoration: none;
  white-space: nowrap;
}
.guest-prompt__link:hover { text-decoration: underline; }
.guest-prompt__dismiss {
  margin-left: auto;
  background: none;
  border: none;
  color: var(--color-text-muted);
  cursor: pointer;
  font-size: 0.75rem;
  padding: 0 var(--space-1);
}

.results-list {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

/* ── Search form rows (desktop: single flex row, mobile: two rows) ───── */
.search-form {
  display: flex;
  gap: var(--space-3);
  max-width: 760px;
  flex-wrap: wrap;   /* rows fall through naturally on mobile */
}
.search-form-row1 {
  display: flex;
  gap: var(--space-3);
  flex: 1;
  min-width: 0;
}
.search-form-row2 {
  display: flex;
  gap: var(--space-2);
  flex-shrink: 0;
}

/* ── Mobile filter drawer toggle (hidden on desktop) ─────────────────── */
.filter-drawer-toggle {
  display: none;
}

.filter-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 16px;
  height: 16px;
  padding: 0 4px;
  margin-left: var(--space-1);
  background: var(--app-primary);
  color: var(--color-text-inverse);
  border-radius: var(--radius-full);
  font-size: 0.625rem;
  font-weight: 700;
  line-height: 1;
}

/* ── Responsive breakpoints ──────────────────────────────────────────── */
@media (max-width: 767px) {
  /* Search header: tighter padding on mobile */
  .search-header {
    padding: var(--space-3) var(--space-3) var(--space-3);
  }

  /* Form rows: row1 takes full width, row2 stretches buttons */
  .search-form {
    gap: var(--space-2);
  }
  .search-form-row1 {
    width: 100%;
    flex: unset;
  }
  .search-form-row2 {
    width: 100%;
    flex-shrink: unset;
  }
  .search-btn {
    flex: 1;   /* stretch search button to fill row */
  }

  /* Category select: don't let it crowd the input */
  .search-category-select {
    max-width: 110px;
    font-size: 0.8125rem;
  }

  /* Filter drawer toggle: show on mobile */
  .filter-drawer-toggle {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    padding: var(--space-2) var(--space-3);
    margin: var(--space-2) var(--space-3);
    background: var(--color-surface-raised);
    border: 1px solid var(--color-border);
    border-radius: var(--radius-md);
    color: var(--color-text-muted);
    font-family: var(--font-body);
    font-size: 0.875rem;
    cursor: pointer;
    width: calc(100% - var(--space-6));
    transition: border-color 150ms ease, color 150ms ease;
    align-self: flex-start;
  }
  .filter-drawer-toggle--active {
    border-color: var(--app-primary);
    color: var(--app-primary);
  }

  /* Filter sidebar: hidden by default, slides down when open */
  .filter-sidebar {
    display: none;
    width: 100%;
    max-height: 65dvh;
    overflow-y: auto;
    border-right: none;
    border-bottom: 1px solid var(--color-border);
    padding: var(--space-4) var(--space-4) var(--space-6);
    background: var(--color-surface-2);
    animation: drawer-slide-down 180ms ease;
  }
  .filter-sidebar--open {
    display: flex;
  }

  /* Search body: stack vertically (toggle → sidebar → results) */
  .search-body {
    flex-direction: column;
  }

  /* Results: full-width, slightly tighter padding */
  .results-area {
    padding: var(--space-4) var(--space-3);
    overflow-y: unset;   /* let the page scroll on mobile, not a sub-scroll container */
  }

  /* Toolbar: wrap if needed */
  .results-toolbar {
    flex-wrap: wrap;
    gap: var(--space-2);
  }
  .toolbar-actions {
    flex-wrap: wrap;
  }

  /* Save inline form: full width */
  .save-inline-form {
    flex-wrap: wrap;
  }
  .save-name-input {
    width: 100%;
  }
}

@keyframes drawer-slide-down {
  from { opacity: 0; transform: translateY(-8px); }
  to   { opacity: 1; transform: translateY(0); }
}

/* ── Platform tab strip ──────────────────────────────────────────────── */
.platform-tabs {
  display: flex;
  gap: var(--space-1);
  margin-bottom: var(--space-3);
}

.platform-tab {
  display: inline-flex;
  align-items: center;
  gap: var(--space-1);
  padding: var(--space-1) var(--space-3);
  background: transparent;
  border: 1.5px solid var(--color-border);
  border-radius: var(--radius-full);
  color: var(--color-text-muted);
  font-family: var(--font-body);
  font-size: 0.8125rem;
  font-weight: 500;
  cursor: pointer;
  transition: border-color 150ms ease, color 150ms ease, background 150ms ease;
  white-space: nowrap;
}

.platform-tab:hover:not(:disabled):not(.platform-tab--active) {
  border-color: var(--app-primary);
  color: var(--app-primary);
}

.platform-tab--active {
  background: var(--app-primary);
  border-color: var(--app-primary);
  color: var(--color-text-inverse);
  font-weight: 600;
}

.platform-tab--soon {
  opacity: 0.45;
  cursor: not-allowed;
}

.platform-tab__soon {
  font-size: 0.625rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  opacity: 0.8;
}

</style>

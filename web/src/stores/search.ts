import { defineStore } from 'pinia'
import { ref } from 'vue'

// ── Domain types (mirror app/db/models.py) ───────────────────────────────────

export interface Listing {
  id: number | null
  platform: string
  platform_listing_id: string
  title: string
  price: number
  currency: string
  condition: string
  seller_platform_id: string
  url: string
  photo_urls: string[]
  listing_age_days: number
  buying_format: 'fixed_price' | 'auction' | 'best_offer'
  ends_at: string | null
  fetched_at: string | null
  trust_score_id: number | null
}

export interface TrustScore {
  id: number | null
  listing_id: number
  composite_score: number         // 0–100
  account_age_score: number       // 0–20
  feedback_count_score: number    // 0–20
  feedback_ratio_score: number    // 0–20
  price_vs_market_score: number   // 0–20
  category_history_score: number  // 0–20
  photo_hash_duplicate: boolean
  photo_analysis_json: string | null
  red_flags_json: string          // JSON array of flag strings
  score_is_partial: boolean
  scored_at: string | null
}

export interface Seller {
  id: number | null
  platform: string
  platform_seller_id: string
  username: string
  account_age_days: number | null
  feedback_count: number
  feedback_ratio: number          // 0.0–1.0
  category_history_json: string
  fetched_at: string | null
}

export type MustIncludeMode = 'all' | 'any' | 'groups'

export interface SavedSearch {
  id: number
  name: string
  query: string
  platform: string
  filters_json: string   // JSON blob of SearchFilters subset
  created_at: string | null
  last_run_at: string | null
}

export interface SearchParamsResult {
  base_query: string
  must_include_mode: string
  must_include: string
  must_exclude: string
  max_price: number | null
  min_price: number | null
  condition: string[]
  category_id: string | null
  explanation: string
}

export interface SearchFilters {
  minTrustScore?: number
  minPrice?: number
  maxPrice?: number
  conditions?: string[]
  minAccountAgeDays?: number
  minFeedbackCount?: number
  minFeedbackRatio?: number
  hideNewAccounts?: boolean
  hideSuspiciousPrice?: boolean
  hideDuplicatePhotos?: boolean
  hideScratchDent?: boolean
  hideLongOnMarket?: boolean
  hidePriceDrop?: boolean
  pages?: number               // number of eBay result pages to fetch (48 listings/page, default 1)
  mustInclude?: string         // term string; client-side title filter; semantics set by mustIncludeMode
  mustIncludeMode?: MustIncludeMode  // 'all' = AND, 'any' = OR, 'groups' = CNF (pipe = OR within group)
  mustExclude?: string         // comma-separated; forwarded to eBay -term AND client-side
  categoryId?: string          // eBay category ID (e.g. "27386" = Graphics/Video Cards)
  adapter?: 'auto' | 'api' | 'scraper'  // override adapter selection
}

// ── Session cache ─────────────────────────────────────────────────────────────

const CACHE_KEY = 'snipe:search-cache'

function saveCache(data: {
  query: string
  results: Listing[]
  trustScores: Record<string, TrustScore>
  sellers: Record<string, Seller>
  marketPrice: number | null
  adapterUsed: 'api' | 'scraper' | null
}) {
  try { sessionStorage.setItem(CACHE_KEY, JSON.stringify(data)) } catch { /* quota */ }
}

function loadCache() {
  try {
    const raw = sessionStorage.getItem(CACHE_KEY)
    return raw ? JSON.parse(raw) : null
  } catch { return null }
}

// ── Store ────────────────────────────────────────────────────────────────────

export const useSearchStore = defineStore('search', () => {
  const cached = loadCache()

  const query = ref<string>(cached?.query ?? '')
  const results = ref<Listing[]>(cached?.results ?? [])
  const trustScores = ref<Map<string, TrustScore>>(
    cached ? new Map(Object.entries(cached.trustScores ?? {})) : new Map()
  )
  const sellers = ref<Map<string, Seller>>(
    cached ? new Map(Object.entries(cached.sellers ?? {})) : new Map()
  )
  const marketPrice = ref<number | null>(cached?.marketPrice ?? null)
  const adapterUsed = ref<'api' | 'scraper' | null>(cached?.adapterUsed ?? null)
  const filters = ref<SearchFilters>({})
  const affiliateActive = ref<boolean>(false)
  const loading = ref(false)
  const error = ref<string | null>(null)
  const enriching = ref(false)   // true while SSE stream is open

  let _abort: AbortController | null = null
  let _sse: EventSource | null = null

  function cancelSearch() {
    _abort?.abort()
    _abort = null
    loading.value = false
    closeUpdates()
  }

  async function search(q: string, filters: SearchFilters = {}) {
    // Cancel any in-flight search before starting a new one
    _abort?.abort()
    _abort = new AbortController()
    const signal = _abort.signal

    query.value = q
    loading.value = true
    error.value = null

    try {
      // VITE_API_BASE is '' in dev; '/snipe' under menagerie (baked at build time by Vite)
      const apiBase = (import.meta.env.VITE_API_BASE as string) ?? ''
      const params = new URLSearchParams({ q })
      // v-model.number sends empty string when a number input is cleared — guard against that
      const maxPrice = Number(filters.maxPrice)
      const minPrice = Number(filters.minPrice)
      if (Number.isFinite(maxPrice) && maxPrice > 0) params.set('max_price', String(maxPrice))
      if (Number.isFinite(minPrice) && minPrice > 0) params.set('min_price', String(minPrice))
      if (filters.pages != null && filters.pages > 1) params.set('pages', String(filters.pages))
      if (filters.mustInclude?.trim()) params.set('must_include', filters.mustInclude.trim())
      if (filters.mustIncludeMode) params.set('must_include_mode', filters.mustIncludeMode)
      if (filters.mustExclude?.trim()) params.set('must_exclude', filters.mustExclude.trim())
      if (filters.categoryId?.trim()) params.set('category_id', filters.categoryId.trim())
      if (filters.adapter && filters.adapter !== 'auto') params.set('adapter', filters.adapter)

      // Use the async endpoint: returns 202 immediately with a session_id, then
      // streams listings + trust scores via SSE as the scrape completes.
      const res = await fetch(`${apiBase}/api/search/async?${params}`, { signal })
      if (!res.ok) throw new Error(`Search failed: ${res.status} ${res.statusText}`)

      const data = await res.json() as {
        session_id: string
        status: 'queued'
      }

      // HTTP 202 received — scraping is underway in the background.
      // Stay in loading state until the first "listings" SSE event arrives.
      // loading.value stays true; enriching tracks the SSE stream being open.
      enriching.value = true
      _openUpdates(data.session_id, apiBase)
    } catch (e) {
      if (e instanceof DOMException && e.name === 'AbortError') {
        // User cancelled — clear loading but don't surface as an error
        results.value = []
        loading.value = false
      } else {
        error.value = e instanceof Error ? e.message : 'Unknown error'
        results.value = []
        loading.value = false
      }
      _abort = null
    }
    // Note: loading.value is NOT set to false here — it stays true until the
    // first "listings" SSE event arrives (see _openUpdates handler below).
  }

  function closeUpdates() {
    if (_sse) {
      _sse.close()
      _sse = null
    }
    enriching.value = false
  }

  // Internal type for typed SSE events from the async search endpoint
  type _AsyncListingsEvent = {
    type: 'listings'
    listings: Listing[]
    trust_scores: Record<string, TrustScore>
    sellers: Record<string, Seller>
    market_price: number | null
    adapter_used: 'api' | 'scraper'
    affiliate_active: boolean
    session_id: string
  }

  type _MarketPriceEvent = {
    type: 'market_price'
    market_price: number | null
  }

  type _UpdateEvent = {
    type: 'update'
    platform_listing_id: string
    trust_score: TrustScore
    seller: Seller
    market_price: number | null
  }

  type _LegacyUpdateEvent = {
    platform_listing_id: string
    trust_score: TrustScore
    seller: Record<string, unknown>
    market_price: number | null
  }

  type _SSEEvent =
    | _AsyncListingsEvent
    | _MarketPriceEvent
    | _UpdateEvent
    | _LegacyUpdateEvent

  function _openUpdates(sessionId: string, apiBase: string) {
    // Close any pre-existing stream but preserve enriching state — caller sets it.
    if (_sse) {
      _sse.close()
      _sse = null
    }

    const es = new EventSource(`${apiBase}/api/updates/${sessionId}`)
    _sse = es

    es.onmessage = (e) => {
      try {
        const update = JSON.parse(e.data) as _SSEEvent

        if ('type' in update) {
          // Typed events from the async search endpoint
          if (update.type === 'listings') {
            // First batch: hydrate store and transition out of loading state
            results.value = update.listings ?? []
            trustScores.value = new Map(Object.entries(update.trust_scores ?? {}))
            sellers.value = new Map(Object.entries(update.sellers ?? {}))
            marketPrice.value = update.market_price ?? null
            adapterUsed.value = update.adapter_used ?? null
            affiliateActive.value = update.affiliate_active ?? false
            saveCache({
              query: query.value,
              results: results.value,
              trustScores: update.trust_scores ?? {},
              sellers: update.sellers ?? {},
              marketPrice: marketPrice.value,
              adapterUsed: adapterUsed.value,
            })
            // Scrape complete — turn off the initial loading spinner.
            // enriching stays true while enrichment SSE is still open.
            loading.value = false
          } else if (update.type === 'market_price') {
            if (update.market_price != null) {
              marketPrice.value = update.market_price
            }
          } else if (update.type === 'update') {
            // Per-seller enrichment update (same as legacy format but typed)
            if (update.platform_listing_id && update.trust_score) {
              trustScores.value = new Map(trustScores.value)
              trustScores.value.set(update.platform_listing_id, update.trust_score)
            }
            if (update.seller?.platform_seller_id) {
              sellers.value = new Map(sellers.value)
              sellers.value.set(update.seller.platform_seller_id, update.seller)
            }
            if (update.market_price != null) {
              marketPrice.value = update.market_price
            }
          }
          // type: "error" — no special handling; stream will close via 'done'
        } else {
          // Legacy enrichment update (no type field) from synchronous search path
          const legacy = update as _LegacyUpdateEvent
          if (legacy.platform_listing_id && legacy.trust_score) {
            trustScores.value = new Map(trustScores.value)
            trustScores.value.set(legacy.platform_listing_id, legacy.trust_score)
          }
          if (legacy.seller) {
            const s = legacy.seller as Seller
            if (s.platform_seller_id) {
              sellers.value = new Map(sellers.value)
              sellers.value.set(s.platform_seller_id, s)
            }
          }
          if (legacy.market_price != null) {
            marketPrice.value = legacy.market_price
          }
        }
      } catch {
        // malformed event — ignore
      }
    }

    es.addEventListener('done', () => {
      closeUpdates()
    })

    es.onerror = () => {
      // If loading is still true (never got a "listings" event), clear it
      loading.value = false
      closeUpdates()
    }
  }

  async function enrichSeller(sellerUsername: string, listingId: string): Promise<void> {
    const apiBase = (import.meta.env.VITE_API_BASE as string) ?? ''
    const params = new URLSearchParams({
      seller: sellerUsername,
      listing_id: listingId,
      query: query.value,
    })
    const res = await fetch(`${apiBase}/api/enrich?${params}`, { method: 'POST' })
    if (!res.ok) throw new Error(`Enrich failed: ${res.status} ${res.statusText}`)
    const data = await res.json() as {
      trust_score: TrustScore | null
      seller: Seller | null
    }
    if (data.trust_score) trustScores.value.set(listingId, data.trust_score)
    if (data.seller) sellers.value.set(sellerUsername, data.seller)
  }

  function clearResults() {
    results.value = []
    trustScores.value = new Map()
    sellers.value = new Map()
    marketPrice.value = null
    error.value = null
  }

  function populateFromLLM(params: SearchParamsResult) {
    query.value = params.base_query
    const mode = params.must_include_mode as MustIncludeMode
    filters.value = {
      ...filters.value,
      mustInclude: params.must_include,
      mustIncludeMode: mode,
      mustExclude: params.must_exclude,
      maxPrice: params.max_price ?? undefined,
      minPrice: params.min_price ?? undefined,
      conditions: params.condition.length > 0 ? params.condition : undefined,
      categoryId: params.category_id ?? undefined,
    }
  }

  function getListing(platformListingId: string): Listing | undefined {
    return results.value.find(l => l.platform_listing_id === platformListingId)
  }

  return {
    query,
    results,
    trustScores,
    sellers,
    marketPrice,
    adapterUsed,
    affiliateActive,
    loading,
    enriching,
    error,
    filters,
    search,
    cancelSearch,
    enrichSeller,
    closeUpdates,
    clearResults,
    populateFromLLM,
    getListing,
  }
})

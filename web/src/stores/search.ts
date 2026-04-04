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
  const loading = ref(false)
  const error = ref<string | null>(null)

  let _abort: AbortController | null = null

  function cancelSearch() {
    _abort?.abort()
    _abort = null
    loading.value = false
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
      // TODO: POST /api/search with { query: q, filters }
      // API does not exist yet — stub returns empty results
      // VITE_API_BASE is '' in dev; '/snipe' under menagerie (baked at build time by Vite)
      const apiBase = (import.meta.env.VITE_API_BASE as string) ?? ''
      const params = new URLSearchParams({ q })
      if (filters.maxPrice != null) params.set('max_price', String(filters.maxPrice))
      if (filters.minPrice != null) params.set('min_price', String(filters.minPrice))
      if (filters.pages != null && filters.pages > 1) params.set('pages', String(filters.pages))
      if (filters.mustInclude?.trim()) params.set('must_include', filters.mustInclude.trim())
      if (filters.mustIncludeMode) params.set('must_include_mode', filters.mustIncludeMode)
      if (filters.mustExclude?.trim()) params.set('must_exclude', filters.mustExclude.trim())
      if (filters.categoryId?.trim()) params.set('category_id', filters.categoryId.trim())
      if (filters.adapter && filters.adapter !== 'auto') params.set('adapter', filters.adapter)
      const res = await fetch(`${apiBase}/api/search?${params}`, { signal })
      if (!res.ok) throw new Error(`Search failed: ${res.status} ${res.statusText}`)

      const data = await res.json() as {
        listings: Listing[]
        trust_scores: Record<string, TrustScore>
        sellers: Record<string, Seller>
        market_price: number | null
        adapter_used: 'api' | 'scraper'
      }

      results.value = data.listings ?? []
      trustScores.value = new Map(Object.entries(data.trust_scores ?? {}))
      sellers.value = new Map(Object.entries(data.sellers ?? {}))
      marketPrice.value = data.market_price ?? null
      adapterUsed.value = data.adapter_used ?? null
      saveCache({
        query: q,
        results: results.value,
        trustScores: data.trust_scores ?? {},
        sellers: data.sellers ?? {},
        marketPrice: marketPrice.value,
        adapterUsed: adapterUsed.value,
      })
    } catch (e) {
      if (e instanceof DOMException && e.name === 'AbortError') {
        // User cancelled — clear loading but don't surface as an error
        results.value = []
      } else {
        error.value = e instanceof Error ? e.message : 'Unknown error'
        results.value = []
      }
    } finally {
      loading.value = false
      _abort = null
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

  return {
    query,
    results,
    trustScores,
    sellers,
    marketPrice,
    adapterUsed,
    loading,
    error,
    search,
    cancelSearch,
    enrichSeller,
    clearResults,
  }
})

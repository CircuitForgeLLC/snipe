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
  account_age_days: number
  feedback_count: number
  feedback_ratio: number          // 0.0–1.0
  category_history_json: string
  fetched_at: string | null
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
  pages?: number  // number of eBay result pages to fetch (48 listings/page, default 1)
}

// ── Store ────────────────────────────────────────────────────────────────────

export const useSearchStore = defineStore('search', () => {
  const query = ref('')
  const results = ref<Listing[]>([])
  const trustScores = ref<Map<string, TrustScore>>(new Map())   // key: platform_listing_id
  const sellers = ref<Map<string, Seller>>(new Map())           // key: platform_seller_id
  const marketPrice = ref<number | null>(null)
  const loading = ref(false)
  const error = ref<string | null>(null)

  async function search(q: string, filters: SearchFilters = {}) {
    query.value = q
    loading.value = true
    error.value = null

    try {
      // TODO: POST /api/search with { query: q, filters }
      // API does not exist yet — stub returns empty results
      const params = new URLSearchParams({ q })
      if (filters.maxPrice != null) params.set('max_price', String(filters.maxPrice))
      if (filters.minPrice != null) params.set('min_price', String(filters.minPrice))
      if (filters.pages != null && filters.pages > 1) params.set('pages', String(filters.pages))
      const res = await fetch(`/api/search?${params}`)
      if (!res.ok) throw new Error(`Search failed: ${res.status} ${res.statusText}`)

      const data = await res.json() as {
        listings: Listing[]
        trust_scores: Record<string, TrustScore>
        sellers: Record<string, Seller>
        market_price: number | null
      }

      results.value = data.listings ?? []
      trustScores.value = new Map(Object.entries(data.trust_scores ?? {}))
      sellers.value = new Map(Object.entries(data.sellers ?? {}))
      marketPrice.value = data.market_price ?? null
    } catch (e) {
      error.value = e instanceof Error ? e.message : 'Unknown error'
      results.value = []
    } finally {
      loading.value = false
    }
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
    loading,
    error,
    search,
    clearResults,
  }
})

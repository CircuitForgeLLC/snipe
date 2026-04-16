import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it } from 'vitest'
import { useSearchStore } from '../stores/search'
import type { Listing, TrustScore, Seller } from '../stores/search'

function makeListing(id: string, overrides: Partial<Listing> = {}): Listing {
  return {
    id: null,
    platform: 'ebay',
    platform_listing_id: id,
    title: `Listing ${id}`,
    price: 100,
    currency: 'USD',
    condition: 'used',
    seller_platform_id: 'seller1',
    url: `https://ebay.com/itm/${id}`,
    photo_urls: [],
    listing_age_days: 1,
    buying_format: 'fixed_price',
    ends_at: null,
    fetched_at: null,
    trust_score_id: null,
    ...overrides,
  }
}

function makeTrust(score: number, flags: string[] = []): TrustScore {
  return {
    id: null,
    listing_id: 1,
    composite_score: score,
    account_age_score: 20,
    feedback_count_score: 20,
    feedback_ratio_score: 20,
    price_vs_market_score: 20,
    category_history_score: 20,
    photo_hash_duplicate: false,
    photo_analysis_json: null,
    red_flags_json: JSON.stringify(flags),
    score_is_partial: false,
    scored_at: null,
  }
}

describe('useSearchStore.getListing', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    sessionStorage.clear()
  })

  it('returns undefined when results are empty', () => {
    const store = useSearchStore()
    expect(store.getListing('abc')).toBeUndefined()
  })

  it('returns the listing when present in results', () => {
    const store = useSearchStore()
    const listing = makeListing('v1|123|0')
    store.results.push(listing)
    expect(store.getListing('v1|123|0')).toEqual(listing)
  })

  it('returns undefined for an id not in results', () => {
    const store = useSearchStore()
    store.results.push(makeListing('v1|123|0'))
    expect(store.getListing('v1|999|0')).toBeUndefined()
  })

  it('returns the correct listing when multiple are present', () => {
    const store = useSearchStore()
    store.results.push(makeListing('v1|001|0', { title: 'First' }))
    store.results.push(makeListing('v1|002|0', { title: 'Second' }))
    store.results.push(makeListing('v1|003|0', { title: 'Third' }))
    expect(store.getListing('v1|002|0')?.title).toBe('Second')
  })

  it('handles URL-encoded pipe characters in listing IDs', () => {
    const store = useSearchStore()
    // The route param arrives decoded from vue-router; store uses decoded string
    const listing = makeListing('v1|157831011297|0')
    store.results.push(listing)
    expect(store.getListing('v1|157831011297|0')).toEqual(listing)
  })
})

describe('useSearchStore trust and seller maps', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    sessionStorage.clear()
  })

  it('trustScores map returns trust by platform_listing_id', () => {
    const store = useSearchStore()
    const trust = makeTrust(85, ['low_feedback_count'])
    store.trustScores.set('v1|123|0', trust)
    expect(store.trustScores.get('v1|123|0')?.composite_score).toBe(85)
  })

  it('sellers map returns seller by seller_platform_id', () => {
    const store = useSearchStore()
    const seller: Seller = {
      id: null, platform: 'ebay', platform_seller_id: 'sellerA',
      username: 'powertech99', account_age_days: 720,
      feedback_count: 1200, feedback_ratio: 0.998,
      category_history_json: '{}', fetched_at: null,
    }
    store.sellers.set('sellerA', seller)
    expect(store.sellers.get('sellerA')?.username).toBe('powertech99')
  })
})

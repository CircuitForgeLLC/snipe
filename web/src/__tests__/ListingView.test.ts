import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { Listing, TrustScore, Seller } from '../stores/search'
import { useSearchStore } from '../stores/search'

// ── Mock vue-router — ListingView reads route.params.id ──────────────────────

const mockRouteId = { value: 'test-listing-id' }

vi.mock('vue-router', () => ({
  useRoute:    () => ({ params: { id: mockRouteId.value } }),
  RouterLink:  { template: '<a><slot /></a>' },
}))

// ── Helpers ──────────────────────────────────────────────────────────────────

function makeListing(id: string, overrides: Partial<Listing> = {}): Listing {
  return {
    id: null, platform: 'ebay', platform_listing_id: id,
    title: 'NVIDIA RTX 4090 24GB — Used Excellent', price: 849.99,
    currency: 'USD', condition: 'used_excellent', seller_platform_id: 'seller1',
    url: 'https://ebay.com/itm/test', photo_urls: ['https://example.com/img.jpg'],
    listing_age_days: 3, buying_format: 'fixed_price', ends_at: null,
    fetched_at: null, trust_score_id: null, ...overrides,
  }
}

function makeTrust(score: number, flags: string[] = [], partial = false): TrustScore {
  return {
    id: null, listing_id: 1, composite_score: score,
    account_age_score: 18, feedback_count_score: 20, feedback_ratio_score: 20,
    price_vs_market_score: 15, category_history_score: 14,
    photo_hash_duplicate: false, photo_analysis_json: null,
    red_flags_json: JSON.stringify(flags), score_is_partial: partial, scored_at: null,
  }
}

function makeSeller(overrides: Partial<Seller> = {}): Seller {
  return {
    id: null, platform: 'ebay', platform_seller_id: 'seller1',
    username: 'techdeals_rog', account_age_days: 720, feedback_count: 4711,
    feedback_ratio: 0.997, category_history_json: '{}', fetched_at: null,
    ...overrides,
  }
}

async function mountView(storeSetup?: (store: ReturnType<typeof useSearchStore>) => void) {
  setActivePinia(createPinia())
  const store = useSearchStore()
  if (storeSetup) storeSetup(store)

  const { default: ListingView } = await import('../views/ListingView.vue')
  return mount(ListingView, {
    global: { plugins: [] },
  })
}

// ── Tests ────────────────────────────────────────────────────────────────────

describe('ListingView — not found', () => {
  beforeEach(() => {
    mockRouteId.value = 'missing-id'
    sessionStorage.clear()
  })

  it('shows not-found state when listing is absent from store', async () => {
    const wrapper = await mountView()
    expect(wrapper.text()).toContain('Listing not found')
    expect(wrapper.text()).toContain('Return to search')
  })

  it('does not render the trust section when listing is absent', async () => {
    const wrapper = await mountView()
    expect(wrapper.find('.lv-trust').exists()).toBe(false)
  })
})

describe('ListingView — listing present', () => {
  const ID = 'test-listing-id'

  beforeEach(() => {
    mockRouteId.value = ID
    sessionStorage.clear()
  })

  it('renders the listing title', async () => {
    const wrapper = await mountView(store => {
      store.results.push(makeListing(ID))
      store.trustScores.set(ID, makeTrust(85))
      store.sellers.set('seller1', makeSeller())
    })
    expect(wrapper.text()).toContain('NVIDIA RTX 4090 24GB')
  })

  it('renders the formatted price', async () => {
    const wrapper = await mountView(store => {
      store.results.push(makeListing(ID))
      store.trustScores.set(ID, makeTrust(85))
    })
    expect(wrapper.text()).toContain('$849.99')
  })

  it('shows the composite trust score in the ring', async () => {
    const wrapper = await mountView(store => {
      store.results.push(makeListing(ID))
      store.trustScores.set(ID, makeTrust(72))
    })
    expect(wrapper.find('.lv-ring__score').text()).toBe('72')
  })

  it('renders all five signal rows in the table', async () => {
    const wrapper = await mountView(store => {
      store.results.push(makeListing(ID))
      store.trustScores.set(ID, makeTrust(80))
      store.sellers.set('seller1', makeSeller())
    })
    const rows = wrapper.findAll('.lv-signals__row')
    expect(rows).toHaveLength(5)
  })

  it('shows score values in signal table', async () => {
    const wrapper = await mountView(store => {
      store.results.push(makeListing(ID))
      store.trustScores.set(ID, makeTrust(80))
      store.sellers.set('seller1', makeSeller())
    })
    // feedback_count_score = 20
    expect(wrapper.text()).toContain('20 / 20')
  })

  it('shows seller username', async () => {
    const wrapper = await mountView(store => {
      store.results.push(makeListing(ID))
      store.trustScores.set(ID, makeTrust(80))
      store.sellers.set('seller1', makeSeller({ username: 'gpu_warehouse' }))
    })
    expect(wrapper.text()).toContain('gpu_warehouse')
  })
})

describe('ListingView — red flags', () => {
  const ID = 'test-listing-id'

  beforeEach(() => {
    mockRouteId.value = ID
    sessionStorage.clear()
  })

  it('renders hard flag badge for new_account', async () => {
    const wrapper = await mountView(store => {
      store.results.push(makeListing(ID))
      store.trustScores.set(ID, makeTrust(40, ['new_account']))
    })
    const flags = wrapper.findAll('.lv-flag--hard')
    expect(flags.length).toBeGreaterThan(0)
    expect(wrapper.text()).toContain('New account')
  })

  it('renders soft flag badge for scratch_dent_mentioned', async () => {
    const wrapper = await mountView(store => {
      store.results.push(makeListing(ID))
      store.trustScores.set(ID, makeTrust(55, ['scratch_dent_mentioned']))
    })
    const flags = wrapper.findAll('.lv-flag--soft')
    expect(flags.length).toBeGreaterThan(0)
    expect(wrapper.text()).toContain('Damage mentioned')
  })

  it('shows no flag badges when red_flags_json is empty', async () => {
    const wrapper = await mountView(store => {
      store.results.push(makeListing(ID))
      store.trustScores.set(ID, makeTrust(90, []))
    })
    expect(wrapper.find('.lv-flag').exists()).toBe(false)
  })

  it('applies triple-red class when account + price + photo flags all present', async () => {
    const wrapper = await mountView(store => {
      store.results.push(makeListing(ID))
      store.trustScores.set(ID, makeTrust(12, [
        'new_account', 'suspicious_price', 'duplicate_photo',
      ]))
    })
    expect(wrapper.find('.lv-layout--triple-red').exists()).toBe(true)
  })

  it('does not apply triple-red class when only two flag categories present', async () => {
    const wrapper = await mountView(store => {
      store.results.push(makeListing(ID))
      store.trustScores.set(ID, makeTrust(30, ['new_account', 'suspicious_price']))
    })
    expect(wrapper.find('.lv-layout--triple-red').exists()).toBe(false)
  })
})

describe('ListingView — partial/pending signals', () => {
  const ID = 'test-listing-id'

  beforeEach(() => {
    mockRouteId.value = ID
    sessionStorage.clear()
  })

  it('shows pending for account age when seller.account_age_days is null', async () => {
    const wrapper = await mountView(store => {
      store.results.push(makeListing(ID))
      store.trustScores.set(ID, makeTrust(60, [], true))
      store.sellers.set('seller1', makeSeller({ account_age_days: null }))
    })
    expect(wrapper.text()).toContain('pending')
  })

  it('shows partial warning text when score_is_partial is true', async () => {
    const wrapper = await mountView(store => {
      store.results.push(makeListing(ID))
      store.trustScores.set(ID, makeTrust(60, [], true))
      store.sellers.set('seller1', makeSeller({ account_age_days: null }))
    })
    expect(wrapper.find('.lv-verdict__partial').exists()).toBe(true)
  })
})

describe('ListingView — ring colour class', () => {
  const ID = 'test-listing-id'

  beforeEach(() => {
    mockRouteId.value = ID
    sessionStorage.clear()
  })

  it('applies lv-ring--high for score >= 80', async () => {
    const wrapper = await mountView(store => {
      store.results.push(makeListing(ID))
      store.trustScores.set(ID, makeTrust(82))
    })
    expect(wrapper.find('.lv-ring--high').exists()).toBe(true)
  })

  it('applies lv-ring--mid for score 50–79', async () => {
    const wrapper = await mountView(store => {
      store.results.push(makeListing(ID))
      store.trustScores.set(ID, makeTrust(63))
    })
    expect(wrapper.find('.lv-ring--mid').exists()).toBe(true)
  })

  it('applies lv-ring--low for score < 50', async () => {
    const wrapper = await mountView(store => {
      store.results.push(makeListing(ID))
      store.trustScores.set(ID, makeTrust(22))
    })
    expect(wrapper.find('.lv-ring--low').exists()).toBe(true)
  })
})

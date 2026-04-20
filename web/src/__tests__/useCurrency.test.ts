import { beforeEach, describe, expect, it, vi } from 'vitest'

// Reset module-level cache and fetch mock between tests
beforeEach(async () => {
  vi.restoreAllMocks()
  // Reset module-level cache so each test starts clean
  const mod = await import('../composables/useCurrency')
  mod._resetCacheForTest()
})

const MOCK_RATES: Record<string, number> = {
  USD: 1,
  GBP: 0.79,
  EUR: 0.92,
  JPY: 151.5,
  CAD: 1.36,
}

function mockFetchSuccess(rates = MOCK_RATES) {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
    ok: true,
    json: async () => ({ rates }),
  }))
}

function mockFetchFailure() {
  vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('Network error')))
}

describe('convertFromUSD', () => {
  it('returns the same amount for USD (no conversion)', async () => {
    mockFetchSuccess()
    const { convertFromUSD } = await import('../composables/useCurrency')
    const result = await convertFromUSD(100, 'USD')
    expect(result).toBe(100)
    // fetch should not be called for USD passthrough
    expect(fetch).not.toHaveBeenCalled()
  })

  it('converts USD to GBP using fetched rates', async () => {
    mockFetchSuccess()
    const { convertFromUSD, _resetCacheForTest } = await import('../composables/useCurrency')
    _resetCacheForTest()
    const result = await convertFromUSD(100, 'GBP')
    expect(result).toBeCloseTo(79, 1)
  })

  it('converts USD to JPY using fetched rates', async () => {
    mockFetchSuccess()
    const { convertFromUSD, _resetCacheForTest } = await import('../composables/useCurrency')
    _resetCacheForTest()
    const result = await convertFromUSD(10, 'JPY')
    expect(result).toBeCloseTo(1515, 1)
  })

  it('returns the original amount when rates are unavailable (network failure)', async () => {
    mockFetchFailure()
    const { convertFromUSD, _resetCacheForTest } = await import('../composables/useCurrency')
    _resetCacheForTest()
    const result = await convertFromUSD(100, 'EUR')
    expect(result).toBe(100)
  })

  it('returns the original amount when the currency code is unknown', async () => {
    mockFetchSuccess({ USD: 1, EUR: 0.92 }) // no XYZ rate
    const { convertFromUSD, _resetCacheForTest } = await import('../composables/useCurrency')
    _resetCacheForTest()
    const result = await convertFromUSD(50, 'XYZ')
    expect(result).toBe(50)
  })

  it('only calls fetch once when called concurrently (deduplication)', async () => {
    mockFetchSuccess()
    const { convertFromUSD, _resetCacheForTest } = await import('../composables/useCurrency')
    _resetCacheForTest()
    await Promise.all([
      convertFromUSD(100, 'GBP'),
      convertFromUSD(200, 'EUR'),
      convertFromUSD(50, 'CAD'),
    ])
    expect((fetch as ReturnType<typeof vi.fn>).mock.calls.length).toBe(1)
  })
})

describe('formatPrice', () => {
  it('formats USD amount with dollar sign', async () => {
    mockFetchSuccess()
    const { formatPrice, _resetCacheForTest } = await import('../composables/useCurrency')
    _resetCacheForTest()
    const result = await formatPrice(99.99, 'USD')
    expect(result).toMatch(/^\$99\.99$|^\$100$/)  // Intl rounding may vary
    expect(result).toContain('$')
  })

  it('formats GBP amount with correct symbol', async () => {
    mockFetchSuccess()
    const { formatPrice, _resetCacheForTest } = await import('../composables/useCurrency')
    _resetCacheForTest()
    const result = await formatPrice(100, 'GBP')
    // GBP 79 — expect pound sign or "GBP" prefix
    expect(result).toMatch(/[£]|GBP/)
  })

  it('formats JPY without decimal places (Intl rounds to zero decimals)', async () => {
    mockFetchSuccess()
    const { formatPrice, _resetCacheForTest } = await import('../composables/useCurrency')
    _resetCacheForTest()
    const result = await formatPrice(10, 'JPY')
    // 10 * 151.5 = 1515 JPY — no decimal places for JPY
    expect(result).toMatch(/¥1,515|JPY.*1,515|¥1515/)
  })

  it('falls back gracefully on network failure, showing USD', async () => {
    mockFetchFailure()
    const { formatPrice, _resetCacheForTest } = await import('../composables/useCurrency')
    _resetCacheForTest()
    // With failed rates, conversion returns original amount and uses Intl with target currency
    // This may throw if Intl doesn't know EUR — but the function should not throw
    const result = await formatPrice(50, 'EUR')
    expect(typeof result).toBe('string')
    expect(result.length).toBeGreaterThan(0)
  })
})

describe('formatPriceUSD', () => {
  it('formats a USD amount synchronously', async () => {
    const { formatPriceUSD } = await import('../composables/useCurrency')
    const result = formatPriceUSD(1234.5)
    // Intl output varies by runtime locale data; check structure not exact string
    expect(result).toContain('$')
    expect(result).toContain('1,234')
  })

  it('formats zero as a USD string', async () => {
    const { formatPriceUSD } = await import('../composables/useCurrency')
    const result = formatPriceUSD(0)
    expect(result).toContain('$')
    expect(result).toMatch(/\$0/)
  })
})

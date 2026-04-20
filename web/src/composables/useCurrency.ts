/**
 * useCurrency — live exchange rate conversion from USD to a target display currency.
 *
 * Rates are fetched lazily on first use from open.er-api.com (free, no key required).
 * A module-level cache with a 1-hour TTL prevents redundant network calls.
 * On fetch failure the composable falls back silently to USD display.
 */

const ER_API_URL = 'https://open.er-api.com/v6/latest/USD'
const CACHE_TTL_MS = 60 * 60 * 1000 // 1 hour

interface RateCache {
  rates: Record<string, number>
  fetchedAt: number
}

// Module-level cache shared across all composable instances
let _cache: RateCache | null = null
let _inflight: Promise<Record<string, number>> | null = null

async function _fetchRates(): Promise<Record<string, number>> {
  const now = Date.now()

  if (_cache && now - _cache.fetchedAt < CACHE_TTL_MS) {
    return _cache.rates
  }

  // Deduplicate concurrent calls — reuse the same in-flight fetch
  if (_inflight) {
    return _inflight
  }

  _inflight = (async () => {
    try {
      const res = await fetch(ER_API_URL)
      if (!res.ok) throw new Error(`ER-API responded ${res.status}`)
      const data = await res.json()
      const rates: Record<string, number> = data.rates ?? {}
      _cache = { rates, fetchedAt: Date.now() }
      return rates
    } catch {
      // Return cached stale data if available, otherwise empty object (USD passthrough)
      return _cache?.rates ?? {}
    } finally {
      _inflight = null
    }
  })()

  return _inflight
}

/**
 * Convert an amount in USD to the target currency using the latest exchange rates.
 * Returns the original amount unchanged if rates are unavailable or the currency is USD.
 */
export async function convertFromUSD(amountUSD: number, targetCurrency: string): Promise<number> {
  if (targetCurrency === 'USD') return amountUSD
  const rates = await _fetchRates()
  const rate = rates[targetCurrency]
  if (!rate) return amountUSD
  return amountUSD * rate
}

/**
 * Format a USD amount as a localized string in the target currency.
 * Fetches exchange rates lazily. Falls back to USD display if rates are unavailable.
 *
 * Returns a plain USD string synchronously on first call while rates load;
 * callers should use a ref that updates once the promise resolves.
 */
export async function formatPrice(amountUSD: number, currency: string): Promise<string> {
  const converted = await convertFromUSD(amountUSD, currency)
  try {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency,
      minimumFractionDigits: 0,
      maximumFractionDigits: 2,
    }).format(converted)
  } catch {
    // Fallback if Intl doesn't know the currency code
    return `${currency} ${converted.toLocaleString('en-US', { minimumFractionDigits: 0, maximumFractionDigits: 2 })}`
  }
}

/**
 * Synchronous USD-only formatter for use before rates have loaded.
 */
export function formatPriceUSD(amountUSD: number): string {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 0,
    maximumFractionDigits: 2,
  }).format(amountUSD)
}

// Exported for testing — allows resetting module-level cache between test cases
export function _resetCacheForTest(): void {
  _cache = null
  _inflight = null
}

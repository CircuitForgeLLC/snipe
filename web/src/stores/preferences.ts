import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { useSessionStore } from './session'

export interface UserPreferences {
  affiliate?: {
    opt_out?: boolean
    byok_ids?: {
      ebay?: string
    }
  }
  community?: {
    blocklist_share?: boolean
  }
  display?: {
    currency?: string
  }
}

const CURRENCY_LS_KEY = 'snipe:currency'
const DEFAULT_CURRENCY = 'USD'

const apiBase = (import.meta.env.VITE_API_BASE as string) ?? ''

export const usePreferencesStore = defineStore('preferences', () => {
  const session = useSessionStore()
  const prefs = ref<UserPreferences>({})
  const loading = ref(false)
  const error = ref<string | null>(null)

  const affiliateOptOut = computed(() => prefs.value.affiliate?.opt_out ?? false)
  const affiliateByokId = computed(() => prefs.value.affiliate?.byok_ids?.ebay ?? '')
  const communityBlocklistShare = computed(() => prefs.value.community?.blocklist_share ?? false)

  // displayCurrency: DB preference for logged-in users, localStorage for anon users
  const displayCurrency = computed((): string => {
    return prefs.value.display?.currency ?? DEFAULT_CURRENCY
  })

  async function load() {
    if (!session.isLoggedIn) {
      // Anonymous user: read currency from localStorage
      const stored = localStorage.getItem(CURRENCY_LS_KEY)
      if (stored) {
        prefs.value = { ...prefs.value, display: { ...prefs.value.display, currency: stored } }
      }
      return
    }
    loading.value = true
    error.value = null
    try {
      const res = await fetch(`${apiBase}/api/preferences`)
      if (res.ok) {
        const data: UserPreferences = await res.json()
        // Migration: if logged in but no DB preference, fall back to localStorage value
        if (!data.display?.currency) {
          const lsVal = localStorage.getItem(CURRENCY_LS_KEY)
          if (lsVal) {
            data.display = { ...data.display, currency: lsVal }
          }
        }
        prefs.value = data
      }
    } catch {
      // Non-cloud deploy or network error — preferences unavailable
    } finally {
      loading.value = false
    }
  }

  async function setPref(path: string, value: boolean | string | null) {
    if (!session.isLoggedIn) return
    error.value = null
    try {
      const res = await fetch(`${apiBase}/api/preferences`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path, value }),
      })
      if (res.ok) {
        prefs.value = await res.json()
      } else {
        const data = await res.json().catch(() => ({}))
        error.value = data.detail ?? 'Failed to save preference.'
      }
    } catch {
      error.value = 'Network error saving preference.'
    }
  }

  async function setAffiliateOptOut(value: boolean) {
    await setPref('affiliate.opt_out', value)
  }

  async function setAffiliateByokId(id: string) {
    // Empty string clears the BYOK ID (router falls back to CF env var)
    await setPref('affiliate.byok_ids.ebay', id.trim() || null)
  }

  async function setCommunityBlocklistShare(value: boolean) {
    await setPref('community.blocklist_share', value)
  }

  async function setDisplayCurrency(code: string) {
    const upper = code.toUpperCase()
    // Optimistic local update so the UI reacts immediately
    prefs.value = { ...prefs.value, display: { ...prefs.value.display, currency: upper } }
    if (session.isLoggedIn) {
      await setPref('display.currency', upper)
    } else {
      // Anonymous user: persist to localStorage only
      localStorage.setItem(CURRENCY_LS_KEY, upper)
    }
  }

  return {
    prefs,
    loading,
    error,
    affiliateOptOut,
    affiliateByokId,
    communityBlocklistShare,
    displayCurrency,
    load,
    setAffiliateOptOut,
    setAffiliateByokId,
    setCommunityBlocklistShare,
    setDisplayCurrency,
  }
})

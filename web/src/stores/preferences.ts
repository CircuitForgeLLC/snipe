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
}

export const usePreferencesStore = defineStore('preferences', () => {
  const session = useSessionStore()
  const prefs = ref<UserPreferences>({})
  const loading = ref(false)
  const error = ref<string | null>(null)

  const affiliateOptOut = computed(() => prefs.value.affiliate?.opt_out ?? false)
  const affiliateByokId = computed(() => prefs.value.affiliate?.byok_ids?.ebay ?? '')

  async function load() {
    if (!session.isLoggedIn) return
    loading.value = true
    error.value = null
    try {
      const res = await fetch('/api/preferences')
      if (res.ok) {
        prefs.value = await res.json()
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
      const res = await fetch('/api/preferences', {
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

  return {
    prefs,
    loading,
    error,
    affiliateOptOut,
    affiliateByokId,
    load,
    setAffiliateOptOut,
    setAffiliateByokId,
  }
})

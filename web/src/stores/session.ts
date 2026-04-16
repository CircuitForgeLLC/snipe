import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

// Mirrors api/cloud_session.py SessionFeatures dataclass
export interface SessionFeatures {
  saved_searches: boolean
  saved_searches_limit: number | null  // null = unlimited
  background_monitoring: boolean
  max_pages: number
  upc_search: boolean
  photo_analysis: boolean
  shared_scammer_db: boolean
  shared_image_db: boolean
  llm_query_builder: boolean
}

const LOCAL_FEATURES: SessionFeatures = {
  saved_searches: true,
  saved_searches_limit: null,
  background_monitoring: true,
  max_pages: 999,
  upc_search: true,
  photo_analysis: true,
  shared_scammer_db: true,
  shared_image_db: true,
  llm_query_builder: true,
}

export const useSessionStore = defineStore('session', () => {
  const userId = ref<string>('local')
  const tier = ref<string>('local')
  const features = ref<SessionFeatures>(LOCAL_FEATURES)
  const loaded = ref(false)

  const isCloud = computed(() => tier.value !== 'local')
  const isFree = computed(() => tier.value === 'free')
  const isPaid = computed(() => ['paid', 'premium', 'ultra', 'local'].includes(tier.value))
  const isPremium = computed(() => ['premium', 'ultra'].includes(tier.value))
  // isGuest: transient visitor with a snipe_guest UUID but no Heimdall account
  const isGuest = computed(() => userId.value.startsWith('guest:'))
  // isLoggedIn: cloud user with a real account (not anonymous or guest)
  const isLoggedIn = computed(() => isCloud.value && userId.value !== 'anonymous' && !isGuest.value)

  async function bootstrap() {
    const apiBase = (import.meta.env.VITE_API_BASE as string) ?? ''
    try {
      const res = await fetch(`${apiBase}/api/session`)
      if (!res.ok) return  // local-mode with no session endpoint — keep defaults
      const data = await res.json()
      userId.value = data.user_id
      tier.value = data.tier
      features.value = data.features
    } catch {
      // Network error or non-cloud deploy — keep local defaults
    } finally {
      loaded.value = true
    }
  }

  return { userId, tier, features, loaded, isCloud, isFree, isPaid, isPremium, isGuest, isLoggedIn, bootstrap }
})

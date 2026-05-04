import { defineStore } from 'pinia'
import { ref } from 'vue'

export interface WatchAlert {
  id: number
  saved_search_id: number
  platform_listing_id: string
  title: string
  price: number
  currency: string
  trust_score: number
  url: string | null
  first_alerted_at: string
  dismissed_at: string | null
}

const BASE = import.meta.env.VITE_API_BASE ?? ''

export const useAlertsStore = defineStore('alerts', () => {
  const alerts = ref<WatchAlert[]>([])
  const unreadCount = ref(0)
  const loading = ref(false)
  const error = ref<string | null>(null)

  async function fetchAlerts(includeDismissed = false) {
    loading.value = true
    error.value = null
    try {
      const res = await fetch(
        `${BASE}/api/alerts${includeDismissed ? '?include_dismissed=true' : ''}`,
        { credentials: 'include' },
      )
      if (!res.ok) throw new Error(`${res.status}`)
      const data = await res.json()
      alerts.value = data.alerts
      unreadCount.value = data.unread_count
    } catch (e) {
      error.value = e instanceof Error ? e.message : 'Failed to load alerts'
    } finally {
      loading.value = false
    }
  }

  async function dismiss(alertId: number) {
    await fetch(`${BASE}/api/alerts/${alertId}/dismiss`, {
      method: 'POST',
      credentials: 'include',
    })
    alerts.value = alerts.value.filter((a) => a.id !== alertId)
    unreadCount.value = Math.max(0, unreadCount.value - 1)
  }

  async function dismissAll() {
    await fetch(`${BASE}/api/alerts/dismiss-all`, {
      method: 'POST',
      credentials: 'include',
    })
    alerts.value = []
    unreadCount.value = 0
  }

  return { alerts, unreadCount, loading, error, fetchAlerts, dismiss, dismissAll }
})

import { defineStore } from 'pinia'
import { ref } from 'vue'

const apiBase = (import.meta.env.VITE_API_BASE as string) ?? ''

/**
 * Tracks sellers the user has already reported to eBay T&S.
 * Persisted server-side for logged-in users; falls back to a session-local
 * Set for guests so the UI still suppresses duplicate prompts within a session.
 */
export const useReportedStore = defineStore('reported', () => {
  const reportedIds = ref<Set<string>>(new Set())
  const loading = ref(false)

  async function load() {
    loading.value = true
    try {
      const res = await fetch(`${apiBase}/api/reported`)
      if (res.ok) {
        const data = await res.json() as { reported: string[] }
        reportedIds.value = new Set(data.reported)
      }
    } catch {
      // Non-cloud deploy or network error — start with empty set
    } finally {
      loading.value = false
    }
  }

  async function markReported(sellers: Array<{ platform_seller_id: string; username?: string | null }>) {
    // Optimistic update — add to local set immediately
    const next = new Set(reportedIds.value)
    for (const s of sellers) next.add(s.platform_seller_id)
    reportedIds.value = next

    // Persist server-side (best-effort — no rollback on failure)
    try {
      await fetch(`${apiBase}/api/reported`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          sellers: sellers.map(s => ({
            platform_seller_id: s.platform_seller_id,
            username: s.username ?? null,
          })),
        }),
      })
    } catch {
      // Persist failed — local set already updated, good enough for session
    }
  }

  function isReported(platformSellerId: string): boolean {
    return reportedIds.value.has(platformSellerId)
  }

  return { reportedIds, loading, load, markReported, isReported }
})

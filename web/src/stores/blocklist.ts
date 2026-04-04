import { defineStore } from 'pinia'
import { ref } from 'vue'
import { apiFetch } from '../utils/api'

const apiBase = (import.meta.env.VITE_API_BASE as string) ?? ''

export interface BlocklistEntry {
  id: number | null
  platform: string
  platform_seller_id: string
  username: string
  reason: string | null
  source: string
  created_at: string | null
}

export const useBlocklistStore = defineStore('blocklist', () => {
  const entries = ref<BlocklistEntry[]>([])
  const loading = ref(false)
  const error = ref<string | null>(null)

  async function fetchBlocklist() {
    loading.value = true
    error.value = null
    try {
      const res = await apiFetch(`${apiBase}/api/blocklist`)
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const data = await res.json()
      entries.value = data.entries
    } catch (e) {
      error.value = e instanceof Error ? e.message : 'Failed to load blocklist'
    } finally {
      loading.value = false
    }
  }

  async function addSeller(
    platformSellerId: string,
    username: string,
    reason: string,
  ): Promise<void> {
    const res = await apiFetch(`${apiBase}/api/blocklist`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        platform: 'ebay',
        platform_seller_id: platformSellerId,
        username,
        reason,
      }),
    })
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    const entry: BlocklistEntry = await res.json()
    // Prepend so the new entry appears at the top
    entries.value = [entry, ...entries.value.filter(
      e => e.platform_seller_id !== platformSellerId,
    )]
  }

  async function removeSeller(platformSellerId: string): Promise<void> {
    const res = await apiFetch(`${apiBase}/api/blocklist/${encodeURIComponent(platformSellerId)}`, {
      method: 'DELETE',
    })
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    entries.value = entries.value.filter(e => e.platform_seller_id !== platformSellerId)
  }

  function isBlocklisted(platformSellerId: string): boolean {
    return entries.value.some(e => e.platform_seller_id === platformSellerId)
  }

  async function exportCsv(): Promise<void> {
    const res = await apiFetch(`${apiBase}/api/blocklist/export`)
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    const blob = await res.blob()
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = 'snipe-blocklist.csv'
    a.click()
    URL.revokeObjectURL(url)
  }

  async function importCsv(file: File): Promise<{ imported: number; errors: string[] }> {
    const formData = new FormData()
    formData.append('file', file)
    const res = await apiFetch(`${apiBase}/api/blocklist/import`, {
      method: 'POST',
      body: formData,
    })
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    const result = await res.json()
    // Refresh to pick up all imported entries
    await fetchBlocklist()
    return result
  }

  return {
    entries,
    loading,
    error,
    fetchBlocklist,
    addSeller,
    removeSeller,
    isBlocklisted,
    exportCsv,
    importCsv,
  }
})

import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { SavedSearch, SearchFilters } from './search'
import { apiFetch } from '../utils/api'

export type { SavedSearch }

const apiBase = (import.meta.env.VITE_API_BASE as string) ?? ''

export const useSavedSearchesStore = defineStore('savedSearches', () => {
  const items = ref<SavedSearch[]>([])
  const loading = ref(false)
  const error = ref<string | null>(null)

  async function fetchAll() {
    loading.value = true
    error.value = null
    try {
      const res = await apiFetch(`${apiBase}/api/saved-searches`)
      if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
      const data = await res.json() as { saved_searches: SavedSearch[] }
      items.value = data.saved_searches
    } catch (e) {
      error.value = e instanceof Error ? e.message : 'Failed to load saved searches'
    } finally {
      loading.value = false
    }
  }

  async function create(name: string, query: string, filters: SearchFilters): Promise<SavedSearch> {
    // Strip per-run fields before persisting
    const { pages: _pages, ...persistable } = filters
    const res = await apiFetch(`${apiBase}/api/saved-searches`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, query, filters_json: JSON.stringify(persistable) }),
    })
    if (!res.ok) throw new Error(`Save failed: ${res.status} ${res.statusText}`)
    const created = await res.json() as SavedSearch
    items.value = [created, ...items.value]
    return created
  }

  async function remove(id: number) {
    await fetch(`${apiBase}/api/saved-searches/${id}`, { method: 'DELETE' })
    items.value = items.value.filter(s => s.id !== id)
  }

  async function markRun(id: number) {
    // Fire-and-forget — don't block navigation on this
    fetch(`${apiBase}/api/saved-searches/${id}/run`, { method: 'PATCH' }).catch(() => {})
    const item = items.value.find(s => s.id === id)
    if (item) item.last_run_at = new Date().toISOString()
  }

  return { items, loading, error, fetchAll, create, remove, markRun }
})

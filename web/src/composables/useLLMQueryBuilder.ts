// web/src/composables/useLLMQueryBuilder.ts
// BSL 1.1 License
/**
 * State and API call logic for the LLM query builder panel.
 */
import { ref } from 'vue'
import { useSearchStore, type SearchParamsResult } from '@/stores/search'

export type BuildStatus = 'idle' | 'thinking' | 'done' | 'error'

const LS_AUTORUN_KEY = 'snipe:llm-autorun'

// Module-level refs so state persists across component re-renders
const isOpen = ref(false)
const isLoading = ref(false)
const status = ref<BuildStatus>('idle')
const explanation = ref<string>('')
const error = ref<string | null>(null)
const autoRun = ref<boolean>(localStorage.getItem(LS_AUTORUN_KEY) === 'true')

export function useLLMQueryBuilder() {
  const store = useSearchStore()

  function toggle() {
    isOpen.value = !isOpen.value
    if (!isOpen.value) {
      status.value = 'idle'
      error.value = null
      explanation.value = ''
    }
  }

  function setAutoRun(value: boolean) {
    autoRun.value = value
    localStorage.setItem(LS_AUTORUN_KEY, value ? 'true' : 'false')
  }

  async function buildQuery(naturalLanguage: string): Promise<SearchParamsResult | null> {
    if (!naturalLanguage.trim()) return null

    isLoading.value = true
    status.value = 'thinking'
    error.value = null
    explanation.value = ''

    try {
      const resp = await fetch('/api/search/build', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ natural_language: naturalLanguage.trim() }),
      })

      if (!resp.ok) {
        const data = await resp.json().catch(() => ({}))
        const msg = typeof data.detail === 'string'
          ? data.detail
          : (data.detail?.message ?? `Server error (${resp.status})`)
        throw new Error(msg)
      }

      const params: SearchParamsResult = await resp.json()
      store.populateFromLLM(params)
      explanation.value = params.explanation
      status.value = 'done'

      if (autoRun.value) {
        await store.search(params.base_query, store.filters.value)
      }

      return params
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Something went wrong.'
      error.value = msg
      status.value = 'error'
      return null
    } finally {
      isLoading.value = false
    }
  }

  return {
    isOpen,
    isLoading,
    status,
    explanation,
    error,
    autoRun,
    toggle,
    setAutoRun,
    buildQuery,
  }
}

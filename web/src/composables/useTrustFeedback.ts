// web/src/composables/useTrustFeedback.ts
// MIT -- component layer; the API call routes to a BSL endpoint.
import { ref } from 'vue'

export type FeedbackState = 'idle' | 'sending' | 'confirmed' | 'disputed'

export function useTrustFeedback(sellerId: string) {
  const state = ref<FeedbackState>('idle')

  async function submitFeedback(confirmed: boolean): Promise<void> {
    if (state.value !== 'idle') return
    state.value = 'sending'
    try {
      await fetch('/api/community/signal', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ seller_id: sellerId, confirmed }),
      })
      // Always confirm regardless of response -- fail-soft contract.
    } catch {
      // Network unreachable -- still confirm to the user. Signal is best-effort.
    } finally {
      state.value = confirmed ? 'confirmed' : 'disputed'
    }
  }

  return { state, submitFeedback }
}

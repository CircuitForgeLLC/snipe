<!-- web/src/components/TrustFeedbackButtons.vue -->
<!-- MIT -- component layer -->
<template>
  <div class="trust-feedback" v-if="trust">
    <template v-if="state === 'idle' || state === 'sending'">
      <button
        type="button"
        class="trust-feedback__btn trust-feedback__btn--confirm"
        :disabled="state === 'sending'"
        :aria-busy="state === 'sending'"
        @click="submitFeedback(true)"
      >
        This score looks right
      </button>
      <button
        type="button"
        class="trust-feedback__btn trust-feedback__btn--dispute"
        :disabled="state === 'sending'"
        :aria-busy="state === 'sending'"
        @click="submitFeedback(false)"
      >
        This score is wrong
      </button>
    </template>

    <!-- Confirmation -- persistent, no countdown, no urgency -->
    <p
      v-else
      class="trust-feedback__confirmation"
      role="status"
      aria-live="polite"
    >
      Thanks, noted.
    </p>
  </div>
</template>

<script setup lang="ts">
import type { TrustScore } from '../stores/search'
import { useTrustFeedback } from '../composables/useTrustFeedback'

const props = defineProps<{
  sellerId: string
  trust: TrustScore | null
}>()

const { state, submitFeedback } = useTrustFeedback(props.sellerId)
</script>

<style scoped>
.trust-feedback {
  display: flex;
  gap: 0.5rem;
  margin-top: 0.5rem;
  flex-wrap: wrap;
}

.trust-feedback__btn {
  font-size: 0.75rem;
  padding: 0.25rem 0.6rem;
  border-radius: 4px;
  border: 1px solid currentColor;
  background: transparent;
  cursor: pointer;
  color: inherit;
  opacity: 0.7;
  transition: opacity 0.15s;
}

@media (prefers-reduced-motion: reduce) {
  .trust-feedback__btn { transition: none; }
}

.trust-feedback__btn:hover:not(:disabled),
.trust-feedback__btn:focus-visible {
  opacity: 1;
  outline: 2px solid currentColor;
  outline-offset: 2px;
}

.trust-feedback__btn:disabled { cursor: default; }
.trust-feedback__btn--confirm { border-color: var(--trust-high, #3fb950); }
.trust-feedback__btn--dispute { border-color: var(--trust-low, #f85149); }

.trust-feedback__confirmation {
  font-size: 0.75rem;
  opacity: 0.8;
  margin: 0;
  padding: 0.25rem 0;
}
</style>

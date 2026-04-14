<!-- web/src/components/LLMQueryPanel.vue -->
<!-- BSL 1.1 License -->
<template>
  <div class="llm-panel-wrapper">
    <button
      type="button"
      class="llm-panel-toggle"
      :class="{ 'llm-panel-toggle--open': isOpen }"
      :aria-expanded="String(isOpen)"
      aria-controls="llm-panel"
      @click="toggle"
    >
      Search with AI
      <span class="llm-panel-toggle__chevron" aria-hidden="true">{{ isOpen ? '▲' : '▾' }}</span>
    </button>

    <section
      id="llm-panel"
      class="llm-panel"
      :class="{ 'llm-panel--open': isOpen }"
      :hidden="!isOpen"
    >
      <label for="llm-input" class="llm-panel__label">
        Describe what you're looking for
      </label>
      <textarea
        id="llm-input"
        ref="textareaRef"
        v-model="inputText"
        class="llm-panel__textarea"
        rows="2"
        placeholder="e.g. used RTX 3080 under $300, no mining cards or for-parts listings"
        :disabled="isLoading"
        @keydown.escape.prevent="handleEscape"
        @keydown.ctrl.enter.prevent="onSearch"
      />

      <div class="llm-panel__actions">
        <button
          type="button"
          class="llm-panel__search-btn"
          :disabled="isLoading || !inputText.trim()"
          @click="onSearch"
        >
          {{ isLoading ? 'Searching…' : 'Search' }}
        </button>

        <span
          role="status"
          aria-live="polite"
          class="llm-panel__status-pill"
          :class="`llm-panel__status-pill--${status}`"
        >
          <span v-if="status === 'thinking'">
            <span class="llm-panel__spinner" aria-hidden="true" />
            Thinking…
          </span>
          <span v-else-if="status === 'done'">Filters ready</span>
          <span v-else-if="status === 'error'">Error</span>
        </span>
      </div>

      <p v-if="error" class="llm-panel__error" role="alert">
        {{ error }}
      </p>

      <p v-if="status === 'done' && explanation" class="llm-panel__explanation">
        {{ explanation }}
      </p>

      <label class="llm-panel__autorun">
        <input
          type="checkbox"
          :checked="autoRun"
          @change="setAutoRun(($event.target as HTMLInputElement).checked)"
        />
        Run search automatically
      </label>
    </section>
  </div>
</template>

<script setup lang="ts">
import { ref, nextTick, watch } from 'vue'
import { useLLMQueryBuilder } from '../composables/useLLMQueryBuilder'

const {
  isOpen,
  isLoading,
  status,
  explanation,
  error,
  autoRun,
  toggle,
  setAutoRun,
  buildQuery,
} = useLLMQueryBuilder()

const inputText = ref('')
const textareaRef = ref<HTMLTextAreaElement | null>(null)

watch(isOpen, async (open) => {
  if (open) {
    await nextTick()
    textareaRef.value?.focus()
  }
})

async function onSearch() {
  await buildQuery(inputText.value)
}

function handleEscape() {
  toggle()
  const toggleBtn = document.querySelector<HTMLButtonElement>('[aria-controls="llm-panel"]')
  toggleBtn?.focus()
}
</script>

<style scoped>
.llm-panel-wrapper {
  width: 100%;
}

/* Toggle — muted at rest, amber on hover/open. Matches sidebar toolbar buttons. */
.llm-panel-toggle {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-2) var(--space-3);
  background: var(--color-surface-raised);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  color: var(--color-text-muted);
  font-size: 0.8rem;
  font-weight: 500;
  cursor: pointer;
  transition: background var(--transition), border-color var(--transition), color var(--transition);
  margin-bottom: var(--space-2);
}

.llm-panel-toggle:hover {
  background: var(--app-primary-light);
  border-color: var(--app-primary);
  color: var(--app-primary);
}

.llm-panel-toggle--open {
  background: var(--app-primary-light);
  border-color: var(--app-primary);
  color: var(--app-primary);
}

/* Panel */
.llm-panel {
  display: none;
  flex-direction: column;
  gap: var(--space-3);
  padding: var(--space-4);
  background: var(--color-surface-raised);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  margin-bottom: var(--space-3);
}

.llm-panel--open {
  display: flex;
}

.llm-panel__label {
  font-size: 0.8rem;
  font-weight: 500;
  color: var(--color-text-muted);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.llm-panel__textarea {
  width: 100%;
  padding: var(--space-2) var(--space-3);
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  color: var(--color-text);
  font-size: 0.9rem;
  resize: vertical;
  font-family: inherit;
}

.llm-panel__textarea:focus {
  outline: 2px solid var(--app-primary);
  outline-offset: 1px;
  border-color: var(--app-primary);
}

.llm-panel__actions {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  flex-wrap: wrap;
}

/* Search button — same amber style as the main Search button */
.llm-panel__search-btn {
  padding: var(--space-2) var(--space-4);
  background: var(--app-primary);
  color: var(--color-text-inverse);
  border: none;
  border-radius: var(--radius-sm);
  font-weight: 600;
  font-size: 0.875rem;
  cursor: pointer;
  transition: background var(--transition);
}

.llm-panel__search-btn:hover:not(:disabled) {
  background: var(--app-primary-hover);
}

.llm-panel__search-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.llm-panel__status-pill {
  font-size: 0.8rem;
  color: var(--color-text-muted);
  font-family: var(--font-mono);
}

.llm-panel__status-pill--idle {
  visibility: hidden;
}

.llm-panel__status-pill--done {
  color: var(--color-success);
}

.llm-panel__status-pill--error {
  color: var(--color-error);
}

@media (prefers-reduced-motion: no-preference) {
  .llm-panel__spinner {
    display: inline-block;
    width: 0.75em;
    height: 0.75em;
    border: 2px solid var(--app-primary);
    border-top-color: transparent;
    border-radius: 50%;
    animation: llm-spin 0.7s linear infinite;
    vertical-align: middle;
    margin-right: 0.25em;
  }
}

@keyframes llm-spin {
  to { transform: rotate(360deg); }
}

.llm-panel__error {
  font-size: 0.85rem;
  color: var(--color-error);
  margin: 0;
}

.llm-panel__explanation {
  font-size: 0.85rem;
  color: var(--color-text-muted);
  margin: 0;
  font-style: italic;
}

.llm-panel__autorun {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  font-size: 0.8rem;
  color: var(--color-text-muted);
  cursor: pointer;
}
</style>

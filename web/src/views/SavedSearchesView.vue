<template>
  <div class="saved-view">
    <header class="saved-header">
      <h1 class="saved-title">Saved Searches</h1>
    </header>

    <div v-if="store.loading" class="saved-state">
      <p class="saved-state-text">Loading…</p>
    </div>

    <div v-else-if="store.error" class="saved-state saved-state--error" role="alert">
      {{ store.error }}
    </div>

    <div v-else-if="!store.items.length" class="saved-state">
      <span class="saved-state-icon" aria-hidden="true">🔖</span>
      <p class="saved-state-text">No saved searches yet.</p>
      <p class="saved-state-hint">Run a search and click <strong>Save</strong> to bookmark it here.</p>
      <RouterLink to="/" class="saved-back">← Go to Search</RouterLink>
    </div>

    <ul v-else class="saved-list" role="list">
      <li v-for="item in store.items" :key="item.id" class="saved-card">
        <div class="saved-card-body">
          <p class="saved-card-name">{{ item.name }}</p>
          <p class="saved-card-query">
            <span class="saved-card-q-label">q:</span>
            {{ item.query }}
          </p>
          <p class="saved-card-meta">
            <span v-if="item.last_run_at">Last run {{ formatDate(item.last_run_at) }}</span>
            <span v-else>Never run</span>
            · Saved {{ formatDate(item.created_at) }}
            <span v-if="item.last_checked_at" class="saved-card-checked">
              · Monitored {{ formatDate(item.last_checked_at) }}
            </span>
          </p>
        </div>

        <div class="saved-card-right">
          <!-- Monitor toggle — only shown to paid+ users -->
          <div v-if="session.isPaid || session.tier === 'local'" class="monitor-section">
            <label class="monitor-toggle-label">
              <input
                type="checkbox"
                class="monitor-toggle-input"
                :checked="item.monitor_enabled"
                :aria-label="`Monitor ${item.name}`"
                @change="onToggleMonitor(item, ($event.target as HTMLInputElement).checked)"
              />
              <span class="monitor-toggle-track" aria-hidden="true" />
              <span class="monitor-toggle-text">Monitor</span>
            </label>

            <!-- Inline settings — only when enabled -->
            <Transition name="slide">
              <div v-if="item.monitor_enabled" class="monitor-settings">
                <label class="monitor-setting-label">
                  Check every
                  <input
                    type="number"
                    class="monitor-setting-input"
                    :value="item.poll_interval_min"
                    min="15"
                    max="1440"
                    step="15"
                    :aria-label="`Poll interval for ${item.name} in minutes`"
                    @change="onIntervalChange(item, ($event.target as HTMLInputElement).valueAsNumber)"
                  />
                  min
                  <span class="monitor-hint">Min 15. 60 = hourly.</span>
                </label>
                <label class="monitor-setting-label">
                  Trust ≥
                  <input
                    type="number"
                    class="monitor-setting-input"
                    :value="item.min_trust_score"
                    min="0"
                    max="100"
                    step="5"
                    :aria-label="`Minimum trust score for ${item.name}`"
                    @change="onThresholdChange(item, ($event.target as HTMLInputElement).valueAsNumber)"
                  />
                  <span class="monitor-hint">0–100. 60 = medium confidence.</span>
                </label>
              </div>
            </Transition>
          </div>

          <div class="saved-card-actions">
            <button class="saved-run-btn" type="button" @click="onRun(item)">
              Run
            </button>
            <button
              class="saved-delete-btn"
              type="button"
              :aria-label="`Delete saved search: ${item.name}`"
              @click="onDelete(item)"
            >
              ✕
            </button>
          </div>
        </div>
      </li>
    </ul>

    <!-- Undo toast for delete -->
    <Transition name="toast">
      <div v-if="pendingDelete" class="undo-toast" role="status" aria-live="polite">
        <span>Deleted "{{ pendingDelete.name }}"</span>
        <button class="undo-btn" @click="onUndoDelete">Undo</button>
      </div>
    </Transition>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter, RouterLink } from 'vue-router'
import { useSavedSearchesStore } from '../stores/savedSearches'
import { useSessionStore } from '../stores/session'
import type { SavedSearch } from '../stores/savedSearches'

const store = useSavedSearchesStore()
const session = useSessionStore()
const router = useRouter()

const BASE = import.meta.env.VITE_API_BASE ?? ''

// Soft-delete state — holds for 3 seconds before committing
const pendingDelete = ref<SavedSearch | null>(null)
let deleteTimer: ReturnType<typeof setTimeout> | null = null

onMounted(() => store.fetchAll())

function formatDate(iso: string | null): string {
  if (!iso) return '—'
  return new Date(iso).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })
}

async function onRun(item: SavedSearch) {
  store.markRun(item.id)
  const query: Record<string, string> = { q: item.query, autorun: '1' }
  if (item.filters_json && item.filters_json !== '{}') query.filters = item.filters_json
  router.push({ path: '/', query })
}

function onDelete(item: SavedSearch) {
  // Soft-delete: show undo toast, commit after 3s.
  if (deleteTimer) clearTimeout(deleteTimer)
  pendingDelete.value = item
  deleteTimer = setTimeout(async () => {
    if (pendingDelete.value?.id === item.id) {
      await store.remove(item.id)
      pendingDelete.value = null
    }
  }, 3000)
}

function onUndoDelete() {
  if (deleteTimer) clearTimeout(deleteTimer)
  pendingDelete.value = null
}

async function onToggleMonitor(item: SavedSearch, enabled: boolean) {
  await fetch(`${BASE}/api/saved-searches/${item.id}/monitor`, {
    method: 'PATCH',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      monitor_enabled: enabled,
      poll_interval_min: item.poll_interval_min,
      min_trust_score: item.min_trust_score,
    }),
  })
  await store.fetchAll()
}

async function onIntervalChange(item: SavedSearch, minutes: number) {
  if (isNaN(minutes) || minutes < 15) return
  await fetch(`${BASE}/api/saved-searches/${item.id}/monitor`, {
    method: 'PATCH',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      monitor_enabled: item.monitor_enabled,
      poll_interval_min: minutes,
      min_trust_score: item.min_trust_score,
    }),
  })
  await store.fetchAll()
}

async function onThresholdChange(item: SavedSearch, score: number) {
  if (isNaN(score)) return
  await fetch(`${BASE}/api/saved-searches/${item.id}/monitor`, {
    method: 'PATCH',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      monitor_enabled: item.monitor_enabled,
      poll_interval_min: item.poll_interval_min,
      min_trust_score: score,
    }),
  })
  await store.fetchAll()
}
</script>

<style scoped>
.saved-view {
  display: flex;
  flex-direction: column;
  min-height: 100dvh;
}

.saved-header {
  padding: var(--space-6);
  border-bottom: 1px solid var(--color-border);
  background: var(--color-surface-2);
}

.saved-title {
  font-family: var(--font-display);
  font-size: 1.25rem;
  color: var(--color-text);
}

/* Empty / loading / error state */
.saved-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-4);
  padding: var(--space-16) var(--space-4);
  text-align: center;
}
.saved-state--error { color: var(--color-error); }
.saved-state-icon { font-size: 2.5rem; }
.saved-state-text { color: var(--color-text-muted); font-size: 0.9375rem; margin: 0; }
.saved-state-hint { color: var(--color-text-muted); font-size: 0.875rem; margin: 0; }
.saved-back {
  color: var(--app-primary);
  text-decoration: none;
  font-weight: 600;
  font-size: 0.875rem;
}
.saved-back:hover { opacity: 0.75; }

/* Card list */
.saved-list {
  list-style: none;
  padding: var(--space-6);
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  max-width: 800px;
}

.saved-card {
  display: flex;
  align-items: flex-start;
  gap: var(--space-4);
  padding: var(--space-4) var(--space-5);
  background: var(--color-surface-2);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  transition: border-color 150ms ease;
}
.saved-card:hover { border-color: var(--app-primary); }

.saved-card-body { flex: 1; min-width: 0; }

.saved-card-name {
  font-weight: 600;
  font-size: 0.9375rem;
  color: var(--color-text);
  margin: 0 0 var(--space-1);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.saved-card-query {
  font-family: var(--font-mono);
  font-size: 0.75rem;
  color: var(--app-primary);
  margin: 0 0 var(--space-1);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.saved-card-q-label {
  color: var(--color-text-muted);
  margin-right: var(--space-1);
}

.saved-card-meta {
  font-size: 0.75rem;
  color: var(--color-text-muted);
  margin: 0;
}

.saved-card-checked {
  color: var(--app-primary);
}

/* Right column: monitor section + action buttons */
.saved-card-right {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: var(--space-3);
  flex-shrink: 0;
}

.saved-card-actions {
  display: flex;
  align-items: center;
  gap: var(--space-2);
}

/* Monitor toggle */
.monitor-section {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: var(--space-2);
}

.monitor-toggle-label {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  cursor: pointer;
  user-select: none;
}

/* Visually hide the native checkbox but keep it accessible */
.monitor-toggle-input {
  position: absolute;
  width: 1px;
  height: 1px;
  opacity: 0;
  pointer-events: none;
}

.monitor-toggle-track {
  display: inline-block;
  width: 32px;
  height: 18px;
  border-radius: 9px;
  background: var(--color-border);
  position: relative;
  transition: background 150ms ease;
  flex-shrink: 0;
}

.monitor-toggle-track::after {
  content: '';
  position: absolute;
  top: 2px;
  left: 2px;
  width: 14px;
  height: 14px;
  border-radius: 50%;
  background: #fff;
  transition: transform 150ms ease;
}

.monitor-toggle-input:checked + .monitor-toggle-track {
  background: var(--app-primary);
}

.monitor-toggle-input:checked + .monitor-toggle-track::after {
  transform: translateX(14px);
}

/* Focus ring on the label when the hidden checkbox is focused */
.monitor-toggle-label:has(.monitor-toggle-input:focus-visible) .monitor-toggle-track {
  outline: 2px solid var(--app-primary);
  outline-offset: 2px;
}

.monitor-toggle-text {
  font-size: 0.8125rem;
  color: var(--color-text-muted);
  white-space: nowrap;
}

/* Inline monitor settings */
.monitor-settings {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  padding: var(--space-3);
  background: var(--color-surface);
  border: 1px solid var(--color-border-light);
  border-radius: var(--radius-md);
  font-size: 0.8125rem;
  color: var(--color-text-muted);
}

.monitor-setting-label {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  flex-wrap: wrap;
}

.monitor-setting-input {
  width: 60px;
  padding: var(--space-1) var(--space-2);
  background: var(--color-surface-2);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  color: var(--color-text);
  font-family: var(--font-mono);
  font-size: 0.8125rem;
  text-align: center;
}

.monitor-hint {
  font-size: 0.6875rem;
  color: var(--color-text-muted);
  opacity: 0.75;
}

.saved-run-btn {
  padding: var(--space-2) var(--space-4);
  background: var(--app-primary);
  border: none;
  border-radius: var(--radius-md);
  color: var(--color-text-inverse);
  font-family: var(--font-body);
  font-size: 0.875rem;
  font-weight: 600;
  cursor: pointer;
  transition: background 150ms ease;
}
.saved-run-btn:hover { background: var(--app-primary-hover); }

.saved-delete-btn {
  padding: var(--space-2);
  background: transparent;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  color: var(--color-text-muted);
  font-size: 0.75rem;
  line-height: 1;
  cursor: pointer;
  transition: border-color 150ms ease, color 150ms ease;
  min-width: 28px;
  min-height: 28px;
}
.saved-delete-btn:hover { border-color: var(--color-error); color: var(--color-error); }

/* Undo toast */
.undo-toast {
  position: fixed;
  bottom: calc(var(--space-6) + env(safe-area-inset-bottom));
  left: 50%;
  transform: translateX(-50%);
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-3) var(--space-5);
  background: var(--color-surface-2);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  box-shadow: 0 4px 16px rgba(0,0,0,0.4);
  font-size: 0.875rem;
  color: var(--color-text);
  z-index: 300;
  white-space: nowrap;
}

.undo-btn {
  padding: var(--space-1) var(--space-3);
  background: var(--app-primary);
  border: none;
  border-radius: var(--radius-sm);
  color: var(--color-text-inverse);
  font-family: var(--font-body);
  font-size: 0.8125rem;
  font-weight: 600;
  cursor: pointer;
}

/* Transitions */
.slide-enter-active,
.slide-leave-active { transition: opacity 150ms ease, max-height 200ms ease; max-height: 200px; overflow: hidden; }
.slide-enter-from,
.slide-leave-to    { opacity: 0; max-height: 0; }

.toast-enter-active,
.toast-leave-active { transition: opacity 200ms ease, transform 200ms ease; }
.toast-enter-from,
.toast-leave-to    { opacity: 0; transform: translateX(-50%) translateY(8px); }

@media (prefers-reduced-motion: reduce) {
  .slide-enter-active, .slide-leave-active,
  .toast-enter-active, .toast-leave-active { transition: none; }
}

@media (max-width: 767px) {
  .saved-header { padding: var(--space-4); }
  .saved-list { padding: var(--space-4); }
  .saved-card { flex-direction: column; align-items: flex-start; gap: var(--space-3); }
  .saved-card-right { width: 100%; align-items: flex-start; }
  .saved-card-actions { width: 100%; justify-content: flex-end; }
  .monitor-section { width: 100%; align-items: flex-start; }
  .monitor-settings { width: 100%; }
}
</style>

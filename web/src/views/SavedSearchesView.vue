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
          </p>
        </div>
        <div class="saved-card-actions">
          <button class="saved-run-btn" type="button" @click="onRun(item)">
            Run
          </button>
          <button
            class="saved-delete-btn"
            type="button"
            :aria-label="`Delete saved search: ${item.name}`"
            @click="onDelete(item.id)"
          >
            ✕
          </button>
        </div>
      </li>
    </ul>
  </div>
</template>

<script setup lang="ts">
import { onMounted } from 'vue'
import { useRouter, RouterLink } from 'vue-router'
import { useSavedSearchesStore } from '../stores/savedSearches'
import type { SavedSearch } from '../stores/savedSearches'

const store = useSavedSearchesStore()
const router = useRouter()

onMounted(() => store.fetchAll())

function formatDate(iso: string | null): string {
  if (!iso) return '—'
  const d = new Date(iso)
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })
}

async function onRun(item: SavedSearch) {
  store.markRun(item.id)
  const query: Record<string, string> = { q: item.query }
  if (item.filters_json && item.filters_json !== '{}') query.filters = item.filters_json
  router.push({ path: '/', query })
}

async function onDelete(id: number) {
  await store.remove(id)
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
  max-width: 720px;
}

.saved-card {
  display: flex;
  align-items: center;
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

.saved-card-actions {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  flex-shrink: 0;
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
}
.saved-delete-btn:hover { border-color: var(--color-error); color: var(--color-error); }

@media (max-width: 767px) {
  .saved-header { padding: var(--space-4); }
  .saved-list { padding: var(--space-4); }
  .saved-card { flex-direction: column; align-items: flex-start; gap: var(--space-3); }
  .saved-card-actions { width: 100%; justify-content: flex-end; }
}
</style>

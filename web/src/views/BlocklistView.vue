<template>
  <div class="blocklist-view">
    <header class="blocklist-header">
      <div class="blocklist-header__title-row">
        <h1 class="blocklist-title">Scammer Blocklist</h1>
        <span class="blocklist-count" v-if="!store.loading">
          {{ store.entries.length }} {{ store.entries.length === 1 ? 'entry' : 'entries' }}
        </span>
      </div>
      <p class="blocklist-desc">
        Sellers on this list are force-scored to 0 and flagged as bad actors on every search.
        Use the block button on any listing card to add sellers.
      </p>

      <div class="blocklist-actions">
        <button class="bl-btn bl-btn--secondary" @click="onExport" :disabled="store.entries.length === 0">
          ↓ Export CSV
        </button>
        <label class="bl-btn bl-btn--secondary bl-btn--upload">
          ↑ Import CSV
          <input type="file" accept=".csv,text/csv" class="sr-only" @change="onImport" />
        </label>
      </div>
      <p v-if="importResult" class="import-result" :class="{ 'import-result--error': importResult.errors.length }">
        Imported {{ importResult.imported }} sellers.
        <span v-if="importResult.errors.length">
          {{ importResult.errors.length }} row(s) skipped.
        </span>
      </p>
    </header>

    <div v-if="store.loading" class="blocklist-empty">Loading…</div>

    <div v-else-if="store.error" class="blocklist-empty blocklist-empty--error">
      {{ store.error }}
    </div>

    <div v-else-if="store.entries.length === 0" class="blocklist-empty">
      No blocked sellers yet. Use the ⚑ button on any listing card to add one.
    </div>

    <table v-else class="bl-table">
      <thead>
        <tr>
          <th>Seller</th>
          <th>Reason</th>
          <th>Source</th>
          <th>Added</th>
          <th aria-label="Remove"></th>
        </tr>
      </thead>
      <tbody>
        <tr
          v-for="entry in store.entries"
          :key="entry.platform_seller_id"
          class="bl-table__row"
        >
          <td class="bl-table__seller">
            <span class="bl-table__username">{{ entry.username }}</span>
            <span class="bl-table__id">{{ entry.platform_seller_id }}</span>
          </td>
          <td class="bl-table__reason">{{ entry.reason || '—' }}</td>
          <td class="bl-table__source">
            <span class="bl-source-badge" :class="`bl-source-badge--${entry.source}`">
              {{ sourceLabel(entry.source) }}
            </span>
          </td>
          <td class="bl-table__date">{{ formatDate(entry.created_at) }}</td>
          <td class="bl-table__remove">
            <button
              class="bl-remove-btn"
              title="Remove from blocklist"
              @click="onRemove(entry.platform_seller_id)"
            >✕</button>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useBlocklistStore } from '../stores/blocklist'

const store = useBlocklistStore()
const importResult = ref<{ imported: number; errors: string[] } | null>(null)

onMounted(() => store.fetchBlocklist())

async function onRemove(sellerId: string) {
  await store.removeSeller(sellerId)
}

async function onExport() {
  await store.exportCsv()
}

async function onImport(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  importResult.value = null
  try {
    importResult.value = await store.importCsv(file)
  } catch {
    importResult.value = { imported: 0, errors: ['Upload failed — check file format'] }
  } finally {
    input.value = ''
  }
}

function sourceLabel(source: string): string {
  const map: Record<string, string> = {
    manual:      'Manual',
    csv_import:  'CSV',
    community:   'Community',
  }
  return map[source] ?? source
}

function formatDate(iso: string | null): string {
  if (!iso) return '—'
  return new Date(iso).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })
}
</script>

<style scoped>
.blocklist-view {
  max-width: 860px;
  margin: 0 auto;
  padding: var(--space-6) var(--space-4);
}

.blocklist-header {
  margin-bottom: var(--space-6);
}

.blocklist-header__title-row {
  display: flex;
  align-items: baseline;
  gap: var(--space-3);
  margin-bottom: var(--space-2);
}

.blocklist-title {
  font-size: 1.5rem;
  font-weight: 700;
  margin: 0;
}

.blocklist-count {
  font-size: 0.875rem;
  color: var(--color-text-muted);
}

.blocklist-desc {
  font-size: 0.875rem;
  color: var(--color-text-muted);
  margin: 0 0 var(--space-4);
  line-height: 1.5;
}

.blocklist-actions {
  display: flex;
  gap: var(--space-2);
  flex-wrap: wrap;
}

.bl-btn {
  padding: var(--space-2) var(--space-3);
  border-radius: var(--radius-md);
  font-size: 0.8125rem;
  font-weight: 500;
  cursor: pointer;
  transition: background 150ms ease, opacity 150ms ease;
}

.bl-btn--secondary {
  background: var(--color-surface-raised);
  border: 1px solid var(--color-border);
  color: var(--color-text);
}

.bl-btn--secondary:hover:not(:disabled) {
  background: var(--color-surface-2);
  border-color: var(--app-primary);
  color: var(--app-primary);
}

.bl-btn--secondary:disabled {
  opacity: 0.45;
  cursor: default;
}

.bl-btn--upload {
  display: inline-flex;
  align-items: center;
  cursor: pointer;
}

.import-result {
  margin-top: var(--space-3);
  font-size: 0.8125rem;
  color: var(--color-success, var(--trust-high));
}

.import-result--error {
  color: var(--color-warning);
}

.blocklist-empty {
  text-align: center;
  padding: var(--space-10) var(--space-4);
  color: var(--color-text-muted);
  font-size: 0.9375rem;
}

.blocklist-empty--error {
  color: var(--color-error);
}

/* Table */
.bl-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.875rem;
}

.bl-table thead th {
  text-align: left;
  font-size: 0.75rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--color-text-muted);
  border-bottom: 1px solid var(--color-border);
  padding: var(--space-2) var(--space-3);
}

.bl-table__row {
  border-bottom: 1px solid var(--color-border);
  transition: background 120ms ease;
}

.bl-table__row:hover {
  background: var(--color-surface-raised);
}

.bl-table__row td {
  padding: var(--space-3);
  vertical-align: middle;
}

.bl-table__seller {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.bl-table__username {
  font-weight: 600;
  color: var(--color-text);
}

.bl-table__id {
  font-size: 0.75rem;
  color: var(--color-text-muted);
  font-family: var(--font-mono);
}

.bl-table__reason {
  color: var(--color-text-muted);
  max-width: 280px;
}

.bl-table__date {
  white-space: nowrap;
  color: var(--color-text-muted);
}

.bl-source-badge {
  padding: 2px var(--space-2);
  border-radius: var(--radius-sm);
  font-size: 0.7rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.bl-source-badge--manual    { background: color-mix(in srgb, var(--color-info) 15%, transparent); color: var(--color-info); }
.bl-source-badge--csv_import { background: color-mix(in srgb, var(--color-accent) 15%, transparent); color: var(--color-accent); }
.bl-source-badge--community  { background: color-mix(in srgb, var(--color-success) 15%, transparent); color: var(--color-success); }

.bl-remove-btn {
  background: none;
  border: 1px solid transparent;
  border-radius: var(--radius-sm);
  color: var(--color-text-muted);
  cursor: pointer;
  font-size: 0.75rem;
  padding: 2px var(--space-2);
  transition: color 120ms ease, border-color 120ms ease;
}

.bl-remove-btn:hover {
  color: var(--color-error);
  border-color: var(--color-error);
}

/* Mobile */
@media (max-width: 600px) {
  .bl-table thead th:nth-child(3),
  .bl-table tbody td:nth-child(3) {
    display: none;
  }
}
</style>

<template>
  <div class="alert-bell-wrap" ref="wrapRef">
    <!-- Bell trigger button -->
    <button
      ref="bellRef"
      class="alert-bell"
      :class="{ 'alert-bell--active': panelOpen }"
      :aria-label="unreadCount > 0 ? `${unreadCount} new watch alert${unreadCount === 1 ? '' : 's'}` : 'Watch alerts'"
      :aria-expanded="panelOpen"
      aria-haspopup="true"
      @click="togglePanel"
    >
      <BellIcon class="alert-bell__icon" aria-hidden="true" />
      <span
        v-if="unreadCount > 0"
        class="alert-badge"
        aria-hidden="true"
      >{{ unreadCount > 99 ? '99+' : unreadCount }}</span>
    </button>

    <!-- Polite live region — announces count changes without moving focus -->
    <div aria-live="polite" aria-atomic="true" class="sr-only">
      {{ liveAnnouncement }}
    </div>

    <!-- Alert panel -->
    <Transition name="panel">
      <div
        v-if="panelOpen"
        class="alert-panel"
        role="dialog"
        aria-label="Watch alerts"
        aria-modal="false"
      >
        <div class="alert-panel__header">
          <span class="alert-panel__title">Watch Alerts</span>
          <button
            v-if="store.alerts.length > 0"
            class="alert-panel__clear"
            @click="onDismissAll"
          >
            Clear all
          </button>
          <button
            class="alert-panel__close"
            aria-label="Close alerts panel"
            @click="closePanel"
          >
            ✕
          </button>
        </div>

        <div v-if="store.loading" class="alert-panel__state">
          Loading…
        </div>

        <div v-else-if="store.alerts.length === 0" class="alert-panel__state">
          <span aria-hidden="true">🔔</span>
          <p>No new alerts. Enable monitoring on a saved search to get notified.</p>
        </div>

        <ul v-else class="alert-list" role="list">
          <li
            v-for="alert in store.alerts"
            :key="alert.id"
            class="alert-card"
          >
            <div class="alert-card__body">
              <p class="alert-card__title">{{ alert.title }}</p>
              <div class="alert-card__meta">
                <span class="alert-card__price">${{ alert.price.toFixed(2) }}</span>
                <span class="alert-card__score" :class="scoreClass(alert.trust_score)">
                  Trust {{ alert.trust_score }}
                </span>
              </div>
            </div>
            <div class="alert-card__actions">
              <a
                v-if="alert.url"
                :href="alert.url"
                target="_blank"
                rel="noopener noreferrer"
                class="alert-card__view"
                :aria-label="`View listing: ${alert.title}`"
              >
                View on eBay
              </a>
              <button
                class="alert-card__dismiss"
                :aria-label="`Dismiss alert: ${alert.title}`"
                @click="onDismiss(alert.id)"
                @keydown.delete.prevent="onDismiss(alert.id)"
              >
                ✕
              </button>
            </div>
          </li>
        </ul>
      </div>
    </Transition>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { BellIcon } from '@heroicons/vue/24/outline'
import { useAlertsStore } from '../stores/alerts'

const store = useAlertsStore()
const panelOpen = ref(false)
const bellRef = ref<HTMLButtonElement | null>(null)
const wrapRef = ref<HTMLDivElement | null>(null)
const liveAnnouncement = ref('')

const unreadCount = computed(() => store.unreadCount)

// Announce count changes to screen readers via the polite live region.
watch(unreadCount, (count, prev) => {
  if (count > prev) {
    liveAnnouncement.value = `${count} new watch alert${count === 1 ? '' : 's'}`
    // Reset after announcement so repeat counts still fire.
    setTimeout(() => { liveAnnouncement.value = '' }, 1500)
  }
})

function togglePanel() {
  panelOpen.value = !panelOpen.value
  if (panelOpen.value) store.fetchAlerts()
}

function closePanel() {
  panelOpen.value = false
  bellRef.value?.focus()
}

async function onDismiss(id: number) {
  await store.dismiss(id)
  if (store.alerts.length === 0) {
    // Return focus to bell when last alert is dismissed.
    panelOpen.value = false
    bellRef.value?.focus()
  }
}

async function onDismissAll() {
  await store.dismissAll()
  panelOpen.value = false
  bellRef.value?.focus()
}

function scoreClass(score: number) {
  if (score >= 75) return 'score--high'
  if (score >= 50) return 'score--medium'
  return 'score--low'
}

// Close on outside click.
function handleOutsideClick(e: MouseEvent) {
  if (wrapRef.value && !wrapRef.value.contains(e.target as Node)) {
    panelOpen.value = false
  }
}

onMounted(() => {
  store.fetchAlerts()
  // Poll for new alerts every 2 minutes while the app is open.
  const interval = setInterval(() => store.fetchAlerts(), 120_000)
  document.addEventListener('click', handleOutsideClick)
  onBeforeUnmount(() => {
    clearInterval(interval)
    document.removeEventListener('click', handleOutsideClick)
  })
})
</script>

<style scoped>
.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border: 0;
}

.alert-bell-wrap {
  position: relative;
}

.alert-bell {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 40px;
  height: 40px;
  background: transparent;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  color: var(--color-text-muted);
  cursor: pointer;
  transition: border-color 150ms ease, color 150ms ease, background 150ms ease;
}

.alert-bell:hover,
.alert-bell--active {
  border-color: var(--app-primary);
  color: var(--app-primary);
  background: var(--app-primary-light);
}

.alert-bell__icon {
  width: 1.25rem;
  height: 1.25rem;
}

.alert-badge {
  position: absolute;
  top: -6px;
  right: -6px;
  min-width: 18px;
  height: 18px;
  padding: 0 4px;
  background: var(--color-error, #ef4444);
  color: #fff;
  font-size: 0.625rem;
  font-weight: 700;
  font-family: var(--font-mono);
  border-radius: 9px;
  display: flex;
  align-items: center;
  justify-content: center;
  line-height: 1;
}

/* Panel */
.alert-panel {
  position: absolute;
  top: calc(100% + 8px);
  right: 0;
  width: min(360px, 92vw);
  background: var(--color-surface-2);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.4);
  z-index: 200;
  overflow: hidden;
}

.alert-panel__header {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-3) var(--space-4);
  border-bottom: 1px solid var(--color-border);
}

.alert-panel__title {
  flex: 1;
  font-weight: 600;
  font-size: 0.875rem;
  color: var(--color-text);
}

.alert-panel__clear {
  font-size: 0.75rem;
  color: var(--color-text-muted);
  background: none;
  border: none;
  cursor: pointer;
  padding: var(--space-1) var(--space-2);
  border-radius: var(--radius-sm);
  transition: color 150ms ease;
}
.alert-panel__clear:hover { color: var(--color-error); }

.alert-panel__close {
  background: none;
  border: none;
  color: var(--color-text-muted);
  font-size: 0.75rem;
  cursor: pointer;
  padding: var(--space-1);
  border-radius: var(--radius-sm);
  line-height: 1;
  transition: color 150ms ease;
  min-width: 24px;
  min-height: 24px;
}
.alert-panel__close:hover { color: var(--color-error); }

.alert-panel__state {
  padding: var(--space-8) var(--space-4);
  text-align: center;
  color: var(--color-text-muted);
  font-size: 0.875rem;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-2);
}

/* Alert list */
.alert-list {
  list-style: none;
  max-height: 360px;
  overflow-y: auto;
}

.alert-card {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-3) var(--space-4);
  border-bottom: 1px solid var(--color-border-light);
  transition: background 150ms ease;
}
.alert-card:hover { background: var(--color-surface); }
.alert-card:last-child { border-bottom: none; }

.alert-card__body { flex: 1; min-width: 0; }

.alert-card__title {
  font-size: 0.8125rem;
  color: var(--color-text);
  margin: 0 0 var(--space-1);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.alert-card__meta {
  display: flex;
  gap: var(--space-2);
  align-items: center;
}

.alert-card__price {
  font-family: var(--font-mono);
  font-size: 0.75rem;
  color: var(--app-primary);
}

.alert-card__score {
  font-size: 0.6875rem;
  font-weight: 600;
  padding: 1px var(--space-2);
  border-radius: var(--radius-sm);
}
.score--high  { background: rgba(34,197,94,0.15); color: #22c55e; }
.score--medium { background: rgba(234,179,8,0.15); color: #eab308; }
.score--low   { background: rgba(239,68,68,0.15);  color: #ef4444; }

.alert-card__actions {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  flex-shrink: 0;
}

.alert-card__view {
  font-size: 0.75rem;
  color: var(--app-primary);
  text-decoration: none;
  white-space: nowrap;
  padding: var(--space-1) var(--space-2);
  border-radius: var(--radius-sm);
  transition: background 150ms ease;
}
.alert-card__view:hover { background: var(--app-primary-light); }

.alert-card__dismiss {
  background: none;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  color: var(--color-text-muted);
  font-size: 0.625rem;
  cursor: pointer;
  min-width: 24px;
  min-height: 24px;
  transition: border-color 150ms ease, color 150ms ease;
}
.alert-card__dismiss:hover { border-color: var(--color-error); color: var(--color-error); }

/* Transition */
.panel-enter-active,
.panel-leave-active { transition: opacity 120ms ease, transform 120ms ease; }
.panel-enter-from,
.panel-leave-to    { opacity: 0; transform: translateY(-6px); }

@media (prefers-reduced-motion: reduce) {
  .panel-enter-active,
  .panel-leave-active { transition: none; }
}
</style>

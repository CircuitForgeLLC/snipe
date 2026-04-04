<template>
  <!-- Desktop: persistent sidebar (≥1024px) -->
  <!-- Mobile: bottom tab bar (<1024px) -->
  <nav class="app-sidebar" role="navigation" aria-label="Main navigation">
    <!-- Brand -->
    <div class="sidebar__brand">
      <RouterLink to="/" class="sidebar__logo">
        <span class="sidebar__target" aria-hidden="true">🎯</span>
        <span class="sidebar__wordmark">Snipe</span>
      </RouterLink>
    </div>

    <!-- Nav links -->
    <ul class="sidebar__links" role="list">
      <li v-for="link in navLinks" :key="link.to">
        <RouterLink
          :to="link.to"
          class="sidebar__link"
          active-class="sidebar__link--active"
          :aria-label="link.label"
        >
          <component :is="link.icon" class="sidebar__icon" aria-hidden="true" />
          <span class="sidebar__label">{{ link.label }}</span>
        </RouterLink>
      </li>
    </ul>

    <!-- Snipe mode exit (shows when active) -->
    <div v-if="isSnipeMode" class="sidebar__snipe-exit">
      <button class="sidebar__snipe-btn" @click="deactivate">
        Exit snipe mode
      </button>
    </div>

    <!-- Settings at bottom -->
    <div class="sidebar__footer">
      <RouterLink to="/settings" class="sidebar__link sidebar__link--footer" active-class="sidebar__link--active">
        <Cog6ToothIcon class="sidebar__icon" aria-hidden="true" />
        <span class="sidebar__label">Settings</span>
      </RouterLink>
    </div>
  </nav>

  <!-- Mobile bottom tab bar -->
  <nav class="app-tabbar" role="navigation" aria-label="Main navigation">
    <ul class="tabbar__links" role="list">
      <li v-for="link in mobileLinks" :key="link.to">
        <RouterLink
          :to="link.to"
          class="tabbar__link"
          active-class="tabbar__link--active"
          :aria-label="link.label"
        >
          <component :is="link.icon" class="tabbar__icon" aria-hidden="true" />
          <span class="tabbar__label">{{ link.label }}</span>
        </RouterLink>
      </li>
    </ul>
  </nav>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { RouterLink } from 'vue-router'
import {
  MagnifyingGlassIcon,
  BookmarkIcon,
  Cog6ToothIcon,
  ShieldExclamationIcon,
} from '@heroicons/vue/24/outline'
import { useSnipeMode } from '../composables/useSnipeMode'

const { active: isSnipeMode, deactivate } = useSnipeMode()

const navLinks = computed(() => [
  { to: '/',          icon: MagnifyingGlassIcon,    label: 'Search' },
  { to: '/saved',     icon: BookmarkIcon,            label: 'Saved' },
  { to: '/blocklist', icon: ShieldExclamationIcon,   label: 'Blocklist' },
])

const mobileLinks = [
  { to: '/',          icon: MagnifyingGlassIcon,    label: 'Search' },
  { to: '/saved',     icon: BookmarkIcon,            label: 'Saved' },
  { to: '/blocklist', icon: ShieldExclamationIcon,   label: 'Block' },
  { to: '/settings',  icon: Cog6ToothIcon,           label: 'Settings' },
]
</script>

<style scoped>
/* ── Sidebar (desktop ≥1024px) ──────────────────────── */
.app-sidebar {
  position: fixed;
  top: 0;
  left: 0;
  bottom: 0;
  width: var(--sidebar-width);
  display: flex;
  flex-direction: column;
  background: var(--color-surface-2);
  border-right: 1px solid var(--color-border);
  z-index: 100;
  padding: var(--space-4) 0;
}

.sidebar__brand {
  padding: 0 var(--space-4) var(--space-4);
  border-bottom: 1px solid var(--color-border-light);
  margin-bottom: var(--space-3);
}

.sidebar__logo {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  text-decoration: none;
}

.sidebar__target {
  font-size: 1.5rem;
  line-height: 1;
  flex-shrink: 0;
}

.sidebar__wordmark {
  font-family: var(--font-display);
  font-weight: 700;
  font-size: 1.35rem;
  color: var(--app-primary);
  letter-spacing: -0.01em;
}

.sidebar__links {
  flex: 1;
  list-style: none;
  margin: 0;
  padding: 0 var(--space-3);
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  overflow-y: auto;
}

.sidebar__link {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-3) var(--space-4);
  border-radius: var(--radius-md);
  color: var(--color-text-muted);
  text-decoration: none;
  font-size: 0.875rem;
  font-weight: 500;
  min-height: 44px;  /* WCAG 2.5.5 touch target */
  transition:
    background 150ms ease,
    color      150ms ease;
}

.sidebar__link:hover {
  background: var(--app-primary-light);
  color: var(--app-primary);
}

.sidebar__link--active {
  background: var(--app-primary-light);
  color: var(--app-primary);
  font-weight: 600;
}

.sidebar__icon {
  width: 1.25rem;
  height: 1.25rem;
  flex-shrink: 0;
}

/* Snipe mode exit button */
.sidebar__snipe-exit {
  padding: var(--space-3);
  border-top: 1px solid var(--color-border-light);
}

.sidebar__snipe-btn {
  width: 100%;
  padding: var(--space-2) var(--space-3);
  background: transparent;
  border: 1px solid var(--app-primary);
  border-radius: var(--radius-md);
  color: var(--app-primary);
  font-family: var(--font-mono);
  font-size: 0.75rem;
  cursor: pointer;
  transition: background 150ms ease, color 150ms ease;
}

.sidebar__snipe-btn:hover {
  background: var(--app-primary);
  color: var(--color-surface);
}

.sidebar__footer {
  padding: var(--space-3) var(--space-3) 0;
  border-top: 1px solid var(--color-border-light);
}

/* ── Mobile tab bar (<1024px) ───────────────────────── */
.app-tabbar {
  display: none;
  position: fixed;
  bottom: 0;
  left: 0;
  right: 0;
  background: var(--color-surface-2);
  border-top: 1px solid var(--color-border);
  z-index: 100;
  padding-bottom: env(safe-area-inset-bottom);
}

.tabbar__links {
  display: flex;
  list-style: none;
  margin: 0;
  padding: 0;
}

.tabbar__link {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 2px;
  padding: var(--space-2) var(--space-1);
  min-height: 56px;  /* WCAG 2.5.5 touch target */
  color: var(--color-text-muted);
  text-decoration: none;
  font-size: 10px;
  transition: color 150ms ease;
}

.tabbar__link--active { color: var(--app-primary); }
.tabbar__icon { width: 1.5rem; height: 1.5rem; }

/* ── Responsive ─────────────────────────────────────── */
@media (max-width: 1023px) {
  .app-sidebar { display: none; }
  .app-tabbar  { display: block; }
}
</style>

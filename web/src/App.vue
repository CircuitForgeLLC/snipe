<template>
  <!-- Root uses .app-root class, NOT id="app" — index.html owns #app.
       Nested #app elements cause ambiguous CSS specificity. Gotcha #1. -->
  <div class="app-root" :class="{ 'rich-motion': motion.rich.value }">
    <!-- Skip to main content — must be first focusable element before the nav -->
    <a href="#main-content" class="skip-link">Skip to main content</a>
    <AppNav />
    <main class="app-main" id="main-content" tabindex="-1">
      <RouterView />
    </main>

    <!-- Feedback FAB — hidden when FORGEJO_API_TOKEN not configured -->
    <FeedbackButton :current-view="String(route.name ?? 'unknown')" />
  </div>
</template>

<script setup lang="ts">
import { onMounted } from 'vue'
import { RouterView, useRoute } from 'vue-router'
import { useMotion } from './composables/useMotion'
import { useSnipeMode } from './composables/useSnipeMode'
import { useKonamiCode } from './composables/useKonamiCode'
import { useSessionStore } from './stores/session'
import { useBlocklistStore } from './stores/blocklist'
import { usePreferencesStore } from './stores/preferences'
import AppNav from './components/AppNav.vue'
import FeedbackButton from './components/FeedbackButton.vue'

const motion = useMotion()
const { activate, restore } = useSnipeMode()
const session = useSessionStore()
const blocklistStore = useBlocklistStore()
const preferencesStore = usePreferencesStore()
const route = useRoute()

useKonamiCode(activate)

onMounted(async () => {
  restore()                           // re-apply snipe mode from localStorage on hard reload
  await session.bootstrap()           // fetch tier + feature flags from API
  blocklistStore.fetchBlocklist()     // pre-load so card block buttons reflect state immediately
  preferencesStore.load()             // load user preferences after session resolves
})
</script>

<style>
/* Global resets — unscoped, applied once to document */
*, *::before, *::after {
  box-sizing: border-box;
  margin: 0;
  padding: 0;
}

html {
  font-family: var(--font-body, sans-serif);
  color: var(--color-text, #e6edf3);
  background: var(--color-surface, #0d1117);
  overflow-x: clip;  /* no BFC side effects. Gotcha #3. */
}

body {
  min-height: 100dvh;   /* dynamic viewport — mobile chrome-aware. Gotcha #13. */
  overflow-x: hidden;
}

#app { min-height: 100dvh; }

/* Layout root — sidebar pushes content right on desktop */
.app-root {
  display: flex;
  min-height: 100dvh;
}

/* Main content area */
.app-main {
  flex: 1;
  min-width: 0;  /* prevents flex blowout */
  /* Desktop: offset by sidebar width */
  margin-left: var(--sidebar-width, 220px);
}

/* Skip-to-content link — visible only on keyboard focus */
.skip-link {
  position: absolute;
  top: -999px;
  left: var(--space-4);
  background: var(--app-primary);
  color: var(--color-text-inverse);
  padding: var(--space-2) var(--space-4);
  border-radius: var(--radius-md);
  font-weight: 600;
  z-index: 9999;
  text-decoration: none;
  transition: top 0ms;
}

.skip-link:focus {
  top: var(--space-4);
}

/* Mobile: no sidebar margin, add bottom tab bar clearance */
@media (max-width: 1023px) {
  .app-main {
    margin-left: 0;
    padding-bottom: calc(56px + env(safe-area-inset-bottom));
  }
}
</style>

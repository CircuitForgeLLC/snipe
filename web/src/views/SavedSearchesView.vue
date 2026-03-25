<template>
  <div class="saved-view">
    <div class="placeholder">
      <span class="placeholder__icon" aria-hidden="true">🔖</span>
      <h1 class="placeholder__title">Saved Searches</h1>
      <p class="placeholder__body">Coming soon — save searches and get background monitoring alerts when new matching listings appear.</p>
      <RouterLink to="/" class="placeholder__back">← Back to Search</RouterLink>
    </div>
  </div>
</template>

<script setup lang="ts">
import { RouterLink } from 'vue-router'
</script>

<style scoped>
.saved-view {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 60dvh;
  padding: var(--space-8);
}

.placeholder {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-4);
  text-align: center;
  max-width: 480px;
}

.placeholder__icon { font-size: 3rem; }

.placeholder__title {
  font-family: var(--font-display);
  font-size: 1.5rem;
  color: var(--app-primary);
}

.placeholder__body {
  color: var(--color-text-muted);
  line-height: 1.6;
}

.placeholder__back {
  color: var(--app-primary);
  text-decoration: none;
  font-weight: 600;
  transition: opacity 150ms ease;
}

.placeholder__back:hover { opacity: 0.75; }
</style>

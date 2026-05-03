<template>
  <div class="search-progress" role="status" aria-label="Search in progress" aria-live="polite">
    <!-- Indeterminate progress bar -->
    <div class="progress-track" aria-hidden="true">
      <div class="progress-bar"></div>
    </div>

    <!-- Status line -->
    <p class="progress-label">
      Searching <strong>{{ platformLabel }}</strong> for <strong>{{ query }}</strong>…
    </p>

    <!-- Skeleton listing cards -->
    <div class="skeleton-list" aria-hidden="true">
      <div v-for="n in 4" :key="n" class="skeleton-card">
        <div class="skeleton-thumb"></div>
        <div class="skeleton-body">
          <div class="skeleton-line skeleton-line--title"></div>
          <div class="skeleton-line skeleton-line--meta"></div>
          <div class="skeleton-footer">
            <div class="skeleton-chip"></div>
            <div class="skeleton-chip skeleton-chip--price"></div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{ query: string; platform?: string }>()

const PLATFORM_LABELS: Record<string, string> = {
  ebay: 'eBay',
  mercari: 'Mercari',
  poshmark: 'Poshmark',
}

const platformLabel = computed(() =>
  PLATFORM_LABELS[props.platform ?? 'ebay'] ?? props.platform ?? 'eBay'
)
</script>

<style scoped>
.search-progress {
  padding: var(--space-6);
  display: flex;
  flex-direction: column;
  gap: var(--space-5);
}

/* ── Indeterminate progress bar ───────────────── */
.progress-track {
  height: 3px;
  background: var(--color-surface-raised);
  border-radius: var(--radius-full);
  overflow: hidden;
}

.progress-bar {
  height: 100%;
  width: 40%;
  background: var(--app-primary);
  border-radius: var(--radius-full);
  animation: progress-slide 1.6s ease-in-out infinite;
}

@keyframes progress-slide {
  0%   { transform: translateX(-100%); }
  100% { transform: translateX(300%); }
}

/* ── Status label ─────────────────────────────── */
.progress-label {
  font-size: 0.875rem;
  color: var(--color-text-muted);
  margin: 0;
}

.progress-label strong {
  color: var(--color-text);
  font-weight: 600;
}

/* ── Skeleton cards ───────────────────────────── */
.skeleton-list {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.skeleton-card {
  display: flex;
  gap: var(--space-4);
  padding: var(--space-4);
  background: var(--color-surface-2);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
}

.skeleton-thumb {
  width: 100px;
  height: 80px;
  flex-shrink: 0;
  background: var(--color-surface-raised);
  border-radius: var(--radius-md);
  animation: shimmer 1.8s ease-in-out infinite;
}

.skeleton-body {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  justify-content: center;
}

.skeleton-line {
  height: 12px;
  background: var(--color-surface-raised);
  border-radius: var(--radius-sm);
  animation: shimmer 1.8s ease-in-out infinite;
}

.skeleton-line--title {
  width: 70%;
  height: 14px;
}

.skeleton-line--meta {
  width: 45%;
}

.skeleton-footer {
  display: flex;
  gap: var(--space-2);
  margin-top: var(--space-1);
}

.skeleton-chip {
  height: 22px;
  width: 64px;
  background: var(--color-surface-raised);
  border-radius: var(--radius-full);
  animation: shimmer 1.8s ease-in-out infinite;
}

.skeleton-chip--price {
  width: 80px;
}

/* Stagger shimmer so cards don't all pulse in sync */
.skeleton-card:nth-child(2) .skeleton-line,
.skeleton-card:nth-child(2) .skeleton-thumb,
.skeleton-card:nth-child(2) .skeleton-chip { animation-delay: 0.15s; }

.skeleton-card:nth-child(3) .skeleton-line,
.skeleton-card:nth-child(3) .skeleton-thumb,
.skeleton-card:nth-child(3) .skeleton-chip { animation-delay: 0.3s; }

.skeleton-card:nth-child(4) .skeleton-line,
.skeleton-card:nth-child(4) .skeleton-thumb,
.skeleton-card:nth-child(4) .skeleton-chip { animation-delay: 0.45s; }

@keyframes shimmer {
  0%, 100% { opacity: 1; }
  50%       { opacity: 0.4; }
}

@media (max-width: 480px) {
  .skeleton-thumb {
    width: 72px;
    height: 60px;
  }

  .skeleton-line--title { width: 85%; }
}
</style>

<template>
  <article
    class="listing-card"
    :class="{
      'steal-card': isSteal,
      'listing-card--auction': isAuction && hoursRemaining !== null && hoursRemaining > 1,
    }"
  >
    <!-- Thumbnail -->
    <div class="card__thumb">
      <img
        v-if="listing.photo_urls.length"
        :src="listing.photo_urls[0]"
        :alt="listing.title"
        class="card__img"
        loading="lazy"
        @error="imgFailed = true"
      />
      <div v-if="!listing.photo_urls.length || imgFailed" class="card__img-placeholder" aria-hidden="true">
        📷
      </div>
    </div>

    <!-- Main info -->
    <div class="card__body">
      <!-- Title row -->
      <a :href="listing.url" target="_blank" rel="noopener noreferrer" class="card__title">
        {{ listing.title }}
      </a>

      <!-- Format + condition badges -->
      <div class="card__badges">
        <span v-if="isAuction" class="auction-badge" :title="auctionEndsLabel">
          ⏱ {{ auctionCountdown }}
        </span>
        <span v-else class="fixed-price-badge">Fixed Price</span>
        <span v-if="listing.buying_format === 'best_offer'" class="fixed-price-badge">Best Offer</span>
        <span class="card__condition">{{ conditionLabel }}</span>
      </div>

      <!-- Seller info -->
      <p class="card__seller" v-if="seller">
        <span class="card__seller-name">{{ seller.username }}</span>
        · {{ seller.feedback_count }} feedback
        · {{ (seller.feedback_ratio * 100).toFixed(1) }}%
        · {{ accountAgeLabel }}
      </p>
      <p class="card__seller" v-else>
        <span class="card__seller-name">{{ listing.seller_platform_id }}</span>
        <span class="card__seller-unavail">· seller data unavailable</span>
      </p>

      <!-- Red flag badges -->
      <div v-if="redFlags.length" class="card__flags" role="list" aria-label="Risk flags">
        <span
          v-for="flag in redFlags"
          :key="flag"
          class="card__flag-badge"
          role="listitem"
        >
          {{ flagLabel(flag) }}
        </span>
      </div>
      <p v-if="pendingSignalNames.length" class="card__score-pending">
        ↻ Updating: {{ pendingSignalNames.join(', ') }}
      </p>
      <p v-if="!trust" class="card__partial-warning">
        ⚠ Could not score this listing
      </p>
    </div>

    <!-- Score + price column -->
    <div class="card__score-col">
      <!-- Trust score badge -->
      <div
        class="card__trust"
        :class="[trustClass, { 'card__trust--partial': trust?.score_is_partial }]"
        :title="trustBadgeTitle"
      >
        <span class="card__trust-num">{{ trust?.composite_score ?? '?' }}</span>
        <span class="card__trust-label">Trust</span>
        <!-- Signal dots: one per scoring signal, grey = pending -->
        <span v-if="trust" class="card__signal-dots" aria-hidden="true">
          <span
            v-for="dot in signalDots"
            :key="dot.key"
            class="card__signal-dot"
            :class="dot.pending ? 'card__signal-dot--pending' : 'card__signal-dot--present'"
            :title="dot.label"
          />
        </span>
        <!-- Jump the queue: force enrichment for this seller -->
        <button
          v-if="pendingSignalNames.length"
          class="card__enrich-btn"
          :class="{ 'card__enrich-btn--spinning': enriching, 'card__enrich-btn--error': enrichError }"
          :title="enrichError ? 'Enrichment failed — try again' : 'Refresh score now'"
          :disabled="enriching"
          @click.stop="onEnrich"
        >{{ enrichError ? '✗' : '↻' }}</button>
      </div>

      <!-- Price -->
      <div class="card__price-wrap">
        <span
          class="card__price"
          :class="{ 'auction-price--live': isAuction && hoursRemaining !== null && hoursRemaining > 1 }"
        >
          {{ formattedPrice }}
        </span>
        <span v-if="marketPrice && isSteal" class="card__steal-label">
          🎯 Steal
        </span>
        <span v-if="marketPrice" class="card__market-price" title="Median market price">
          market ~{{ formattedMarket }}
        </span>
      </div>
    </div>
  </article>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import type { Listing, TrustScore, Seller } from '../stores/search'
import { useSearchStore } from '../stores/search'

const props = defineProps<{
  listing: Listing
  trust: TrustScore | null
  seller: Seller | null
  marketPrice: number | null
}>()

const store = useSearchStore()
const enriching = ref(false)
const enrichError = ref(false)

async function onEnrich() {
  if (enriching.value) return
  enriching.value = true
  enrichError.value = false
  try {
    await store.enrichSeller(props.listing.seller_platform_id, props.listing.platform_listing_id)
  } catch {
    enrichError.value = true
  } finally {
    enriching.value = false
  }
}

const imgFailed = ref(false)

// ── Computed helpers ─────────────────────────────────────────────────────────

const isAuction = computed(() => props.listing.buying_format === 'auction')

const hoursRemaining = computed<number | null>(() => {
  if (!props.listing.ends_at) return null
  const ms = new Date(props.listing.ends_at).getTime() - Date.now()
  return ms > 0 ? ms / 3_600_000 : 0
})

const auctionCountdown = computed(() => {
  const h = hoursRemaining.value
  if (h === null) return 'Auction'
  if (h <= 0) return 'Ended'
  if (h < 1) return `${Math.round(h * 60)}m left`
  if (h < 24) return `${h.toFixed(1)}h left`
  return `${Math.floor(h / 24)}d left`
})

const auctionEndsLabel = computed(() =>
  props.listing.ends_at
    ? `Ends ${new Date(props.listing.ends_at).toLocaleString()}`
    : 'Auction',
)

const conditionLabel = computed(() => {
  const map: Record<string, string> = {
    new: 'New',
    like_new: 'Like New',
    very_good: 'Very Good',
    good: 'Good',
    acceptable: 'Acceptable',
    for_parts: 'For Parts',
  }
  return map[props.listing.condition] ?? props.listing.condition
})

const accountAgeLabel = computed(() => {
  if (!props.seller) return ''
  const days = props.seller.account_age_days
  if (days == null) return 'member'
  if (days >= 365) return `${Math.floor(days / 365)}yr member`
  return `${days}d member`
})

const redFlags = computed<string[]>(() => {
  try {
    return JSON.parse(props.trust?.red_flags_json ?? '[]')
  } catch {
    return []
  }
})

function flagLabel(flag: string): string {
  const labels: Record<string, string> = {
    new_account:           '✗ New account',
    account_under_30_days: '⚠ Account <30d',
    low_feedback_count:    '⚠ Low feedback',
    suspicious_price:      '✗ Suspicious price',
    duplicate_photo:       '✗ Duplicate photo',
    established_bad_actor: '✗ Bad actor',
    marketing_photo:       '✗ Marketing photo',
  }
  return labels[flag] ?? `⚠ ${flag}`
}

const trustClass = computed(() => {
  const s = props.trust?.composite_score
  if (s == null) return 'card__trust--unknown'
  if (s >= 80) return 'card__trust--high'
  if (s >= 50) return 'card__trust--mid'
  return 'card__trust--low'
})

interface SignalDot { key: string; label: string; pending: boolean }

const signalDots = computed<SignalDot[]>(() => {
  const agePending = props.seller?.account_age_days == null
  const catPending = !props.seller || props.seller.category_history_json === '{}'
  const mktPending = props.marketPrice == null
  return [
    { key: 'feedback_count',    label: 'Feedback count',    pending: false },
    { key: 'feedback_ratio',    label: 'Feedback ratio',    pending: false },
    { key: 'account_age',       label: agePending ? 'Account age: pending' : 'Account age',        pending: agePending },
    { key: 'price_vs_market',   label: mktPending ? 'Market price: pending' : 'vs market price',  pending: mktPending },
    { key: 'category_history',  label: catPending ? 'Category history: pending' : 'Category history', pending: catPending },
  ]
})

const pendingSignalNames = computed<string[]>(() => {
  if (!props.trust?.score_is_partial) return []
  return signalDots.value.filter(d => d.pending).map(d => d.label.replace(': pending', ''))
})

const trustBadgeTitle = computed(() => {
  const base = `Trust score: ${props.trust?.composite_score ?? '?'}/100`
  if (!pendingSignalNames.value.length) return base
  return `${base} · pending: ${pendingSignalNames.value.join(', ')} (search again to update)`
})

const isSteal = computed(() => {
  const s = props.trust?.composite_score
  if (!s || s < 80) return false
  if (!props.marketPrice) return false
  return props.listing.price < props.marketPrice * 0.8
})

const formattedPrice = computed(() => {
  const sym = props.listing.currency === 'USD' ? '$' : props.listing.currency + ' '
  return `${sym}${props.listing.price.toLocaleString('en-US', { minimumFractionDigits: 0, maximumFractionDigits: 2 })}`
})

const formattedMarket = computed(() => {
  if (!props.marketPrice) return ''
  return `$${props.marketPrice.toLocaleString('en-US', { maximumFractionDigits: 0 })}`
})
</script>

<style scoped>
.listing-card {
  display: grid;
  grid-template-columns: 80px 1fr auto;
  gap: var(--space-3);
  padding: var(--space-4);
  background: var(--color-surface-2);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  position: relative;
  overflow: hidden;
  transition: border-color 150ms ease, box-shadow 150ms ease;
}

.listing-card:hover {
  border-color: var(--app-primary);
  box-shadow: var(--shadow-md);
}

/* Thumbnail */
.card__thumb {
  width: 80px;
  height: 80px;
  border-radius: var(--radius-md);
  overflow: hidden;
  flex-shrink: 0;
  background: var(--color-surface-raised);
  display: flex;
  align-items: center;
  justify-content: center;
}

.card__img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.card__img-placeholder {
  font-size: 2rem;
  opacity: 0.4;
}

/* Body */
.card__body {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}

.card__title {
  font-weight: 600;
  font-size: 0.9375rem;
  color: var(--color-text);
  text-decoration: none;
  line-height: 1.4;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.card__title:hover { color: var(--app-primary); text-decoration: underline; }

.card__badges {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-1);
  align-items: center;
}

.card__condition {
  font-size: 0.75rem;
  color: var(--color-text-muted);
  padding: 2px var(--space-2);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-full);
}

.card__seller {
  font-size: 0.8125rem;
  color: var(--color-text-muted);
  margin: 0;
}

.card__seller-name { color: var(--color-text); font-weight: 500; }
.card__seller-unavail { font-style: italic; }

.card__flags {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-1);
}

.card__flag-badge {
  background: rgba(248, 81, 73, 0.15);
  color: var(--color-error);
  border: 1px solid rgba(248, 81, 73, 0.3);
  padding: 1px var(--space-2);
  border-radius: var(--radius-sm);
  font-size: 0.6875rem;
  font-weight: 600;
}

.card__partial-warning {
  font-size: 0.75rem;
  color: var(--color-warning);
  margin: 0;
}

.card__score-pending {
  font-size: 0.7rem;
  color: var(--color-text-muted);
  margin: 0;
  font-style: italic;
}

/* Score + price column */
.card__score-col {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: var(--space-2);
  min-width: 72px;
}

.card__trust {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: var(--space-1) var(--space-2);
  border-radius: var(--radius-md);
  border: 1.5px solid currentColor;
  min-width: 52px;
}

.card__trust-num {
  font-family: var(--font-mono);
  font-size: 1.1rem;
  font-weight: 700;
  line-height: 1;
}

.card__trust-label {
  font-size: 0.625rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  opacity: 0.8;
}

.card__trust--high { color: var(--trust-high); }
.card__trust--mid  { color: var(--trust-mid); }
.card__trust--low  { color: var(--trust-low); }
.card__trust--unknown { color: var(--color-text-muted); }

.card__trust--partial {
  animation: trust-pulse 2.5s ease-in-out infinite;
}
@keyframes trust-pulse {
  0%, 100% { opacity: 1; }
  50%       { opacity: 0.55; }
}

.card__signal-dots {
  display: flex;
  gap: 3px;
  margin-top: 4px;
  justify-content: center;
}
.card__signal-dot {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  flex-shrink: 0;
}
.card__signal-dot--present { background: currentColor; opacity: 0.7; }
.card__signal-dot--pending { background: var(--color-border); opacity: 1; }

.card__enrich-btn {
  margin-top: 4px;
  background: none;
  border: 1px solid currentColor;
  border-radius: var(--radius-sm);
  color: currentColor;
  cursor: pointer;
  font-size: 0.65rem;
  line-height: 1;
  opacity: 0.6;
  padding: 1px 4px;
  transition: opacity 150ms ease;
}
.card__enrich-btn:hover:not(:disabled) { opacity: 1; }
.card__enrich-btn:disabled { cursor: default; }
.card__enrich-btn--spinning { animation: enrich-spin 0.8s linear infinite; }
.card__enrich-btn--error { color: var(--color-error); opacity: 1; }
@keyframes enrich-spin {
  from { transform: rotate(0deg); }
  to   { transform: rotate(360deg); }
}

.card__price-wrap {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 2px;
}

.card__price {
  font-family: var(--font-mono);
  font-size: 1.1rem;
  font-weight: 700;
  color: var(--color-text);
}

.card__steal-label {
  font-size: 0.7rem;
  font-weight: 700;
  color: var(--trust-high);
  text-transform: uppercase;
  letter-spacing: 0.06em;
}

.card__market-price {
  font-size: 0.7rem;
  color: var(--color-text-muted);
  font-family: var(--font-mono);
}

/* Mobile: stack vertically */
@media (max-width: 600px) {
  .listing-card {
    grid-template-columns: 60px 1fr;
    grid-template-rows: auto auto;
  }

  .card__score-col {
    grid-column: 1 / -1;
    flex-direction: row;
    justify-content: space-between;
    align-items: center;
    min-width: unset;
    padding-top: var(--space-2);
    border-top: 1px solid var(--color-border);
  }
}
</style>

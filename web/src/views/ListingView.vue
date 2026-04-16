<template>
  <div class="listing-view">

    <!-- Not found — store was cleared (page refresh or direct URL) -->
    <div v-if="!listing" class="lv-empty">
      <span class="lv-empty__icon" aria-hidden="true">🎯</span>
      <h1 class="lv-empty__title">Listing not found</h1>
      <p class="lv-empty__body">
        Search results are held in session memory.
        Return to search and click a listing to view its trust breakdown.
      </p>
      <RouterLink to="/" class="lv-empty__back">← Back to Search</RouterLink>
    </div>

    <template v-else>

      <!-- Back link -->
      <RouterLink to="/" class="lv-back">← Back to results</RouterLink>

      <div class="lv-layout" :class="{ 'lv-layout--triple-red': tripleRed }">

        <!-- Photo carousel -->
        <section class="lv-photos" aria-label="Listing photos">
          <div v-if="listing.photo_urls.length" class="lv-carousel">
            <img
              :src="listing.photo_urls[photoIdx]"
              :alt="`Photo ${photoIdx + 1} of ${listing.photo_urls.length}: ${listing.title}`"
              class="lv-carousel__img"
              @error="onImgError"
            />
            <div v-if="listing.photo_urls.length > 1" class="lv-carousel__controls">
              <button
                class="lv-carousel__btn"
                aria-label="Previous photo"
                :disabled="photoIdx === 0"
                @click="photoIdx--"
              >‹</button>
              <span class="lv-carousel__counter">{{ photoIdx + 1 }} / {{ listing.photo_urls.length }}</span>
              <button
                class="lv-carousel__btn"
                aria-label="Next photo"
                :disabled="photoIdx === listing.photo_urls.length - 1"
                @click="photoIdx++"
              >›</button>
            </div>
          </div>
          <div v-else class="lv-carousel lv-carousel--empty" aria-hidden="true">📷</div>
        </section>

        <!-- Main content -->
        <div class="lv-content">

          <!-- Header -->
          <header class="lv-header">
            <h1 class="lv-title">{{ listing.title }}</h1>
            <div class="lv-price-row">
              <span class="lv-price">{{ formattedPrice }}</span>
              <span v-if="store.marketPrice" class="lv-market">
                market ~{{ formattedMarket }}
              </span>
              <span v-if="isSteal" class="lv-steal-badge">🎯 Potential steal</span>
            </div>
            <div class="lv-badges">
              <span class="lv-badge">{{ conditionLabel }}</span>
              <span class="lv-badge">{{ formatLabel }}</span>
              <span v-if="listing.category_name" class="lv-badge">{{ listing.category_name }}</span>
              <span v-if="isAuction && listing.ends_at" class="lv-badge lv-badge--auction">
                ⏱ Ends {{ auctionEnds }}
              </span>
            </div>
          </header>

          <!-- Red flags -->
          <div v-if="redFlags.length" class="lv-flags" role="list" aria-label="Risk flags">
            <span
              v-for="flag in redFlags"
              :key="flag"
              class="lv-flag"
              :class="hardFlags.has(flag) ? 'lv-flag--hard' : 'lv-flag--soft'"
              role="listitem"
            >{{ flagLabel(flag) }}</span>
          </div>

          <!-- Trust score: ring + verdict + signal table -->
          <section class="lv-trust" aria-labelledby="trust-heading">
            <h2 id="trust-heading" class="lv-section-heading">Trust Score</h2>

            <div class="lv-ring-row">
              <!-- SVG ring -->
              <div class="lv-ring" :class="ringClass" role="img" :aria-label="`Trust score: ${scoreDisplay} out of 100`">
                <svg width="88" height="88" viewBox="0 0 88 88" aria-hidden="true">
                  <circle cx="44" cy="44" r="36" fill="none" stroke="var(--ring-track)" stroke-width="8"/>
                  <circle
                    v-if="trust && trust.composite_score != null"
                    cx="44" cy="44" r="36"
                    fill="none"
                    :stroke="ringColor"
                    stroke-width="8"
                    stroke-linecap="round"
                    :stroke-dasharray="`${ringFill} 226.2`"
                    transform="rotate(-90 44 44)"
                  />
                </svg>
                <div class="lv-ring__center">
                  <span class="lv-ring__score" :style="{ color: ringColor }">{{ scoreDisplay }}</span>
                  <span class="lv-ring__denom">/ 100</span>
                </div>
              </div>

              <!-- Verdict -->
              <div class="lv-verdict">
                <p class="lv-verdict__label" :style="{ color: ringColor }">{{ verdictLabel }}</p>
                <p class="lv-verdict__text">{{ verdictText }}</p>
                <p v-if="trust?.score_is_partial" class="lv-verdict__partial">
                  ↻ Some signals are still loading — run again to update
                </p>
              </div>
            </div>

            <!-- Signal table -->
            <table class="lv-signals" aria-label="Trust signal breakdown">
              <thead>
                <tr>
                  <th scope="col" class="lv-signals__col-name">Signal</th>
                  <th scope="col" class="lv-signals__col-bar" aria-hidden="true"></th>
                  <th scope="col" class="lv-signals__col-score">Score</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="sig in signals" :key="sig.key" class="lv-signals__row">
                  <td class="lv-signals__name">{{ sig.label }}</td>
                  <td class="lv-signals__bar" aria-hidden="true">
                    <div class="lv-mini-bar">
                      <div
                        class="lv-mini-bar__fill"
                        :class="sig.pending ? 'lv-mini-bar__fill--pending' : barClass(sig.score)"
                        :style="{ width: sig.pending ? '8%' : `${(sig.score / 20) * 100}%` }"
                      ></div>
                    </div>
                  </td>
                  <td class="lv-signals__score">
                    <span v-if="sig.pending" class="lv-sig-pending">↻ pending</span>
                    <span v-else>{{ sig.score }} / 20</span>
                  </td>
                </tr>
              </tbody>
            </table>
          </section>

          <!-- Seller panel -->
          <section v-if="seller" class="lv-seller" aria-label="Seller information">
            <h2 class="lv-section-heading">Seller</h2>
            <div class="lv-seller__panel">
              <div class="lv-seller__avatar" aria-hidden="true">👤</div>
              <div class="lv-seller__info">
                <p class="lv-seller__name">{{ seller.username }}</p>
                <p class="lv-seller__stats">
                  {{ seller.feedback_count.toLocaleString() }} feedback
                  · {{ (seller.feedback_ratio * 100).toFixed(1) }}% positive
                </p>
                <p class="lv-seller__age" v-if="seller.account_age_days != null">
                  Account age: {{ accountAgeLabel }}
                </p>
                <p class="lv-seller__age lv-seller__age--unknown" v-else>
                  Account age: pending enrichment
                </p>
              </div>
            </div>
          </section>

          <!-- Actions -->
          <div class="lv-actions">
            <a
              :href="listing.url"
              target="_blank"
              rel="noopener noreferrer"
              class="lv-btn-primary"
            >↗ View on eBay</a>
            <button
              v-if="seller"
              class="lv-btn-secondary"
              type="button"
              @click="blockingOpen = !blockingOpen"
            >⊘ Block seller</button>
          </div>

          <!-- Block seller inline form -->
          <div v-if="blockingOpen && seller" class="lv-block-form" role="dialog" aria-label="Block seller">
            <p class="lv-block-form__title">Block <strong>{{ seller.username }}</strong>?</p>
            <input
              v-model="blockReason"
              class="lv-block-form__input"
              placeholder="Reason (optional)"
              aria-label="Reason for blocking seller (optional)"
              maxlength="200"
              @keydown.enter="onBlock"
              @keydown.escape="blockingOpen = false"
            />
            <div class="lv-block-form__btns">
              <button class="lv-block-form__confirm" type="button" @click="onBlock">Block</button>
              <button class="lv-block-form__cancel" type="button" @click="blockingOpen = false; blockReason = ''">Cancel</button>
            </div>
            <p v-if="blockError" class="lv-block-form__error" role="alert">{{ blockError }}</p>
          </div>

        </div><!-- /lv-content -->
      </div><!-- /lv-layout -->
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { useRoute, RouterLink } from 'vue-router'
import { useSearchStore } from '../stores/search'

const RING_CIRCUMFERENCE = 226.2   // 2π × r=36

const route  = useRoute()
const store  = useSearchStore()
const id     = route.params.id as string

const listing = computed(() => store.getListing(id))
const trust   = computed(() => store.trustScores.get(id) ?? null)
const seller  = computed(() => {
  if (!listing.value) return null
  return store.sellers.get(listing.value.seller_platform_id) ?? null
})

// ── Photo carousel ───────────────────────────────────────────────────────────

const photoIdx = ref(0)

function onImgError() {
  // Skip broken photos by advancing to next; if at end, go back
  const max = (listing.value?.photo_urls.length ?? 1) - 1
  if (photoIdx.value < max) photoIdx.value++
  else if (photoIdx.value > 0) photoIdx.value--
}

// ── Price / format helpers ───────────────────────────────────────────────────

const formattedPrice = computed(() => {
  if (!listing.value) return ''
  const sym = listing.value.currency === 'USD' ? '$' : listing.value.currency + ' '
  return `${sym}${listing.value.price.toLocaleString('en-US', { minimumFractionDigits: 0, maximumFractionDigits: 2 })}`
})

const formattedMarket = computed(() =>
  store.marketPrice
    ? `$${store.marketPrice.toLocaleString('en-US', { maximumFractionDigits: 0 })}`
    : ''
)

const isSteal = computed(() => {
  const s = trust.value?.composite_score
  if (!s || s < 80 || !store.marketPrice || !listing.value) return false
  return listing.value.price < store.marketPrice * 0.8
})

const isAuction = computed(() => listing.value?.buying_format === 'auction')

const auctionEnds = computed(() => {
  const end = listing.value?.ends_at
  if (!end) return ''
  return new Date(end).toLocaleString('en-US', { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' })
})

const conditionLabel = computed(() => {
  const c = listing.value?.condition ?? ''
  const map: Record<string, string> = {
    new:           'New',
    open_box:      'Open Box',
    used_excellent:'Used – Excellent',
    used_good:     'Used – Good',
    used_fair:     'Used – Fair',
    for_parts:     'For Parts',
  }
  return map[c] ?? c
})

const formatLabel = computed(() => {
  const f = listing.value?.buying_format ?? 'fixed_price'
  if (f === 'auction') return 'Auction'
  if (f === 'best_offer') return 'Best Offer'
  return 'Fixed Price'
})

// ── Red flags ────────────────────────────────────────────────────────────────

const FLAG_LABELS: Record<string, string> = {
  new_account:            '✗ New account',
  account_under_30_days:  '⚠ Account <30d',
  low_feedback_count:     '⚠ Low feedback',
  suspicious_price:       '✗ Suspicious price',
  duplicate_photo:        '✗ Duplicate photo',
  established_bad_actor:  '✗ Known bad actor',
  zero_feedback:          '✗ No feedback',
  marketing_photo:        '✗ Marketing photo',
  scratch_dent_mentioned: '⚠ Damage mentioned',
  long_on_market:         '⚠ Long on market',
  significant_price_drop: '⚠ Price dropped',
}

const HARD_FLAGS = new Set([
  'new_account', 'established_bad_actor', 'zero_feedback', 'suspicious_price', 'duplicate_photo',
])

const hardFlags = HARD_FLAGS

function flagLabel(flag: string): string {
  return FLAG_LABELS[flag] ?? `⚠ ${flag}`
}

const redFlags = computed<string[]>(() => {
  try { return JSON.parse(trust.value?.red_flags_json ?? '[]') } catch { return [] }
})

// ── Score ring ───────────────────────────────────────────────────────────────

const scoreDisplay = computed(() => trust.value?.composite_score ?? '?')

const ringColor = computed(() => {
  const s = trust.value?.composite_score
  if (s == null) return 'var(--color-text-muted)'
  if (s >= 80)   return 'var(--trust-high)'
  if (s >= 50)   return 'var(--trust-mid)'
  return 'var(--trust-low)'
})

const ringClass = computed(() => {
  const s = trust.value?.composite_score
  if (s == null) return 'lv-ring--unknown'
  if (s >= 80)   return 'lv-ring--high'
  if (s >= 50)   return 'lv-ring--mid'
  return 'lv-ring--low'
})

const ringFill = computed(() => {
  const s = trust.value?.composite_score
  if (s == null) return 0
  return (s / 100) * RING_CIRCUMFERENCE
})

// ── Verdict ──────────────────────────────────────────────────────────────────

const verdictLabel = computed(() => {
  const s = trust.value?.composite_score
  if (s == null)  return 'Unscored'
  if (s >= 80)    return 'Looks trustworthy'
  if (s >= 50)    return 'Moderate risk'
  return 'High risk'
})

const verdictText = computed(() => {
  const s   = trust.value?.composite_score
  const f   = new Set(redFlags.value)
  const sel = seller.value

  if (s == null) return 'No trust data available for this listing.'

  const parts: string[] = []

  if (f.has('established_bad_actor')) return 'This seller is on your blocklist. Do not proceed.'
  if (f.has('zero_feedback')) parts.push('seller has no feedback history')
  if (f.has('new_account'))   parts.push('account is less than a week old')
  else if (f.has('account_under_30_days') && sel)
    parts.push(`account is only ${sel.account_age_days} days old`)
  if (f.has('suspicious_price'))          parts.push('price is suspiciously below market')
  else if (trust.value?.price_vs_market_score === 0 && store.marketPrice)
                                          parts.push('price is above the market median')
  if (f.has('duplicate_photo')) parts.push('photo appears in other listings')
  if (f.has('scratch_dent_mentioned')) parts.push('title mentions damage or wear')
  if (f.has('long_on_market')) parts.push('listing has been sitting for a while')
  if (f.has('significant_price_drop')) parts.push('price has dropped significantly since first seen')

  if (s >= 80 && parts.length === 0)
    return 'Strong seller history and clean signals across the board.'
  if (parts.length === 0)
    return 'No specific red flags, but some signals are weak or pending.'

  const list = parts.map((p, i) => (i === 0 ? p[0].toUpperCase() + p.slice(1) : p))
  return list.join(', ') + '.'
})

// ── Signal table ─────────────────────────────────────────────────────────────

interface Signal { key: string; label: string; score: number; pending: boolean }

const signals = computed<Signal[]>(() => {
  const t   = trust.value
  const sel = seller.value
  return [
    {
      key: 'feedback_count', label: 'Feedback Volume',
      score: t?.feedback_count_score ?? 0,
      pending: false,
    },
    {
      key: 'feedback_ratio', label: 'Feedback Ratio',
      score: t?.feedback_ratio_score ?? 0,
      pending: false,
    },
    {
      key: 'account_age', label: 'Account Age',
      score: t?.account_age_score ?? 0,
      pending: sel?.account_age_days == null,
    },
    {
      key: 'price_vs_market', label: 'Price vs Market',
      score: t?.price_vs_market_score ?? 0,
      pending: store.marketPrice == null,
    },
    {
      key: 'category_history', label: 'Category History',
      score: t?.category_history_score ?? 0,
      pending: !sel || sel.category_history_json === '{}',
    },
  ]
})

function barClass(score: number): string {
  if (score >= 16) return 'lv-mini-bar__fill--high'
  if (score >= 8)  return 'lv-mini-bar__fill--mid'
  return 'lv-mini-bar__fill--low'
}

// ── Triple Red easter egg ────────────────────────────────────────────────────

const tripleRed = computed(() => {
  const f = new Set(redFlags.value)
  const hasAccountFlag = f.has('new_account') || f.has('account_under_30_days')
  const hasPriceFlag   = f.has('suspicious_price')
  const hasThirdFlag   = f.has('duplicate_photo') || f.has('established_bad_actor') ||
                         f.has('zero_feedback')   || f.has('scratch_dent_mentioned')
  return hasAccountFlag && hasPriceFlag && hasThirdFlag
})

// ── Seller account age label ─────────────────────────────────────────────────

const accountAgeLabel = computed(() => {
  const d = seller.value?.account_age_days
  if (d == null)   return 'unknown'
  if (d < 30)      return `${d} days`
  if (d < 365)     return `${Math.floor(d / 30)} months`
  const y = Math.floor(d / 365)
  const m = Math.floor((d % 365) / 30)
  return m > 0 ? `${y}y ${m}mo` : `${y} year${y !== 1 ? 's' : ''}`
})

// ── Block seller ─────────────────────────────────────────────────────────────

const blockingOpen = ref(false)
const blockReason  = ref('')
const blockError   = ref('')

const apiBase = import.meta.env.VITE_API_BASE ?? ''

async function onBlock() {
  if (!seller.value) return
  blockError.value = ''
  try {
    const res = await fetch(`${apiBase}/api/blocklist`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        platform: seller.value.platform,
        platform_seller_id: seller.value.platform_seller_id,
        username: seller.value.username,
        reason: blockReason.value.trim() || null,
        source: 'manual',
      }),
    })
    if (!res.ok) {
      const body = await res.json().catch(() => ({}))
      blockError.value = body.detail ?? `Error ${res.status}`
      return
    }
    blockingOpen.value = false
    blockReason.value  = ''
  } catch {
    blockError.value = 'Network error — try again'
  }
}
</script>

<style scoped>
.listing-view {
  max-width: 900px;
  margin: 0 auto;
  padding: var(--space-6) var(--space-4);
}

/* ── Empty / not-found ── */
.lv-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-4);
  text-align: center;
  padding: var(--space-16) var(--space-8);
}
.lv-empty__icon   { font-size: 3rem; }
.lv-empty__title  { font-family: var(--font-display); font-size: 1.5rem; color: var(--app-primary); }
.lv-empty__body   { color: var(--color-text-muted); line-height: 1.6; max-width: 400px; }
.lv-empty__back   { color: var(--app-primary); font-weight: 600; text-decoration: none; }
.lv-empty__back:hover { opacity: 0.75; }

/* ── Back link ── */
.lv-back {
  display: inline-block;
  color: var(--color-text-muted);
  text-decoration: none;
  font-size: 0.85rem;
  margin-bottom: var(--space-4);
  transition: color var(--transition);
}
.lv-back:hover { color: var(--app-primary); }

/* ── Layout ── */
.lv-layout {
  display: grid;
  grid-template-columns: 260px 1fr;
  gap: var(--space-6);
  align-items: start;
}

/* Triple Red: pulsing red glow around the whole card */
.lv-layout--triple-red {
  border-radius: var(--radius-lg);
  animation: triple-red-pulse 1.8s ease-in-out infinite;
}
@keyframes triple-red-pulse {
  0%, 100% { box-shadow: 0 0 0 0 rgba(248,81,73,0); }
  50%       { box-shadow: 0 0 0 8px rgba(248,81,73,0.25); }
}
@media (prefers-reduced-motion: reduce) {
  .lv-layout--triple-red { animation: none; box-shadow: 0 0 0 2px rgba(248,81,73,0.4); }
}

/* ── Photo carousel ── */
.lv-photos { position: sticky; top: var(--space-4); }

.lv-carousel {
  background: var(--color-surface-2);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  overflow: hidden;
  display: flex;
  flex-direction: column;
}
.lv-carousel--empty {
  height: 220px;
  align-items: center;
  justify-content: center;
  font-size: 3rem;
  color: var(--color-text-muted);
}
.lv-carousel__img {
  width: 100%;
  aspect-ratio: 1;
  object-fit: contain;
  background: var(--color-surface-2);
}
.lv-carousel__controls {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--space-3);
  padding: var(--space-2) var(--space-4);
  border-top: 1px solid var(--color-border);
}
.lv-carousel__btn {
  background: none;
  border: none;
  color: var(--color-text-muted);
  font-size: 1.25rem;
  cursor: pointer;
  padding: var(--space-1) var(--space-2);
  border-radius: var(--radius-sm);
  transition: color var(--transition);
  line-height: 1;
}
.lv-carousel__btn:hover:not(:disabled) { color: var(--app-primary); }
.lv-carousel__btn:disabled { opacity: 0.3; cursor: default; }
.lv-carousel__counter { font-size: 0.75rem; color: var(--color-text-muted); font-family: var(--font-mono); }

/* ── Content column ── */
.lv-content { display: flex; flex-direction: column; gap: var(--space-5); min-width: 0; }

/* ── Header ── */
.lv-title {
  font-family: var(--font-display);
  font-size: 1.2rem;
  line-height: 1.4;
  color: var(--color-text);
  margin-bottom: var(--space-2);
  overflow-wrap: break-word;
  word-break: break-word;
}
.lv-price-row { display: flex; align-items: baseline; gap: var(--space-3); flex-wrap: wrap; margin-bottom: var(--space-2); }
.lv-price {
  font-family: var(--font-mono);
  font-size: 1.6rem;
  font-weight: 700;
  color: var(--app-primary);
}
.lv-market { font-size: 0.8rem; color: var(--color-text-muted); }
.lv-steal-badge {
  font-size: 0.72rem;
  padding: 0.2rem 0.6rem;
  border-radius: var(--radius-full);
  background: rgba(63,185,80,0.15);
  color: var(--trust-high);
  border: 1px solid rgba(63,185,80,0.3);
  font-weight: 600;
}
.lv-badges { display: flex; flex-wrap: wrap; gap: var(--space-2); }
.lv-badge {
  font-size: 0.72rem;
  padding: 0.2rem 0.6rem;
  border-radius: var(--radius-full);
  background: var(--color-surface-raised);
  border: 1px solid var(--color-border);
  color: var(--color-text-muted);
}
.lv-badge--auction { color: var(--color-warning); border-color: rgba(210,153,34,0.3); background: rgba(210,153,34,0.1); }

/* ── Red flags ── */
.lv-flags { display: flex; flex-wrap: wrap; gap: var(--space-2); }
.lv-flag {
  font-size: 0.72rem;
  padding: 0.2rem 0.6rem;
  border-radius: var(--radius-full);
  font-weight: 600;
}
.lv-flag--hard { background: rgba(248,81,73,0.12); color: var(--trust-low); border: 1px solid rgba(248,81,73,0.3); }
.lv-flag--soft { background: rgba(210,153,34,0.1); color: var(--trust-mid); border: 1px solid rgba(210,153,34,0.3); }

/* ── Section heading ── */
.lv-section-heading {
  font-size: 0.65rem;
  text-transform: uppercase;
  letter-spacing: 0.1em;
  color: var(--color-text-muted);
  font-weight: 600;
  margin-bottom: var(--space-3);
}

/* ── Trust section ── */
.lv-trust {
  background: var(--color-surface-2);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  padding: var(--space-4);
}

/* ── Ring row ── */
.lv-ring-row { display: flex; align-items: center; gap: var(--space-5); margin-bottom: var(--space-4); }

.lv-ring {
  position: relative;
  width: 88px;
  height: 88px;
  flex-shrink: 0;
}
.lv-ring--high { --ring-track: rgba(63,185,80,0.12); }
.lv-ring--mid  { --ring-track: rgba(210,153,34,0.12); }
.lv-ring--low  { --ring-track: rgba(248,81,73,0.12); }
.lv-ring--unknown { --ring-track: var(--color-surface-raised); }

.lv-ring__center {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
}
.lv-ring__score {
  font-family: var(--font-mono);
  font-size: 1.4rem;
  font-weight: 700;
  line-height: 1;
}
.lv-ring__denom { font-size: 0.55rem; color: var(--color-text-muted); text-transform: uppercase; letter-spacing: 0.05em; margin-top: 0.1rem; }

/* ── Verdict ── */
.lv-verdict { flex: 1; }
.lv-verdict__label { font-size: 0.9rem; font-weight: 700; margin-bottom: var(--space-1); }
.lv-verdict__text  { font-size: 0.8rem; color: var(--color-text-muted); line-height: 1.55; }
.lv-verdict__partial { font-size: 0.72rem; color: var(--color-info); margin-top: var(--space-2); }

/* ── Signal table ── */
.lv-signals { width: 100%; border-collapse: collapse; }
.lv-signals th {
  font-size: 0.62rem;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--color-text-muted);
  font-weight: 600;
  padding: 0 var(--space-2) var(--space-2);
  text-align: left;
  border-bottom: 1px solid var(--color-border-light);
}
.lv-signals__col-score { text-align: right; }
.lv-signals__row td { padding: var(--space-2) var(--space-2); border-bottom: 1px solid var(--color-border-light); }
.lv-signals__row:last-child td { border-bottom: none; }
.lv-signals__name  { font-size: 0.82rem; color: var(--color-text); }
.lv-signals__bar   { width: 80px; }
.lv-signals__score { font-family: var(--font-mono); font-size: 0.78rem; color: var(--color-text-muted); text-align: right; white-space: nowrap; }

.lv-mini-bar { height: 4px; background: var(--color-surface-raised); border-radius: var(--radius-full); overflow: hidden; }
.lv-mini-bar__fill { height: 100%; border-radius: var(--radius-full); transition: width 0.4s ease; }
.lv-mini-bar__fill--high    { background: var(--trust-high); }
.lv-mini-bar__fill--mid     { background: var(--trust-mid); }
.lv-mini-bar__fill--low     { background: var(--trust-low); }
.lv-mini-bar__fill--pending { background: var(--color-border); }

.lv-sig-pending { color: var(--color-info); font-size: 0.72rem; }

/* ── Seller ── */
.lv-seller__panel {
  display: flex;
  align-items: center;
  gap: var(--space-4);
  background: var(--color-surface-2);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  padding: var(--space-3) var(--space-4);
}
.lv-seller__avatar {
  width: 40px; height: 40px;
  background: var(--color-surface-raised);
  border: 1px solid var(--color-border);
  border-radius: 50%;
  display: flex; align-items: center; justify-content: center;
  font-size: 1.1rem;
  flex-shrink: 0;
}
.lv-seller__name  { font-weight: 700; font-size: 0.9rem; color: var(--color-text); }
.lv-seller__stats { font-size: 0.75rem; color: var(--color-text-muted); margin-top: var(--space-1); }
.lv-seller__age   { font-size: 0.72rem; color: var(--color-info); margin-top: 0.2rem; }
.lv-seller__age--unknown { color: var(--color-text-muted); }

/* ── Actions ── */
.lv-actions { display: flex; gap: var(--space-3); }

.lv-btn-primary {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: var(--space-3) var(--space-4);
  border-radius: var(--radius-md);
  background: var(--app-primary);
  color: var(--color-text-inverse);
  font-weight: 700;
  font-size: 0.85rem;
  text-decoration: none;
  transition: background var(--transition);
}
.lv-btn-primary:hover { background: var(--app-primary-hover); }

.lv-btn-secondary {
  padding: var(--space-3) var(--space-4);
  border-radius: var(--radius-md);
  border: 1px solid var(--color-border);
  background: transparent;
  color: var(--color-text-muted);
  font-size: 0.85rem;
  cursor: pointer;
  transition: border-color var(--transition), color var(--transition);
  font-family: inherit;
}
.lv-btn-secondary:hover { border-color: var(--trust-low); color: var(--trust-low); }

/* ── Block seller form ── */
.lv-block-form {
  background: var(--color-surface-2);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  padding: var(--space-4);
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}
.lv-block-form__title { font-size: 0.85rem; }
.lv-block-form__input {
  width: 100%;
  padding: var(--space-2) var(--space-3);
  background: var(--color-surface-raised);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  color: var(--color-text);
  font-size: 0.82rem;
  font-family: inherit;
}
.lv-block-form__input:focus { outline: 2px solid var(--app-primary); outline-offset: 1px; }
.lv-block-form__btns { display: flex; gap: var(--space-2); }
.lv-block-form__confirm {
  padding: var(--space-2) var(--space-4);
  background: var(--trust-low);
  color: white;
  border: none;
  border-radius: var(--radius-md);
  font-size: 0.82rem;
  font-weight: 700;
  cursor: pointer;
  font-family: inherit;
}
.lv-block-form__cancel {
  padding: var(--space-2) var(--space-4);
  background: transparent;
  border: 1px solid var(--color-border);
  color: var(--color-text-muted);
  border-radius: var(--radius-md);
  font-size: 0.82rem;
  cursor: pointer;
  font-family: inherit;
}
.lv-block-form__error { font-size: 0.78rem; color: var(--trust-low); }

/* ── Responsive: single column on narrow ── */
@media (max-width: 640px) {
  .lv-layout { grid-template-columns: 1fr; }
  .lv-photos { position: static; }
  .lv-carousel__img { aspect-ratio: 4/3; }
}
</style>

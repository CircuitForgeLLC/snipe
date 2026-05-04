<template>
  <div class="settings-view">
    <h1 class="settings-heading">Settings</h1>

    <section class="settings-section">
      <h2 class="settings-section-title">Community</h2>

      <label class="settings-toggle">
        <div class="settings-toggle-text">
          <span class="settings-toggle-label">Trust score feedback</span>
          <span class="settings-toggle-desc">
            Show "This score looks right / wrong" buttons on each listing.
            Your feedback helps improve trust scores for everyone.
          </span>
        </div>
        <button
          class="toggle-btn"
          :class="{ 'toggle-btn--on': trustSignalEnabled }"
          :aria-pressed="String(trustSignalEnabled)"
          aria-label="Enable trust score feedback buttons"
          @click="setEnabled(!trustSignalEnabled)"
        >
          <span class="toggle-btn__track" />
          <span class="toggle-btn__thumb" />
        </button>
      </label>

      <!-- Community blocklist share — cloud signed-in users only -->
      <label v-if="session.isLoggedIn" class="settings-toggle">
        <div class="settings-toggle-text">
          <span class="settings-toggle-label">Share blocklist with community</span>
          <span class="settings-toggle-desc">
            When enabled, sellers you block are anonymously contributed to the
            community blocklist. Only the seller ID and flag reason are shared,
            never your identity. A consensus threshold prevents false positives.
          </span>
        </div>
        <button
          class="toggle-btn"
          :class="{ 'toggle-btn--on': communityBlocklistShare }"
          :aria-pressed="String(communityBlocklistShare)"
          :aria-busy="prefs.loading"
          aria-label="Share blocked sellers with community blocklist"
          @click="prefs.setCommunityBlocklistShare(!communityBlocklistShare)"
        >
          <span class="toggle-btn__track" />
          <span class="toggle-btn__thumb" />
        </button>
      </label>
    </section>

    <!-- Appearance -->
    <section class="settings-section">
      <h2 class="settings-section-title">Appearance</h2>
      <div class="settings-toggle">
        <div class="settings-toggle-text">
          <span class="settings-toggle-label">Theme</span>
          <span class="settings-toggle-desc">Override the system color scheme. Default follows your OS preference.</span>
        </div>
        <div class="theme-btn-group" role="group" aria-label="Theme selection">
          <button
            v-for="opt in themeOptions"
            :key="opt.value"
            class="theme-btn"
            :class="{ 'theme-btn--active': theme.mode.value === opt.value }"
            :aria-pressed="theme.mode.value === opt.value"
            type="button"
            @click="theme.setMode(opt.value)"
          >{{ opt.label }}</button>
        </div>
      </div>

      <!-- Display currency -->
      <div class="settings-toggle">
        <div class="settings-toggle-text">
          <span class="settings-toggle-label">Display currency</span>
          <span class="settings-toggle-desc">
            Listing prices are converted from USD using live exchange rates.
            Rates update hourly.
          </span>
        </div>
        <select
          id="display-currency"
          class="settings-select"
          :value="prefs.displayCurrency"
          aria-label="Select display currency"
          @change="prefs.setDisplayCurrency(($event.target as HTMLSelectElement).value)"
        >
          <option v-for="opt in currencyOptions" :key="opt.code" :value="opt.code">
            {{ opt.code }} — {{ opt.label }}
          </option>
        </select>
      </div>
    </section>

    <!-- eBay Account Connection — paid+ only -->
    <section v-if="ebay.oauth_available && session.isLoggedIn" class="settings-section">
      <h2 class="settings-section-title">eBay Account</h2>

      <!-- Connected state -->
      <div v-if="ebay.connected" class="ebay-connected">
        <div class="ebay-status-row">
          <span class="ebay-status-dot ebay-status-dot--on" aria-hidden="true" />
          <span class="settings-toggle-label">Connected</span>
        </div>
        <p class="settings-toggle-desc">
          Snipe uses your eBay account to fetch seller registration dates instantly
          via the Trading API, without Playwright scraping. This means faster, more
          accurate trust scores on every search.
          <span v-if="ebay.access_token_expired" class="ebay-warn">
            Your access token has expired — reconnect to restore instant enrichment.
          </span>
        </p>
        <div class="ebay-action-row">
          <button
            v-if="ebay.access_token_expired"
            class="ebay-btn ebay-btn--primary"
            :disabled="ebay.connecting"
            @click="startConnect"
          >
            Reconnect eBay account
          </button>
          <button
            class="ebay-btn ebay-btn--danger"
            :disabled="ebay.disconnecting"
            @click="disconnect"
          >
            {{ ebay.disconnecting ? 'Disconnecting…' : 'Disconnect' }}
          </button>
        </div>
      </div>

      <!-- Not connected — paid tier -->
      <div v-else-if="session.isPaid || session.isPremium" class="ebay-disconnected">
        <p class="settings-toggle-desc">
          Connect your eBay account to enable instant seller registration date lookup
          via the Trading API. Without it, Snipe falls back to slower Playwright
          scraping (or Shopping API rate-limited calls) to determine account age.
        </p>
        <button
          class="ebay-btn ebay-btn--primary"
          :disabled="ebay.connecting"
          @click="startConnect"
        >
          {{ ebay.connecting ? 'Redirecting to eBay…' : 'Connect eBay account' }}
        </button>
      </div>

      <!-- Not connected — free tier upsell -->
      <div v-else class="ebay-disconnected">
        <p class="settings-toggle-desc">
          Connect your eBay account for instant seller trust scoring without scraping.
          Available on Paid tier and above.
        </p>
        <a class="ebay-btn ebay-btn--upsell" href="/pricing" rel="noopener">
          Upgrade to Paid
        </a>
      </div>

      <p v-if="ebay.error" class="settings-error" role="alert">{{ ebay.error }}</p>
      <p v-if="ebay.success" class="settings-success" role="status">{{ ebay.success }}</p>
    </section>

    <!-- Affiliate Links — only shown to signed-in cloud users -->
    <section v-if="session.isLoggedIn" class="settings-section">
      <h2 class="settings-section-title">Affiliate Links</h2>

      <label class="settings-toggle">
        <div class="settings-toggle-text">
          <span class="settings-toggle-label">Opt out of affiliate links</span>
          <span class="settings-toggle-desc">
            When enabled, listing links go directly to eBay without an affiliate code.
            Opting out means your purchases won't support Snipe's development.
          </span>
        </div>
        <button
          class="toggle-btn"
          :class="{ 'toggle-btn--on': prefs.affiliateOptOut }"
          :aria-pressed="String(prefs.affiliateOptOut)"
          :aria-busy="prefs.loading"
          aria-label="Opt out of affiliate links"
          @click="prefs.setAffiliateOptOut(!prefs.affiliateOptOut)"
        >
          <span class="toggle-btn__track" />
          <span class="toggle-btn__thumb" />
        </button>
      </label>

      <!-- BYOK affiliate ID — Premium tier only -->
      <div v-if="session.isPremium" class="settings-field">
        <label class="settings-toggle-label" for="byok-id">
          Your eBay Partner Network campaign ID
        </label>
        <p class="settings-toggle-desc">
          Override Snipe's affiliate ID with your own eBay Partner Network (EPN) campaign ID.
          Your purchases generate revenue for your own EPN account instead.
        </p>
        <div class="settings-field-row">
          <input
            id="byok-id"
            v-model="byokInput"
            type="text"
            class="settings-input"
            placeholder="e.g. 5339149249"
            aria-label="Your eBay Partner Network campaign ID"
            @blur="saveByokId"
            @keydown.enter="saveByokId"
          />
          <button class="settings-field-save" @click="saveByokId" aria-label="Save campaign ID">
            Save
          </button>
        </div>
      </div>

      <p v-if="prefs.error" class="settings-error" role="alert">{{ prefs.error }}</p>
    </section>

    <section class="settings-section">
      <h2 class="settings-section-title">Search</h2>

      <label class="settings-toggle">
        <div class="settings-toggle-text">
          <span class="settings-toggle-label">Auto-run after Search with AI</span>
          <span class="settings-toggle-desc">
            When enabled, Snipe starts searching immediately after AI fills in your filters.
            Disable to review the filters before searching.
          </span>
        </div>
        <button
          class="toggle-btn"
          :class="{ 'toggle-btn--on': llmAutoRun }"
          :aria-pressed="String(llmAutoRun)"
          aria-label="Run search automatically after Search with AI"
          @click="setLLMAutoRun(!llmAutoRun)"
        >
          <span class="toggle-btn__track" />
          <span class="toggle-btn__thumb" />
        </button>
      </label>
    </section>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, reactive, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useTrustSignalPref } from '../composables/useTrustSignalPref'
import { useTheme } from '../composables/useTheme'
import { useSessionStore } from '../stores/session'
import { usePreferencesStore } from '../stores/preferences'
import { useLLMQueryBuilder } from '../composables/useLLMQueryBuilder'

const route = useRoute()
const router = useRouter()
const { enabled: trustSignalEnabled, setEnabled } = useTrustSignalPref()
const theme = useTheme()
const themeOptions: { value: 'system' | 'dark' | 'light'; label: string }[] = [
  { value: 'system', label: 'System' },
  { value: 'dark',   label: 'Dark' },
  { value: 'light',  label: 'Light' },
]
const currencyOptions: { code: string; label: string }[] = [
  { code: 'USD', label: 'US Dollar' },
  { code: 'EUR', label: 'Euro' },
  { code: 'GBP', label: 'British Pound' },
  { code: 'CAD', label: 'Canadian Dollar' },
  { code: 'AUD', label: 'Australian Dollar' },
  { code: 'JPY', label: 'Japanese Yen' },
  { code: 'CHF', label: 'Swiss Franc' },
  { code: 'MXN', label: 'Mexican Peso' },
  { code: 'BRL', label: 'Brazilian Real' },
  { code: 'INR', label: 'Indian Rupee' },
]
const session = useSessionStore()
const prefs = usePreferencesStore()
const { autoRun: llmAutoRun, setAutoRun: setLLMAutoRun } = useLLMQueryBuilder()
const communityBlocklistShare = computed(() => prefs.communityBlocklistShare)

// Local input buffer for BYOK ID — synced from store, saved on blur/enter
const byokInput = ref(prefs.affiliateByokId)
watch(() => prefs.affiliateByokId, (val) => { byokInput.value = val })

function saveByokId() {
  prefs.setAffiliateByokId(byokInput.value)
}

// ── eBay Account Connection ──────────────────────────────────────────────────

const ebay = reactive({
  oauth_available: false,
  connected: false,
  access_token_expired: false,
  scopes: [] as string[],
  connecting: false,
  disconnecting: false,
  error: '',
  success: '',
})

async function fetchEbayStatus() {
  try {
    const res = await fetch('/api/ebay/status')
    if (!res.ok) return
    const data = await res.json()
    ebay.oauth_available = data.oauth_available ?? false
    ebay.connected = data.connected ?? false
    ebay.access_token_expired = data.access_token_expired ?? false
    ebay.scopes = data.scopes ?? []
  } catch {
    // silently ignore — section stays hidden if fetch fails
  }
}

async function startConnect() {
  ebay.connecting = true
  ebay.error = ''
  try {
    const res = await fetch('/api/ebay/connect')
    if (!res.ok) {
      const body = await res.json().catch(() => ({}))
      ebay.error = body.detail ?? 'eBay connection unavailable.'
      return
    }
    const { auth_url } = await res.json()
    window.location.href = auth_url
  } catch {
    ebay.error = 'Could not reach the server. Try again.'
    ebay.connecting = false
  }
}

async function disconnect() {
  ebay.disconnecting = true
  ebay.error = ''
  ebay.success = ''
  try {
    const res = await fetch('/api/ebay/disconnect', { method: 'DELETE' })
    if (res.ok || res.status === 204) {
      ebay.connected = false
      ebay.access_token_expired = false
      ebay.scopes = []
      ebay.success = 'eBay account disconnected.'
    } else {
      ebay.error = 'Disconnect failed. Try again.'
    }
  } catch {
    ebay.error = 'Could not reach the server. Try again.'
  } finally {
    ebay.disconnecting = false
  }
}

onMounted(async () => {
  await fetchEbayStatus()

  // Handle OAuth callback redirect params: ?ebay_connected=1 or ?ebay_error=access_denied
  const connected = route.query.ebay_connected
  const oauthError = route.query.ebay_error
  if (connected) {
    ebay.success = 'eBay account connected! Trust scores will now use the Trading API.'
    await fetchEbayStatus()
    router.replace({ query: { ...route.query, ebay_connected: undefined } })
  } else if (oauthError) {
    ebay.error = oauthError === 'access_denied'
      ? 'eBay authorization was cancelled.'
      : `eBay OAuth error: ${oauthError}`
    router.replace({ query: { ...route.query, ebay_error: undefined } })
  }
})
</script>

<style scoped>
.settings-view {
  max-width: 600px;
  margin: 0 auto;
  padding: var(--space-8) var(--space-4);
  display: flex;
  flex-direction: column;
  gap: var(--space-6);
}

.settings-heading {
  font-family: var(--font-display);
  font-size: 1.5rem;
  color: var(--app-primary);
  margin: 0 0 var(--space-8);
}

.settings-section {
  background: var(--color-surface-2);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  padding: var(--space-4);
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

.settings-section-title {
  font-family: var(--font-display);
  font-size: 0.75rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--color-text-muted);
  margin: 0 0 var(--space-2);
}

.settings-toggle {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-6);
  cursor: pointer;
}

.settings-toggle-text {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}

.settings-toggle-label {
  font-size: 0.9375rem;
  font-weight: 500;
  color: var(--color-text);
}

.settings-toggle-desc {
  font-size: 0.8125rem;
  color: var(--color-text-muted);
  line-height: 1.5;
}

/* Toggle button */
.toggle-btn {
  position: relative;
  width: 44px;
  height: 24px;
  background: none;
  border: none;
  padding: 0;
  cursor: pointer;
  flex-shrink: 0;
}

.toggle-btn__track {
  position: absolute;
  inset: 0;
  border-radius: var(--radius-full);
  background: var(--color-border);
  transition: background 0.2s ease;
}

.toggle-btn--on .toggle-btn__track {
  background: var(--app-primary);
}

.toggle-btn__thumb {
  position: absolute;
  top: 3px;
  left: 3px;
  width: 18px;
  height: 18px;
  border-radius: 50%;
  background: var(--color-text-muted);
  transition: transform 0.2s ease, background 0.2s ease;
}

.toggle-btn--on .toggle-btn__thumb {
  transform: translateX(20px);
  background: var(--color-surface);
}

@media (prefers-reduced-motion: reduce) {
  .toggle-btn__track,
  .toggle-btn__thumb { transition: none; }
}

/* ---- BYOK text input field ---- */
.settings-field {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.settings-field-row {
  display: flex;
  gap: var(--space-2);
  align-items: center;
  flex-wrap: wrap;
}

.settings-input {
  flex: 1;
  min-width: 0;
  padding: var(--space-2) var(--space-3);
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  color: var(--color-text);
  font-size: 0.9375rem;
  font-family: var(--font-mono, monospace);
  outline: none;
  transition: border-color 0.15s ease;
}

.settings-input:focus {
  border-color: var(--app-primary);
}

.settings-field-save {
  padding: var(--space-2) var(--space-4);
  background: var(--app-primary);
  color: var(--color-text-inverse, #fff);
  border: none;
  border-radius: var(--radius-md);
  font-size: 0.875rem;
  font-weight: 600;
  cursor: pointer;
  white-space: nowrap;
  transition: opacity 0.15s ease;
}

.settings-field-save:hover { opacity: 0.85; }
.settings-field-save:focus-visible {
  outline: 2px solid var(--app-primary);
  outline-offset: 2px;
}

/* ---- Error / success feedback ---- */
.settings-error {
  font-size: 0.8125rem;
  color: var(--color-danger, #f85149);
  margin: 0;
}

.settings-select {
  padding: var(--space-2) var(--space-3);
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  color: var(--color-text);
  font-size: 0.875rem;
  font-family: inherit;
  cursor: pointer;
  outline: none;
  flex-shrink: 0;
  transition: border-color 0.15s ease;
}

.settings-select:focus {
  border-color: var(--app-primary);
}

.settings-success {
  font-size: 0.8125rem;
  color: var(--color-success, #3fb950);
  margin: 0;
}

/* ---- eBay Account section ---- */
.ebay-status-row {
  display: flex;
  align-items: center;
  gap: var(--space-2);
}

.ebay-status-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  flex-shrink: 0;
  background: var(--color-border);
}

.ebay-status-dot--on {
  background: var(--color-success, #3fb950);
}

.ebay-connected,
.ebay-disconnected {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.ebay-warn {
  display: block;
  margin-top: var(--space-1);
  color: var(--color-warning, #d29922);
}

.ebay-action-row {
  display: flex;
  gap: var(--space-2);
  flex-wrap: wrap;
}

.ebay-btn {
  padding: var(--space-2) var(--space-4);
  border: none;
  border-radius: var(--radius-md);
  font-size: 0.875rem;
  font-weight: 600;
  cursor: pointer;
  font-family: inherit;
  white-space: nowrap;
  transition: opacity 0.15s ease;
  text-decoration: none;
  display: inline-flex;
  align-items: center;
}

.ebay-btn:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}

.ebay-btn--primary {
  background: var(--app-primary);
  color: var(--color-text-inverse, #fff);
}

.ebay-btn--primary:hover:not(:disabled) { opacity: 0.85; }

.ebay-btn--danger {
  background: transparent;
  color: var(--color-danger, #f85149);
  border: 1px solid var(--color-danger, #f85149);
}

.ebay-btn--danger:hover:not(:disabled) {
  background: color-mix(in srgb, var(--color-danger, #f85149) 12%, transparent);
}

.ebay-btn--upsell {
  background: var(--color-surface-raised);
  color: var(--color-text);
  border: 1px solid var(--color-border);
}

.ebay-btn--upsell:hover { opacity: 0.85; }

.ebay-btn:focus-visible {
  outline: 2px solid var(--app-primary);
  outline-offset: 2px;
}

.theme-btn-group {
  display: flex;
  gap: 0;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  overflow: hidden;
  flex-shrink: 0;
}

.theme-btn {
  padding: var(--space-2) var(--space-4);
  background: transparent;
  border: none;
  border-right: 1px solid var(--color-border);
  color: var(--color-text-muted);
  font-size: 0.8rem;
  cursor: pointer;
  font-family: inherit;
  transition: background var(--transition), color var(--transition);
}
.theme-btn:last-child { border-right: none; }
.theme-btn:hover { background: var(--color-surface-raised); color: var(--color-text); }
.theme-btn--active {
  background: var(--app-primary-light);
  color: var(--app-primary);
  font-weight: 600;
}
</style>

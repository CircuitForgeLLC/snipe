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
import { ref, watch } from 'vue'
import { useTrustSignalPref } from '../composables/useTrustSignalPref'
import { useTheme } from '../composables/useTheme'
import { useSessionStore } from '../stores/session'
import { usePreferencesStore } from '../stores/preferences'
import { useLLMQueryBuilder } from '../composables/useLLMQueryBuilder'

const { enabled: trustSignalEnabled, setEnabled } = useTrustSignalPref()
const theme = useTheme()
const themeOptions: { value: 'system' | 'dark' | 'light'; label: string }[] = [
  { value: 'system', label: 'System' },
  { value: 'dark',   label: 'Dark' },
  { value: 'light',  label: 'Light' },
]
const session = useSessionStore()
const prefs = usePreferencesStore()
const { autoRun: llmAutoRun, setAutoRun: setLLMAutoRun } = useLLMQueryBuilder()

// Local input buffer for BYOK ID — synced from store, saved on blur/enter
const byokInput = ref(prefs.affiliateByokId)
watch(() => prefs.affiliateByokId, (val) => { byokInput.value = val })

function saveByokId() {
  prefs.setAffiliateByokId(byokInput.value)
}
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

/* ---- Error feedback ---- */
.settings-error {
  font-size: 0.8125rem;
  color: var(--color-danger, #f85149);
  margin: 0;
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

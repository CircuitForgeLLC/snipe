<template>
  <!-- Floating trigger button -->
  <button
    v-if="enabled"
    class="feedback-fab"
    @click="open = true"
    aria-label="Send feedback or report a bug"
    title="Send feedback or report a bug"
  >
    <svg class="feedback-fab-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
      <path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z"/>
    </svg>
    <span class="feedback-fab-label">Feedback</span>
  </button>

  <!-- Modal — teleported to body to avoid z-index / overflow clipping -->
  <Teleport to="body">
    <Transition name="modal-fade">
      <div v-if="open" class="feedback-overlay" @click.self="close">
        <div class="feedback-modal" role="dialog" aria-modal="true" aria-label="Send Feedback">

          <!-- Header -->
          <div class="feedback-header">
            <h2 class="feedback-title">{{ step === 1 ? "What's on your mind?" : "Review & submit" }}</h2>
            <button class="feedback-close" @click="close" aria-label="Close">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" width="18" height="18">
                <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
              </svg>
            </button>
          </div>

          <!-- ── Step 1: Form ─────────────────────────────────────────── -->
          <div v-if="step === 1" class="feedback-body">
            <div class="form-group">
              <label class="form-label">Type</label>
              <div class="filter-chip-row">
                <button
                  v-for="t in types"
                  :key="t.value"
                  :class="['btn-chip', { active: form.type === t.value }]"
                  @click="form.type = t.value"
                  type="button"
                >{{ t.label }}</button>
              </div>
            </div>

            <div class="form-group">
              <label class="form-label">Title <span class="form-required">*</span></label>
              <input
                v-model="form.title"
                class="form-input"
                type="text"
                placeholder="Short summary of the issue or idea"
                maxlength="120"
              />
            </div>

            <div class="form-group">
              <label class="form-label">Description <span class="form-required">*</span></label>
              <textarea
                v-model="form.description"
                class="form-input feedback-textarea"
                placeholder="Describe what happened or what you'd like to see…"
                rows="4"
              />
            </div>

            <div v-if="form.type === 'bug'" class="form-group">
              <label class="form-label">Reproduction steps</label>
              <textarea
                v-model="form.repro"
                class="form-input feedback-textarea"
                placeholder="1. Go to…&#10;2. Tap…&#10;3. See error"
                rows="3"
              />
            </div>

            <p v-if="stepError" class="feedback-error">{{ stepError }}</p>
          </div>

          <!-- ── Step 2: Attribution + confirm ──────────────────────────── -->
          <div v-if="step === 2" class="feedback-body">
            <div class="feedback-summary card">
              <div class="feedback-summary-row">
                <span class="text-muted text-sm">Type</span>
                <span class="text-sm font-semibold">{{ typeLabel }}</span>
              </div>
              <div class="feedback-summary-row">
                <span class="text-muted text-sm">Title</span>
                <span class="text-sm">{{ form.title }}</span>
              </div>
              <div class="feedback-summary-row">
                <span class="text-muted text-sm">Description</span>
                <span class="text-sm feedback-summary-desc">{{ form.description }}</span>
              </div>
            </div>

            <div class="form-group mt-md">
              <label class="form-label">Attribution (optional)</label>
              <input
                v-model="form.submitter"
                class="form-input"
                type="text"
                placeholder="Your name &lt;email@example.com&gt;"
              />
              <p class="text-muted text-xs mt-xs">Include your name and email in the issue if you'd like a response. Never required.</p>
            </div>

            <p v-if="submitError" class="feedback-error">{{ submitError }}</p>
            <div v-if="submitted" class="feedback-success">
              Issue filed! <a :href="issueUrl" target="_blank" rel="noopener" class="feedback-link">View on Forgejo →</a>
            </div>
          </div>

          <!-- Footer nav -->
          <div class="feedback-footer">
            <button v-if="step === 2 && !submitted" class="btn btn-ghost" @click="step = 1" :disabled="loading">← Back</button>
            <button v-if="!submitted" class="btn btn-ghost" @click="close" :disabled="loading">Cancel</button>
            <button
              v-if="step === 1"
              class="btn btn-primary"
              @click="nextStep"
            >Next →</button>
            <button
              v-if="step === 2 && !submitted"
              class="btn btn-primary"
              @click="submit"
              :disabled="loading"
            >{{ loading ? 'Filing…' : 'Submit' }}</button>
            <button v-if="submitted" class="btn btn-primary" @click="close">Done</button>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'

const props = defineProps<{ currentView?: string }>()

// Probe once on mount — hidden until confirmed enabled so button never flashes
const enabled = ref(false)
onMounted(async () => {
  try {
    const res = await fetch('/api/feedback/status')
    if (res.ok) {
      const data = await res.json()
      enabled.value = data.enabled === true
    }
  } catch { /* network error — stay hidden */ }
})

const open = ref(false)
const step = ref(1)
const loading = ref(false)
const stepError = ref('')
const submitError = ref('')
const submitted = ref(false)
const issueUrl = ref('')

const types: { value: 'bug' | 'feature' | 'other'; label: string }[] = [
  { value: 'bug', label: '🐛 Bug' },
  { value: 'feature', label: '✨ Feature request' },
  { value: 'other', label: '💬 Other' },
]

const form = ref({
  type: 'bug' as 'bug' | 'feature' | 'other',
  title: '',
  description: '',
  repro: '',
  submitter: '',
})

const typeLabel = computed(() => types.find(t => t.value === form.value.type)?.label ?? '')

function close() {
  open.value = false
  // reset after transition
  setTimeout(reset, 300)
}

function reset() {
  step.value = 1
  loading.value = false
  stepError.value = ''
  submitError.value = ''
  submitted.value = false
  issueUrl.value = ''
  form.value = { type: 'bug', title: '', description: '', repro: '', submitter: '' }
}

function nextStep() {
  stepError.value = ''
  if (!form.value.title.trim() || !form.value.description.trim()) {
    stepError.value = 'Please fill in both Title and Description.'
    return
  }
  step.value = 2
}

async function submit() {
  loading.value = true
  submitError.value = ''
  try {
    const res = await fetch('/api/feedback', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        title: form.value.title.trim(),
        description: form.value.description.trim(),
        type: form.value.type,
        repro: form.value.repro.trim(),
        view: props.currentView ?? 'unknown',
        submitter: form.value.submitter.trim(),
      }),
    })
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }))
      submitError.value = err.detail ?? 'Submission failed.'
      return
    }
    const data = await res.json()
    issueUrl.value = data.issue_url
    submitted.value = true
  } catch (e) {
    submitError.value = 'Network error — please try again.'
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
/* ── Floating action button ─────────────────────────────────────────── */
.feedback-fab {
  position: fixed;
  right: var(--spacing-md);
  bottom: calc(68px + var(--spacing-md)); /* above mobile bottom nav */
  z-index: 190;
  display: flex;
  align-items: center;
  gap: var(--spacing-xs);
  padding: 9px var(--spacing-md);
  background: var(--color-bg-elevated);
  border: 1px solid var(--color-border);
  border-radius: 999px;
  color: var(--color-text-secondary);
  font-size: var(--font-size-sm);
  font-family: var(--font-body);
  font-weight: 500;
  cursor: pointer;
  box-shadow: var(--shadow-md);
  transition: background 0.15s, color 0.15s, box-shadow 0.15s, border-color 0.15s;
}
.feedback-fab:hover {
  background: var(--color-bg-card);
  color: var(--color-text-primary);
  border-color: var(--color-border-focus);
  box-shadow: var(--shadow-lg);
}
.feedback-fab-icon { width: 15px; height: 15px; flex-shrink: 0; }
.feedback-fab-label { white-space: nowrap; }

/* On desktop, bottom nav is gone — drop to standard corner */
@media (min-width: 769px) {
  .feedback-fab {
    bottom: var(--spacing-lg);
  }
}

/* ── Overlay ──────────────────────────────────────────────────────────── */
.feedback-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.55);
  z-index: 1000;
  display: flex;
  align-items: flex-end;
  justify-content: center;
  padding: 0;
}

@media (min-width: 500px) {
  .feedback-overlay {
    align-items: center;
    padding: var(--spacing-md);
  }
}

/* ── Modal ────────────────────────────────────────────────────────────── */
.feedback-modal {
  background: var(--color-bg-elevated);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg) var(--radius-lg) 0 0;
  width: 100%;
  max-height: 90vh;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  box-shadow: var(--shadow-xl);
}

@media (min-width: 500px) {
  .feedback-modal {
    border-radius: var(--radius-lg);
    width: 100%;
    max-width: 520px;
    max-height: 85vh;
  }
}

.feedback-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--spacing-md) var(--spacing-md) var(--spacing-sm);
  border-bottom: 1px solid var(--color-border);
  flex-shrink: 0;
}
.feedback-title {
  font-family: var(--font-display);
  font-size: var(--font-size-lg);
  font-weight: 600;
  margin: 0;
}
.feedback-close {
  background: transparent;
  border: none;
  color: var(--color-text-muted);
  cursor: pointer;
  padding: 4px;
  border-radius: var(--radius-sm);
  display: flex;
  align-items: center;
  justify-content: center;
}
.feedback-close:hover { color: var(--color-text-primary); }

.feedback-body {
  padding: var(--spacing-md);
  flex: 1;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: var(--spacing-md);
}

.feedback-footer {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: var(--spacing-sm);
  padding: var(--spacing-sm) var(--spacing-md);
  border-top: 1px solid var(--color-border);
  flex-shrink: 0;
}

.feedback-textarea {
  resize: vertical;
  min-height: 80px;
  font-family: var(--font-body);
  font-size: var(--font-size-sm);
}

.form-required { color: var(--color-error); margin-left: 2px; }

.feedback-error {
  color: var(--color-error);
  font-size: var(--font-size-sm);
  margin: 0;
}

.feedback-success {
  color: var(--color-success);
  font-size: var(--font-size-sm);
  padding: var(--spacing-sm) var(--spacing-md);
  background: var(--color-success-bg);
  border: 1px solid var(--color-success-border);
  border-radius: var(--radius-md);
}
.feedback-link { color: var(--color-success); font-weight: 600; text-decoration: underline; }

/* Summary card (step 2) */
.feedback-summary {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-xs);
  padding: var(--spacing-sm) var(--spacing-md);
  background: var(--color-bg-secondary);
  border-radius: var(--radius-md);
  border: 1px solid var(--color-border);
}
.feedback-summary-row {
  display: flex;
  gap: var(--spacing-md);
  align-items: flex-start;
}
.feedback-summary-row > :first-child { min-width: 72px; flex-shrink: 0; }
.feedback-summary-desc {
  white-space: pre-wrap;
  word-break: break-word;
}

.mt-md { margin-top: var(--spacing-md); }
.mt-xs { margin-top: var(--spacing-xs); }

/* Transition */
.modal-fade-enter-active, .modal-fade-leave-active { transition: opacity 0.2s ease; }
.modal-fade-enter-from, .modal-fade-leave-to { opacity: 0; }
</style>

import { ref } from 'vue'

const LS_KEY = 'cf-snipe-mode'
const DATA_ATTR = 'snipeMode'

// Module-level ref so state is shared across all callers
const active = ref(false)

/**
 * Snipe Mode easter egg — activated by Konami code.
 *
 * When active:
 *  - Sets data-snipe-mode="active" on <html> (triggers CSS theme override in theme.css)
 *  - Persists to localStorage
 *  - Plays a snipe sound via Web Audio API (if audioEnabled is true)
 *
 * Audio synthesis mirrors the Streamlit version:
 *   1. High-frequency sine blip (targeting beep)
 *   2. Lower resonant hit with decay (impact)
 */
export function useSnipeMode(audioEnabled = true) {
  function _playSnipeSound() {
    if (!audioEnabled) return
    try {
      const ctx = new AudioContext()

      // Phase 1: targeting blip — short high sine
      const blip = ctx.createOscillator()
      const blipGain = ctx.createGain()
      blip.type = 'sine'
      blip.frequency.setValueAtTime(880, ctx.currentTime)
      blip.frequency.linearRampToValueAtTime(1200, ctx.currentTime + 0.05)
      blipGain.gain.setValueAtTime(0.25, ctx.currentTime)
      blipGain.gain.linearRampToValueAtTime(0, ctx.currentTime + 0.08)
      blip.connect(blipGain)
      blipGain.connect(ctx.destination)
      blip.start(ctx.currentTime)
      blip.stop(ctx.currentTime + 0.08)

      // Phase 2: resonant hit — lower freq with exponential decay
      const hit = ctx.createOscillator()
      const hitGain = ctx.createGain()
      hit.type = 'sine'
      hit.frequency.setValueAtTime(440, ctx.currentTime + 0.08)
      hit.frequency.exponentialRampToValueAtTime(110, ctx.currentTime + 0.45)
      hitGain.gain.setValueAtTime(0.4, ctx.currentTime + 0.08)
      hitGain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.5)
      hit.connect(hitGain)
      hitGain.connect(ctx.destination)
      hit.start(ctx.currentTime + 0.08)
      hit.stop(ctx.currentTime + 0.5)

      // Close context after sound finishes
      setTimeout(() => ctx.close(), 600)
    } catch {
      // Web Audio API unavailable — silently skip
    }
  }

  function activate() {
    active.value = true
    document.documentElement.dataset[DATA_ATTR] = 'active'
    localStorage.setItem(LS_KEY, 'active')
    _playSnipeSound()
  }

  function deactivate() {
    active.value = false
    delete document.documentElement.dataset[DATA_ATTR]
    localStorage.removeItem(LS_KEY)
  }

  /** Re-apply from localStorage on hard reload (call from App.vue onMounted). */
  function restore() {
    if (localStorage.getItem(LS_KEY) === 'active') {
      active.value = true
      document.documentElement.dataset[DATA_ATTR] = 'active'
    }
  }

  return { active, activate, deactivate, restore }
}

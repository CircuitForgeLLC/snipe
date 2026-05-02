import { ref, onMounted, onUnmounted } from 'vue'
import { useSnipeMode } from './useSnipeMode'

const LS_KEY = 'cf-candycore'
const DATA_ATTR = 'candycore'

// Module-level ref — shared across all callers
const active = ref(false)

/**
 * Candycore easter egg theme — activated by typing "neon" outside a form field.
 * Tribute to artist Neon, whose iPad painting (snipe_v0_Neon_IPad_Paint.jpeg)
 * defined the candy palette: lavender primary, cyan glow, yellow crown, bubblegum pink.
 *
 * Mutually exclusive with Snipe Mode (each deactivates the other).
 * Stores state in localStorage under 'cf-candycore'.
 */
export function useCandycoreMode() {
  const snipe = useSnipeMode(false /* no sound on deactivate */)

  function _playCandySound() {
    try {
      const ctx = new AudioContext()
      // Ascending arpeggio: C5 → E5 → G5 → C6
      const notes = [523.25, 659.25, 783.99, 1046.50]
      const step = 0.08

      notes.forEach((freq, i) => {
        const t = ctx.currentTime + i * step
        const osc = ctx.createOscillator()
        const gain = ctx.createGain()
        osc.type = 'sine'
        osc.frequency.setValueAtTime(freq, t)
        gain.gain.setValueAtTime(0, t)
        gain.gain.linearRampToValueAtTime(0.22, t + 0.01)
        gain.gain.exponentialRampToValueAtTime(0.001, t + step * 1.4)
        osc.connect(gain)
        gain.connect(ctx.destination)
        osc.start(t)
        osc.stop(t + step * 1.5)
      })

      setTimeout(() => ctx.close(), (notes.length * step + 0.3) * 1000)
    } catch {
      // Web Audio API unavailable
    }
  }

  function activate() {
    // Deactivate Snipe Mode if it's running — can't have both
    if (snipe.active.value) snipe.deactivate()
    active.value = true
    document.documentElement.dataset[DATA_ATTR] = 'active'
    localStorage.setItem(LS_KEY, 'active')
    _playCandySound()
  }

  function deactivate() {
    active.value = false
    delete document.documentElement.dataset[DATA_ATTR]
    localStorage.removeItem(LS_KEY)
  }

  function restore() {
    if (localStorage.getItem(LS_KEY) === 'active') {
      active.value = true
      document.documentElement.dataset[DATA_ATTR] = 'active'
    }
  }

  /**
   * Registers a document keydown listener that fires activate() when the user
   * types "neon" outside of any form field. Call from component setup().
   * The listener is automatically removed when the calling component unmounts.
   */
  function useWordTrigger() {
    const TARGET = 'neon'
    let buffer = ''

    function handleKey(e: KeyboardEvent) {
      const tag = (e.target as HTMLElement | null)?.tagName ?? ''
      if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return
      if (e.key.length !== 1) return   // skip modifier/arrow keys

      buffer = (buffer + e.key.toLowerCase()).slice(-TARGET.length)
      if (buffer === TARGET) {
        buffer = ''
        if (active.value) deactivate()
        else activate()
      }
    }

    onMounted(() => document.addEventListener('keydown', handleKey))
    onUnmounted(() => document.removeEventListener('keydown', handleKey))
  }

  return { active, activate, deactivate, restore, useWordTrigger }
}

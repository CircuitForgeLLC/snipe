import { onMounted, onUnmounted } from 'vue'

const KONAMI = [
  'ArrowUp', 'ArrowUp',
  'ArrowDown', 'ArrowDown',
  'ArrowLeft', 'ArrowRight',
  'ArrowLeft', 'ArrowRight',
  'b', 'a',
]

/**
 * Listens for the Konami code sequence on the document and calls `onActivate`
 * when the full sequence is entered. Works identically to Peregrine's pattern.
 */
export function useKonamiCode(onActivate: () => void) {
  let pos = 0

  function handleKey(e: KeyboardEvent) {
    if (e.key === KONAMI[pos]) {
      pos++
      if (pos === KONAMI.length) {
        pos = 0
        onActivate()
      }
    } else {
      pos = e.key === KONAMI[0] ? 1 : 0
    }
  }

  onMounted(() => document.addEventListener('keydown', handleKey))
  onUnmounted(() => document.removeEventListener('keydown', handleKey))
}

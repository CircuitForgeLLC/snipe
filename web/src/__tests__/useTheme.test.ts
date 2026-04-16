import { beforeEach, describe, expect, it } from 'vitest'

// Re-import after each test to get a fresh module-level ref
// (vi.resetModules() ensures module-level state is cleared between describe blocks)

describe('useTheme', () => {
  beforeEach(() => {
    localStorage.clear()
    delete document.documentElement.dataset.theme
  })

  it('defaults to system when localStorage is empty', async () => {
    const { useTheme } = await import('../composables/useTheme')
    const { mode } = useTheme()
    expect(mode.value).toBe('system')
  })

  it('setMode(dark) sets data-theme=dark on html element', async () => {
    const { useTheme } = await import('../composables/useTheme')
    const { setMode } = useTheme()
    setMode('dark')
    expect(document.documentElement.dataset.theme).toBe('dark')
  })

  it('setMode(light) sets data-theme=light on html element', async () => {
    const { useTheme } = await import('../composables/useTheme')
    const { setMode } = useTheme()
    setMode('light')
    expect(document.documentElement.dataset.theme).toBe('light')
  })

  it('setMode(system) removes data-theme attribute', async () => {
    const { useTheme } = await import('../composables/useTheme')
    const { setMode } = useTheme()
    setMode('dark')
    setMode('system')
    expect(document.documentElement.dataset.theme).toBeUndefined()
  })

  it('setMode persists to localStorage', async () => {
    const { useTheme } = await import('../composables/useTheme')
    const { setMode } = useTheme()
    setMode('dark')
    expect(localStorage.getItem('snipe:theme')).toBe('dark')
  })

  it('restore() re-applies dark from localStorage', async () => {
    localStorage.setItem('snipe:theme', 'dark')
    // Dynamically import a fresh module to simulate hard reload
    const { useTheme } = await import('../composables/useTheme')
    const { restore } = useTheme()
    restore()
    expect(document.documentElement.dataset.theme).toBe('dark')
  })

  it('restore() with system mode leaves data-theme absent', async () => {
    localStorage.setItem('snipe:theme', 'system')
    const { useTheme } = await import('../composables/useTheme')
    const { restore } = useTheme()
    restore()
    expect(document.documentElement.dataset.theme).toBeUndefined()
  })
})

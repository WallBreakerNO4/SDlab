const STORAGE_KEY_PREFIX = "promptcodex-scroll-pos"

export function saveScrollPosition(fileId: string, entryId: string): void {
  try {
    localStorage.setItem(`${STORAGE_KEY_PREFIX}:${fileId}`, entryId)
  } catch {
    // localStorage 不可用时静默忽略
  }
}

export function getScrollPosition(fileId: string): string | null {
  try {
    return localStorage.getItem(`${STORAGE_KEY_PREFIX}:${fileId}`)
  } catch {
    return null
  }
}

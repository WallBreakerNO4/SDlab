import type { FileIndex, FileData } from "@/lib/prompt-types"

let indexCache: FileIndex | null = null
const fileDataCache = new Map<string, FileData>()

export async function loadIndex(): Promise<FileIndex> {
  if (indexCache) return indexCache
  const res = await fetch("/data/prompts/index.json")
  if (!res.ok) throw new Error("Failed to load prompt index")
  indexCache = (await res.json()) as FileIndex
  return indexCache
}

export async function loadFileData(fileId: string): Promise<FileData> {
  if (fileDataCache.has(fileId)) {
    return fileDataCache.get(fileId)!
  }
  const res = await fetch(`/data/prompts/files/${fileId}.json`)
  if (!res.ok) throw new Error(`Failed to load prompt file data: ${fileId}`)
  const data = (await res.json()) as FileData
  fileDataCache.set(fileId, data)
  return data
}

export function clearFileCache(fileId?: string) {
  if (fileId) {
    fileDataCache.delete(fileId)
  } else {
    fileDataCache.clear()
  }
}

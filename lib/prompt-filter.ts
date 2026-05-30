import Fuse from "fuse.js"
import type { Entry, PromptNode, TocNode, FilterScope, FilterMode } from "@/lib/prompt-types"

export type { FilterScope, FilterMode }

function extractNodeTags(nodes: PromptNode[]): string[] {
  const texts: string[] = []
  const stack = [...nodes]
  while (stack.length > 0) {
    const node = stack.pop()!
    if (node.type === "tag") {
      texts.push(node.text)
    } else if (node.type === "choice") {
      for (const opt of node.options) {
        stack.push(...opt)
      }
    }
  }
  return texts
}

function getEntrySearchableName(entry: Entry): string {
  return entry.name
}

function getEntrySearchableTags(entry: Entry): string {
  const parts: string[] = []
  parts.push(...extractNodeTags(entry.prompt.base))
  for (const char of entry.prompt.characters) {
    parts.push(...extractNodeTags(char.tags))
  }
  if (entry.variants) {
    for (const v of entry.variants) {
      parts.push(v.name)
      parts.push(...extractNodeTags(v.prompt.base))
      for (const char of v.prompt.characters) {
        parts.push(...extractNodeTags(char.tags))
      }
    }
  }
  return parts.join(" ")
}

function matchesExact(entry: Entry, query: string, scope: FilterScope): boolean {
  const q = query.toLowerCase()
  if (scope === "name") {
    return getEntrySearchableName(entry).toLowerCase().includes(q)
  }
  if (scope === "tag") {
    return getEntrySearchableTags(entry).toLowerCase().includes(q)
  }
  return (
    getEntrySearchableName(entry).toLowerCase().includes(q) ||
    getEntrySearchableTags(entry).toLowerCase().includes(q)
  )
}

type FuseEntry = Entry & { _searchText: string }

function buildFuseDocs(entries: Entry[]): FuseEntry[] {
  return entries.map((e) => ({ ...e, _searchText: getEntrySearchableTags(e) }))
}

export function createFilterFuse(entries: Entry[], scope: FilterScope): Fuse<FuseEntry> {
  const docs = buildFuseDocs(entries)
  const keys: Array<{ name: keyof FuseEntry; weight: number }> = []
  if (scope === "all" || scope === "name") {
    keys.push({ name: "name", weight: 0.5 })
  }
  if (scope === "all" || scope === "tag") {
    keys.push({ name: "_searchText", weight: 0.5 })
  }
  return new Fuse(docs, {
    keys,
    threshold: 0.6,
    ignoreLocation: true,
    includeScore: false,
  })
}

export function filterEntriesExact(entries: Entry[], query: string, scope: FilterScope): Entry[] {
  if (!query.trim()) return entries
  return entries.filter((e) => matchesExact(e, query.trim(), scope))
}

export function filterEntriesFuzzy(
  fuse: Fuse<FuseEntry>,
  query: string
): Entry[] {
  if (!query.trim()) return []
  return fuse.search(query.trim()).map((r) => r.item)
}

export function filterToc(toc: TocNode[], matchedEntries: Entry[]): TocNode[] {
  const sectionPaths = new Set(matchedEntries.map((e) => e.path.join(" > ")))

  function walk(nodes: TocNode[], parentPath: string[]): TocNode[] {
    const result: TocNode[] = []
    for (const node of nodes) {
      const nodePath = [...parentPath, node.title]
      const pathStr = nodePath.join(" > ")
      const isMatched = sectionPaths.has(pathStr)
      const filteredChildren = node.children ? walk(node.children, nodePath) : undefined
      if (isMatched || (filteredChildren && filteredChildren.length > 0)) {
        result.push({
          ...node,
          children: filteredChildren ?? node.children,
        })
      }
    }
    return result
  }

  return walk(toc, [])
}

export function getAllTocKeys(
  toc: TocNode[],
  parentPath: string[] = []
): string[] {
  const keys: string[] = []
  for (const node of toc) {
    const nodePath = [...parentPath, node.title]
    keys.push(nodePath.join("\0"))
    if (node.children) {
      keys.push(...getAllTocKeys(node.children, nodePath))
    }
  }
  return keys
}

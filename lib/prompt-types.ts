/**
 * Prompt 结构化标签的共享 TypeScript 类型定义
 * 与 PromptCodex docs/final-yaml-schema.md 对齐
 */

export interface TagNode {
  type: "tag"
  text: string
  weight: number
  comment?: string
  placeholder?: boolean
}

export interface ChoiceNode {
  type: "choice"
  weight: number
  options: PromptNode[][]
  allow_empty: boolean
}

export type PromptNode = TagNode | ChoiceNode

export interface CharacterBlock {
  id: number
  tags: PromptNode[]
  notes: string[]
}

export interface Prompt {
  base: PromptNode[]
  characters: CharacterBlock[]
  comments: string[]
}

export interface Variant {
  name: string
  prompt: Prompt
  notes?: string
}

export interface Entry {
  id: string
  name: string
  path: string[]
  prompt: Prompt
  notes?: string
  variants?: Variant[]
}

export interface TocNode {
  title: string
  level: number
  children?: TocNode[]
}

export type TargetModel = "novelai" | "comfyui"

export type FilterScope = "all" | "name" | "tag"
export type FilterMode = "exact" | "fuzzy"

export interface FileInfo {
  id: string
  title: string
  filename: string
  entryCount: number
}

export interface FileData {
  toc: TocNode[]
  entries: Entry[]
}

export interface FileIndex {
  files: FileInfo[]
}

/**
 * Prompt 数据构建脚本
 * 读取 data/prompt-codex/*.yaml → 生成 public/data/prompts/ 下的 JSON 文件
 *
 * 用法: pnpm tsx data/prompt-codex/build-data.ts
 */
import * as fs from "fs"
import * as path from "path"
import * as yaml from "js-yaml"

const DATA_DIR = path.resolve("data/prompt-codex")
const OUTPUT_DIR = path.resolve("public/data/prompts")

// --- 类型定义 (与 lib/prompt-types.ts 共享) ---

interface TagNode {
  type: "tag"
  text: string
  weight: number
  comment?: string
  placeholder?: boolean
}

interface ChoiceNode {
  type: "choice"
  weight: number
  options: PromptNode[][]
  allow_empty: boolean
}

type PromptNode = TagNode | ChoiceNode

interface CharacterBlock {
  id: number
  tags: PromptNode[]
  notes: string[]
}

interface Prompt {
  base: PromptNode[]
  characters: CharacterBlock[]
  comments: string[]
}

interface Variant {
  name: string
  prompt: Prompt
  notes?: string
}

interface Entry {
  id: string
  name: string
  path: string[]
  prompt: Prompt
  notes?: string
  variants?: Variant[]
}

interface TocNode {
  title: string
  level: number
  children?: TocNode[]
}

interface FileData {
  toc: TocNode[]
  entries: Entry[]
}

interface FileInfo {
  id: string
  title: string
  filename: string
  entryCount: number
}

// --- 工具函数 ---

function ensureDir(dir: string) {
  if (!fs.existsSync(dir)) {
    fs.mkdirSync(dir, { recursive: true })
  }
}

function buildTocTree(obj: Record<string, unknown>, level = 0): TocNode[] {
  const result: TocNode[] = []
  for (const key of Object.keys(obj || {})) {
    const node = obj[key] as Record<string, unknown> | undefined
    const hasEntries = node && Array.isArray(node.entries) && node.entries.length > 0
    const childKeys = Object.keys(node || {}).filter((k) => k !== "entries")
    const hasChildren = childKeys.length > 0

    const tocNode: TocNode = { title: key, level }

    if (hasChildren) {
      const children: TocNode[] = []
      for (const childKey of childKeys) {
        const childNode = node![childKey] as Record<string, unknown> | undefined
        const childHasContent =
          (childNode && Array.isArray(childNode.entries) && childNode.entries.length > 0) ||
          Object.keys(childNode || {}).some((k) => k !== "entries")
        if (childHasContent) {
          const built = buildTocTree({ [childKey]: childNode }, level + 1)
          children.push(...built)
        }
      }
      if (children.length > 0) {
        tocNode.children = children
      }
    }

    if (hasEntries || tocNode.children) {
      result.push(tocNode)
    }
  }
  return result
}

function collectEntries(
  obj: Record<string, unknown>,
  pathSegments: string[] = [],
  fileId: string,
  entries: Entry[] = []
): Entry[] {
  if (obj && Array.isArray(obj.entries)) {
    for (let i = 0; i < obj.entries.length; i++) {
      const raw = obj.entries[i] as Record<string, unknown>
      const entry: Entry = {
        id: `${fileId}--${pathSegments.join("--")}--${i}`,
        name: (raw.name as string) || "",
        path: [...pathSegments],
        prompt: (raw.prompt as Prompt) || { base: [], characters: [], comments: [] },
        notes: raw.notes as string | undefined,
      }
      if (raw.variants && (raw.variants as unknown[]).length > 0) {
        entry.variants = (raw.variants as unknown[]).map((v: unknown) => {
          const vObj = v as Record<string, unknown>
          return {
            name: vObj.name as string,
            prompt: (vObj.prompt as Prompt) || { base: [], characters: [], comments: [] },
            notes: vObj.notes as string | undefined,
          }
        })
      }
      entries.push(entry)
    }
  }

  for (const key of Object.keys(obj || {})) {
    if (key === "entries") continue
    const child = obj[key] as Record<string, unknown> | undefined
    if (typeof child === "object" && child !== null) {
      collectEntries(child, [...pathSegments, key], fileId, entries)
    }
  }

  return entries
}

function cleanFileId(filename: string): string {
  const base = filename
    .replace(/\.yaml$/i, "")
    .replace(/NovelAI个人法典/g, "")
    .replace(/NovalAI个人法典/g, "")
    .replace(/所长/g, "")
    .replace(/一般所长整理/g, "")
    .replace(/（[^）]*版[^）]*）/g, "")
    .trim()

  if (base.includes("常规")) return "normal"
  // 不分上下的色色文件统一用 nsfw
  if (base.includes("色色")) return "nsfw"
  return base.replace(/\s+/g, "-").replace(/[^a-zA-Z0-9一-龥_-]/g, "").toLowerCase()
}

function cleanTitle(filename: string): string {
  const base = filename.replace(/\.yaml$/i, "")

  if (base.includes("常规")) return "常规法典"
  if (base.includes("色色")) return "色色法典"

  return base
    .replace(/（[^）]*版[^）]*）/g, "")
    .replace(/所长/g, "")
    .trim()
}

function countTocNodes(nodes: TocNode[]): number {
  let count = nodes.length
  for (const n of nodes) {
    if (n.children) count += countTocNodes(n.children)
  }
  return count
}

// --- 主流程 ---

async function main() {
  ensureDir(OUTPUT_DIR)
  ensureDir(path.join(OUTPUT_DIR, "files"))

  const yamlFiles = fs
    .readdirSync(DATA_DIR)
    .filter((f) => f.endsWith(".yaml"))
    .sort()

  if (yamlFiles.length === 0) {
    console.warn(`警告: 在 ${DATA_DIR} 中未找到 YAML 文件`)
    return
  }

  console.log(`发现 ${yamlFiles.length} 个 YAML 文件`)

  const filesInfo: FileInfo[] = []

  for (const filename of yamlFiles) {
    const fileId = cleanFileId(filename)
    const title = cleanTitle(filename)
    console.log(`\n处理: ${filename} (id=${fileId})`)

    const content = fs.readFileSync(path.join(DATA_DIR, filename), "utf-8")
    const data = yaml.load(content) as Record<string, unknown>

    // 构建 TOC
    const toc = buildTocTree(data)
    console.log(`  TOC 节点数: ${countTocNodes(toc)}`)

    // 收集 entries
    const entries = collectEntries(data, [], fileId)
    console.log(`  Entries 数: ${entries.length}`)

    // 写入文件数据
    const fileData: FileData = { toc, entries }
    const outFilename = `${fileId}.json`
    fs.writeFileSync(
      path.join(OUTPUT_DIR, "files", outFilename),
      JSON.stringify(fileData),
      "utf-8"
    )
    console.log(`  输出: files/${outFilename}`)

    filesInfo.push({
      id: fileId,
      title,
      filename: outFilename,
      entryCount: entries.length,
    })
  }

  // 生成 index.json
  const index = { files: filesInfo }
  fs.writeFileSync(path.join(OUTPUT_DIR, "index.json"), JSON.stringify(index), "utf-8")
  console.log(`\n输出: index.json (${filesInfo.length} 个文件)`)

  // 生成文件大小报告
  console.log("\n--- 输出文件大小 ---")
  for (const f of filesInfo) {
    const fp = path.join(OUTPUT_DIR, "files", f.filename)
    if (fs.existsSync(fp)) {
      const size = fs.statSync(fp).size
      console.log(`  ${f.filename}: ${(size / 1024 / 1024).toFixed(2)} MB (${f.entryCount} entries)`)
    }
  }
}

main().catch((err) => {
  console.error("构建失败:", err)
  process.exit(1)
})

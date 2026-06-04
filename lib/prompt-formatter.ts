/**
 * Prompt 格式化引擎
 * 将结构化 Prompt 转换为目标模型的文本格式
 */
import type { TagNode, PromptNode, Prompt, TargetModel, WeightMode } from "@/lib/prompt-types"

function formatTagNode(
  node: TagNode,
  model: TargetModel,
  effectiveWeight: number,
  weightMode: WeightMode
): string {
  const text = node.text.trim()
  if (!text) return ""

  // Anima 模式：对权重取平方
  const finalWeight =
    weightMode === "anima" && model === "comfyui"
      ? effectiveWeight * effectiveWeight
      : effectiveWeight

  if (model === "comfyui") {
    if (finalWeight === 1.0) return text
    return `(${text}:${finalWeight.toFixed(2)})`
  }

  // novelai (default)
  if (finalWeight === 1.0) return text
  return `${finalWeight.toFixed(2)}::${text}::`
}

/**
 * 递归格式化节点列表，支持外层权重累积
 */
function formatNodes(
  nodes: PromptNode[],
  model: TargetModel,
  selections: Record<string, number>,
  choiceIdPrefix: string,
  outerWeight: number,
  weightMode: WeightMode
): string {
  const parts: string[] = []

  for (let i = 0; i < nodes.length; i++) {
    const node = nodes[i]
    const nodeId = `${choiceIdPrefix}-${i}`

    if (node.type === "tag") {
      const effectiveWeight = node.weight * outerWeight
      const formatted = formatTagNode(node, model, effectiveWeight, weightMode)
      if (formatted) parts.push(formatted)
    } else if (node.type === "choice") {
      const selectedIndex = selections[nodeId]
      const hasSelection = selectedIndex !== undefined

      if (hasSelection && selectedIndex === -1) {
        // 用户明确选择了 "不添加"
        continue
      }

      const optionIndex = hasSelection
        ? selectedIndex
        : node.allow_empty
          ? -1
          : 0

      if (optionIndex === -1) {
        continue
      }

      const option = node.options[optionIndex]
      if (!option) continue

      // choice 权重乘到 option 内部
      const choiceWeight = node.weight * outerWeight
      const inner = formatNodes(
        option,
        model,
        selections,
        `${nodeId}-opt`,
        choiceWeight,
        weightMode
      )

      if (inner) parts.push(inner)
    }
  }

  return parts.join(", ")
}

export function formatPrompt(
  prompt: Prompt,
  model: TargetModel,
  selections: Record<string, number>,
  prefix: string = "root",
  weightMode: WeightMode = "default"
): string {
  const basePart = formatNodes(prompt.base, model, selections, prefix, 1.0, weightMode)

  if (prompt.characters.length === 0) {
    return basePart
  }

  // 多角色处理
  const charParts: string[] = []
  for (let i = 0; i < prompt.characters.length; i++) {
    const char = prompt.characters[i]
    const charText = formatNodes(char.tags, model, selections, `${prefix}-char-${i}`, 1.0, weightMode)
    if (charText) charParts.push(charText)
  }

  if (model === "novelai") {
    // NovelAI V4+ 管道语法: base | char1 | char2
    return [basePart, ...charParts].filter(Boolean).join(" | ")
  } else {
    // ComfyUI: 用换行 + Character N: 前缀分隔角色
    const charLines = charParts.map((c, i) => `Character ${i + 1}: ${c}`)
    return [basePart, ...charLines].filter(Boolean).join("\n")
  }
}

/**
 * 检查 prompt 是否包含占位符
 */
export function hasPlaceholders(nodes: PromptNode[]): boolean {
  const stack = [...nodes]
  while (stack.length > 0) {
    const node = stack.pop()!
    if (node.type === "tag" && node.placeholder) {
      return true
    } else if (node.type === "choice") {
      for (const opt of node.options) {
        stack.push(...opt)
      }
    }
  }
  return false
}

/**
 * 统计 prompt 中的占位符数量
 */
export function countPlaceholders(nodes: PromptNode[]): number {
  let count = 0
  const stack = [...nodes]
  while (stack.length > 0) {
    const node = stack.pop()!
    if (node.type === "tag" && node.placeholder) {
      count++
    } else if (node.type === "choice") {
      for (const opt of node.options) {
        stack.push(...opt)
      }
    }
  }
  return count
}

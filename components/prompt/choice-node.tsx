"use client"

import { useState } from "react"
import type { ChoiceNode } from "@/lib/prompt-types"
import { useChoices } from "@/lib/prompt-choice-context"
import { PromptRenderer } from "./prompt-renderer"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Eye } from "lucide-react"

interface ChoiceNodeComponentProps {
  node: ChoiceNode
  choiceId: string
}

export function ChoiceNodeComponent({ node, choiceId }: ChoiceNodeComponentProps) {
  const { selections, setSelection } = useChoices()
  const [showAll, setShowAll] = useState(false)

  const selectedIndex = selections[choiceId]
  const hasSelection = selectedIndex !== undefined

  // 计算每个 option 的文本预览（取前 2-3 个 tag）
  const getOptionPreview = (option: typeof node.options[number]) => {
    const tags = option
      .filter((n) => n.type === "tag")
      .map((n) => n.text)
      .slice(0, 3)
    return tags.join(", ") || "(空)"
  }

  const currentOption =
    hasSelection && node.options[selectedIndex]
      ? node.options[selectedIndex]
      : null

  return (
    <span className="inline-flex items-center gap-1.5 rounded-md border border-dashed border-primary/30 bg-primary/5 px-2 py-1">
      <span className="text-[10px] text-muted-foreground font-medium">选择</span>

      <Select
        value={hasSelection ? String(selectedIndex) : node.allow_empty ? "empty" : ""}
        onValueChange={(v) => {
          if (v === "empty") {
            setSelection(choiceId, -1)
          } else {
            setSelection(choiceId, parseInt(v, 10))
          }
        }}
      >
        <SelectTrigger className="h-6 w-auto min-w-[80px] text-xs border-none bg-transparent shadow-none focus:ring-0 px-1">
          <SelectValue placeholder={node.allow_empty ? "不选" : "选择..."} />
        </SelectTrigger>
        <SelectContent>
          {node.allow_empty && (
            <SelectItem value="empty" className="text-xs">
              (不添加)
            </SelectItem>
          )}
          {node.options.map((opt, i) => (
            <SelectItem key={i} value={String(i)} className="text-xs">
              {getOptionPreview(opt)}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>

      {/* 查看全部按钮 */}
      <Button
        variant="ghost"
        size="icon"
        className="h-5 w-5"
        onClick={() => setShowAll(true)}
      >
        <Eye className="h-3 w-3" />
      </Button>

      {/* 显示当前选中的 tags */}
      {currentOption && (
        <PromptRenderer nodes={currentOption} pathPrefix={`${choiceId}-sel`} />
      )}

      {/* 查看全部 Dialog */}
      <Dialog open={showAll} onOpenChange={setShowAll}>
        <DialogContent className="max-w-2xl max-h-[80vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="text-sm">所有选项</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            {node.allow_empty && (
              <div className="rounded-md border border-dashed border-muted-foreground/30 p-3">
                <div className="text-xs font-medium text-muted-foreground mb-1">
                  选项: (不添加)
                </div>
                <div className="text-xs text-muted-foreground">不添加任何 tag</div>
              </div>
            )}
            {node.options.map((opt, i) => (
              <div
                key={i}
                className={`rounded-md border p-3 transition-colors ${
                  hasSelection && selectedIndex === i
                    ? "border-primary bg-primary/5"
                    : "border-border hover:bg-accent/50"
                }`}
                onClick={() => {
                  setSelection(choiceId, i)
                }}
              >
                <div className="flex items-center justify-between mb-2">
                  <span className="text-xs font-medium">选项 {i + 1}</span>
                  {hasSelection && selectedIndex === i && (
                    <Badge variant="default" className="text-[10px] h-4">
                      已选中
                    </Badge>
                  )}
                </div>
                <PromptRenderer nodes={opt} pathPrefix={`${choiceId}-opt-${i}`} />
              </div>
            ))}
          </div>
        </DialogContent>
      </Dialog>
    </span>
  )
}

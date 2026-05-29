"use client"

import { useState, useCallback } from "react"
import type { Prompt, TargetModel } from "@/lib/prompt-types"
import { useChoices } from "@/lib/prompt-choice-context"
import { formatPrompt } from "@/lib/prompt-formatter"
import { Button } from "@/components/ui/button"
import { Copy, Check } from "lucide-react"

interface CopyButtonProps {
  prompt: Prompt
  model: TargetModel
  prefix?: string
  size?: "sm" | "default"
  className?: string
}

export function CopyButton({
  prompt,
  model,
  prefix = "copy",
  size = "sm",
  className,
}: CopyButtonProps) {
  const { selections } = useChoices()
  const [copied, setCopied] = useState(false)

  const handleCopy = useCallback(async () => {
    const text = formatPrompt(prompt, model, selections, prefix)
    try {
      await navigator.clipboard.writeText(text)
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    } catch {
      // fallback
      const textarea = document.createElement("textarea")
      textarea.value = text
      document.body.appendChild(textarea)
      textarea.select()
      document.execCommand("copy")
      document.body.removeChild(textarea)
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    }
  }, [prompt, model, selections, prefix])

  return (
    <Button
      variant="outline"
      size={size === "sm" ? "sm" : "default"}
      className={className}
      onClick={handleCopy}
    >
      {copied ? (
        <Check className="h-3.5 w-3.5 mr-1" />
      ) : (
        <Copy className="h-3.5 w-3.5 mr-1" />
      )}
      <span className="text-xs">{copied ? "已复制" : "复制"}</span>
    </Button>
  )
}

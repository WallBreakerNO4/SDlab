"use client"

import { createContext, useContext, useState, useEffect, type ReactNode } from "react"
import type { TargetModel } from "@/lib/prompt-types"

interface ModelContextValue {
  model: TargetModel
  setModel: (model: TargetModel) => void
}

const ModelContext = createContext<ModelContextValue | null>(null)

const STORAGE_KEY = "promptcodex-model"

function getSavedModel(): TargetModel {
  if (typeof window === "undefined") return "comfyui"
  try {
    const saved = localStorage.getItem(STORAGE_KEY)
    if (saved === "novelai" || saved === "comfyui") return saved
  } catch {
    // localStorage 不可用时静默回退
  }
  return "comfyui"
}

export function ModelProvider({ children }: { children: ReactNode }) {
  const [model, setModel] = useState<TargetModel>(getSavedModel)

  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, model)
    } catch {
      // localStorage 不可用时静默忽略
    }
  }, [model])

  return (
    <ModelContext.Provider value={{ model, setModel }}>
      {children}
    </ModelContext.Provider>
  )
}

export function useModel() {
  const ctx = useContext(ModelContext)
  if (!ctx) throw new Error("useModel must be used within ModelProvider")
  return ctx
}

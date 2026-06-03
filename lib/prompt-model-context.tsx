"use client"

import { createContext, useContext, useState, useEffect, type ReactNode } from "react"
import type { TargetModel, WeightMode } from "@/lib/prompt-types"

interface ModelContextValue {
  model: TargetModel
  setModel: (model: TargetModel) => void
  weightMode: WeightMode
  setWeightMode: (mode: WeightMode) => void
}

const ModelContext = createContext<ModelContextValue | null>(null)

const MODEL_STORAGE_KEY = "promptcodex-model"
const WEIGHT_MODE_STORAGE_KEY = "promptcodex-weight-mode"

function getSavedModel(): TargetModel {
  if (typeof window === "undefined") return "comfyui"
  try {
    const saved = localStorage.getItem(MODEL_STORAGE_KEY)
    if (saved === "novelai" || saved === "comfyui") return saved
  } catch {
    // localStorage 不可用时静默回退
  }
  return "comfyui"
}

function getSavedWeightMode(): WeightMode {
  if (typeof window === "undefined") return "default"
  try {
    const saved = localStorage.getItem(WEIGHT_MODE_STORAGE_KEY)
    if (saved === "default" || saved === "anima") return saved
  } catch {
    // localStorage 不可用时静默回退
  }
  return "default"
}

export function ModelProvider({ children }: { children: ReactNode }) {
  const [model, setModel] = useState<TargetModel>(getSavedModel)
  const [weightMode, setWeightMode] = useState<WeightMode>(getSavedWeightMode)

  useEffect(() => {
    try {
      localStorage.setItem(MODEL_STORAGE_KEY, model)
    } catch {
      // localStorage 不可用时静默忽略
    }
  }, [model])

  useEffect(() => {
    try {
      localStorage.setItem(WEIGHT_MODE_STORAGE_KEY, weightMode)
    } catch {
      // localStorage 不可用时静默忽略
    }
  }, [weightMode])

  return (
    <ModelContext.Provider value={{ model, setModel, weightMode, setWeightMode }}>
      {children}
    </ModelContext.Provider>
  )
}

export function useModel() {
  const ctx = useContext(ModelContext)
  if (!ctx) throw new Error("useModel must be used within ModelProvider")
  return ctx
}

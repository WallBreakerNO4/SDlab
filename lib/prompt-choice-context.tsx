"use client"

import { createContext, useContext, useState, useCallback, type ReactNode } from "react"

interface ChoiceContextValue {
  selections: Record<string, number>
  setSelection: (choiceId: string, optionIndex: number) => void
  resetAll: () => void
}

const ChoiceContext = createContext<ChoiceContextValue | null>(null)

export function ChoiceProvider({ children }: { children: ReactNode }) {
  const [selections, setSelections] = useState<Record<string, number>>({})

  const setSelection = useCallback((choiceId: string, optionIndex: number) => {
    setSelections((prev) => ({ ...prev, [choiceId]: optionIndex }))
  }, [])

  const resetAll = useCallback(() => {
    setSelections({})
  }, [])

  return (
    <ChoiceContext.Provider value={{ selections, setSelection, resetAll }}>
      {children}
    </ChoiceContext.Provider>
  )
}

export function useChoices() {
  const ctx = useContext(ChoiceContext)
  if (!ctx) throw new Error("useChoices must be used within ChoiceProvider")
  return ctx
}

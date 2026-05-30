"use client"

import type { CharacterBlock } from "@/lib/prompt-types"
import { PromptRenderer } from "./prompt-renderer"
import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "@/components/ui/tabs"
import { Badge } from "@/components/ui/badge"
import { Users } from "lucide-react"

interface CharacterBlockComponentProps {
  characters: CharacterBlock[]
  pathPrefix?: string
}

export function CharacterBlockComponent({
  characters,
  pathPrefix = "",
}: CharacterBlockComponentProps) {
  if (characters.length === 0) return null

  return (
    <div className="mt-2 rounded-md border bg-muted/30 p-2">
      <div className="flex items-center gap-1.5 mb-2 text-xs text-muted-foreground">
        <Users className="h-3.5 w-3.5" />
        <span className="font-medium">多角色</span>
        <Badge variant="outline" className="text-[10px] h-4">
          {characters.length} 个角色
        </Badge>
      </div>

      <Tabs defaultValue="char-0" className="w-full">
        <TabsList className="h-7">
          {characters.map((char, i) => (
            <TabsTrigger key={i} value={`char-${i}`} className="text-[10px] h-5 px-2 py-0">
              角色 {char.id}
            </TabsTrigger>
          ))}
        </TabsList>
        {characters.map((char, i) => (
          <TabsContent key={i} value={`char-${i}`} className="mt-2">
            <PromptRenderer
              nodes={char.tags}
              pathPrefix={`${pathPrefix}-char-${i}`}
            />
            {char.notes.length > 0 && (
              <div className="mt-1.5 text-[10px] text-muted-foreground">
                {char.notes.map((n, j) => (
                  <div key={j}>• {n}</div>
                ))}
              </div>
            )}
          </TabsContent>
        ))}
      </Tabs>
    </div>
  )
}

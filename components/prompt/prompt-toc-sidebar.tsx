"use client"

import { useState } from "react"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetTrigger } from "@/components/ui/sheet"
import { Button } from "@/components/ui/button"
import { TocTree } from "./prompt-toc-tree"
import { Menu } from "lucide-react"
import type { TocNode } from "@/lib/prompt-types"

interface TocSidebarProps {
  toc: TocNode[]
  activeSection: string | null
  onSectionClick: (title: string) => void
  expandedNodes: Set<string>
  onToggleExpand: (key: string) => void
}

export function TocSidebar({
  toc,
  activeSection,
  onSectionClick,
  expandedNodes,
  onToggleExpand,
}: TocSidebarProps) {
  const [mobileOpen, setMobileOpen] = useState(false)

  const handleSectionClick = (title: string) => {
    onSectionClick(title)
    setMobileOpen(false)
  }

  const sidebarContent = (
    <>
      <div className="px-3 py-2 border-b">
        <h2 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
          目录
        </h2>
      </div>
      <ScrollArea className="flex-1">
        <div className="p-2">
          <TocTree
            nodes={toc}
            activeSection={activeSection}
            onSectionClick={handleSectionClick}
            expandedNodes={expandedNodes}
            onToggleExpand={onToggleExpand}
          />
        </div>
      </ScrollArea>
    </>
  )

  return (
    <>
      {/* Desktop sidebar */}
      <aside className="hidden md:flex w-64 border-r bg-background flex-col">
        {sidebarContent}
      </aside>

      {/* Mobile sidebar toggle + sheet */}
      <div className="md:hidden">
        <Sheet open={mobileOpen} onOpenChange={setMobileOpen}>
          <SheetTrigger asChild>
            <Button
              variant="ghost"
              size="icon"
              className="fixed bottom-4 left-4 z-50 h-10 w-10 rounded-full shadow-lg bg-background border"
            >
              <Menu className="h-5 w-5" />
            </Button>
          </SheetTrigger>
          <SheetContent side="left" className="w-72 p-0 flex flex-col">
            <SheetHeader className="px-3 py-2 border-b">
              <SheetTitle className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                目录
              </SheetTitle>
            </SheetHeader>
            <ScrollArea className="flex-1">
              <div className="p-2">
                <TocTree
                  nodes={toc}
                  activeSection={activeSection}
                  onSectionClick={handleSectionClick}
                  expandedNodes={expandedNodes}
                  onToggleExpand={onToggleExpand}
                />
              </div>
            </ScrollArea>
          </SheetContent>
        </Sheet>
      </div>
    </>
  )
}

"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { ModelCard } from "@/components/home/model-card";
import { MasonryGrid } from "@/components/ui/masonry-grid";
import { PreviewDialog } from "@/components/home/preview-dialog";
import { Badge } from "@/components/ui/badge";
import {
  Empty,
  EmptyDescription,
  EmptyHeader,
  EmptyTitle,
} from "@/components/ui/empty";

import type { RunSummary } from "@/lib/comfyui-types";

type HomePageClientProps = {
  models: RunSummary[];
  hasError?: boolean;
};

export default function HomePageClient({
  models,
  hasError = false,
}: HomePageClientProps) {
  const t = useTranslations("home");
  const [previewImage, setPreviewImage] = useState<string | null>(null);
  const isEmpty = models.length === 0;

  return (
    <main className="relative h-full w-full flex flex-col items-center selection:bg-primary/20 selection:text-primary overflow-y-auto">
      {/* Decorative Grid Background - refined opacity */}
      <div className="pointer-events-none absolute inset-0 flex justify-center z-[-1]">
        <div className="w-full h-full bg-[linear-gradient(to_right,var(--color-border)_1px,transparent_1px),linear-gradient(to_bottom,var(--color-border)_1px,transparent_1px)] bg-size-[32px_32px] opacity-20 mask-[radial-gradient(ellipse_70%_60%_at_50%_0%,#000_60%,transparent_100%)]"></div>
      </div>

      {/* Decorative Glow */}
      <div className="pointer-events-none absolute top-0 left-1/2 -translate-x-1/2 w-200 h-100 opacity-10 dark:opacity-20 mix-blend-screen blur-[100px] rounded-full bg-primary/30 z-[-1]"></div>

      <div className="w-full max-w-7xl px-4 md:px-8 py-24 md:py-32 flex flex-col gap-32">
        {/* Hero Section */}
        <section className="animate-fade-in-up flex flex-col items-start gap-8 max-w-3xl">
          <div className="flex flex-col space-y-6">
            <div className="flex items-center">
              <Badge
                variant="outline"
                className="px-3 py-1 font-mono text-[10px] tracking-[0.2em] border-primary/20 text-primary bg-primary/5 rounded-none uppercase flex items-center gap-2"
              >
                <span className="w-1.5 h-1.5 rounded-full bg-primary animate-pulse" />
                {t("badge")}
              </Badge>
            </div>

            <h1 className="text-5xl md:text-7xl font-black tracking-tight leading-[1.05] text-foreground">
              {t("title")}
              <span className="block mt-1 bg-linear-to-br from-primary to-primary/40 bg-clip-text text-transparent">
                {t("titleAccent")}
              </span>
            </h1>
          </div>

          <p className="text-lg md:text-xl text-muted-foreground leading-relaxed max-w-2xl font-light">
            {t("subtitle")}
          </p>
        </section>

        {/* Models Section */}
        <section className="w-full flex flex-col gap-10">
          <div className="flex flex-col sm:flex-row sm:items-end justify-between border-b border-border/40 pb-5 gap-4">
            <div className="space-y-1">
              <h2 className="text-2xl md:text-3xl font-bold tracking-tight">
                {t("modelsSection")}
              </h2>
              <p className="text-sm text-muted-foreground">
                {t("modelsDescription")}
              </p>
            </div>
            {!isEmpty && (
              <div className="flex items-center gap-3 shrink-0">
                <span className="text-muted-foreground font-mono text-[10px] tracking-widest uppercase border border-border/40 px-2 py-1 bg-muted/20">
                  {t("modelsCount", { count: models.length })}
                </span>
              </div>
            )}
          </div>

          {isEmpty ? (
            <Empty className="py-24 border border-dashed border-border/50 bg-background/30 backdrop-blur-sm">
              <EmptyHeader>
                <EmptyTitle className="text-xl">
                  {hasError ? t("errorTitle") : t("emptyTitle")}
                </EmptyTitle>
                <EmptyDescription className="text-sm max-w-sm mx-auto">
                  {hasError
                    ? t("errorDescription")
                    : t("emptyDescription")}
                </EmptyDescription>
              </EmptyHeader>
            </Empty>
          ) : null}

          {models.length > 0 ? (
            <MasonryGrid>
              {models.map((modelSummary, index) => (
                <ModelCard
                  key={modelSummary.run_dir}
                  index={index}
                  modelSummary={modelSummary}
                  onPreviewImage={setPreviewImage}
                />
              ))}
            </MasonryGrid>
          ) : null}
        </section>
      </div>

      <PreviewDialog
        imageUrl={previewImage}
        onOpenChange={(open) => !open && setPreviewImage(null)}
      />
    </main>
  );
}

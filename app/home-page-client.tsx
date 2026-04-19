"use client";

import { useState } from "react";

import { ModelCard } from "@/components/home/model-card";
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
                Stable Diffusion Research
              </Badge>
            </div>

            <h1 className="text-5xl md:text-7xl font-black tracking-tight leading-[1.05] text-foreground">
              AI 图像风格
              <span className="block mt-1 bg-linear-to-br from-primary to-primary/40 bg-clip-text text-transparent">
                实验室
              </span>
            </h1>
          </div>

          <p className="text-lg md:text-xl text-muted-foreground leading-relaxed max-w-2xl font-light">
            系统化的 Stable Diffusion
            模型画风评估平台。通过可复现的测试与画风组合实验，展示可对比的画风实验。
          </p>
        </section>

        {/* Models Section */}
        <section className="w-full flex flex-col gap-10">
          <div className="flex flex-col sm:flex-row sm:items-end justify-between border-b border-border/40 pb-5 gap-4">
            <div className="space-y-1">
              <h2 className="text-2xl md:text-3xl font-bold tracking-tight">
                模型目录
              </h2>
              <p className="text-sm text-muted-foreground">
                浏览最近收录的模型评测与风格网格
              </p>
            </div>
            {!isEmpty && (
              <div className="flex items-center gap-3 shrink-0">
                <span className="text-muted-foreground font-mono text-[10px] tracking-widest uppercase border border-border/40 px-2 py-1 bg-muted/20">
                  {models.length} Models Found
                </span>
              </div>
            )}
          </div>

          {isEmpty ? (
            <Empty className="py-24 border border-dashed border-border/50 bg-background/30 backdrop-blur-sm">
              <EmptyHeader>
                <EmptyTitle className="text-xl">
                  {hasError ? "加载失败" : "暂无模型"}
                </EmptyTitle>
                <EmptyDescription className="text-sm max-w-sm mx-auto">
                  {hasError
                    ? "请查看终端日志或 Network 面板定位首页数据链路错误。"
                    : "暂无可用模型数据，等待后端数据同步。"}
                </EmptyDescription>
              </EmptyHeader>
            </Empty>
          ) : null}

          {models.length > 0 ? (
            <div className="columns-1 md:columns-2 lg:columns-3 gap-8">
              {models.map((modelSummary, index) => (
                <ModelCard
                  key={modelSummary.run_dir}
                  index={index}
                  modelSummary={modelSummary}
                  onPreviewImage={setPreviewImage}
                />
              ))}
            </div>
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

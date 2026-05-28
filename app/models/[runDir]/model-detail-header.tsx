import { useLocale, useTranslations } from "next-intl";
import { HugeiconsIcon } from "@hugeicons/react";
import { HuggingFace, Civitai, ComfyUI } from "@lobehub/icons";
import type { User } from "@supabase/supabase-js";
import { FileIcon, LinkSquare02Icon } from "@hugeicons/core-free-icons";

import type { ModelDetailResponse } from "./model-detail-types";

type ModelDetailHeaderProps = {
  detailData: ModelDetailResponse;
  user: User | null;
  onRequireLogin: () => void;
};

export function ModelDetailHeader({
  detailData,
  user,
  onRequireLogin,
}: ModelDetailHeaderProps) {
  const t = useTranslations("modelDetail");
  const locale = useLocale();
  const modelName = detailData.run.model?.name || detailData.run.run_dir;
  const modelDesc =
    detailData.run.model?.description?.[locale as "zh" | "en"] ??
    detailData.run.model?.description?.zh ??
    detailData.run.model?.description?.en;
  const links = detailData.run.model?.links;
  const workflow = detailData.run.workflow;

  return (
    <div className="animate-fade-in-up flex flex-col gap-3 py-2 px-1">
      <div className="flex items-end justify-between gap-4 flex-wrap">
        <div className="flex items-center gap-3">
          <h1 className="text-xl font-semibold tracking-tight">{modelName}</h1>
          <div className="text-muted-foreground flex items-center gap-1.5 bg-muted/30 px-2 py-0.5 rounded-md border border-border/40">
            <HugeiconsIcon
              icon={FileIcon}
              className="size-3.5"
              strokeWidth={2}
            />
            <span className="font-mono text-xs">{detailData.run.run_dir}</span>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2 text-xs">
          {links && (links.homepage || links.huggingface || links.civitai) ? (
            <div className="flex items-center gap-1.5">
              {links.homepage ? (
                <a
                  href={links.homepage}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="hover:bg-primary/10 hover:text-primary text-muted-foreground inline-flex items-center gap-1 rounded-md border border-border/40 bg-background/50 px-2 py-1 font-medium transition-colors backdrop-blur-sm"
                >
                  <HugeiconsIcon
                    icon={LinkSquare02Icon}
                    className="size-3"
                    strokeWidth={2}
                  />
                  {t("homepage")}
                </a>
              ) : null}
              {links.huggingface ? (
                <a
                  href={links.huggingface}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="hover:bg-primary/10 hover:text-primary text-muted-foreground inline-flex items-center gap-1 rounded-md border border-border/40 bg-background/50 px-2 py-1 font-medium transition-colors backdrop-blur-sm"
                >
                  <HuggingFace.Color className="size-3" />
                  {t("huggingface")}
                </a>
              ) : null}
              {links.civitai ? (
                <a
                  href={links.civitai}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="hover:bg-primary/10 hover:text-primary text-muted-foreground inline-flex items-center gap-1 rounded-md border border-border/40 bg-background/50 px-2 py-1 font-medium transition-colors backdrop-blur-sm"
                >
                  <Civitai.Color className="size-3" />
                  {t("civitai")}
                </a>
              ) : null}
            </div>
          ) : null}

          {workflow?.download_url ? (
            user ? (
              <a
                href={workflow.download_url}
                download
                className="hover:bg-primary/10 hover:text-primary text-muted-foreground inline-flex items-center gap-1 rounded-md border border-border/40 bg-background/50 px-2 py-1 font-medium transition-colors backdrop-blur-sm"
              >
                <ComfyUI.Color className="size-3" />
                {t("downloadWorkflow")}
              </a>
            ) : (
              <button
                type="button"
                onClick={onRequireLogin}
                className="hover:bg-primary/10 hover:text-primary text-muted-foreground inline-flex items-center gap-1 rounded-md border border-border/40 bg-background/50 px-2 py-1 font-medium transition-colors backdrop-blur-sm"
              >
                <ComfyUI.Color className="size-3" />
                {t("downloadWorkflow")}
              </button>
            )
          ) : null}
        </div>
      </div>

      {modelDesc ? (
        <div className="group relative">
          <p className="text-muted-foreground/80 text-xs leading-relaxed line-clamp-1 group-hover:line-clamp-none transition-all duration-300">
            {modelDesc}
          </p>
        </div>
      ) : null}
    </div>
  );
}

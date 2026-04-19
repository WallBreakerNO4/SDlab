"use client";

import { useMemo, useState } from "react";
import Link from "next/link";

import { AuthLoginDialog } from "@/components/auth-login-dialog";
import { useAuth } from "@/components/auth-provider";
import {
  type BlurhashCell,
  VirtualGrid,
} from "@/components/comfyui/virtual-grid";
import { useUserPreferences } from "@/components/user-preferences-provider";
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from "@/components/ui/breadcrumb";
import {
  Empty,
  EmptyDescription,
  EmptyHeader,
  EmptyTitle,
} from "@/components/ui/empty";
import { ModelDetailHeader } from "./model-detail-header";
import { GridSkeleton, SummarySkeleton } from "./model-detail-skeletons";
import { useModelDetailData } from "./use-model-detail-data";

export function ModelDetailClientPage({ runDir }: { runDir: string }) {
  const { user } = useAuth();
  const { showNsfw } = useUserPreferences();
  const [loginDialogOpen, setLoginDialogOpen] = useState(false);
  const { detailLoadState, gridLoadState, detailData, gridData } =
    useModelDetailData(runDir, showNsfw);

  const isDetailLoading = detailLoadState === "loading";
  const isGridLoading = gridLoadState === "loading";
  const isDetailReady = detailLoadState === "ready" && detailData !== null;
  const isGridReady = gridLoadState === "ready" && gridData !== null;

  const breadcrumbTitle = isDetailReady
    ? detailData.run.model?.name || detailData.run.run_dir
    : runDir;

  const blurhashMap = useMemo(() => {
    const map = new Map<string, BlurhashCell>();
    if (!gridData?.blurhash_cells) return map;
    for (const cell of gridData.blurhash_cells) {
      const key = `${cell.x_index}:${cell.y_index}`;
      if (!map.has(key)) {
        map.set(key, cell);
      }
    }
    return map;
  }, [gridData]);

  return (
    <main className="mx-auto flex h-full w-full max-w-none flex-col gap-2 overflow-hidden p-2">
      <Breadcrumb>
        <BreadcrumbList>
          <BreadcrumbItem>
            <BreadcrumbLink asChild>
              <Link href="/">首页</Link>
            </BreadcrumbLink>
          </BreadcrumbItem>
          <BreadcrumbSeparator />
          <BreadcrumbItem>
            <BreadcrumbPage>{breadcrumbTitle}</BreadcrumbPage>
          </BreadcrumbItem>
        </BreadcrumbList>
      </Breadcrumb>
      {isDetailLoading ? (
        <div data-testid="model-detail-loading">
          <SummarySkeleton />
        </div>
      ) : null}

      {detailLoadState === "not-found" ? (
        <Empty data-testid="model-not-found">
          <EmptyHeader>
            <EmptyTitle>未找到模型</EmptyTitle>
            <EmptyDescription>
              这个模型页可能已被删除，或当前会话无权访问。
            </EmptyDescription>
          </EmptyHeader>
        </Empty>
      ) : null}

      {detailLoadState === "error" ? (
        <Empty data-testid="model-error">
          <EmptyHeader>
            <EmptyTitle>加载失败</EmptyTitle>
            <EmptyDescription>
              请求模型详情失败，请稍后刷新重试。
            </EmptyDescription>
          </EmptyHeader>
        </Empty>
      ) : null}

      {isDetailReady ? (
        <ModelDetailHeader
          detailData={detailData}
          user={user}
          onRequireLogin={() => setLoginDialogOpen(true)}
        />
      ) : null}

      <div className="flex min-h-0 flex-1 flex-col">
        {isGridLoading ? <GridSkeleton /> : null}

        {isGridReady ? (
          <div className="min-h-0 flex-1">
            <VirtualGrid
              key={`${runDir}:${showNsfw ? "nsfw" : "sfw"}`}
              runDir={runDir}
              grid={gridData}
              blurhashMap={blurhashMap}
              showNsfw={showNsfw}
            />
          </div>
        ) : null}

        {(gridLoadState === "not-found" || gridLoadState === "error") &&
        isDetailReady ? (
          <Empty>
            <EmptyHeader>
              <EmptyTitle>暂无网格可展示</EmptyTitle>
              <EmptyDescription>
                修复模型标识或请求错误后，此区域将显示完整网格。
              </EmptyDescription>
            </EmptyHeader>
          </Empty>
        ) : null}
      </div>

      <AuthLoginDialog
        open={loginDialogOpen}
        onOpenChange={setLoginDialogOpen}
      />
    </main>
  );
}

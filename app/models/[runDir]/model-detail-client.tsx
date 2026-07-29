"use client";

import { useLocale, useTranslations } from "next-intl";
import { useMemo, useState } from "react";

import { AuthLoginDialog } from "@/components/auth-login-dialog";
import { useAuth } from "@/components/auth-provider";
import { JsonLdBreadcrumbList } from "@/components/json-ld";
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
import { Link } from "@/i18n/navigation";
import { SITE_ORIGIN } from "@/lib/site-origin";

export function ModelDetailClientPage({
  runDir,
  guideHref,
}: {
  runDir: string;
  guideHref: string | null;
}) {
  const t = useTranslations("modelDetail");
  const locale = useLocale();
  const { user } = useAuth();
  const { showNsfw } = useUserPreferences();
  const [loginDialogOpen, setLoginDialogOpen] = useState(false);
  const {
    detailLoadState,
    gridLoadState,
    detailData,
    gridData,
    currentView,
    viewAccess,
    refreshViewAccess,
  } = useModelDetailData({
    runDir,
    showNsfw,
    currentUserId: user?.id ?? null,
  });

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
      <JsonLdBreadcrumbList
        items={[
          { name: t("breadcrumbHome"), url: `${SITE_ORIGIN}/${locale}` },
          {
            name: breadcrumbTitle,
            url: `${SITE_ORIGIN}/${locale}/models/${encodeURIComponent(runDir)}`,
          },
        ]}
      />
      <Breadcrumb>
        <BreadcrumbList>
          <BreadcrumbItem>
            <BreadcrumbLink asChild>
              <Link href="/">{t("breadcrumbHome")}</Link>
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
            <EmptyTitle>{t("notFoundTitle")}</EmptyTitle>
            <EmptyDescription>{t("notFoundDesc")}</EmptyDescription>
          </EmptyHeader>
        </Empty>
      ) : null}

      {detailLoadState === "error" ? (
        <Empty data-testid="model-error">
          <EmptyHeader>
            <EmptyTitle>{t("errorTitle")}</EmptyTitle>
            <EmptyDescription>{t("errorDesc")}</EmptyDescription>
          </EmptyHeader>
        </Empty>
      ) : null}

      {isDetailReady ? (
        <ModelDetailHeader
          detailData={detailData}
          guideHref={guideHref}
          user={user}
          onRequireLogin={() => setLoginDialogOpen(true)}
        />
      ) : null}

      <div className="flex min-h-0 flex-1 flex-col">
        {isGridLoading ? <GridSkeleton /> : null}

        {isGridReady ? (
          <div className="min-h-0 flex-1">
            <VirtualGrid
              key={`${runDir}:${currentView?.release_id ?? "no-release"}:${showNsfw ? "nsfw" : "sfw"}:${viewAccess?.viewer_variant ?? "public"}`}
              runDir={runDir}
              grid={gridData}
              blurhashMap={blurhashMap}
              showNsfw={showNsfw}
              currentView={currentView}
              viewAccess={viewAccess}
              onRefreshViewAccess={refreshViewAccess}
            />
          </div>
        ) : null}

        {(gridLoadState === "not-found" || gridLoadState === "error") &&
        isDetailReady ? (
          <Empty>
            <EmptyHeader>
              <EmptyTitle>{t("noGridTitle")}</EmptyTitle>
              <EmptyDescription>{t("noGridDesc")}</EmptyDescription>
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

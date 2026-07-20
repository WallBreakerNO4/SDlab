"use client";

import { useEffect, useMemo, useState } from "react";
import { useTranslations } from "next-intl";
import { ChevronLeft, ChevronRight, ImageOff } from "lucide-react";
import { Link } from "@/i18n/navigation";
import { useAuth } from "@/components/auth-provider";
import { useUserPreferences } from "@/components/user-preferences-provider";
import { BlurhashCanvas } from "@/components/comfyui/blurhash-canvas";
import { GridImage } from "@/components/comfyui/grid-image";
import { useRenderableVariantSource } from "@/components/comfyui/use-renderable-variant-source";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  flattenRowSlides,
  type ComparisonModel,
  type ComparisonSlice,
  type ComparisonSlide,
} from "@/lib/style-comparison";
import {
  fetchComparisonSlice,
  loadComparisonRowState,
  mapWithConcurrency,
  resolveComparisonRowState,
  type ComparisonRowState,
} from "./comparison-loader";

export default function FavoriteComparisonDetail({
  styleKey,
}: {
  styleKey: string;
}) {
  const t = useTranslations("styleFavorites");
  const { user } = useAuth();
  const { showNsfw } = useUserPreferences();
  const [favorite, setFavorite] = useState<{
    style_key: string;
    label: string;
  } | null>(null);
  const [models, setModels] = useState<ComparisonModel[]>([]);
  const [slice, setSlice] = useState<ComparisonSlice | null>(null);
  const [sliceError, setSliceError] = useState(false);
  const [rows, setRows] = useState<Map<string, ComparisonRowState>>(new Map());
  const [indexes, setIndexes] = useState<Map<string, number>>(new Map());
  const [dialog, setDialog] = useState<{
    key: string;
    index: number;
    xIndex?: number;
  } | null>(null);

  useEffect(() => {
    if (!user) return;
    const controller = new AbortController();
    fetch(`/api/viewer/style-comparison/${encodeURIComponent(styleKey)}`, {
      cache: "no-store",
      signal: controller.signal,
    })
      .then(async (response) => {
        if (!response.ok) return;
        const payload = (await response.json()) as {
          favorite?: { style_key: string; label: string };
          models?: ComparisonModel[];
        };
        if (payload.favorite) setFavorite(payload.favorite);
        setModels(payload.models ?? []);
      })
      .catch(() => {});
    return () => controller.abort();
  }, [styleKey, user]);

  useEffect(() => {
    if (!favorite || !models.length) return;
    const controller = new AbortController();
    // eslint-disable-next-line react-hooks/set-state-in-effect -- reset stale detail data before loading a new comparison window
    setSlice(null);
    setSliceError(false);
    setRows(new Map());
    const runDirs = models.map((model) => model.run_dir);
    Promise.all(
      Array.from({ length: Math.ceil(runDirs.length / 12) }, (_, index) =>
        fetchComparisonSlice(
          [styleKey],
          runDirs.slice(index * 12, index * 12 + 12),
          controller.signal,
        ),
      ),
    )
      .then(async (parts) => {
        const next = {
          access: parts.flatMap((part) => part.access),
          placements: {
            [styleKey]: parts.flatMap(
              (part) => part.placements[styleKey] ?? [],
            ),
          },
        };
        setSlice(next);
        const accessByRun = new Map(
          next.access.map((access) => [access.run_dir, access]),
        );
        const jobs = (next.placements[styleKey] ?? []).map(
          (placement) => async () => {
            const access = accessByRun.get(placement.run_dir);
            const stateKey = `${placement.run_dir}|${placement.y_index}`;
            if (!access) {
              setRows((current) =>
                new Map(current).set(stateKey, { status: "error" }),
              );
              return;
            }
            setRows((current) =>
              new Map(current).set(stateKey, { status: "loading" }),
            );
            const state = await loadComparisonRowState(
              {
                key: stateKey,
                runDir: placement.run_dir,
                releaseId: access.release_id,
                viewerVariant: access.viewer_variant,
                grant: access.grant,
                yIndex: placement.y_index,
              },
              controller.signal,
            );
            if (controller.signal.aborted) return;
            setRows((current) => new Map(current).set(stateKey, state));
          },
        );
        await mapWithConcurrency(jobs, async (job) => job(), 4);
      })
      .catch(() => {
        if (!controller.signal.aborted) setSliceError(true);
      });
    return () => controller.abort();
  }, [favorite, models, showNsfw, styleKey]);

  const xColumns = models[0]?.x_columns ?? [];
  const accessByRun = useMemo(
    () =>
      new Map((slice?.access ?? []).map((access) => [access.run_dir, access])),
    [slice],
  );
  if (!user) return null;
  if (!favorite)
    return (
      <main className="p-8 text-sm text-muted-foreground">{t("loading")}</main>
    );

  const dialogData = dialog
    ? (() => {
        const [runDir, yIndex] = dialog.key.split("|");
        const state = rows.get(`${runDir}|${yIndex}`);
        const allSlides = flattenRowSlides(
          state?.status === "ready" ? state.row : null,
        );
        const slides =
          dialog.xIndex === undefined
            ? allSlides
            : allSlides.filter((slide) => slide.xIndex === dialog.xIndex);
        return {
          slides,
          slide: slides[dialog.index] ?? null,
          access: accessByRun.get(runDir) ?? null,
        };
      })()
    : null;
  return (
    <main className="flex h-full min-h-0 flex-col overflow-hidden px-4 py-6 sm:px-6">
      <div className="mx-auto flex w-full max-w-[1600px] min-h-0 flex-1 flex-col gap-4">
        <div>
          <Link
            href="/favorites"
            className="text-xs text-muted-foreground hover:underline"
          >
            {t("backToFavorites")}
          </Link>
          <h1 className="mt-2 text-xl font-semibold">{favorite.label}</h1>
        </div>
        <div className="min-h-0 flex-1 overflow-auto rounded border">
          <table className="w-full min-w-[720px] border-collapse text-xs">
            <thead>
              <tr className="border-b bg-background">
                <th className="sticky left-0 top-0 z-20 min-w-44 border-r bg-background p-3 text-left">
                  {t("comparisonScene")}
                </th>
                {models.map((model) => (
                  <th
                    key={model.run_dir}
                    className="sticky top-0 z-10 min-w-40 border-l bg-background p-3 text-left"
                  >
                    {model.name ?? model.run_dir}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {xColumns.map((column) => (
                <tr key={column.x_index} className="border-b">
                  <th className="sticky left-0 z-10 border-r bg-background p-3 text-left font-medium">
                    {column.description?.zh ??
                      column.description?.en ??
                      column.type ??
                      `#${column.x_index + 1}`}
                  </th>
                  {models.map((model) => {
                    const placement = (slice?.placements[styleKey] ?? []).find(
                      (item) => item.run_dir === model.run_dir,
                    );
                    const key = placement
                      ? `${model.run_dir}|${placement.y_index}`
                      : "";
                    const state = sliceError
                      ? ({ status: "error" } satisfies ComparisonRowState)
                      : resolveComparisonRowState(
                          slice === null || placement !== undefined,
                          placement ? rows.get(key) : undefined,
                        );
                    const row = state.status === "ready" ? state.row : null;
                    const slides = row
                      ? flattenRowSlides(row).filter(
                          (slide) => slide.xIndex === column.x_index,
                        )
                      : [];
                    const index = Math.min(
                      indexes.get(`${key}|${column.x_index}`) ?? 0,
                      Math.max(slides.length - 1, 0),
                    );
                    const slide = slides[index] ?? null;
                    const access = accessByRun.get(model.run_dir) ?? null;
                    return (
                      <td key={model.run_dir} className="border-l p-2">
                        <div className="h-28 rounded bg-muted/30">
                          <button
                            type="button"
                            className="block h-full w-full"
                            onClick={() =>
                              slide &&
                              setDialog({ key, index, xIndex: column.x_index })
                            }
                            disabled={!slide}
                          >
                            {state.status === "loading" ? (
                              <div
                                data-testid="comparison-image-skeleton"
                                data-state="loading"
                                className="h-full w-full animate-pulse bg-muted"
                              />
                            ) : slide ? (
                              <GridImage
                                thumbVariants={slide.item.thumb}
                                blurhash={slide.item.blurhash}
                                alt={`${favorite.label} × ${model.name ?? model.run_dir}`}
                                currentUserId={user.id}
                                grant={access?.grant ?? null}
                                onRefreshViewAccess={async () => access ?? null}
                              />
                            ) : (
                              <div
                                data-state={
                                  state.status === "ready"
                                    ? "missing"
                                    : state.status
                                }
                                className="flex h-full items-center justify-center text-muted-foreground"
                              >
                                <ImageOff className="size-4" />
                              </div>
                            )}
                          </button>
                        </div>
                        {slides.length > 1 ? (
                          <div className="mt-1 flex items-center justify-between">
                            <Button
                              size="icon"
                              variant="ghost"
                              className="size-6"
                              onClick={() =>
                                setIndexes((current) =>
                                  new Map(current).set(
                                    `${key}|${column.x_index}`,
                                    Math.max(0, index - 1),
                                  ),
                                )
                              }
                            >
                              <ChevronLeft className="size-3" />
                            </Button>
                            <span>
                              {index + 1}/{slides.length}
                            </span>
                            <Button
                              size="icon"
                              variant="ghost"
                              className="size-6"
                              onClick={() =>
                                setIndexes((current) =>
                                  new Map(current).set(
                                    `${key}|${column.x_index}`,
                                    Math.min(slides.length - 1, index + 1),
                                  ),
                                )
                              }
                            >
                              <ChevronRight className="size-3" />
                            </Button>
                          </div>
                        ) : null}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {dialogData ? (
          <DetailDialog
            open={!!dialog}
            slide={dialogData.slide}
            slides={dialogData.slides}
            access={dialogData.access}
            userId={user.id}
            onOpenChange={(open) => {
              if (!open) setDialog(null);
            }}
            current={dialog?.index ?? 0}
            onPrevious={() =>
              setDialog((current) =>
                current
                  ? { ...current, index: Math.max(0, current.index - 1) }
                  : current,
              )
            }
            onNext={() =>
              setDialog((current) =>
                current
                  ? {
                      ...current,
                      index: Math.min(
                        dialogData.slides.length - 1,
                        current.index + 1,
                      ),
                    }
                  : current,
              )
            }
          />
        ) : null}
      </div>
    </main>
  );
}

function DetailDialog({
  open,
  slide,
  slides,
  access,
  userId,
  onOpenChange,
  current,
  onPrevious,
  onNext,
}: {
  open: boolean;
  slide: ComparisonSlide | null;
  slides: ComparisonSlide[];
  access: ComparisonSlice["access"][number] | null;
  userId: string;
  onOpenChange: (open: boolean) => void;
  current: number;
  onPrevious: () => void;
  onNext: () => void;
}) {
  const [loadedSrc, setLoadedSrc] = useState<string | null>(null);
  const { src, loading } = useRenderableVariantSource({
    variants: open ? (slide?.item.display ?? null) : null,
    currentUserId: userId,
    grant: access?.grant ?? null,
    onRefreshViewAccess: async () => access,
  });
  const isLoaded = src !== null && loadedSrc === src;
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-5xl">
        <DialogHeader className="sr-only">
          <DialogTitle>Image preview</DialogTitle>
          <DialogDescription>Image preview</DialogDescription>
        </DialogHeader>
        <div className="relative flex min-h-[55vh] items-center justify-center overflow-hidden rounded bg-black">
          {slide?.item.blurhash ? (
            <BlurhashCanvas
              blurhash={slide.item.blurhash}
              className={`absolute inset-0 h-full w-full object-cover blur-md transition-opacity duration-500 ${isLoaded ? "opacity-0" : "opacity-100"}`}
            />
          ) : null}
          {src ? (
            <img
              src={src}
              alt="Image preview"
              className={`relative z-10 max-h-[75vh] max-w-full object-contain transition-opacity duration-500 ${isLoaded ? "opacity-100" : "opacity-0"}`}
              onLoad={() => setLoadedSrc(src)}
            />
          ) : !slide?.item.blurhash ? (
            <span className="text-sm text-white/70">
              {loading ? "Loading..." : "-"}
            </span>
          ) : null}
        </div>
        <div className="flex items-center justify-between">
          <Button
            size="icon"
            variant="outline"
            onClick={onPrevious}
            disabled={current <= 0}
          >
            <ChevronLeft className="size-4" />
          </Button>
          <span className="text-xs text-muted-foreground">
            {slides.length ? `${current + 1}/${slides.length}` : "-"}
          </span>
          <Button
            size="icon"
            variant="outline"
            onClick={onNext}
            disabled={current >= slides.length - 1}
          >
            <ChevronRight className="size-4" />
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

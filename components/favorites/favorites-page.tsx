"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import {
  ArrowUpRight,
  ChevronLeft,
  ChevronRight,
  Info,
  SlidersHorizontal,
  X,
} from "lucide-react";
import { toast } from "sonner";

import { useAuth } from "@/components/auth-provider";
import { AuthLoginDialog } from "@/components/auth-login-dialog";
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
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  HoverCard,
  HoverCardContent,
  HoverCardTrigger,
} from "@/components/ui/hover-card";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { Link } from "@/i18n/navigation";
import { useUserPreferences } from "@/components/user-preferences-provider";
import { deleteStyleFavorite } from "@/lib/style-favorites";
import {
  flattenRowSlides,
  getVisibleModels,
  mergeComparisonFavorites,
  reconcileHiddenRunDirs,
  type ComparisonModel,
  type ComparisonSlice,
  type ComparisonSlide,
} from "@/lib/style-comparison";
import {
  fetchComparisonCatalog,
  fetchComparisonSlice,
  loadComparisonRowState,
  mapWithConcurrency,
  resolveComparisonRowState,
  type ComparisonRowState,
} from "./comparison-loader";
import {
  buildComparisonBlurhashLookup,
  getComparisonBlurhash,
  getComparisonPlaceholderBlurhash,
  getHorizontalModelWindow,
  getSceneColumnDescription,
  getShiftWheelDelta,
  getComparisonSyncModePersistenceValue,
  getComparisonSyncModeToggleValue,
  getVariantBoundValue,
  isComparisonSyncMode,
  resolveComparisonSyncMode,
  wrapSlideIndex,
  type ComparisonSyncMode,
} from "./comparison-matrix-utils";

const HIDDEN_MODELS_KEY = "sdlab:favorites:hidden-models";
const SYNC_MODE_KEY = "sdlab:favorites:sync-mode";
const VISIBLE_ROWS = 6;
const MODEL_COLUMN_WIDTH = 216;
const DESKTOP_PROMPT_COLUMN_WIDTH = 280;
const MOBILE_PROMPT_COLUMN_WIDTH = 176;
const ROW_HEIGHT = 312;
const HEADER_HEIGHT = 64;
const SLICE_MODEL_LIMIT = 12;

function readHiddenModels(): Set<string> {
  try {
    const value = JSON.parse(localStorage.getItem(HIDDEN_MODELS_KEY) ?? "[]");
    return new Set(
      Array.isArray(value)
        ? value.filter((item): item is string => typeof item === "string")
        : [],
    );
  } catch {
    return new Set();
  }
}

function readSyncMode(): ComparisonSyncMode {
  try {
    return resolveComparisonSyncMode(localStorage.getItem(SYNC_MODE_KEY));
  } catch {
    return "all";
  }
}

function formatTime(iso: string, locale: string) {
  const value = new Date(iso);
  return Number.isNaN(value.getTime())
    ? iso
    : new Intl.DateTimeFormat(locale, {
        dateStyle: "medium",
        timeStyle: "short",
      }).format(value);
}

function ComparisonImage({
  state,
  slide,
  access,
  userId,
  onRefresh,
  alt,
  onClick,
  blurhash,
}: {
  state: ComparisonRowState;
  slide: ComparisonSlide | null;
  access: ComparisonSlice["access"][number] | null;
  userId: string;
  onRefresh: () => Promise<ComparisonSlice["access"][number] | null>;
  alt: string;
  onClick?: () => void;
  blurhash: string | null;
}) {
  const t = useTranslations("styleFavorites");
  if (state.status === "loading") {
    if (blurhash) {
      return (
        <BlurhashCanvas
          blurhash={blurhash}
          className="h-full w-full object-cover blur-md"
        />
      );
    }
    return (
      <div
        data-testid="comparison-image-skeleton"
        data-state="loading"
        className="h-full w-full animate-pulse rounded-lg bg-muted/60"
      />
    );
  }
  if (state.status !== "ready" || !slide) {
    return (
      <div
        data-state={state.status === "ready" ? "missing" : state.status}
        className="flex h-full min-h-28 items-center justify-center text-[11px] text-muted-foreground/50"
      >
        {t("noImage")}
      </div>
    );
  }
  return (
    <button
      type="button"
      className="block h-full w-full cursor-zoom-in text-left transition-transform duration-500 ease-out group-hover:scale-[1.03]"
      onClick={onClick}
      disabled={!onClick}
    >
      <GridImage
        thumbVariants={slide.item.thumb}
        blurhash={blurhash}
        alt={alt}
        currentUserId={userId}
        grant={access?.grant ?? null}
        onRefreshViewAccess={onRefresh}
      />
    </button>
  );
}

function ComparisonDialog({
  open,
  slide,
  access,
  userId,
  onRefresh,
  onOpenChange,
  onPrevious,
  onNext,
  current,
  total,
  title,
  blurhash,
}: {
  open: boolean;
  slide: ComparisonSlide | null;
  access: ComparisonSlice["access"][number] | null;
  userId: string;
  onRefresh: () => Promise<ComparisonSlice["access"][number] | null>;
  onOpenChange: (open: boolean) => void;
  onPrevious: () => void;
  onNext: () => void;
  current: number;
  total: number;
  title: string;
  blurhash: string | null;
}) {
  const [loadedSrc, setLoadedSrc] = useState<string | null>(null);
  const { src, loading } = useRenderableVariantSource({
    variants: open ? (slide?.item.display ?? null) : null,
    currentUserId: userId,
    grant: access?.grant ?? null,
    onRefreshViewAccess: onRefresh,
  });
  const isLoaded = src !== null && loadedSrc === src;
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[92vh] max-w-5xl overflow-auto p-4">
        <DialogHeader className="sr-only">
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription>{title}</DialogDescription>
        </DialogHeader>
        <div className="relative flex min-h-[55vh] items-center justify-center rounded bg-black">
          {blurhash ? (
            <BlurhashCanvas
              blurhash={blurhash}
              className={`absolute inset-0 h-full w-full object-cover blur-md transition-opacity duration-500 ${isLoaded ? "opacity-0" : "opacity-100"}`}
            />
          ) : null}
          {src ? (
            <img
              src={src}
              alt={title}
              className={`relative z-10 max-h-[76vh] max-w-full object-contain transition-opacity duration-500 ${isLoaded ? "opacity-100" : "opacity-0"}`}
              onLoad={() => setLoadedSrc(src)}
            />
          ) : !blurhash ? (
            <span className="text-sm text-white/70">
              {loading ? "Loading..." : "-"}
            </span>
          ) : null}
        </div>
        <div className="flex items-center justify-between gap-3">
          <Button
            type="button"
            size="icon"
            variant="outline"
            aria-label="Previous image"
            onClick={onPrevious}
            disabled={total <= 1}
          >
            <ChevronLeft className="size-4" />
          </Button>
          <span className="text-xs text-muted-foreground">
            {total ? `${current + 1}/${total}` : "-"}
          </span>
          <Button
            type="button"
            size="icon"
            variant="outline"
            aria-label="Next image"
            onClick={onNext}
            disabled={total <= 1}
          >
            <ChevronRight className="size-4" />
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

export default function FavoritesPage() {
  const t = useTranslations("styleFavorites");
  const { user } = useAuth();
  const [loginDialogOpen, setLoginDialogOpen] = useState(false);
  if (!user) {
    return (
      <>
        <div className="flex min-h-svh items-center justify-center">
          <div className="flex max-w-sm flex-col items-center gap-4 px-4 text-center">
            <div className="text-4xl" aria-hidden="true">
              ⭐
            </div>
            <h2 className="text-lg font-semibold">{t("loginGateTitle")}</h2>
            <p className="text-sm text-muted-foreground">
              {t("loginGateDescription")}
            </p>
            <Button onClick={() => setLoginDialogOpen(true)}>
              {t("loginGateButton")}
            </Button>
          </div>
        </div>
        <AuthLoginDialog
          open={loginDialogOpen}
          onOpenChange={setLoginDialogOpen}
        />
      </>
    );
  }
  return <ComparisonWorkspace key={user.id} userId={user.id} />;
}

function ComparisonWorkspace({ userId }: { userId: string }) {
  const t = useTranslations("styleFavorites");
  const locale = useLocale();
  const { showNsfw } = useUserPreferences();
  const rowVariantKey = showNsfw ? "nsfw" : "sfw";
  const [pages, setPages] = useState<
    import("@/lib/style-comparison").ComparisonCatalogPage[]
  >([]);
  const [models, setModels] = useState<ComparisonModel[]>([]);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [hidden, setHidden] = useState<Set<string>>(() => new Set());
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [start, setStart] = useState(0);
  const [matrixViewport, setMatrixViewport] = useState({
    scrollLeft: 0,
    width: 1280,
    promptColumnWidth: DESKTOP_PROMPT_COLUMN_WIDTH,
  });
  const [sliceSnapshot, setSliceSnapshot] = useState<{
    variantKey: string;
    data: ComparisonSlice;
  } | null>(null);
  const slice = getVariantBoundValue(sliceSnapshot, rowVariantKey);
  const [rows, setRows] = useState<Map<string, ComparisonRowState>>(new Map());
  const [slideIndexes, setSlideIndexes] = useState<Map<string, number>>(
    new Map(),
  );
  const [syncMode, setSyncMode] = useState<ComparisonSyncMode>("all");
  const [syncModeHydrated, setSyncModeHydrated] = useState(false);
  const [columnIndexes, setColumnIndexes] = useState<Map<string, number>>(
    new Map(),
  );
  const [allIndex, setAllIndex] = useState(0);
  const [dialog, setDialog] = useState<{ key: string; index: number } | null>(
    null,
  );
  const scrollRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- hydrate browser-only preference after mount
    setSyncMode(readSyncMode());
    setSyncModeHydrated(true);
  }, []);
  useEffect(() => {
    const value = getComparisonSyncModePersistenceValue(
      syncMode,
      syncModeHydrated,
    );
    if (value === null) return;
    try {
      localStorage.setItem(SYNC_MODE_KEY, value);
    } catch {
      /* storage unavailable */
    }
  }, [syncMode, syncModeHydrated]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- hydrate browser-only preference after mount
    setHidden(readHiddenModels());
  }, []);
  useEffect(() => {
    const controller = new AbortController();
    // eslint-disable-next-line react-hooks/set-state-in-effect -- reset async loading state for a new user session
    setLoading(true);
    fetchComparisonCatalog(null, 40, controller.signal)
      .then((page) => {
        if (controller.signal.aborted) return;
        setPages([page]);
        setModels(page.models ?? []);
        setNextCursor(page.next_cursor ?? null);
        setLoading(false);
      })
      .catch(() => {
        if (!controller.signal.aborted) {
          setError(true);
          setLoading(false);
        }
      });
    return () => controller.abort();
  }, []);

  const favorites = useMemo(() => mergeComparisonFavorites(pages), [pages]);
  const visibleModels = useMemo(
    () => getVisibleModels(models, hidden),
    [models, hidden],
  );
  const horizontalWindow = useMemo(
    () =>
      getHorizontalModelWindow({
        scrollLeft: matrixViewport.scrollLeft,
        viewportWidth: matrixViewport.width,
        promptColumnWidth: matrixViewport.promptColumnWidth,
        modelColumnWidth: MODEL_COLUMN_WIDTH,
        modelCount: visibleModels.length,
        overscan: 1,
      }),
    [matrixViewport, visibleModels.length],
  );
  const activeModels = useMemo(
    () =>
      visibleModels.slice(
        horizontalWindow.startIndex,
        horizontalWindow.endIndex,
      ),
    [horizontalWindow, visibleModels],
  );
  const visibleFavorites = useMemo(
    () => favorites.slice(start, start + VISIBLE_ROWS),
    [favorites, start],
  );

  useEffect(() => {
    if (!models.length) return;
    // eslint-disable-next-line react-hooks/set-state-in-effect -- remove stale local model ids after catalog refresh
    setHidden((current) => reconcileHiddenRunDirs(current, models));
  }, [models]);
  useEffect(() => {
    try {
      localStorage.setItem(HIDDEN_MODELS_KEY, JSON.stringify([...hidden]));
    } catch {
      /* storage unavailable */
    }
  }, [hidden]);

  const updateMatrixViewport = useCallback((element: HTMLDivElement) => {
    const promptColumnWidth =
      element.clientWidth < 640
        ? MOBILE_PROMPT_COLUMN_WIDTH
        : DESKTOP_PROMPT_COLUMN_WIDTH;
    setMatrixViewport((current) => {
      const next = {
        scrollLeft:
          Math.floor(element.scrollLeft / MODEL_COLUMN_WIDTH) *
          MODEL_COLUMN_WIDTH,
        width: element.clientWidth,
        promptColumnWidth,
      };
      return current.scrollLeft === next.scrollLeft &&
        current.width === next.width &&
        current.promptColumnWidth === next.promptColumnWidth
        ? current
        : next;
    });
  }, []);

  useEffect(() => {
    const element = scrollRef.current;
    if (!element) return;
    const frame = requestAnimationFrame(() => updateMatrixViewport(element));
    const observer = new ResizeObserver(() => updateMatrixViewport(element));
    observer.observe(element);
    return () => {
      cancelAnimationFrame(frame);
      observer.disconnect();
    };
  }, [updateMatrixViewport]);

  const loadSlice = useCallback(
    async (signal?: AbortSignal) => {
      if (!activeModels.length || !visibleFavorites.length) return;
      setRows((current) => {
        const next = new Map(current);
        for (const favorite of visibleFavorites) {
          for (const model of activeModels) {
            const stateKey = `${rowVariantKey}|${favorite.style_key}|${model.run_dir}`;
            if (!next.has(stateKey)) {
              next.set(stateKey, { status: "loading" });
            }
          }
        }
        return next;
      });
      try {
        const styleKeys = visibleFavorites.map((item) => item.style_key);
        const modelChunks = Array.from(
          { length: Math.ceil(activeModels.length / SLICE_MODEL_LIMIT) },
          (_, index) =>
            activeModels.slice(
              index * SLICE_MODEL_LIMIT,
              (index + 1) * SLICE_MODEL_LIMIT,
            ),
        );
        const slices = await Promise.all(
          modelChunks.map((chunk) =>
            fetchComparisonSlice(
              styleKeys,
              chunk.map((model) => model.run_dir),
              signal,
            ),
          ),
        );
        if (signal?.aborted) return;
        const next: ComparisonSlice = {
          access: slices.flatMap((item) => item.access),
          placements: Object.fromEntries(
            styleKeys.map((styleKey) => [
              styleKey,
              slices.flatMap((item) => item.placements[styleKey] ?? []),
            ]),
          ),
        };
        setSliceSnapshot({ variantKey: rowVariantKey, data: next });
        setRows((current) => {
          const nextRows = new Map(current);
          for (const favorite of visibleFavorites) {
            const placedRuns = new Set(
              (next.placements[favorite.style_key] ?? []).map(
                (placement) => placement.run_dir,
              ),
            );
            for (const model of activeModels) {
              if (!placedRuns.has(model.run_dir)) {
                nextRows.set(
                  `${rowVariantKey}|${favorite.style_key}|${model.run_dir}`,
                  { status: "missing" },
                );
              }
            }
          }
          return nextRows;
        });
        const accessByRun = new Map(
          next.access.map((item) => [item.run_dir, item]),
        );
        const jobs = visibleFavorites.flatMap((favorite) =>
          (next.placements[favorite.style_key] ?? [])
            .filter((placement) =>
              activeModels.some((model) => model.run_dir === placement.run_dir),
            )
            .map((placement) => async () => {
              const stateKey = `${rowVariantKey}|${favorite.style_key}|${placement.run_dir}`;
              const access = accessByRun.get(placement.run_dir);
              if (!access) {
                setRows((current) =>
                  new Map(current).set(stateKey, { status: "error" }),
                );
                return;
              }
              const state = await loadComparisonRowState(
                {
                  key: stateKey,
                  runDir: placement.run_dir,
                  releaseId: access.release_id,
                  viewerVariant: access.viewer_variant,
                  grant: access.grant,
                  yIndex: placement.y_index,
                },
                signal,
              );
              if (signal?.aborted) return;
              setRows((current) => new Map(current).set(stateKey, state));
            }),
        );
        await mapWithConcurrency(jobs, async (job) => job(), 4);
      } catch {
        if (signal?.aborted) return;
        setRows((current) => {
          const next = new Map(current);
          for (const favorite of visibleFavorites) {
            for (const model of activeModels) {
              next.set(
                `${rowVariantKey}|${favorite.style_key}|${model.run_dir}`,
                { status: "error" },
              );
            }
          }
          return next;
        });
      }
    },
    [activeModels, rowVariantKey, visibleFavorites],
  );
  useEffect(() => {
    const controller = new AbortController();
    // eslint-disable-next-line react-hooks/set-state-in-effect -- schedule visible-window network loading
    void loadSlice(controller.signal);
    return () => controller.abort();
  }, [loadSlice, showNsfw]);

  const blurhashLookup = useMemo(
    () => buildComparisonBlurhashLookup(slice?.placements ?? null),
    [slice],
  );

  const shiftSlide = (key: string, runDir: string, delta: number) => {
    if (syncMode === "all") {
      setAllIndex((current) => current + delta);
    } else if (syncMode === "column") {
      setColumnIndexes((current) =>
        new Map(current).set(runDir, (current.get(runDir) ?? 0) + delta),
      );
    } else {
      setSlideIndexes((current) =>
        new Map(current).set(key, (current.get(key) ?? 0) + delta),
      );
    }
  };
  // 整列/全部模式下,表头场景描述跟随该列当前展示的 slide;取该列第一个已就绪的行来定位场景。
  const getSyncedHeaderXIndex = (runDir: string): number | null => {
    if (syncMode === "cell") return null;
    const raw =
      syncMode === "all" ? allIndex : (columnIndexes.get(runDir) ?? 0);
    for (const favorite of visibleFavorites) {
      const state = rows.get(
        `${rowVariantKey}|${favorite.style_key}|${runDir}`,
      );
      if (state?.status !== "ready") continue;
      const slides = flattenRowSlides(state.row);
      if (slides.length) {
        return slides[wrapSlideIndex(raw, slides.length)].xIndex;
      }
    }
    return null;
  };
  const toggleHidden = (runDir: string) =>
    setHidden((current) => {
      const next = new Set(current);
      if (next.has(runDir)) next.delete(runDir);
      else next.add(runDir);
      return next;
    });
  const removeFavorite = async (styleKey: string) => {
    if (!(await deleteStyleFavorite(styleKey))) {
      toast.error(t("toggleFailed"));
      return;
    }
    setPages((current) =>
      current.map((page) => ({
        ...page,
        favorites: page.favorites.filter((item) => item.style_key !== styleKey),
      })),
    );
  };
  const dialogData = useMemo(() => {
    if (!dialog || !slice) return null;
    const [styleKey, runDir] = dialog.key.split("|");
    const state = rows.get(`${rowVariantKey}|${dialog.key}`);
    const row = state?.status === "ready" ? state.row : null;
    const slides = flattenRowSlides(row);
    const placement = (slice.placements[styleKey] ?? []).find(
      (item) => item.run_dir === runDir,
    );
    const slide = slides[dialog.index] ?? null;
    return {
      slide,
      slides,
      access: slice.access.find((item) => item.run_dir === runDir) ?? null,
      title: styleKey,
      blurhash:
        slide && placement
          ? getComparisonBlurhash(
              blurhashLookup,
              runDir,
              placement.y_index,
              slide.xIndex,
              slide.batchIndex,
              slide.item.blurhash,
            )
          : null,
    };
  }, [blurhashLookup, dialog, rowVariantKey, rows, slice]);

  if (loading)
    return (
      <main className="p-8 text-sm text-muted-foreground">{t("loading")}</main>
    );
  if (error)
    return (
      <main className="p-8 text-sm text-muted-foreground">
        {t("loadFailed")}
      </main>
    );
  if (!favorites.length)
    return (
      <main className="p-8 text-sm text-muted-foreground">{t("empty")}</main>
    );

  const leftModelSpacer = horizontalWindow.startIndex * MODEL_COLUMN_WIDTH;
  const rightModelSpacer =
    (visibleModels.length - horizontalWindow.endIndex) * MODEL_COLUMN_WIDTH;
  const matrixWidth =
    matrixViewport.promptColumnWidth +
    visibleModels.length * MODEL_COLUMN_WIDTH;

  return (
    <TooltipProvider delayDuration={300}>
    <main className="flex h-full min-h-0 flex-col overflow-hidden px-3 py-4 sm:px-5 sm:py-5 lg:px-6">
      <div className="flex w-full min-h-0 flex-1 flex-col gap-4">
        <div className="flex flex-wrap items-end justify-between gap-3 border-b pb-4">
          <div className="min-w-0">
            <h1 className="text-lg font-semibold tracking-tight sm:text-xl">
              {t("comparisonTitle")}
            </h1>
            <p className="mt-1 max-w-2xl text-xs leading-relaxed text-muted-foreground">
              {t("comparisonDescription")}
            </p>
          </div>
          <div className="flex items-center gap-2">
            <ToggleGroup
              type="single"
              variant="outline"
              size="sm"
              value={getComparisonSyncModeToggleValue(
                syncMode,
                syncModeHydrated,
              )}
              onValueChange={(value) => {
                if (isComparisonSyncMode(value)) setSyncMode(value);
              }}
              aria-label={t("syncMode")}
              aria-busy={!syncModeHydrated}
            >
              <ToggleGroupItem value="cell" aria-label={t("syncModeCell")}>
                {t("syncModeCell")}
              </ToggleGroupItem>
              <ToggleGroupItem value="column" aria-label={t("syncModeColumn")}>
                {t("syncModeColumn")}
              </ToggleGroupItem>
              <ToggleGroupItem value="all" aria-label={t("syncModeAll")}>
                {t("syncModeAll")}
              </ToggleGroupItem>
            </ToggleGroup>
            <HoverCard openDelay={200}>
              <HoverCardTrigger asChild>
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  className="size-8 text-muted-foreground"
                  aria-label={t("syncModeHelpTitle")}
                >
                  <Info className="size-4" aria-hidden="true" />
                </Button>
              </HoverCardTrigger>
              <HoverCardContent align="end" className="w-72">
                <div className="flex flex-col gap-2">
                  <p className="text-xs font-semibold">
                    {t("syncModeHelpTitle")}
                  </p>
                  <p className="text-xs leading-relaxed text-muted-foreground">
                    {t("syncModeHelpDescription")}
                  </p>
                </div>
              </HoverCardContent>
            </HoverCard>
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="outline" size="sm" className="gap-2">
                  <SlidersHorizontal className="size-3.5" aria-hidden="true" />
                  {t("visibleModels", { count: visibleModels.length })}
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="w-72">
                <DropdownMenuLabel>{t("modelSelector")}</DropdownMenuLabel>
                <DropdownMenuSeparator />
                {models.map((model) => (
                  <DropdownMenuCheckboxItem
                    key={model.run_dir}
                    checked={!hidden.has(model.run_dir)}
                    onCheckedChange={() => toggleHidden(model.run_dir)}
                    onSelect={(event) => event.preventDefault()}
                    className="truncate"
                  >
                    <span className="truncate">
                      {model.name ?? model.run_dir}
                    </span>
                  </DropdownMenuCheckboxItem>
                ))}
              </DropdownMenuContent>
            </DropdownMenu>
            {nextCursor ? (
              <Button
                variant="ghost"
                size="sm"
                onClick={() => {
                  fetchComparisonCatalog(nextCursor, 40)
                    .then((page) => {
                      setPages((current) => [...current, page]);
                      setNextCursor(page.next_cursor ?? null);
                    })
                    .catch(() => {});
                }}
              >
                {t("loadMore")}
              </Button>
            ) : null}
          </div>
        </div>
        <div
          ref={scrollRef}
          data-testid="comparison-matrix-scroll"
          onWheel={(event) => {
            const delta = getShiftWheelDelta({
              shiftKey: event.shiftKey,
              deltaX: event.deltaX,
              deltaY: event.deltaY,
            });
            if (delta === null) return;
            event.preventDefault();
            event.currentTarget.scrollLeft += delta;
            updateMatrixViewport(event.currentTarget);
          }}
          onScroll={(event) => {
            setStart(
              Math.max(
                0,
                Math.min(
                  favorites.length - VISIBLE_ROWS,
                  Math.max(
                    0,
                    Math.floor(
                      (event.currentTarget.scrollTop - HEADER_HEIGHT) /
                        ROW_HEIGHT,
                    ) - 1,
                  ),
                ),
              ),
            );
            updateMatrixViewport(event.currentTarget);
          }}
          className="min-h-0 flex-1 overflow-auto overscroll-contain bg-background [scrollbar-gutter:stable]"
        >
          <div
            className="grid"
            style={{
              minWidth: matrixWidth,
              gridTemplateColumns: `${matrixViewport.promptColumnWidth}px ${leftModelSpacer}px repeat(${activeModels.length}, ${MODEL_COLUMN_WIDTH}px) ${rightModelSpacer}px`,
            }}
          >
            <div className="sticky top-0 left-0 z-30 flex h-16 items-end border-r border-b border-border/40 bg-background/85 px-4 py-3 text-[11px] font-semibold tracking-widest text-muted-foreground uppercase backdrop-blur-md">
              {t("favoriteLabel")}
            </div>
            <div className="sticky top-0 z-20 h-16 border-b border-border/40 bg-background/85 backdrop-blur-md" />
            {activeModels.map((model) => (
              <div
                key={model.run_dir}
                className="sticky top-0 z-20 flex h-16 min-w-0 flex-col justify-end border-b border-border/40 bg-background/85 px-3 py-3 backdrop-blur-md"
              >
                <Link
                  href={`/models/${encodeURIComponent(model.run_dir)}`}
                  className="truncate text-[13px] font-semibold transition-colors hover:text-primary hover:underline"
                >
                  {model.name ?? model.run_dir}
                </Link>
                <div className="mt-0.5 truncate text-[11px] text-muted-foreground">
                  {getSceneColumnDescription(
                    model.x_columns,
                    getSyncedHeaderXIndex(model.run_dir),
                    locale,
                  )}
                </div>
              </div>
            ))}
            <div className="sticky top-0 z-20 h-16 border-b border-border/40 bg-background/85 backdrop-blur-md" />
            <div
              className="col-span-full"
              style={{ height: start * ROW_HEIGHT }}
              aria-hidden="true"
            />
            {visibleFavorites.map((favorite) => (
              <div key={favorite.style_key} className="contents">
                <div
                  data-favorite-entry={favorite.style_key}
                  className="sticky left-0 z-10 flex border-r border-b border-border/40 bg-background p-4"
                  style={{ height: ROW_HEIGHT }}
                >
                  <div className="flex min-w-0 flex-1 flex-col">
                    <Link
                      href={`/favorites/${encodeURIComponent(favorite.style_key)}`}
                      className="line-clamp-4 text-sm leading-relaxed font-medium transition-colors hover:text-primary hover:underline"
                    >
                      {favorite.label}
                    </Link>
                    <p className="mt-2 text-[11px] text-muted-foreground">
                      {formatTime(favorite.created_at, locale)}
                    </p>
                    <div className="mt-auto flex flex-col items-start gap-2 pt-3">
                      <div className="flex max-w-full flex-wrap gap-x-2 gap-y-1">
                        {(slice?.placements[favorite.style_key] ?? [])
                          .slice(0, 2)
                          .map((placement) => (
                            <Link
                              key={placement.run_dir}
                              href={`/models/${encodeURIComponent(placement.run_dir)}#${placement.y_index + 1}`}
                              className="max-w-full truncate text-[10px] text-muted-foreground/70 transition-colors hover:text-muted-foreground hover:underline"
                            >
                              {models.find(
                                (model) => model.run_dir === placement.run_dir,
                              )?.name ?? placement.run_dir}
                            </Link>
                          ))}
                      </div>
                      <Button
                        variant="ghost"
                        size="sm"
                        className="h-7 px-2 text-[10px] text-muted-foreground/70 transition-colors hover:text-destructive"
                        onClick={() => void removeFavorite(favorite.style_key)}
                      >
                        <X className="mr-1 size-3" />
                        {t("remove")}
                      </Button>
                    </div>
                  </div>
                </div>
                <div className="border-b border-border/40" />
                {activeModels.map((model) => {
                  const key = `${favorite.style_key}|${model.run_dir}`;
                  const placement = (
                    slice?.placements[favorite.style_key] ?? []
                  ).find((item) => item.run_dir === model.run_dir);
                  const state = resolveComparisonRowState(
                    slice === null || placement !== undefined,
                    rows.get(`${rowVariantKey}|${key}`),
                  );
                  const row = state.status === "ready" ? state.row : null;
                  const slides = flattenRowSlides(row);
                  const rawIndex =
                    syncMode === "all"
                      ? allIndex
                      : syncMode === "column"
                        ? (columnIndexes.get(model.run_dir) ?? 0)
                        : (slideIndexes.get(key) ?? 0);
                  const index = wrapSlideIndex(rawIndex, slides.length);
                  const access =
                    slice?.access.find(
                      (item) => item.run_dir === model.run_dir,
                    ) ?? null;
                  const slide = slides[index] ?? null;
                  const blurhash = placement
                    ? slide
                      ? getComparisonBlurhash(
                          blurhashLookup,
                          model.run_dir,
                          placement.y_index,
                          slide.xIndex,
                          slide.batchIndex,
                          slide.item.blurhash,
                        )
                      : getComparisonPlaceholderBlurhash(
                          blurhashLookup,
                          model.run_dir,
                          placement.y_index,
                        )
                    : null;
                  const modelName = model.name ?? model.run_dir;
                  const rowJumpLabel = placement
                    ? t("jumpToModelRow", {
                        model: modelName,
                        row: placement.y_index + 1,
                      })
                    : null;
                  return (
                    <div
                      key={key}
                      className="border-b border-border/40 p-2.5"
                      style={{ height: ROW_HEIGHT }}
                    >
                      <div
                        data-testid="comparison-image-frame"
                        className="group relative h-full w-full overflow-hidden rounded-lg"
                      >
                        <ComparisonImage
                          state={state}
                          slide={slide}
                          access={access}
                          userId={userId}
                          onRefresh={async () => access}
                          alt={`${favorite.label} × ${modelName}`}
                          onClick={() => setDialog({ key, index })}
                          blurhash={blurhash}
                        />
                        {placement && rowJumpLabel ? (
                          <Tooltip>
                            <TooltipTrigger asChild>
                              <Button
                                asChild
                                size="icon-sm"
                                variant="secondary"
                                className="absolute top-1.5 right-1.5 z-10 rounded-full bg-background/80 shadow-sm backdrop-blur-sm"
                              >
                                <Link
                                  href={`/models/${encodeURIComponent(model.run_dir)}#${placement.y_index + 1}`}
                                  prefetch={false}
                                  aria-label={rowJumpLabel}
                                  title={rowJumpLabel}
                                >
                                  <ArrowUpRight
                                    className="size-3.5"
                                    aria-hidden="true"
                                  />
                                </Link>
                              </Button>
                            </TooltipTrigger>
                            <TooltipContent side="left">
                              {rowJumpLabel}
                            </TooltipContent>
                          </Tooltip>
                        ) : null}
                        {slides.length ? (
                          <>
                            <Button
                              size="icon"
                              variant="secondary"
                              className="absolute top-1/2 left-1.5 size-7 -translate-y-1/2 rounded-full bg-background/75 opacity-100 shadow-sm backdrop-blur-sm transition-opacity md:opacity-0 md:group-hover:opacity-100 focus-visible:opacity-100"
                              aria-label="Previous image"
                              onClick={() => shiftSlide(key, model.run_dir, -1)}
                            >
                              <ChevronLeft className="size-3.5" />
                            </Button>
                            <Button
                              size="icon"
                              variant="secondary"
                              className="absolute top-1/2 right-1.5 size-7 -translate-y-1/2 rounded-full bg-background/75 opacity-100 shadow-sm backdrop-blur-sm transition-opacity md:opacity-0 md:group-hover:opacity-100 focus-visible:opacity-100"
                              aria-label="Next image"
                              onClick={() => shiftSlide(key, model.run_dir, 1)}
                            >
                              <ChevronRight className="size-3.5" />
                            </Button>
                            <span className="pointer-events-none absolute bottom-1.5 left-1/2 -translate-x-1/2 rounded-full bg-black/55 px-2 py-0.5 text-[10px] font-medium text-white/90 tabular-nums backdrop-blur-sm">
                              {index + 1}/{slides.length}
                            </span>
                          </>
                        ) : null}
                      </div>
                    </div>
                  );
                })}
                <div className="border-b border-border/40" />
              </div>
            ))}
            <div
              className="col-span-full"
              style={{
                height:
                  Math.max(
                    0,
                    favorites.length - start - visibleFavorites.length,
                  ) * ROW_HEIGHT,
              }}
              aria-hidden="true"
            />
          </div>
        </div>
        {dialogData ? (
          <ComparisonDialog
            open={!!dialog}
            slide={dialogData.slide}
            access={dialogData.access}
            userId={userId}
            onRefresh={async () => dialogData.access}
            onOpenChange={(open) => {
              if (!open) setDialog(null);
            }}
            current={dialog?.index ?? 0}
            total={dialogData.slides.length}
            title={dialogData.title}
            blurhash={dialogData.blurhash}
            onPrevious={() =>
              setDialog((current) =>
                current
                  ? {
                      ...current,
                      index: wrapSlideIndex(
                        current.index - 1,
                        dialogData.slides.length,
                      ),
                    }
                  : current,
              )
            }
            onNext={() =>
              setDialog((current) =>
                current
                  ? {
                      ...current,
                      index: wrapSlideIndex(
                        current.index + 1,
                        dialogData.slides.length,
                      ),
                    }
                  : current,
              )
            }
          />
        ) : null}
      </div>
    </main>
    </TooltipProvider>
  );
}

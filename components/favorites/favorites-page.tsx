"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import {
  ChevronLeft,
  ChevronRight,
  EyeOff,
  ImageOff,
  SlidersHorizontal,
  X,
} from "lucide-react";
import { toast } from "sonner";

import { useAuth } from "@/components/auth-provider";
import { AuthLoginDialog } from "@/components/auth-login-dialog";
import { GridImage } from "@/components/comfyui/grid-image";
import { useRenderableVariantSource } from "@/components/comfyui/use-renderable-variant-source";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
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
  fetchComparisonRow,
  fetchComparisonSlice,
  mapWithConcurrency,
} from "./comparison-loader";

const HIDDEN_MODELS_KEY = "sdlab:favorites:hidden-models";
const VISIBLE_ROWS = 6;
const DESKTOP_COLUMNS = 4;

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

function formatTime(iso: string, locale: string) {
  const value = new Date(iso);
  return Number.isNaN(value.getTime())
    ? iso
    : new Intl.DateTimeFormat(locale, {
        dateStyle: "medium",
        timeStyle: "short",
      }).format(value);
}

function modelDescription(model: ComparisonModel, locale: string) {
  const column = model.x_columns[0];
  const description = column?.description;
  if (!description) return column?.type ?? "";
  const localized =
    (locale === "en" ? description.en : description.zh) ??
    description.zh ??
    description.en;
  return typeof localized === "string" ? localized : (column?.type ?? "");
}

function ComparisonImage({
  slide,
  access,
  userId,
  onRefresh,
  alt,
  onClick,
}: {
  slide: ComparisonSlide | null;
  access: ComparisonSlice["access"][number] | null;
  userId: string;
  onRefresh: () => Promise<ComparisonSlice["access"][number] | null>;
  alt: string;
  onClick?: () => void;
}) {
  if (!slide) {
    return (
      <div className="flex h-full min-h-28 items-center justify-center rounded border border-dashed text-muted-foreground">
        <ImageOff className="size-5" aria-hidden="true" />
      </div>
    );
  }
  return (
    <button
      type="button"
      className="block h-full w-full cursor-zoom-in text-left"
      onClick={onClick}
      disabled={!onClick}
    >
      <GridImage
        thumbVariants={slide.item.thumb}
        blurhash={null}
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
}) {
  const { src, loading } = useRenderableVariantSource({
    variants: open ? (slide?.item.display ?? null) : null,
    currentUserId: userId,
    grant: access?.grant ?? null,
    onRefreshViewAccess: onRefresh,
  });
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[92vh] max-w-5xl overflow-auto p-4">
        <DialogHeader className="sr-only">
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription>{title}</DialogDescription>
        </DialogHeader>
        <div className="relative flex min-h-[55vh] items-center justify-center rounded bg-black">
          {src ? (
            <img
              src={src}
              alt={title}
              className="max-h-[76vh] max-w-full object-contain"
            />
          ) : (
            <span className="text-sm text-white/70">
              {loading ? "Loading..." : "-"}
            </span>
          )}
        </div>
        <div className="flex items-center justify-between gap-3">
          <Button
            type="button"
            size="icon"
            variant="outline"
            aria-label="Previous image"
            onClick={onPrevious}
            disabled={current <= 0}
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
            disabled={current >= total - 1}
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
  const [pages, setPages] = useState<
    import("@/lib/style-comparison").ComparisonCatalogPage[]
  >([]);
  const [models, setModels] = useState<ComparisonModel[]>([]);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [hidden, setHidden] = useState<Set<string>>(() => new Set());
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [start, setStart] = useState(0);
  const [mobileRun, setMobileRun] = useState<string | null>(null);
  const [columnStart, setColumnStart] = useState(0);
  const [slice, setSlice] = useState<ComparisonSlice | null>(null);
  const [rows, setRows] = useState<
    Map<string, Awaited<ReturnType<typeof fetchComparisonRow>>>
  >(new Map());
  const [slideIndexes, setSlideIndexes] = useState<Map<string, number>>(
    new Map(),
  );
  const [dialog, setDialog] = useState<{ key: string; index: number } | null>(
    null,
  );
  const scrollRef = useRef<HTMLDivElement | null>(null);

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
  const activeModels = useMemo(() => {
    if (visibleModels.length === 0) return [];
    if (typeof window !== "undefined" && window.innerWidth < 768)
      return visibleModels.filter((model) => {
        const selected = visibleModels.some(
          (candidate) => candidate.run_dir === mobileRun,
        )
          ? mobileRun
          : visibleModels[0].run_dir;
        return model.run_dir === selected;
      });
    return visibleModels.slice(columnStart, columnStart + DESKTOP_COLUMNS);
  }, [columnStart, mobileRun, visibleModels]);
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

  const loadSlice = useCallback(
    async (signal?: AbortSignal) => {
      if (!activeModels.length || !visibleFavorites.length) return;
      setSlice(null);
      setRows(new Map());
      try {
        const next = await fetchComparisonSlice(
          visibleFavorites.map((item) => item.style_key),
          activeModels.map((model) => model.run_dir),
          signal,
        );
        if (signal?.aborted) return;
        setSlice(next);
        const accessByRun = new Map(
          next.access.map((item) => [item.run_dir, item]),
        );
        const jobs = visibleFavorites.flatMap((favorite) =>
          (next.placements[favorite.style_key] ?? [])
            .filter((placement) =>
              activeModels.some((model) => model.run_dir === placement.run_dir),
            )
            .map((placement) => async () => {
              const access = accessByRun.get(placement.run_dir);
              if (!access) return;
              const row = await fetchComparisonRow(
                placement.run_dir,
                access.release_id,
                access.viewer_variant,
                access.grant,
                placement.y_index,
                signal,
              );
              if (signal?.aborted) return;
              setRows((current) =>
                new Map(current).set(
                  `${favorite.style_key}|${placement.run_dir}`,
                  row,
                ),
              );
            }),
        );
        await mapWithConcurrency(jobs, async (job) => job(), 4);
      } catch {
        /* transient slice errors leave empty cells */
      }
    },
    [activeModels, visibleFavorites],
  );
  useEffect(() => {
    const controller = new AbortController();
    // eslint-disable-next-line react-hooks/set-state-in-effect -- schedule visible-window network loading
    void loadSlice(controller.signal);
    return () => controller.abort();
  }, [loadSlice, showNsfw]);

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
    const row = rows.get(dialog.key) ?? null;
    const slides = flattenRowSlides(row);
    return {
      slide: slides[dialog.index] ?? null,
      slides,
      access: slice.access.find((item) => item.run_dir === runDir) ?? null,
      title: styleKey,
    };
  }, [dialog, rows, slice]);

  if (loading)
    return (
      <main className="p-8 text-sm text-muted-foreground">Loading...</main>
    );
  if (error)
    return (
      <main className="p-8 text-sm text-muted-foreground">
        Unable to load favorites.
      </main>
    );
  if (!favorites.length)
    return (
      <main className="p-8 text-sm text-muted-foreground">{t("empty")}</main>
    );

  return (
    <main className="flex h-full min-h-0 flex-col overflow-hidden px-4 py-6 sm:px-6">
      <div className="mx-auto flex w-full max-w-[1600px] min-h-0 flex-1 flex-col gap-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h1 className="text-xl font-semibold">{t("comparisonTitle")}</h1>
            <p className="text-xs text-muted-foreground">
              {t("comparisonDescription")}
            </p>
          </div>
          <div className="flex items-center gap-2">
            <SlidersHorizontal
              className="size-4 text-muted-foreground"
              aria-hidden="true"
            />
            <span className="text-xs text-muted-foreground">
              {t("visibleModels", { count: visibleModels.length })}
            </span>
            {nextCursor ? (
              <Button
                variant="outline"
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
        <div className="flex flex-wrap gap-2 rounded border p-2">
          {models.map((model) => (
            <label
              key={model.run_dir}
              className="flex items-center gap-2 rounded px-2 py-1 text-xs hover:bg-muted"
            >
              <Checkbox
                checked={!hidden.has(model.run_dir)}
                onCheckedChange={() => toggleHidden(model.run_dir)}
              />
              <span>{model.name ?? model.run_dir}</span>
              <EyeOff
                className="size-3 text-muted-foreground"
                aria-hidden="true"
              />
            </label>
          ))}
        </div>
        <div className="flex items-center gap-2 md:hidden">
          <select
            className="h-9 w-full rounded border bg-background px-2 text-sm"
            value={activeModels[0]?.run_dir ?? ""}
            onChange={(event) => setMobileRun(event.target.value)}
            aria-label={t("modelSelector")}
          >
            {visibleModels.map((model) => (
              <option key={model.run_dir} value={model.run_dir}>
                {model.name ?? model.run_dir}
              </option>
            ))}
          </select>
        </div>
        <div className="hidden items-center justify-end gap-2 md:flex">
          <Button
            size="icon"
            variant="outline"
            aria-label={t("previousModels")}
            onClick={() =>
              setColumnStart((value) => Math.max(0, value - DESKTOP_COLUMNS))
            }
            disabled={columnStart === 0}
          >
            <ChevronLeft className="size-4" />
          </Button>
          <span className="text-xs text-muted-foreground">
            {visibleModels.length
              ? `${columnStart + 1}-${Math.min(columnStart + DESKTOP_COLUMNS, visibleModels.length)} / ${visibleModels.length}`
              : "0"}
          </span>
          <Button
            size="icon"
            variant="outline"
            aria-label={t("nextModels")}
            onClick={() =>
              setColumnStart((value) =>
                Math.min(
                  Math.max(visibleModels.length - DESKTOP_COLUMNS, 0),
                  value + DESKTOP_COLUMNS,
                ),
              )
            }
            disabled={columnStart + DESKTOP_COLUMNS >= visibleModels.length}
          >
            <ChevronRight className="size-4" />
          </Button>
        </div>
        <div
          ref={scrollRef}
          onScroll={(event) =>
            setStart(
              Math.max(
                0,
                Math.min(
                  favorites.length - VISIBLE_ROWS,
                  Math.floor(event.currentTarget.scrollTop / 144),
                ),
              ),
            )
          }
          className="min-h-0 flex-1 overflow-auto rounded border"
        >
          <div
            className="grid min-w-[720px]"
            style={{
              minHeight: favorites.length * 144,
              gridTemplateColumns: `minmax(180px, 1.2fr) repeat(${Math.max(activeModels.length, 1)}, minmax(150px, 1fr))`,
            }}
          >
            <div className="sticky top-0 z-10 border-b bg-background p-3 text-xs font-semibold">
              {t("favoriteLabel")}
            </div>
            {activeModels.map((model) => (
              <div
                key={model.run_dir}
                className="sticky top-0 z-10 border-b border-l bg-background p-3 text-xs font-semibold"
              >
                <div className="truncate">{model.name ?? model.run_dir}</div>
                <div className="truncate font-normal text-muted-foreground">
                  {modelDescription(model, locale)}
                </div>
              </div>
            ))}
            <div
              className="col-span-full"
              style={{ height: start * 144 }}
              aria-hidden="true"
            />
            {visibleFavorites.map((favorite) => (
              <div key={favorite.style_key} className="contents">
                <div
                  data-favorite-entry={favorite.style_key}
                  className="min-h-36 border-b p-3"
                >
                  <Link
                    href={`/favorites/${encodeURIComponent(favorite.style_key)}`}
                    className="text-sm font-medium hover:underline"
                  >
                    {favorite.label}
                  </Link>
                  <p className="mt-1 text-[11px] text-muted-foreground">
                    {formatTime(favorite.created_at, locale)}
                  </p>
                  <Button
                    variant="ghost"
                    size="sm"
                    className="mt-2 h-7 px-2 text-xs"
                    onClick={() => void removeFavorite(favorite.style_key)}
                  >
                    <X className="mr-1 size-3" />
                    {t("remove")}
                  </Button>
                  <div className="mt-2 flex flex-wrap gap-2">
                    {(slice?.placements[favorite.style_key] ?? [])
                      .slice(0, 3)
                      .map((placement) => (
                        <Link
                          key={placement.run_dir}
                          href={`/models/${encodeURIComponent(placement.run_dir)}#${placement.y_index + 1}`}
                          className="text-[10px] text-muted-foreground hover:underline"
                        >
                          {models.find(
                            (model) => model.run_dir === placement.run_dir,
                          )?.name ?? placement.run_dir}
                        </Link>
                      ))}
                  </div>
                </div>
                {activeModels.map((model) => {
                  const key = `${favorite.style_key}|${model.run_dir}`;
                  const row = rows.get(key) ?? null;
                  const slides = flattenRowSlides(row);
                  const index = Math.min(
                    slideIndexes.get(key) ?? 0,
                    Math.max(slides.length - 1, 0),
                  );
                  const access =
                    slice?.access.find(
                      (item) => item.run_dir === model.run_dir,
                    ) ?? null;
                  const slide = slides[index] ?? null;
                  return (
                    <div key={key} className="min-h-36 border-b border-l p-2">
                      <div className="relative h-28 overflow-hidden rounded bg-muted/30">
                        <ComparisonImage
                          slide={slide}
                          access={access}
                          userId={userId}
                          onRefresh={async () => access}
                          alt={`${favorite.label} × ${model.name ?? model.run_dir}`}
                          onClick={() => setDialog({ key, index })}
                        />
                      </div>
                      {slides.length ? (
                        <div className="mt-1 flex items-center justify-between gap-1">
                          <Button
                            size="icon"
                            variant="ghost"
                            className="size-7"
                            aria-label="Previous image"
                            onClick={() =>
                              setSlideIndexes((current) =>
                                new Map(current).set(
                                  key,
                                  Math.max(0, index - 1),
                                ),
                              )
                            }
                            disabled={index === 0}
                          >
                            <ChevronLeft className="size-3" />
                          </Button>
                          <span className="text-[10px] text-muted-foreground">
                            {index + 1}/{slides.length}
                          </span>
                          <Button
                            size="icon"
                            variant="ghost"
                            className="size-7"
                            aria-label="Next image"
                            onClick={() =>
                              setSlideIndexes((current) =>
                                new Map(current).set(
                                  key,
                                  Math.min(slides.length - 1, index + 1),
                                ),
                              )
                            }
                            disabled={index >= slides.length - 1}
                          >
                            <ChevronRight className="size-3" />
                          </Button>
                        </div>
                      ) : (
                        <p className="mt-1 text-center text-[10px] text-muted-foreground">
                          {t("noImage")}
                        </p>
                      )}
                    </div>
                  );
                })}
              </div>
            ))}
            <div
              className="col-span-full"
              style={{
                height:
                  Math.max(
                    0,
                    favorites.length - start - visibleFavorites.length,
                  ) * 144,
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

"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useTranslations } from "next-intl";
import { toast } from "sonner";

import { useAuth } from "@/components/auth-provider";
import {
  deleteStyleFavorite,
  fetchStyleFavorites,
  upsertStyleFavorite,
  type StyleFavoriteEntry,
  type StyleKey,
} from "@/lib/style-favorites";

/**
 * 网格侧收藏状态 hook（模型详情页）。
 *
 * - 未登录：`favorites` 为空且不发 GET（星标点击弹登录框由消费侧处理）。
 * - 按 `user?.id` 重拉；消费侧以 `key={user?.id ?? "anonymous"}` 挂载，
 *   切换用户时整体重置（参考 user-preferences-provider 的重置模式）。
 * - `toggle` 乐观更新，失败回滚 + toast.error（文案走 i18n）。
 */
export function useStyleFavorites() {
  const t = useTranslations("styleFavorites");
  const { user } = useAuth();
  const userId = user?.id ?? null;

  const [favorites, setFavorites] = useState<StyleFavoriteEntry[]>([]);
  const [isLoading, setIsLoading] = useState(userId !== null);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      if (!userId) {
        // 未登录 / 退出登录：清空收藏态，不发请求
        setFavorites([]);
        setIsLoading(false);
        return;
      }
      setIsLoading(true);
      // 失败时 fetchStyleFavorites 返回 null，静默降级为空收藏态
      const result = await fetchStyleFavorites();
      if (cancelled) return;
      setFavorites(result ?? []);
      setIsLoading(false);
    }

    void load();

    return () => {
      cancelled = true;
    };
  }, [userId]);

  const favoriteKeys = useMemo(
    () => new Set<StyleKey>(favorites.map((entry) => entry.style_key)),
    [favorites],
  );

  const toggle = useCallback(
    async (styleKey: StyleKey, label: string) => {
      if (!userId) return;

      const existing = favorites.find((entry) => entry.style_key === styleKey);
      if (existing) {
        // 已收藏 → 乐观删除，失败时补回原条目
        setFavorites((prev) =>
          prev.filter((entry) => entry.style_key !== styleKey),
        );
        const ok = await deleteStyleFavorite(styleKey);
        if (!ok) {
          setFavorites((prev) =>
            prev.some((entry) => entry.style_key === styleKey)
              ? prev
              : [...prev, existing],
          );
          toast.error(t("toggleFailed"));
        }
        return;
      }

      // 未收藏 → 乐观加入；runs 反查由下次拉取补齐（网格侧不消费 runs）
      const optimisticEntry: StyleFavoriteEntry = {
        style_key: styleKey,
        label,
        created_at: new Date().toISOString(),
        runs: [],
      };
      setFavorites((prev) => [...prev, optimisticEntry]);
      const ok = await upsertStyleFavorite(styleKey, label);
      if (!ok) {
        setFavorites((prev) =>
          prev.filter((entry) => entry.style_key !== styleKey),
        );
        toast.error(t("toggleFailed"));
      }
    },
    [favorites, t, userId],
  );

  return { favorites, favoriteKeys, isLoading, toggle };
}

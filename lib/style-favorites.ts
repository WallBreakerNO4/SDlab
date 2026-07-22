/**
 * 画师提示词收藏（Style Favorites）共享类型与 API 响应 type guard
 *
 * 身份与匹配约定：
 * - 收藏身份只用 style_key（`{collection_id}:{item_index}`，如 `300-nai-styles-table:9`），
 *   跨 run 匹配只比较 style_key，永不比较 prompt 字符串 / label。
 * - y_index 一律 0-based（= Y 资产 items 原始索引）；所有模型共用同一 Y 资产全量
 *   432 项，故 y_index + 1 恒等于网格行号，hash 跳转直接消费。
 * - label 仅是显示快照，不参与匹配。
 */

/** 收藏身份键：`{collection_id}:{item_index}`，如 `300-nai-styles-table:9` */
export type StyleKey = string;

/** style_key 长度上限：与 DB CHECK / PUT 校验一致（spec 决策记录 10） */
export const STYLE_KEY_MAX_LENGTH = 200;

const STYLE_KEY_REGEX = /^[^:]+:\d+$/;

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isNonNegativeInteger(value: unknown): value is number {
  return typeof value === "number" && Number.isInteger(value) && value >= 0;
}

/** style_key 形态 guard：`{collection_id}:{item_index}` 且长度不超过上限 */
export function isStyleKey(value: unknown): value is StyleKey {
  return (
    typeof value === "string" &&
    value.length <= STYLE_KEY_MAX_LENGTH &&
    STYLE_KEY_REGEX.test(value)
  );
}

/** label 长度上限：与 DB CHECK / PUT 校验一致（spec 决策记录 10） */
export const LABEL_MAX_LENGTH = 1000;

/** 收藏 label guard：非空字符串且长度不超过上限 */
export function isStyleFavoriteLabel(value: unknown): value is string {
  return (
    typeof value === "string" &&
    value.trim().length > 0 &&
    value.length <= LABEL_MAX_LENGTH
  );
}

/** run 内 Y 轴条目映射：style-items API 返回项，网格行收藏态 / 跳转用 */
export interface StyleItem {
  /** 0-based，等于 Y 资产 items 原始索引；y_index + 1 恒等于网格行号 */
  y_index: number;
  style_key: StyleKey;
}

/** 收藏在某个 run 中的可用性引用（收藏页「可用模型」列表项） */
export interface StyleFavoriteRunRef {
  run_dir: string;
  /** 模型显示名（run_list_items.model_name），可能为空 */
  name: string | null;
  /** 0-based；跨模型跳转 hash 用 y_index + 1 */
  y_index: number;
}

/** 用户收藏快照：label 仅作显示，不参与匹配 */
export interface StyleFavorite {
  style_key: StyleKey;
  label: string;
  created_at: string;
}

/** 收藏列表项：收藏快照 + 反查到的可用 run 列表 */
export interface StyleFavoriteEntry extends StyleFavorite {
  runs: StyleFavoriteRunRef[];
}

/** GET /api/viewer/style-favorites 响应 */
export interface StyleFavoritesResponse {
  favorites: StyleFavoriteEntry[];
}

export function isStyleItem(value: unknown): value is StyleItem {
  if (!isRecord(value)) return false;
  return isNonNegativeInteger(value.y_index) && isStyleKey(value.style_key);
}

export function isStyleFavoriteRunRef(
  value: unknown,
): value is StyleFavoriteRunRef {
  if (!isRecord(value)) return false;
  return (
    typeof value.run_dir === "string" &&
    (typeof value.name === "string" || value.name === null) &&
    isNonNegativeInteger(value.y_index)
  );
}

export function isStyleFavoriteEntry(
  value: unknown,
): value is StyleFavoriteEntry {
  if (!isRecord(value)) return false;
  return (
    isStyleKey(value.style_key) &&
    typeof value.label === "string" &&
    typeof value.created_at === "string" &&
    Array.isArray(value.runs) &&
    value.runs.every(isStyleFavoriteRunRef)
  );
}

/**
 * 解析 style-items API 响应（`[{ y_index, style_key }]`）。
 * 形态不符返回 null，调用方按「无收藏态」静默降级。
 */
export function parseStyleItemsResponse(value: unknown): StyleItem[] | null {
  if (!Array.isArray(value)) return null;
  if (!value.every(isStyleItem)) return null;
  return value;
}

/**
 * 解析 style-favorites API 响应（`{ favorites: [...] }`）。
 * 形态不符返回 null。
 */
export function parseStyleFavoritesResponse(
  value: unknown,
): StyleFavoritesResponse | null {
  if (!isRecord(value)) return null;
  const favorites: unknown = value.favorites;
  if (!Array.isArray(favorites)) return null;
  if (!favorites.every(isStyleFavoriteEntry)) return null;
  return { favorites };
}

/* -------------------------------------------------------------------------- */
/* 薄 fetch/mutate 函数（浏览器端调用，无 React 依赖）                          */
/* 约定：任何失败一律返回 null / false，由调用方静默降级，不向用户抛错。         */
/* -------------------------------------------------------------------------- */

/**
 * 拉取当前登录用户的收藏列表。
 * 未登录（401）、网络错误或响应形态不符时返回 null，调用方按「无收藏态」降级。
 */
export async function fetchStyleFavorites(): Promise<
  StyleFavoriteEntry[] | null
> {
  try {
    const res = await fetch("/api/viewer/style-favorites", {
      cache: "no-store",
    });
    if (!res.ok) return null;
    const parsed = parseStyleFavoritesResponse(await res.json());
    return parsed ? parsed.favorites : null;
  } catch {
    return null;
  }
}

/** upsert 一条收藏（body 校验在 API 侧做），成功返回 true */
export async function upsertStyleFavorite(
  styleKey: StyleKey,
  label: string,
): Promise<boolean> {
  try {
    const res = await fetch("/api/viewer/style-favorites", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      cache: "no-store",
      body: JSON.stringify({ style_key: styleKey, label }),
    });
    return res.ok;
  } catch {
    return false;
  }
}

/** 删除一条收藏；styleKey 含 `:`，路径段必须 encodeURIComponent */
export async function deleteStyleFavorite(
  styleKey: StyleKey,
): Promise<boolean> {
  try {
    const res = await fetch(
      `/api/viewer/style-favorites/${encodeURIComponent(styleKey)}`,
      {
        method: "DELETE",
        cache: "no-store",
      },
    );
    return res.ok;
  } catch {
    return false;
  }
}

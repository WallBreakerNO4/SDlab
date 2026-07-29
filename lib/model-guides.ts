import * as yaml from "js-yaml";

export const MODEL_GUIDE_LOCALES = ["zh", "en"] as const;
export type ModelGuideLocale = (typeof MODEL_GUIDE_LOCALES)[number];

export type ModelGuide = {
  modelKey: string;
  locale: ModelGuideLocale;
  title: string;
  content: string;
  sourcePath: string;
};

export type ModelGuideIndex = Readonly<
  Record<string, Readonly<Partial<Record<ModelGuideLocale, ModelGuide>>>>
>;

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function nonEmptyString(
  value: unknown,
  field: string,
  sourcePath: string,
): string {
  if (typeof value !== "string" || value.trim() === "") {
    throw new Error(`${sourcePath}: ${field} must be a non-empty string`);
  }
  return value.trim();
}

function parseFrontmatter(
  source: string,
  sourcePath: string,
): { metadata: Record<string, unknown>; content: string } {
  const match = source.match(
    /^\uFEFF?---\r?\n([\s\S]*?)\r?\n---(?:\r?\n|$)([\s\S]*)$/,
  );
  if (!match) {
    throw new Error(`${sourcePath}: missing YAML frontmatter`);
  }

  let metadata: unknown;
  try {
    metadata = yaml.load(match[1]);
  } catch (error) {
    throw new Error(`${sourcePath}: invalid YAML frontmatter`, {
      cause: error,
    });
  }
  return {
    metadata: isRecord(metadata) ? metadata : {},
    content: match[2].replace(/^\r?\n/, ""),
  };
}

export function parseModelGuide(
  source: string,
  sourcePath: string,
): ModelGuide {
  const { metadata, content } = parseFrontmatter(source, sourcePath);
  return parseModelGuideFromMetadata(metadata, content, sourcePath);
}

export function parseModelGuideFromMetadata(
  metadata: unknown,
  content: string,
  sourcePath: string,
): ModelGuide {
  if (!isRecord(metadata))
    throw new Error(`${sourcePath}: frontmatter must be a mapping`);
  const allowed = new Set(["model_key", "locale", "title"]);
  for (const key of Object.keys(metadata)) {
    if (!allowed.has(key))
      throw new Error(`${sourcePath}: unknown frontmatter field '${key}'`);
  }
  const modelKey = nonEmptyString(metadata.model_key, "model_key", sourcePath);
  const locale = nonEmptyString(metadata.locale, "locale", sourcePath);
  if (!MODEL_GUIDE_LOCALES.includes(locale as ModelGuideLocale)) {
    throw new Error(
      `${sourcePath}: locale must be one of ${MODEL_GUIDE_LOCALES.join(", ")}`,
    );
  }
  const title = nonEmptyString(metadata.title, "title", sourcePath);
  return {
    modelKey,
    locale: locale as ModelGuideLocale,
    title,
    content,
    sourcePath,
  };
}

export function buildGuideIndex(
  guides: readonly ModelGuide[],
): ModelGuideIndex {
  const index: Record<
    string,
    Partial<Record<ModelGuideLocale, ModelGuide>>
  > = {};
  for (const guide of guides) {
    const model = (index[guide.modelKey] ??= {});
    if (model[guide.locale]) {
      throw new Error(
        `duplicate model guide for ${guide.modelKey}/${guide.locale}`,
      );
    }
    model[guide.locale] = guide;
  }
  return index;
}

export function resolveGuideLocale(
  index: ModelGuideIndex,
  modelKey: string,
  preferredLocale: ModelGuideLocale,
): ModelGuideLocale | null {
  const guides = index[modelKey];
  if (!guides) return null;
  if (guides[preferredLocale]) return preferredLocale;
  const fallback = preferredLocale === "zh" ? "en" : "zh";
  return guides[fallback] ? fallback : null;
}

export function getModelGuide(
  index: ModelGuideIndex,
  modelKey: string,
  locale: ModelGuideLocale,
): ModelGuide | null {
  const resolved = resolveGuideLocale(index, modelKey, locale);
  return resolved ? (index[modelKey]?.[resolved] ?? null) : null;
}

/** Resolve the public guide URL, preserving the requested-language fallback. */
export function resolveGuidePath(
  index: ModelGuideIndex,
  modelKey: string,
  preferredLocale: ModelGuideLocale,
): string | null {
  const guide = getModelGuide(index, modelKey, preferredLocale);
  if (!guide) return null;
  return `/${guide.locale}/guides/${encodeURIComponent(guide.modelKey)}`;
}

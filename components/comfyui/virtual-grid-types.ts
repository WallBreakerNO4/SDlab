export type ImageVariantSource = {
  bucket: "public" | "private";
  cache_key: string;
  key: string;
};

export type VariantSources = {
  webp?: ImageVariantSource;
  avif?: ImageVariantSource;
};

export type RowMeta = {
  seed: string | null;
  prompt_id: number | null;
  prompt_hash: string | null;
  positive_prompt: string | null;
  y_value: string | null;
};

export type RowItem = {
  batch_index: number;
  category: string | null;
  width: number | null;
  height: number | null;
  blurhash: string | null;
  meta: RowMeta;
  thumb: VariantSources | null;
  display: VariantSources | null;
};

export type RowCell = {
  x_index: number;
  y_index: number;
  items: RowItem[];
};

export type RowPayload = {
  run_dir: string;
  y_index: number;
  cells: RowCell[];
};

export type RunGridXColumn = {
  type: string | null;
  description: Record<string, unknown> | null;
};

export type RunPrompt = {
  id: number;
  prompt_hash: string | null;
  positive_prompt: string;
};

export type RunGridYPromptParts = {
  yIndex: number;
  artist: string | null;
  commonPrompt: string | null;
};

export type BlurhashCell = {
  x_index: number;
  y_index: number;
  batch_index: number;
  category: string;
  width: number | null;
  height: number | null;
  blurhash: string | null;
};

export type RunGridIndexData = {
  x_columns: RunGridXColumn[];
  y_indexes: number[];
  y_labels?: string[];
  y_prompt_parts?: RunGridYPromptParts[];
  prompts: RunPrompt[];
  blurhash_cells: BlurhashCell[];
};

export type SavedScrollAnchor = {
  version: 1;
  yIndex: number;
  rowOffsetRatio: number;
};

export type SelectedCellPreview = {
  xIndex: number;
  yIndex: number;
  xLabel: string;
  yLabel: string;
  seed: string | null;
  promptHash: string | null;
  positivePrompt: string;
  items: Array<{
    batchIndex: number;
    width: number | null;
    height: number | null;
    thumb: VariantSources | null;
    display: VariantSources | null;
    thumbLoaded: boolean;
    blurhash: string | null;
  }>;
};

export type CachedRow =
  | {
      status: "ready";
      yIndex: number;
      yValue: string | null;
      representativeMeta: RowMeta | null;
      cellsByX: Map<number, RowCell>;
    }
  | {
      status: "error";
      yIndex: number;
      error: string;
    };

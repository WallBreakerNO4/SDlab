// ComfyUI run and grid types for the viewer

export type CellStatus = "success" | "failed" | "skipped" | "missing";

export type RunDir = string;

export interface GenerationParams {
  seed: number | null;
  negative_prompt: string | null;
  width: number | null;
  height: number | null;
  batch_size: number | null;
  steps: number | null;
  cfg: number | null;
  denoise: number | null;
  sampler_name: string | null;
  scheduler: string | null;
}

export interface ModelLinks {
  homepage?: string | null;
  huggingface?: string | null;
  civitai?: string | null;
}

export interface ModelMetadata {
  name?: string | null;
  description?: {
    zh?: string | null;
    en?: string | null;
  } | null;
  links?: ModelLinks | null;
}

export interface VariantUrls {
  webp?: string;
  avif?: string;
}

export interface RunAssetSummary {
  width?: number | null;
  height?: number | null;
  blurhash?: string | null;
  blurhash_width?: number | null;
  blurhash_height?: number | null;
  thumb?: VariantUrls | null;
  display?: VariantUrls | null;
}

export interface RunHomepageAssets {
  cover?: RunAssetSummary | null;
  homepage_cards?: RunAssetSummary[] | null;
}

export interface XFields {
  quality?: string;
  rating?: string;
  gender?: string;
  characters?: string;
  series?: string;
  general?: string;
}

export type GridCellKey = `${number},${number}`;

export interface GridCell {
  status: CellStatus;
  x_index: number;
  y_index: number;
  x_fields: XFields;
  y_value: string | null;
  positive_prompt: string | null;
  prompt_hash: string | null;
  seed: number | null;
  generation_params: GenerationParams | null;
  workflow_hash: string | null;
  comfyui_prompt_id: string | null;
  local_image_path: string | null;
  local_image_paths: string[] | null;
  error: unknown | null;
  started_at: string | null;
  finished_at: string | null;
  elapsed_ms: number | null;
}

export interface Selection {
  x_indexes: number[];
  y_indexes: number[];
  x_count: number;
  y_count: number;
  total_cells: number;
  x_limit: number | null;
  y_limit: number | null;
  x_indexes_raw: string | null;
  y_indexes_raw: string | null;
}

export interface GenerationOverrides {
  negative_prompt: string | null;
  width: number | null;
  height: number | null;
  batch_size: number | null;
  steps: number | null;
  cfg: number | null;
  denoise: number | null;
  sampler_name: string | null;
  scheduler: string | null;
}

export interface RunDetail {
  run_id: string;
  created_at: string;
  dry_run: boolean;
  run_dir: string;
  x_json_path: string;
  y_json_path: string;
  x_json_sha256: string;
  y_json_sha256: string;
  template: string;
  base_seed: number;
  seed_strategy: string;
  workflow_json_path: string;
  workflow_json_sha256: string;
  workflow_status: string;
  selected_ksampler_node_id: string | null;
  comfyui_base_url: string;
  request_timeout_s: number;
  job_timeout_s: number;
  concurrency: number;
  client_id: string | null;
  selection: Selection;
  generation_overrides: GenerationOverrides;
  model?: ModelMetadata | null;
}

export interface RunSummary {
  run_id: string;
  created_at: string;
  run_dir: string;
  x_count: number;
  y_count: number;
  total_cells: number;
  model?: ModelMetadata | null;
  assets?: RunHomepageAssets | null;
}

export interface GridIndex {
  xLabels: string[];
  yLabels: string[];
  x_count: number;
  y_count: number;
  cells: Record<GridCellKey, GridCell>;
}

export const RUN_DIR_REGEX = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;

export function isValidRunDir(runDir: string): runDir is RunDir {
  return RUN_DIR_REGEX.test(runDir);
}

export function isCellStatus(status: string): status is CellStatus {
  return ["success", "failed", "skipped", "missing"].includes(status);
}

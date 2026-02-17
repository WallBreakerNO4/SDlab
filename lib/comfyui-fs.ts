import { readFile, readdir, stat } from "node:fs/promises"
import path from "node:path"

import {
  type CellStatus,
  type GenerationParams,
  type GridCell,
  type GridCellKey,
  type GridIndex,
  type RunDetail,
  type RunDir,
  type RunSummary,
  type XFields,
  isCellStatus,
  isValidRunDir,
} from "./comfyui-types"

type JsonObject = Record<string, unknown>

const RUN_JSON_FILENAME = "run.json"
const METADATA_JSONL_FILENAME = "metadata.jsonl"
const X_FIELDS_ORDER: Array<keyof XFields> = [
  "quality",
  "rating",
  "gender",
  "characters",
  "series",
  "general",
]

export const DEFAULT_COMFYUI_OUTPUTS_ROOT = path.resolve(
  process.cwd(),
  "comfyui_api_outputs",
)

function isErrnoException(error: unknown): error is NodeJS.ErrnoException {
  return typeof error === "object" && error !== null && "code" in error
}

function isJsonObject(value: unknown): value is JsonObject {
  return typeof value === "object" && value !== null && !Array.isArray(value)
}

function parseJsonObject(raw: string): JsonObject | null {
  try {
    const parsed = JSON.parse(raw)
    return isJsonObject(parsed) ? parsed : null
  } catch {
    return null
  }
}

function toNullableString(value: unknown): string | null {
  return typeof value === "string" ? value : null
}

function toStringOrEmpty(value: unknown): string {
  return typeof value === "string" ? value : ""
}

function toNullableNumber(value: unknown): number | null {
  if (typeof value !== "number" || Number.isNaN(value)) {
    return null
  }

  return Number.isFinite(value) ? value : null
}

function toNumberOrZero(value: unknown): number {
  return toNullableNumber(value) ?? 0
}

function toNullableInteger(value: unknown): number | null {
  return typeof value === "number" && Number.isInteger(value) ? value : null
}

function toIntegerArray(value: unknown): number[] {
  if (!Array.isArray(value)) {
    return []
  }

  return value.filter(
    (item): item is number => typeof item === "number" && Number.isInteger(item),
  )
}

function toStringArray(value: unknown): string[] | null {
  if (!Array.isArray(value)) {
    return null
  }

  const values = value.filter(
    (item): item is string => typeof item === "string" && item.length > 0,
  )
  return values.length > 0 ? values : null
}

function toCellKey(xIndex: number, yIndex: number): GridCellKey {
  return `${xIndex},${yIndex}`
}

function normalizeCellStatus(value: unknown): CellStatus {
  if (typeof value === "string" && isCellStatus(value)) {
    return value
  }
  return "failed"
}

function normalizeXFields(value: unknown): XFields {
  if (!isJsonObject(value)) {
    return {}
  }

  const xFields: XFields = {}
  for (const key of X_FIELDS_ORDER) {
    const item = value[key]
    if (typeof item === "string") {
      xFields[key] = item
    }
  }
  return xFields
}

function normalizeGenerationParams(value: unknown): GenerationParams | null {
  if (!isJsonObject(value)) {
    return null
  }

  return {
    seed: toNullableNumber(value.seed),
    negative_prompt: toNullableString(value.negative_prompt),
    width: toNullableNumber(value.width),
    height: toNullableNumber(value.height),
    batch_size: toNullableNumber(value.batch_size),
    steps: toNullableNumber(value.steps),
    cfg: toNullableNumber(value.cfg),
    denoise: toNullableNumber(value.denoise),
    sampler_name: toNullableString(value.sampler_name),
    scheduler: toNullableString(value.scheduler),
  }
}

function normalizeGridCell(record: JsonObject): GridCell | null {
  const xIndex = toNullableInteger(record.x_index)
  const yIndex = toNullableInteger(record.y_index)
  if (xIndex === null || yIndex === null) {
    return null
  }

  const localImagePath = toNullableString(record.local_image_path)
  const imagePaths = toStringArray(record.local_image_paths)
  const mergedImagePaths = imagePaths ?? (localImagePath ? [localImagePath] : null)

  return {
    status: normalizeCellStatus(record.status),
    x_index: xIndex,
    y_index: yIndex,
    x_fields: normalizeXFields(record.x_fields),
    y_value: toNullableString(record.y_value),
    positive_prompt: toNullableString(record.positive_prompt),
    prompt_hash: toNullableString(record.prompt_hash),
    seed: toNullableNumber(record.seed),
    generation_params: normalizeGenerationParams(record.generation_params),
    workflow_hash: toNullableString(record.workflow_hash),
    comfyui_prompt_id: toNullableString(record.comfyui_prompt_id),
    local_image_path: localImagePath ?? mergedImagePaths?.[0] ?? null,
    local_image_paths: mergedImagePaths,
    error: record.error ?? null,
    started_at: toNullableString(record.started_at),
    finished_at: toNullableString(record.finished_at),
    elapsed_ms: toNullableNumber(record.elapsed_ms),
  }
}

function normalizeSelection(value: unknown): RunDetail["selection"] {
  const record = isJsonObject(value) ? value : {}
  const xIndexes = toIntegerArray(record.x_indexes)
  const yIndexes = toIntegerArray(record.y_indexes)

  return {
    x_indexes: xIndexes,
    y_indexes: yIndexes,
    x_count: toNullableInteger(record.x_count) ?? xIndexes.length,
    y_count: toNullableInteger(record.y_count) ?? yIndexes.length,
    total_cells:
      toNullableInteger(record.total_cells) ?? xIndexes.length * yIndexes.length,
    x_limit: toNullableNumber(record.x_limit),
    y_limit: toNullableNumber(record.y_limit),
    x_indexes_raw: toNullableString(record.x_indexes_raw),
    y_indexes_raw: toNullableString(record.y_indexes_raw),
  }
}

function normalizeGenerationOverrides(
  value: unknown,
): RunDetail["generation_overrides"] {
  const record = isJsonObject(value) ? value : {}
  return {
    negative_prompt: toNullableString(record.negative_prompt),
    width: toNullableNumber(record.width),
    height: toNullableNumber(record.height),
    batch_size: toNullableNumber(record.batch_size),
    steps: toNullableNumber(record.steps),
    cfg: toNullableNumber(record.cfg),
    denoise: toNullableNumber(record.denoise),
    sampler_name: toNullableString(record.sampler_name),
    scheduler: toNullableString(record.scheduler),
  }
}

function normalizeRunDetail(record: JsonObject, runDir: RunDir): RunDetail {
  const runId = toNullableString(record.run_id)
  const createdAt = toNullableString(record.created_at)
  if (!runId || !createdAt) {
    throw new Error(`Invalid run.json: missing run_id/created_at for ${runDir}`)
  }

  return {
    run_id: runId,
    created_at: createdAt,
    dry_run: record.dry_run === true,
    run_dir:
      toNullableString(record.run_dir) ??
      path.posix.join("comfyui_api_outputs", runDir),
    x_csv_path: toStringOrEmpty(record.x_csv_path),
    y_csv_path: toStringOrEmpty(record.y_csv_path),
    x_csv_sha256: toStringOrEmpty(record.x_csv_sha256),
    y_csv_sha256: toStringOrEmpty(record.y_csv_sha256),
    template: toStringOrEmpty(record.template),
    base_seed: toNumberOrZero(record.base_seed),
    seed_strategy: toStringOrEmpty(record.seed_strategy),
    workflow_json_path: toStringOrEmpty(record.workflow_json_path),
    workflow_json_sha256: toStringOrEmpty(record.workflow_json_sha256),
    workflow_status: toStringOrEmpty(record.workflow_status),
    selected_ksampler_node_id: toNullableString(record.selected_ksampler_node_id),
    comfyui_base_url: toStringOrEmpty(record.comfyui_base_url),
    request_timeout_s: toNumberOrZero(record.request_timeout_s),
    job_timeout_s: toNumberOrZero(record.job_timeout_s),
    concurrency: toNullableInteger(record.concurrency) ?? 0,
    client_id: toNullableString(record.client_id),
    selection: normalizeSelection(record.selection),
    generation_overrides: normalizeGenerationOverrides(record.generation_overrides),
  }
}

function createMissingCell(xIndex: number, yIndex: number): GridCell {
  return {
    status: "missing",
    x_index: xIndex,
    y_index: yIndex,
    x_fields: {},
    y_value: null,
    positive_prompt: null,
    prompt_hash: null,
    seed: null,
    generation_params: null,
    workflow_hash: null,
    comfyui_prompt_id: null,
    local_image_path: null,
    local_image_paths: null,
    error: null,
    started_at: null,
    finished_at: null,
    elapsed_ms: null,
  }
}

function formatXLabel(cell: GridCell | undefined, xIndex: number): string {
  if (!cell) {
    return `x${xIndex}`
  }

  const values = X_FIELDS_ORDER.map((key) => cell.x_fields[key]?.trim()).filter(
    (item): item is string => Boolean(item),
  )
  return values.length > 0 ? values.join(" ") : `x${xIndex}`
}

function formatYLabel(cell: GridCell | undefined, yIndex: number): string {
  const yValue = cell?.y_value?.trim()
  return yValue && yValue.length > 0 ? yValue : `y${yIndex}`
}

async function containsRunJson(runPath: string): Promise<boolean> {
  try {
    const file = await stat(path.join(runPath, RUN_JSON_FILENAME))
    return file.isFile()
  } catch (error) {
    if (isErrnoException(error) && error.code === "ENOENT") {
      return false
    }
    throw error
  }
}

export async function discoverRunDirs(
  outputsRoot: string = DEFAULT_COMFYUI_OUTPUTS_ROOT,
): Promise<RunDir[]> {
  let entries
  try {
    entries = await readdir(outputsRoot, {
      withFileTypes: true,
      encoding: "utf8",
    })
  } catch (error) {
    if (isErrnoException(error) && error.code === "ENOENT") {
      return []
    }
    throw error
  }

  const candidates = entries.filter(
    (entry) => entry.isDirectory() && isValidRunDir(entry.name),
  )

  const runDirs = await Promise.all(
    candidates.map(async (entry) => {
      const runPath = path.join(outputsRoot, entry.name)
      if (!(await containsRunJson(runPath))) {
        return null
      }
      return entry.name
    }),
  )

  return runDirs
    .filter((runDir): runDir is RunDir => runDir !== null)
    .sort((left, right) => right.localeCompare(left))
}

export async function loadRunDetail(
  runDir: RunDir,
  outputsRoot: string = DEFAULT_COMFYUI_OUTPUTS_ROOT,
): Promise<RunDetail> {
  const runJsonPath = path.join(outputsRoot, runDir, RUN_JSON_FILENAME)
  const raw = await readFile(runJsonPath, "utf8")
  const parsed = parseJsonObject(raw)
  if (!parsed) {
    throw new Error(`Invalid run.json: ${runDir}`)
  }

  return normalizeRunDetail(parsed, runDir)
}

export async function parseMetadataJsonl(
  runDir: RunDir,
  outputsRoot: string = DEFAULT_COMFYUI_OUTPUTS_ROOT,
): Promise<Record<GridCellKey, GridCell>> {
  const metadataPath = path.join(outputsRoot, runDir, METADATA_JSONL_FILENAME)

  let raw: string
  try {
    raw = await readFile(metadataPath, "utf8")
  } catch (error) {
    if (isErrnoException(error) && error.code === "ENOENT") {
      return {}
    }
    throw error
  }

  const cells = new Map<GridCellKey, GridCell>()
  const lines = raw.split(/\r?\n/)

  for (const line of lines) {
    const trimmed = line.trim()
    if (trimmed.length === 0) {
      continue
    }

    const parsed = parseJsonObject(trimmed)
    if (!parsed) {
      continue
    }

    const cell = normalizeGridCell(parsed)
    if (!cell) {
      continue
    }

    cells.set(toCellKey(cell.x_index, cell.y_index), cell)
  }

  return Object.fromEntries(cells) as Record<GridCellKey, GridCell>
}

export function buildGridIndex(
  runDetail: RunDetail,
  cells: Record<GridCellKey, GridCell>,
): GridIndex {
  const xIndexes = runDetail.selection.x_indexes
  const yIndexes = runDetail.selection.y_indexes

  const firstByX = new Map<number, GridCell>()
  const firstByY = new Map<number, GridCell>()
  for (const cell of Object.values(cells)) {
    if (!firstByX.has(cell.x_index)) {
      firstByX.set(cell.x_index, cell)
    }
    if (!firstByY.has(cell.y_index)) {
      firstByY.set(cell.y_index, cell)
    }
  }

  const xLabels = xIndexes.map((xIndex) => formatXLabel(firstByX.get(xIndex), xIndex))
  const yLabels = yIndexes.map((yIndex) => formatYLabel(firstByY.get(yIndex), yIndex))

  const gridCells: Record<GridCellKey, GridCell> = {}
  for (const yIndex of yIndexes) {
    for (const xIndex of xIndexes) {
      const key = toCellKey(xIndex, yIndex)
      gridCells[key] = cells[key] ?? createMissingCell(xIndex, yIndex)
    }
  }

  return {
    xLabels,
    yLabels,
    x_count: xIndexes.length,
    y_count: yIndexes.length,
    cells: gridCells,
  }
}

export async function loadRunGridIndex(
  runDir: RunDir,
  outputsRoot: string = DEFAULT_COMFYUI_OUTPUTS_ROOT,
): Promise<{ runDetail: RunDetail; grid: GridIndex }> {
  const runDetail = await loadRunDetail(runDir, outputsRoot)
  const cells = await parseMetadataJsonl(runDir, outputsRoot)
  const grid = buildGridIndex(runDetail, cells)
  return {
    runDetail,
    grid,
  }
}

export async function listRunSummaries(
  outputsRoot: string = DEFAULT_COMFYUI_OUTPUTS_ROOT,
): Promise<RunSummary[]> {
  const runDirs = await discoverRunDirs(outputsRoot)
  const summaries: RunSummary[] = []

  for (const runDir of runDirs) {
    try {
      const runDetail = await loadRunDetail(runDir, outputsRoot)
      summaries.push({
        run_id: runDetail.run_id,
        created_at: runDetail.created_at,
        run_dir: runDir,
        x_count: runDetail.selection.x_indexes.length,
        y_count: runDetail.selection.y_indexes.length,
        total_cells:
          runDetail.selection.x_indexes.length *
          runDetail.selection.y_indexes.length,
      })
    } catch {
      continue
    }
  }

  return summaries
}

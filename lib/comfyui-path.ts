import path from "node:path"

import { type RunDir, isValidRunDir } from "./comfyui-types"

const WINDOWS_DRIVE_LETTER_PREFIX = /^[a-zA-Z]:/

function toComparablePath(value: string): string {
  return process.platform === "win32" ? value.toLowerCase() : value
}

function assertNonEmptyTrimmed(value: string, fieldName: string): string {
  const trimmed = value.trim()
  if (trimmed.length === 0) {
    throw new Error(`${fieldName} must not be empty`)
  }
  return trimmed
}

export function assertAllowedRunDir(runDir: string, allowed: Set<RunDir>): RunDir {
  const candidate = assertNonEmptyTrimmed(runDir, "runDir")

  if (!isValidRunDir(candidate)) {
    throw new Error("Invalid runDir format")
  }

  if (!allowed.has(candidate)) {
    throw new Error("runDir is not in allowlist")
  }

  return candidate
}

export function assertSafeRelativeImagePath(imagePath: string): string {
  const candidate = assertNonEmptyTrimmed(imagePath, "imagePath")

  if (candidate.includes("\0")) {
    throw new Error("imagePath must not contain null bytes")
  }

  if (candidate.includes("%")) {
    throw new Error("imagePath must not contain URL-encoded characters")
  }

  if (candidate.includes("\\")) {
    throw new Error("imagePath must not contain backslashes")
  }

  if (path.posix.isAbsolute(candidate) || path.win32.isAbsolute(candidate)) {
    throw new Error("imagePath must be relative")
  }

  if (WINDOWS_DRIVE_LETTER_PREFIX.test(candidate)) {
    throw new Error("imagePath must not contain a drive letter")
  }

  const segments = candidate.split("/")
  if (segments.some((segment) => segment.length === 0)) {
    throw new Error("imagePath must not contain empty segments")
  }

  if (segments.includes(".") || segments.includes("..")) {
    throw new Error("imagePath must not contain dot segments")
  }

  const normalized = path.posix.normalize(candidate)
  if (normalized === "." || normalized.startsWith("../") || normalized.includes("/../")) {
    throw new Error("imagePath escapes the expected relative scope")
  }

  return normalized
}

export function resolvePathUnderRoot(root: string, relPath: string): string {
  const safeRoot = assertNonEmptyTrimmed(root, "root")
  const safeRelPath = assertSafeRelativeImagePath(relPath)

  const resolvedRoot = path.resolve(safeRoot)
  const resolvedTarget = path.resolve(resolvedRoot, safeRelPath)

  const comparableRoot = toComparablePath(resolvedRoot)
  const comparableTarget = toComparablePath(resolvedTarget)
  const rootWithSep = comparableRoot.endsWith(path.sep)
    ? comparableRoot
    : `${comparableRoot}${path.sep}`

  if (comparableTarget !== comparableRoot && !comparableTarget.startsWith(rootWithSep)) {
    throw new Error("Resolved path escapes root")
  }

  return resolvedTarget
}

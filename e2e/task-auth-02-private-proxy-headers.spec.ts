import { randomUUID } from "node:crypto"
import { mkdirSync, writeFileSync } from "node:fs"

import { expect, test } from "@playwright/test"
import { createServerClient } from "@supabase/ssr"
import { createClient } from "@supabase/supabase-js"

const evidencePath = ".sisyphus/evidence/task-auth-02-private-proxy-headers.txt"

const forbiddenTokens = [/\/home\//i, /C:\\\\/i, /stack/i, /Traceback/i]

function assertNoSensitiveLeak(payload: string): void {
  for (const token of forbiddenTokens) {
    expect(payload).not.toMatch(token)
  }
}

function requireEnv(name: string): string {
  const value = (process.env[name] ?? "").trim()
  if (!value) {
    throw new Error(`Missing env: ${name}`)
  }
  return value
}

function requireBaseURL(testInfo: unknown): string {
  const candidate = testInfo as { project?: { use?: { baseURL?: unknown } } }
  const baseURL = candidate.project?.use?.baseURL
  if (typeof baseURL !== "string" || !baseURL.trim()) {
    throw new Error("Missing baseURL; check playwright.config.ts")
  }
  return baseURL
}

async function pickFirstRunDir(args: {
  page: { request: { get: (url: string) => Promise<{ status: () => number; text: () => Promise<string> }> } }
  baseURL: string
}): Promise<string> {
  const runsResponse = await args.page.request.get("/api/comfyui/runs")
  const runsText = await runsResponse.text()
  let payload: unknown = null

  try {
    payload = JSON.parse(runsText)
  } catch {
    payload = null
  }

  const evidenceBase = [
    `baseURL=${args.baseURL}`,
    `runs_status=${runsResponse.status()}`,
    `runs_body_snippet=${runsText.slice(0, 400)}`,
  ]

  if (!Array.isArray(payload) || payload.length === 0) {
    writeFileSync(
      evidencePath,
      evidenceBase
        .concat(["error=No runs available; did you seed supabase via uploader?"])
        .join("\n")
        .concat("\n"),
      "utf8",
    )
    throw new Error("No runs available; did you seed supabase via uploader?")
  }

  const first = payload[0]
  if (!first || typeof first !== "object") {
    writeFileSync(
      evidencePath,
      evidenceBase.concat(["error=Unexpected runs payload shape"]).join("\n").concat("\n"),
      "utf8",
    )
    throw new Error("Unexpected /api/comfyui/runs payload shape")
  }

  const record = first as Record<string, unknown>
  const runDir = typeof record.run_dir === "string" ? record.run_dir : ""
  if (!runDir) {
    writeFileSync(
      evidencePath,
      evidenceBase.concat(["error=Missing run_dir in first run"]).join("\n").concat("\n"),
      "utf8",
    )
    throw new Error("Missing run_dir in /api/comfyui/runs first item")
  }

  return runDir
}
async function pickAuthedOriginalDownloadUrl(args: {
  request: { get: (url: string) => Promise<{ status: () => number; ok: () => boolean; text: () => Promise<string> }> }
  baseURL: string
  preferredRunDir?: string
}): Promise<{ runDir: string; originalDownloadUrl: string }> {
  const runsResponse = await args.request.get("/api/comfyui/runs")
  const runsText = await runsResponse.text()
  let payload: unknown = null

  try {
    payload = JSON.parse(runsText)
  } catch {
    payload = null
  }

  const evidenceBase = [
    `baseURL=${args.baseURL}`,
    `runs_status=${runsResponse.status()}`,
    `runs_body_snippet=${runsText.slice(0, 400)}`,
  ]

  if (!Array.isArray(payload) || payload.length === 0) {
    writeFileSync(
      evidencePath,
      evidenceBase
        .concat(["error=No runs available; did you seed supabase via uploader?"])
        .join("\n")
        .concat("\n"),
      "utf8",
    )
    throw new Error("No runs available; did you seed supabase via uploader?")
  }

  const candidates = payload
    .slice(0, 25)
    .map((item) => (item && typeof item === "object" ? (item as Record<string, unknown>) : null))
    .map((record) => (record && typeof record.run_dir === "string" ? record.run_dir : ""))
    .filter((dir) => !!dir)

  if (typeof args.preferredRunDir === "string" && args.preferredRunDir) {
    candidates.unshift(args.preferredRunDir)
  }

  const uniqueCandidates = Array.from(new Set(candidates))

  for (const runDir of uniqueCandidates) {
    const chunkResponse = await args.request.get(
      `/api/comfyui/run/${encodeURIComponent(runDir)}/grid/chunk?y_from=0&y_to=0`,
    )
    if (!chunkResponse.ok()) {
      continue
    }

    const chunkPayload = (JSON.parse(await chunkResponse.text()) as unknown) as {
      cells?: Array<{ items?: Array<{ original_download_url?: unknown }> }>
    }

    for (const cell of chunkPayload.cells ?? []) {
      for (const item of cell.items ?? []) {
        if (typeof item.original_download_url === "string" && item.original_download_url) {
          if (/^\/api\/media\/variant\//.test(item.original_download_url)) {
            return { runDir, originalDownloadUrl: item.original_download_url }
          }
        }
      }
    }
  }

  writeFileSync(
    evidencePath,
    evidenceBase
      .concat([
        `candidate_count=${uniqueCandidates.length}`,
        "error=No original_download_url found from grid/chunk",
      ])
      .join("\n")
      .concat("\n"),
    "utf8",
  )
  throw new Error("No original_download_url found")
}

function resolveSupabaseUrl(): string {
  const fromSupabaseUrl = (process.env.SUPABASE_URL ?? "").trim()
  if (fromSupabaseUrl) return fromSupabaseUrl

  return requireEnv("NEXT_PUBLIC_SUPABASE_URL")
}

function toPlaywrightSameSite(value: unknown): "Lax" | "None" | "Strict" | undefined {
  if (value === "lax" || value === "Lax") return "Lax"
  if (value === "none" || value === "None") return "None"
  if (value === "strict" || value === "Strict") return "Strict"
  return undefined
}

async function createAuthedCookiesForContext(): Promise<
  Array<{ name: string; value: string; options?: Record<string, unknown> }>
> {
  const supabaseUrl = resolveSupabaseUrl()
  const publishableKey = requireEnv("NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY")
  const serviceRoleKey = requireEnv("SUPABASE_SERVICE_ROLE_KEY")

  const email = `e2e-task-auth-${Date.now()}-${randomUUID()}@example.com`
  const password = `e2e-${randomUUID()}`

  const admin = createClient(supabaseUrl, serviceRoleKey, {
    auth: {
      persistSession: false,
      autoRefreshToken: false,
      detectSessionInUrl: false,
    },
  })

  const createResult = await admin.auth.admin.createUser({
    email,
    password,
    email_confirm: true,
  })

  expect(createResult.error?.message ?? null).toBeNull()
  expect(createResult.data.user?.id ?? null).not.toBeNull()

  const client = createClient(supabaseUrl, publishableKey, {
    auth: {
      persistSession: false,
      autoRefreshToken: false,
      detectSessionInUrl: false,
    },
  })

  const signInResult = await client.auth.signInWithPassword({ email, password })
  expect(signInResult.error?.message ?? null).toBeNull()
  expect(signInResult.data.session?.access_token ?? null).not.toBeNull()
  expect(signInResult.data.session?.refresh_token ?? null).not.toBeNull()

  const session = signInResult.data.session
  if (!session) {
    throw new Error("Missing session from signInWithPassword")
  }

  const cookieStore = new Map<string, string>()
  const cookiesToSet: Array<{ name: string; value: string; options?: Record<string, unknown> }> = []

  const ssr = createServerClient(supabaseUrl, publishableKey, {
    cookies: {
      getAll() {
        return Array.from(cookieStore.entries()).map(([name, value]) => ({ name, value }))
      },
      setAll(cookies) {
        for (const cookie of cookies) {
          cookiesToSet.push(cookie)
          cookieStore.set(cookie.name, cookie.value)
        }
      },
    },
  })

  const setSessionResult = await ssr.auth.setSession({
    access_token: session.access_token,
    refresh_token: session.refresh_token,
  })

  expect(setSessionResult.error?.message ?? null).toBeNull()
  expect(cookiesToSet.length).toBeGreaterThan(0)

  return cookiesToSet
}

test("task-auth-02 private proxy headers", async ({ context, page }, testInfo) => {
  mkdirSync(".sisyphus/evidence", { recursive: true })

  const baseURL = requireBaseURL(testInfo)
  const cookieUrl = new URL(baseURL)
  cookieUrl.pathname = "/"
  const origin = cookieUrl.origin

  const cookiesToSet = await createAuthedCookiesForContext()
  await context.addCookies(
    cookiesToSet.map((cookie) => {
      const options = cookie.options ?? {}
      const secure = typeof options.secure === "boolean" ? options.secure : false

      return {
        name: cookie.name,
        value: cookie.value,
        url: origin,
        httpOnly: typeof options.httpOnly === "boolean" ? options.httpOnly : false,
        secure: secure && origin.startsWith("https://"),
        sameSite: toPlaywrightSameSite(options.sameSite),
      }
    }),
  )

  await page.goto("/")

  const preferredRunDir = await pickFirstRunDir({
    page: { request: context.request },
    baseURL,
  })

  const { runDir, originalDownloadUrl } = await pickAuthedOriginalDownloadUrl({
    request: context.request,
    baseURL,
    preferredRunDir,
  })

  const originalResponse = await context.request.get(originalDownloadUrl)
  if (!originalResponse.ok()) {
    const originalBody = await originalResponse.text()
    assertNoSensitiveLeak(originalBody)
  }

  expect(originalResponse.status()).toBe(200)

  const headers = originalResponse.headers()
  const cacheControl = headers["cache-control"] ?? ""
  const vary = headers.vary ?? ""

  expect(cacheControl).toMatch(/private/i)
  expect(cacheControl).toMatch(/no-store/i)
  expect(cacheControl).toMatch(/no-cache/i)
  expect(cacheControl).toMatch(/must-revalidate/i)

  expect(vary).toMatch(/Cookie/i)
  expect(vary).toMatch(/Authorization/i)

  expect(headers["x-content-type-options"]).toBe("nosniff")

  const evidence = [
    `baseURL=${baseURL}`,
    `runDir=${runDir}`,
    `url=${originalDownloadUrl}`,
    `status=${originalResponse.status()}`,
    `cache-control=${cacheControl}`,
    `vary=${vary}`,
    `x-content-type-options=${headers["x-content-type-options"] ?? ""}`,
  ]
    .join("\n")
    .concat("\n")

  writeFileSync(evidencePath, evidence, "utf8")
})

import { mkdirSync, writeFileSync } from "node:fs"

import { expect, test } from "@playwright/test"

const evidencePath = ".sisyphus/evidence/task-auth-01-anon.txt"

function requireBaseURL(testInfo: unknown): string {
  const candidate = testInfo as { project?: { use?: { baseURL?: unknown } } }
  const baseURL = candidate.project?.use?.baseURL
  if (typeof baseURL !== "string" || !baseURL.trim()) {
    throw new Error("Missing baseURL; check playwright.config")
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

  const candidates = payload
    .slice(0, 25)
    .map((item) => (item && typeof item === "object" ? (item as Record<string, unknown>) : null))
    .map((record) => (record && typeof record.run_dir === "string" ? record.run_dir : ""))
    .filter((dir) => !!dir)

  for (const candidateRunDir of candidates) {
    const detailRes = await args.page.request.get(
      `/api/comfyui/run/${encodeURIComponent(candidateRunDir)}`,
    )
    if (!detailRes.status || detailRes.status() < 200 || detailRes.status() >= 300) {
      continue
    }

    const metaRes = await args.page.request.get(
      `/api/comfyui/run/${encodeURIComponent(candidateRunDir)}/grid/meta`,
    )
    if (!metaRes.status || metaRes.status() < 200 || metaRes.status() >= 300) {
      continue
    }

    const meta = (JSON.parse(await metaRes.text()) as unknown) as {
      xColumns?: Array<{ category?: string }>
    }
    const categories = (meta.xColumns ?? []).map((col) => col.category)
    if (categories.length === 0) {
      continue
    }

    if (categories.every((category) => category === "normal")) {
      return candidateRunDir
    }
  }

  writeFileSync(
    evidencePath,
    evidenceBase
      .concat([
        `candidate_count=${candidates.length}`,
        "error=No runDir usable for anon (needs run detail + meta ok and categories all normal)",
      ])
      .join("\n")
      .concat("\n"),
    "utf8",
  )
  throw new Error("No runDir usable for anon")
}

test("task-auth-01 anon only sees normal columns and cannot download original", async (
  { page },
  testInfo,
) => {
  mkdirSync(".sisyphus/evidence", { recursive: true })
  test.setTimeout(60_000)

  const baseURL = requireBaseURL(testInfo)
  const runDir = await pickFirstRunDir({ page, baseURL })

  const metaResponse = await page.request.get(
    `/api/comfyui/run/${encodeURIComponent(runDir)}/grid/meta`,
  )
  expect(metaResponse.ok()).toBeTruthy()

  const metaPayload = (await metaResponse.json()) as {
    xColumns?: Array<{ category?: string }>
  }

  const categories = (metaPayload.xColumns ?? []).map((col) => col.category)
  expect(categories.length).toBeGreaterThan(0)

  for (const category of categories) {
    expect(category).toBe("normal")
  }

  const runPageResponse = await page.goto(`/runs/${encodeURIComponent(runDir)}`)
  expect(runPageResponse?.ok()).toBeTruthy()

  const grid = page.getByTestId("run-grid")
  const notFound = page.getByTestId("run-not-found")

  await expect(grid.or(notFound)).toBeVisible({ timeout: 30_000 })
  if (await notFound.isVisible()) {
    const evidence = [
      `baseURL=${baseURL}`,
      `runDir=${runDir}`,
      `url=${page.url()}`,
      "error=Run not found page rendered",
    ]
      .join("\n")
      .concat("\n")
    writeFileSync(evidencePath, evidence, "utf8")
    throw new Error("Run not found page rendered")
  }

  // Wait for the chunk request to complete
  await page.waitForResponse(/\/grid\/chunk\?/, { timeout: 20_000 }).catch(() => null)

  const openCellButton = grid.locator('button[aria-label^="打开单元格 X"]').first()
  await expect(openCellButton).toBeVisible({ timeout: 20_000 })
  await openCellButton.click()

  const dialog = page.getByTestId("cell-dialog")
  await expect(dialog).toBeVisible()

  const downloadButton = dialog.getByRole("button", { name: "下载原图" })
  await expect(downloadButton).toBeDisabled()

  await expect(dialog.locator('a[href*="/api/media/variant/"]')).toHaveCount(0)

  const evidence = [
    `baseURL=${baseURL}`,
    `runDir=${runDir}`,
    `meta_status=${metaResponse.status()}`,
    `categories=${categories.join(",")}`,
  ]
    .join("\n")
    .concat("\n")

  writeFileSync(evidencePath, evidence, "utf8")
})

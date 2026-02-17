import { mkdirSync } from "node:fs"

import { expect, test, type Page } from "@playwright/test"

const runDir = "run-20260217T072414Z"
const evidencePath = ".sisyphus/evidence/task-16-img-cap.png"
const maxImageDomCount = 300

type GridContract = {
  xLabels: string[]
}

function isGridContract(payload: unknown): payload is GridContract {
  if (typeof payload !== "object" || payload === null) {
    return false
  }

  const value = payload as { xLabels?: unknown }
  return Array.isArray(value.xLabels) && value.xLabels.every((item) => typeof item === "string")
}

async function getFirstVisibleRowIndex(page: Page): Promise<number> {
  const rowIndexText =
    (await page
      .getByTestId("run-grid-row")
      .first()
      .getAttribute("data-row-index")) ?? "0"

  return Number(rowIndexText)
}

test("task 16 performance keeps image DOM count capped and resilient", async ({ page }) => {
  mkdirSync(".sisyphus/evidence", { recursive: true })

  const gridResponse = await page.request.get(`/api/comfyui/run/${runDir}/grid`)
  expect(gridResponse.ok()).toBeTruthy()
  const gridPayload: unknown = await gridResponse.json()
  if (!isGridContract(gridPayload)) {
    throw new Error("Unexpected grid payload")
  }

  const xLabelCount = gridPayload.xLabels.length
  expect(xLabelCount).toBeGreaterThan(0)

  const response = await page.goto(`/runs/${runDir}`)
  expect(response?.ok()).toBeTruthy()

  const grid = page.getByTestId("run-grid")
  const scrollContainer = page.getByTestId("run-grid-scroll")
  const imageLocator = page.locator('img[data-testid="run-grid-image"]')
  const previewLocator = page.locator(
    '[data-testid="run-grid-image"], [data-testid="run-grid-placeholder"]',
  )

  await expect(grid).toBeVisible()
  await expect(scrollContainer).toBeVisible()
  await expect
    .poll(async () => {
      return previewLocator.count()
    })
    .toBeGreaterThan(0)

  const firstRow = page.getByTestId("run-grid-row").first()
  const firstRowPreviewCount = await firstRow
    .locator('[data-testid="run-grid-image"], [data-testid="run-grid-placeholder"]')
    .count()
  expect(firstRowPreviewCount).toBe(xLabelCount)

  const imageCountBeforeScroll = await imageLocator.count()
  expect(imageCountBeforeScroll).toBeLessThan(maxImageDomCount)

  const firstRowIndexBefore = await getFirstVisibleRowIndex(page)

  await scrollContainer.evaluate((element) => {
    element.scrollTop = Math.max(0, element.scrollHeight - element.clientHeight - 100)
  })

  await expect
    .poll(async () => {
      return getFirstVisibleRowIndex(page)
    })
    .toBeGreaterThan(firstRowIndexBefore)

  await expect
    .poll(async () => {
      return imageLocator.count()
    })
    .toBeLessThan(maxImageDomCount)

  const firstRowAfterScrollPreviewCount = await page
    .getByTestId("run-grid-row")
    .first()
    .locator('[data-testid="run-grid-image"], [data-testid="run-grid-placeholder"]')
    .count()
  expect(firstRowAfterScrollPreviewCount).toBe(xLabelCount)

  await page.screenshot({ path: evidencePath, fullPage: true })
})

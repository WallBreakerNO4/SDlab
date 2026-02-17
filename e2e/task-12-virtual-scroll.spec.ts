import { mkdirSync } from "node:fs"

import { expect, test } from "@playwright/test"

const runDir = "run-20260217T072414Z"
const evidencePath = ".sisyphus/evidence/task-12-virtual-scroll.png"

test("run grid uses row virtualization with sticky header and left column", async ({ page }) => {
  mkdirSync(".sisyphus/evidence", { recursive: true })

  const response = await page.goto(`/runs/${runDir}`)
  expect(response?.ok()).toBeTruthy()

  const grid = page.getByTestId("run-grid")
  const scrollContainer = page.getByTestId("run-grid-scroll")

  await expect(grid).toBeVisible()
  await expect(scrollContainer).toBeVisible()

  const rowCount = Number((await grid.getAttribute("data-row-count")) ?? "0")
  expect(rowCount).toBeGreaterThan(0)

  const renderedRowsBefore = await page.getByTestId("run-grid-row").count()
  expect(renderedRowsBefore).toBeGreaterThan(0)
  expect(renderedRowsBefore).toBeLessThan(rowCount)

  const firstRowBefore = Number(
    (await page.getByTestId("run-grid-row").first().getAttribute("data-row-index")) ??
      "0",
  )

  await expect(page.getByTestId("run-grid-corner")).toHaveCSS("position", "sticky")
  await expect(page.getByTestId("run-grid-y-label").first()).toHaveCSS(
    "position",
    "sticky",
  )

  await expect(page.getByTestId("run-grid-image").first()).toBeVisible()

  await scrollContainer.evaluate((element) => {
    element.scrollTop = 2200
  })

  await page.waitForTimeout(200)

  const firstRowAfter = Number(
    (await page.getByTestId("run-grid-row").first().getAttribute("data-row-index")) ??
      "0",
  )
  expect(firstRowAfter).toBeGreaterThan(firstRowBefore)

  const renderedRowsAfter = await page.getByTestId("run-grid-row").count()
  expect(renderedRowsAfter).toBeGreaterThan(0)
  expect(renderedRowsAfter).toBeLessThan(rowCount)

  await page.screenshot({ path: evidencePath, fullPage: true })
})

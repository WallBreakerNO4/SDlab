import { mkdirSync } from "node:fs"

import { expect, test } from "@playwright/test"

const runDir = "run-20260217T072414Z"
const appOrigin = "http://127.0.0.1:3000"
const tracePath = ".sisyphus/evidence/task-14-e2e-trace.zip"

test("home to run detail supports scroll, dialog and prompt copy", async ({ context, page }) => {
  mkdirSync(".sisyphus/evidence", { recursive: true })

  await context.grantPermissions(["clipboard-read", "clipboard-write"], {
    origin: appOrigin,
  })

  await context.tracing.start({
    screenshots: true,
    snapshots: true,
    sources: true,
  })

  try {
    const homeResponse = await page.goto("/")
    expect(homeResponse?.ok()).toBeTruthy()

    const runLink = page.getByRole("link", { name: /run-20260217T072414Z/ })
    await expect(runLink).toBeVisible()
    await runLink.click()

    await expect(page).toHaveURL(new RegExp(`/runs/${runDir}$`))

    const grid = page.getByTestId("run-grid")
    const scrollContainer = page.getByTestId("run-grid-scroll")

    await expect(grid).toBeVisible()
    await expect(scrollContainer).toBeVisible()
    await expect(page.getByTestId("run-grid-image").first()).toBeVisible()

    const firstRowBefore = Number(
      (await page.getByTestId("run-grid-row").first().getAttribute("data-row-index")) ??
        "0",
    )

    await scrollContainer.evaluate((element) => {
      element.scrollTop = Math.max(0, element.scrollHeight - element.clientHeight - 200)
    })

    await expect
      .poll(async () => {
        return Number(
          (await page
            .getByTestId("run-grid-row")
            .first()
            .getAttribute("data-row-index")) ?? "0",
        )
      })
      .toBeGreaterThan(firstRowBefore)

    const openCellButton = grid.locator('button[aria-label^="打开单元格 X"]').first()
    await expect(openCellButton).toBeVisible()
    await openCellButton.click()

    const dialog = page.getByTestId("cell-dialog")
    await expect(dialog).toBeVisible()

    const promptText = (await page.getByTestId("cell-dialog-prompt").innerText()).trim()
    await page.getByTestId("cell-dialog-copy-prompt").click()

    await expect
      .poll(async () => {
        return page.evaluate(async () => navigator.clipboard.readText())
      })
      .toBe(promptText)
  } finally {
    await context.tracing.stop({ path: tracePath })
  }
})

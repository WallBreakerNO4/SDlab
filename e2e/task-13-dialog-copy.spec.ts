import { mkdirSync } from "node:fs"

import { expect, test } from "@playwright/test"

const runDir = "run-20260217T072414Z"
const evidencePath = ".sisyphus/evidence/task-13-dialog-copy.png"
const appOrigin = "http://127.0.0.1:3000"

test("cell dialog supports preview, copy and download", async ({ context, page }) => {
  mkdirSync(".sisyphus/evidence", { recursive: true })

  await context.grantPermissions(["clipboard-read", "clipboard-write"], {
    origin: appOrigin,
  })

  const response = await page.goto(`/runs/${runDir}`)
  expect(response?.ok()).toBeTruthy()

  const grid = page.getByTestId("run-grid")
  await expect(grid).toBeVisible()

  const firstSuccessCellButton = grid
    .locator('button[aria-label^="打开单元格 X"]')
    .first()
  await expect(firstSuccessCellButton).toBeVisible()
  await firstSuccessCellButton.click()

  const dialog = page.getByTestId("cell-dialog")
  await expect(dialog).toBeVisible()

  const promptText = (await page.getByTestId("cell-dialog-prompt").innerText()).trim()
  await page.getByTestId("cell-dialog-copy-prompt").click()
  await expect
    .poll(async () => {
      return page.evaluate(async () => navigator.clipboard.readText())
    })
    .toBe(promptText)

  const copySeedButton = page.getByTestId("cell-dialog-copy-seed")
  await expect(copySeedButton).toBeEnabled()
  const seedText = (await page.getByTestId("cell-dialog-seed").innerText()).trim()
  await copySeedButton.click()
  await expect
    .poll(async () => {
      return page.evaluate(async () => navigator.clipboard.readText())
    })
    .toBe(seedText)

  await expect(dialog.getByRole("link", { name: "下载原图" })).toHaveAttribute(
    "href",
    /\/api\/comfyui\/image\//,
  )

  await page.screenshot({ path: evidencePath, fullPage: true })
})

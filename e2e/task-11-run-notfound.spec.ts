import { mkdirSync } from "node:fs"

import { expect, test } from "@playwright/test"

const evidencePath = ".sisyphus/evidence/task-11-run-notfound.png"

test("run detail shows not-found state", async ({ page }) => {
  mkdirSync(".sisyphus/evidence", { recursive: true })

  const response = await page.goto("/runs/not-exist")
  expect(response?.ok()).toBeTruthy()

  const notFoundState = page.getByTestId("run-not-found")
  await expect(notFoundState).toBeVisible()
  await expect(notFoundState).toContainText("未找到 run")

  await page.screenshot({ path: evidencePath, fullPage: true })
})

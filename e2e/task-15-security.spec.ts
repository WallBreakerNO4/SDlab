import { mkdirSync, writeFileSync } from "node:fs"

import { expect, test } from "@playwright/test"

const evidencePath = ".sisyphus/evidence/task-15-traversal.txt"
const missingRunApiPath = "/api/comfyui/run/not-exist"
const missingRunPagePath = "/runs/not-exist"
const traversalApiPath =
  "/api/comfyui/image/run-20260217T072414Z/..%2f..%2fpackage.json"

const forbiddenTokens = [/\/home\//i, /C:\\\\/i, /stack/i, /Traceback/i]

function assertNoSensitiveLeak(payload: string): void {
  for (const token of forbiddenTokens) {
    expect(payload).not.toMatch(token)
  }
}

test("security regression for invalid run and traversal path", async ({ page }) => {
  mkdirSync(".sisyphus/evidence", { recursive: true })

  const missingRunResponse = await page.request.get(missingRunApiPath)
  expect(missingRunResponse.status()).toBe(404)
  const missingRunBody = await missingRunResponse.text()
  assertNoSensitiveLeak(missingRunBody)

  const missingRunPageResponse = await page.goto(missingRunPagePath)
  expect(missingRunPageResponse?.ok()).toBeTruthy()
  await expect(page.getByTestId("run-not-found")).toBeVisible()

  const traversalResponse = await page.request.get(traversalApiPath)
  expect([400, 404]).toContain(traversalResponse.status())

  const traversalBody = await traversalResponse.text()
  assertNoSensitiveLeak(traversalBody)

  const bodySnippet = traversalBody.slice(0, 400)
  const headers = traversalResponse.headersArray()
  const evidence = [
    `url=${traversalApiPath}`,
    `status=${traversalResponse.status()}`,
    "headers:",
    ...headers.map((header) => `${header.name}: ${header.value}`),
    "body_snippet:",
    bodySnippet,
  ].join("\n")

  writeFileSync(evidencePath, `${evidence}\n`, "utf8")
})

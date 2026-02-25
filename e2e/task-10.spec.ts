import { test, expect } from "@playwright/test"

test("task 10: placeholder appears before image load", async ({ page }) => {
  // We need a runDir that has images. Let's use the API to find one or just mock it.
  // Wait, we can just intercept the image request and delay it.
  
  // First, go to the home page to find a runDir
  await page.goto("/")
  
  // Find the first run link
  const runLink = page.locator("a[href^='/runs/']").first()
  const runUrl = await runLink.getAttribute("href")
  if (!runUrl) throw new Error("No run URL found")
  
  // Intercept image requests and delay them
  await page.route("**/api/comfyui/image/**", async (route) => {
    // Delay the response by 2 seconds
    await new Promise((resolve) => setTimeout(resolve, 2000))
    await route.continue()
  })
  
  // Navigate to the run page
  await page.goto(runUrl)
  
  // Wait for the grid to load
  await expect(page.getByTestId("run-grid")).toBeVisible()
  
  // Check that the blurhash canvas is visible
  const blurhashCanvas = page.getByTestId("blurhash-canvas").first()
  await expect(blurhashCanvas).toBeVisible()
  
  // Check that the image is initially invisible (opacity 0)
  const image = page.getByTestId("run-grid-image").first()
  await expect(image).toHaveClass(/opacity-0/)
  
  // Take a screenshot of the placeholder
  await page.screenshot({ path: ".sisyphus/evidence/task-10-placeholder.png" })
  
  // Wait for the image to load (opacity 100)
  await expect(image).toHaveClass(/opacity-100/, { timeout: 5000 })
  
  // Check that the blurhash canvas is now invisible (opacity 0)
  await expect(blurhashCanvas).toHaveClass(/opacity-0/)
})

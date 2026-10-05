import { expect, test } from "@playwright/test";
import { tokens, waitForMap } from "./helpers";

test("DS pauses and resumes the exercise and places a jammer from the map", async ({ page }) => {
  await page.goto(`/ds?t=${tokens().ds}`);
  await waitForMap(page, "truth");
  const start = page.getByTestId("ds-start");
  const clock = page.getByTestId("ds-clock");
  await expect(start).toHaveText("Pause");

  await start.click();
  await expect(start).toHaveText("Resume");
  await page.waitForTimeout(600);
  const held = await clock.textContent();
  await page.waitForTimeout(2500);
  await expect(clock).toHaveText(held ?? "");

  // An inject placed while paused is queued and applied when the exercise resumes.
  await page.getByTestId("ds-place-jammer").click();
  await expect(page.getByTestId("ds-pick-hint")).toBeVisible();
  const box = (await page.locator(".ds .map").boundingBox())!;
  await page.mouse.click(box.x + box.width * 0.5, box.y + box.height * 0.5);
  await expect(page.getByTestId("ds-note")).toContainText("Jammer J-1 placed");

  await start.click();
  await expect(start).toHaveText("Pause");
  await expect(page.locator(".events")).toContainText("Jammer J-1 placed", { timeout: 30_000 });
  await expect(clock).not.toHaveText(held ?? "");

  await page.locator(".inj-row", { hasText: "J-1" }).getByRole("button", { name: "Remove" }).click();
  await expect(page.locator(".events")).toContainText("Jammer J-1 removed", { timeout: 30_000 });
});

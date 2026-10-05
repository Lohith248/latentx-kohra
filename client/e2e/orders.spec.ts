import { expect, test } from "@playwright/test";
import { tokens, waitForMap } from "./helpers";

test("Send stays disabled until confidence and relied-on are set", async ({ page }) => {
  await page.goto(`/play?t=${tokens().player}`);
  await waitForMap(page, "picture");
  const send = page.getByTestId("send");
  await expect(send).toBeDisabled();

  await page.getByTestId("order-to").selectOption("TIGER-1");
  await page.getByTestId("order-kind").selectOption("MOVE");
  await expect(send).toBeDisabled();

  await page.getByTestId("pick-grid").click();
  const box = (await page.getByTestId("map").boundingBox())!;
  await page.mouse.click(box.x + box.width * 0.45, box.y + box.height * 0.6);
  await expect(page.getByTestId("pick-grid")).toHaveText(/GR \d{3} \d{3}/);
  await expect(send).toBeDisabled();
  await expect(page.getByTestId("sent")).toContainText("confidence");

  await page.getByTestId("confidence").focus();
  await page.keyboard.press("ArrowRight");
  await expect(page.locator(".confidence")).toContainText("Confidence 55%");
  await expect(send).toBeDisabled();
  await expect(page.getByTestId("sent")).toContainText("relied-on");

  await page.getByTestId("relied-none").check();
  await expect(send).toBeEnabled();
  await send.click();

  await expect(page.getByTestId("sent")).toContainText(/transmitted \(awaiting WILCO\)|WILCO/, { timeout: 30_000 });
  await expect(page.getByTestId("radio-log")).toContainText(/TIGER-1.*(MOVE|move|Proceed)/, { timeout: 30_000 });
  // After sending, the next order starts again from an unset confidence.
  await expect(page.locator(".confidence")).toContainText("Set confidence");
});

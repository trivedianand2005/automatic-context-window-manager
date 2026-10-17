import { expect, test } from "@playwright/test";
import type { Page } from "@playwright/test";

const SHOTS = process.env.E2E_SCREENSHOT_DIR;

async function shot(page: Page, name: string) {
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/${name}.png`, fullPage: true });
}

async function nav(page: Page, label: string) {
  await page.getByRole("navigation", { name: "Main" }).getByRole("button", { name: label }).click();
}

test("full workflow: demo -> results -> compare -> export -> repository -> benchmarks", async ({ page }) => {
  const consoleErrors: string[] = [];
  page.on("console", (m) => m.type() === "error" && consoleErrors.push(m.text()));

  await page.goto("/");
  await expect(page.getByText(/API online/)).toBeVisible();
  await shot(page, "01-overview");

  // One-click demo indexes the sample repo and builds the JWT task at 4,000 tokens.
  await page.getByRole("button", { name: "Run the demo" }).click();
  await expect(page.getByRole("heading", { name: "Results" })).toBeVisible();
  await expect(page.getByText("shopapi/api/dependencies.py").first()).toBeVisible();
  await expect(page.getByText("shopapi/services/auth_service.py").first()).toBeVisible();
  const selectedCount = Number(await page.locator("text=Selected items").locator("..").locator("div").nth(1).innerText());
  expect(selectedCount).toBeGreaterThan(3);
  await page.getByRole("button", { name: /shopapi\/services\/auth_service\.py/ }).click();
  await expect(page.getByText("Score components")).toBeVisible();
  await expect(page.getByText("class AuthService").first()).toBeVisible();
  await shot(page, "02-results");

  await page.getByRole("tab", { name: /Dependency view/ }).click();
  await expect(page.locator(".react-flow__node").first()).toBeVisible();
  await shot(page, "03-results-graph");

  // Compare the three methods on the labelled JWT task.
  await nav(page, "Compare");
  await page.getByRole("button", { name: "Run comparison" }).click();
  await expect(page.getByRole("heading", { name: "Full ACWM" })).toBeVisible();
  const acwmCard = page.locator("section", { has: page.getByRole("heading", { name: "Full ACWM" }) });
  const baseCard = page.locator("section", { has: page.getByRole("heading", { name: "Baseline (BM25)" }) });
  const found = async (card: typeof acwmCard) => {
    const text = await card.getByText("relevant found").locator("..").locator("div").first().innerText();
    return Number(text.split("/")[0]);
  };
  expect(await found(acwmCard)).toBeGreaterThan(await found(baseCard));
  await expect(page.locator(".recharts-bar-rectangle").first()).toBeVisible();
  await shot(page, "04-compare");

  // Export: server-rendered Markdown preview and a working download.
  await nav(page, "Export");
  await expect(page.getByText("# ACWM Context Package")).toBeVisible();
  const [download] = await Promise.all([
    page.waitForEvent("download"),
    page.getByRole("button", { name: /Download acwm_context\.md/ }).click(),
  ]);
  expect(download.suggestedFilename()).toBe("acwm_context.md");
  await page.getByRole("tab", { name: "JSON" }).click();
  await expect(page.getByText('"schema_version"')).toBeVisible();
  await shot(page, "05-export");

  // Repository explorer: files, symbols and the interactive graph.
  await nav(page, "Repository");
  await expect(page.getByText("shopapi/db/database.py").first()).toBeVisible();
  await page.getByRole("tab", { name: /Symbols/ }).click();
  await expect(page.getByText(/def |class /).first()).toBeVisible();
  await page.getByRole("tab", { name: /Dependency graph/ }).click();
  await expect(page.locator(".react-flow__node").first()).toBeVisible();
  await shot(page, "06-repository-graph");

  // Benchmarks across all labelled tasks.
  await nav(page, "Benchmarks");
  await page.getByRole("button", { name: "Run benchmarks" }).click();
  await expect(page.getByText(/Mean scores over 5 tasks/)).toBeVisible();
  await shot(page, "07-benchmarks");

  // Build page renders and a custom task works end to end.
  await nav(page, "Build context");
  await page.getByLabel("Coding task").fill("Fix database retry behavior and add regression tests.");
  await page.getByRole("button", { name: "Build context" }).last().click();
  await expect(page.getByText("shopapi/db/database.py").first()).toBeVisible();
  await shot(page, "08-custom-build");

  expect(consoleErrors.filter((e) => !e.includes("favicon"))).toEqual([]);
});

test("rejects paths outside the allowed roots with a friendly error", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByText(/API online/)).toBeVisible();
  await nav(page, "Repository");
  await page.getByLabel("Repository directory").fill("/etc");
  await page.getByRole("button", { name: /Index repository|Re-index/ }).click();
  await expect(page.getByRole("alert")).toContainText("outside the allowed roots");
});

test("mobile layout renders navigation and demo", async ({ browser }) => {
  const ctx = await browser.newContext({ viewport: { width: 390, height: 844 } });
  const page = await ctx.newPage();
  await page.goto("/");
  await expect(page.getByText(/API online/)).toBeVisible();
  await page.getByRole("button", { name: "Run the demo" }).click();
  await expect(page.getByRole("heading", { name: "Results" })).toBeVisible();
  await shot(page, "09-mobile-results");
  await ctx.close();
});

test("second example repository (LibTrack) can be indexed and used", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByText(/API online/)).toBeVisible();
  await nav(page, "Repository");
  await page.getByRole("button", { name: /LibTrack/ }).click();
  await expect(page.getByText("libtrack/fines.py").first()).toBeVisible();
  await nav(page, "Build context");
  await page.getByRole("button", { name: "late-fee-bug" }).click();
  await page.getByLabel("Coding task").fill(
    "Fix the off-by-one bug in the fine calculation (overdue_days) and add regression tests.",
  );
  await page.getByLabel("Total token budget").fill("6000");
  await page.getByRole("button", { name: "Build context" }).last().click();
  await expect(page.getByRole("heading", { name: "Results" })).toBeVisible();
  for (const f of ["libtrack/fines.py", "libtrack/loans.py", "tests/test_fines.py"]) {
    await expect(page.getByText(f, { exact: true }).first()).toBeVisible();
  }
  await shot(page, "10-libtrack-results");
});

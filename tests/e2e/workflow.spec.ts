import { test, expect } from "../../apps/web/node_modules/@playwright/test";
import fs from "node:fs";
import path from "node:path";
const shots = path.resolve(process.cwd(), "../../docs/screenshots");
async function login(
  page: import("../../apps/web/node_modules/@playwright/test").Page,
  role = "analyst",
) {
  await page.goto("/");
  await page.getByLabel("Workspace role").selectOption(role);
  await page.getByRole("button", { name: "Enter workspace" }).click();
  await expect(
    page.getByRole("heading", { name: "Clarity for every case." }),
  ).toBeVisible();
}

test("analyst investigation, version-bound approval and simulator resolution", async ({
  page,
}) => {
  fs.mkdirSync(shots, { recursive: true });
  await page.setViewportSize({ width: 1440, height: 1050 });
  await login(page);
  await expect(page.getByText("DEMO MODE")).toBeVisible();
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({
    path: path.join(shots, "caseflow-inbox.png"),
    fullPage: true,
  });
  await page.getByLabel("Search cases").fill("Two charges");
  await expect(
    page.getByRole("button", { name: /Two charges, one purchase/ }),
  ).toBeVisible();
  await page.getByRole("button", { name: /Two charges, one purchase/ }).click();
  await expect(
    page.getByRole("heading", { name: "Two charges, one purchase" }),
  ).toBeVisible();
  const alreadyResolved = await page
    .locator(".detail-heading")
    .getByText("Resolved", { exact: true })
    .count();
  if (!alreadyResolved) {
    if (
      await page
        .getByRole("button", { name: "Run investigation", exact: true })
        .count()
    )
      await page
        .getByRole("button", { name: "Run investigation", exact: true })
        .click();
    await expect(
      page.getByText(
        "A supervisor must approve this exact version before resolution.",
      ),
    ).toBeVisible({ timeout: 45000 });
    await expect(page.getByRole("button", { name: /Approve v/ })).toHaveCount(
      0,
    );
    await page.getByRole("tab", { name: /Activity/ }).click();
    await expect(
      page.getByText("Proposal Prepared", { exact: true }).first(),
    ).toBeVisible({ timeout: 30000 });
    await page.getByRole("tab", { name: "Overview" }).click();
    await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({
      path: path.join(shots, "caseflow-investigation.png"),
      fullPage: true,
    });
    await page.getByRole("button", { name: "Sign out" }).click();
    await login(page, "supervisor");
    await page
      .getByRole("button", { name: /Two charges, one purchase/ })
      .click();
    await page.getByRole("button", { name: /Approve v/ }).click();
    await expect(page.getByRole("dialog")).toBeVisible();
    await page.getByRole("button", { name: "Confirm approve" }).click();
    await expect(page.getByRole("dialog")).toHaveCount(0);
    await page.getByRole("button", { name: "Record resolution" }).click();
    await page.getByRole("button", { name: "Confirm resolve" }).click();
    await expect(
      page.locator(".detail-heading").getByText("Resolved", { exact: true }),
    ).toBeVisible({ timeout: 45000 });
  }
  await page.getByRole("tab", { name: /Activity/ }).click();
  await expect(
    page.getByText("Resolution Registered", { exact: true }).first(),
  ).toBeVisible();
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({
    path: path.join(shots, "caseflow-resolved.png"),
    fullPage: true,
  });
});

test("responsive inbox, empty search, keyboard focus and invalid credentials", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  await page.getByLabel("Password", { exact: true }).fill("incorrect");
  await page.getByRole("button", { name: "Enter workspace" }).click();
  await expect(page.locator(".alert.error")).toBeVisible();
  await page.getByLabel("Password", { exact: true }).fill("demo-pass");
  await page.getByRole("button", { name: "Enter workspace" }).click();
  await expect(
    page.getByRole("heading", { name: "Clarity for every case." }),
  ).toBeVisible();
  await page.getByLabel("Search cases").focus();
  await page.keyboard.press("Tab");
  await expect(page.getByLabel("Filter by status")).toBeFocused();
  await page.getByLabel("Search cases").fill("no-such-synthetic-case");
  await expect(
    page.getByRole("heading", { name: "No cases match this view" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Clear filters" }).click();
  await expect(
    page.getByRole("button", { name: /Two charges, one purchase/ }),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({
    path: path.join(shots, "caseflow-mobile.png"),
    fullPage: true,
  });
});

test('supervisor can reject a recommendation without a reimbursement proposal', async ({page}) => {
  await login(page);
  await page.getByRole('button',{name:/Purchase confirmed by customer/}).click();
  await expect(page.getByRole('heading',{name:'Purchase confirmed by customer'})).toBeVisible();
  if(await page.locator('.detail-heading').getByText('Rejected',{exact:true}).count())return;
  if(await page.getByRole('button',{name:'Run investigation',exact:true}).count())await page.getByRole('button',{name:'Run investigation',exact:true}).click();
  await expect(page.getByText('Evidence requested; supervisor review pending.',{exact:true})).toBeVisible({timeout:45000});
  await expect(page.getByRole('button',{name:'Run investigation',exact:true})).toHaveCount(0);
  await expect(page.getByRole('button',{name:'Reject case',exact:true})).toHaveCount(0);
  await page.getByRole('tab',{name:/Activity/}).click();
  await expect(page.getByText('Rejection Recommended',{exact:true})).toBeVisible();
  await page.getByRole('button',{name:'Sign out'}).click();
  await login(page,'supervisor');
  await page.getByRole('button',{name:/Purchase confirmed by customer/}).click();
  await page.getByRole('button',{name:'Reject case',exact:true}).click();
  await expect(page.getByRole('heading',{name:'Reject this case?'})).toBeVisible();
  await page.getByRole('button',{name:'Confirm reject'}).click();
  await expect(page.locator('.detail-heading').getByText('Rejected',{exact:true})).toBeVisible();
  await expect(page.getByText('Case rejected. This case is closed.')).toBeVisible();
  await expect(page.getByRole('button',{name:'Run investigation',exact:true})).toHaveCount(0);
  await page.getByRole('tab',{name:/Activity/}).click();
  await expect(page.getByText('Proposal Rejected',{exact:true})).toBeVisible();
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({path:path.join(shots,'caseflow-rejected.png'),fullPage:true});
});

test('insufficient evidence and recoverable failures expose the correct next action', async ({page}) => {
  await login(page);
  await page.getByRole('button',{name:/Missing delivery evidence/}).click();
  await expect(page.getByRole('heading',{name:'Missing delivery evidence'})).toBeVisible();
  if(await page.getByRole('button',{name:'Run investigation',exact:true}).count())await page.getByRole('button',{name:'Run investigation',exact:true}).click();
  await expect(page.getByText('Evidence requested; supervisor review pending.',{exact:true})).toBeVisible({timeout:45000});
  await expect(page.getByRole('button',{name:'Run investigation',exact:true})).toHaveCount(0);
  for(const title of ['Merchant feed unavailable','Interrupted investigation']) {
    await page.getByRole('button',{name:'Back to case inbox'}).click();
    await page.getByRole('button',{name:new RegExp(title)}).click();
    await expect(page.getByRole('heading',{name:title})).toBeVisible();
    if(await page.locator('.detail-heading').getByText('Awaiting Approval',{exact:true}).count())continue;
    if(await page.getByRole('button',{name:'Run investigation',exact:true}).count())await page.getByRole('button',{name:'Run investigation',exact:true}).click();
    await expect(page.getByRole('button',{name:'Resume investigation',exact:true})).toBeVisible({timeout:45000});
    await expect(page.getByRole('button',{name:'Run investigation',exact:true})).toHaveCount(0);
    await page.getByRole('button',{name:'Resume investigation',exact:true}).click();
    await expect(page.locator('.detail-heading').getByText('Awaiting Approval',{exact:true})).toBeVisible({timeout:45000});
    await expect(page.getByRole('button',{name:'Run investigation',exact:true})).toHaveCount(0);
  }
});

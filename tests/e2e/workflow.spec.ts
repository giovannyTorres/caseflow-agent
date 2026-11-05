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
    path: path.join(shots, "audit-caseflow-inbox.png"),
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
  // A completed fixture is not evidence that this test exercised the workflow.
  await expect(page.locator(".detail-heading").getByText("New", {exact:true})).toBeVisible();
  await page.getByRole("button", {name:"Run investigation",exact:true}).click();
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
      path: path.join(shots, "audit-caseflow-investigation.png"),
      fullPage: true,
    });
    await page.getByRole("button", { name: "Sign out" }).click();
    await login(page, "supervisor");
    await page
      .getByRole("button", { name: /Two charges, one purchase/ })
      .click();
    await page.getByRole("button", { name: /Approve v/ }).click();
    await expect(page.getByRole("dialog")).toBeVisible();
    await expect(page.getByRole("button", {name:"Cancel",exact:true})).toBeFocused();
    await page.keyboard.press("Shift+Tab");
    await expect(page.getByRole("button", {name:"Confirm approve",exact:true})).toBeFocused();
    await page.keyboard.press("Escape");
    await expect(page.getByRole("dialog")).toHaveCount(0);
    await page.getByRole("button", {name:/Approve v/}).click();
    await page.getByRole("button", { name: "Confirm approve" }).click();
    await expect(page.getByRole("dialog")).toHaveCount(0);
    await page.getByRole("button", { name: "Record resolution" }).click();
    await page.getByRole("button", { name: "Confirm resolve" }).click();
    await expect(
      page.locator(".detail-heading").getByText("Resolved", { exact: true }),
    ).toBeVisible({ timeout: 45000 });
  await page.getByRole("tab", { name: /Activity/ }).click();
  await expect(
    page.getByText("Resolution Registered", { exact: true }).first(),
  ).toBeVisible();
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({
    path: path.join(shots, "audit-caseflow-resolved.png"),
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
    path: path.join(shots, "audit-caseflow-mobile.png"),
    fullPage: true,
  });
});

test('supervisor can reject a recommendation without a reimbursement proposal', async ({page}) => {
  await login(page);
  await page.getByRole('button',{name:/Purchase confirmed by customer/}).click();
  await expect(page.getByRole('heading',{name:'Purchase confirmed by customer'})).toBeVisible();
  await expect(page.locator('.detail-heading').getByText('New',{exact:true})).toBeVisible();
  await page.getByRole('button',{name:'Run investigation',exact:true}).click();
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
  await page.screenshot({path:path.join(shots,'audit-caseflow-rejected.png'),fullPage:true});
});

test('insufficient evidence and recoverable failures expose the correct next action', async ({page}) => {
  await login(page);
  await page.getByRole('button',{name:/Missing delivery evidence/}).click();
  await expect(page.getByRole('heading',{name:'Missing delivery evidence'})).toBeVisible();
  await expect(page.locator('.detail-heading').getByText('New',{exact:true})).toBeVisible();
  await page.getByRole('button',{name:'Run investigation',exact:true}).click();
  await expect(page.getByText('Evidence requested; supervisor review pending.',{exact:true})).toBeVisible({timeout:45000});
  await expect(page.getByRole('button',{name:'Run investigation',exact:true})).toHaveCount(0);
  for(const [title,id] of [['Merchant feed unavailable','demo-004'],['Interrupted investigation','demo-005']]) {
    await page.getByRole('button',{name:'Back to case inbox'}).click();
    await page.getByRole('button',{name:new RegExp(`${title} ${id} `)}).click();
    await expect(page.getByRole('heading',{name:title})).toBeVisible();
    await expect(page.locator('.detail-heading').getByText('New',{exact:true})).toBeVisible();
    await page.getByRole('button',{name:'Run investigation',exact:true}).click();
    await expect(page.getByRole('button',{name:'Resume investigation',exact:true})).toBeVisible({timeout:45000});
    await expect(page.getByRole('button',{name:'Run investigation',exact:true})).toHaveCount(0);
    await page.getByRole('button',{name:'Resume investigation',exact:true}).click();
    await expect(page.locator('.detail-heading').getByText('Awaiting Approval',{exact:true})).toBeVisible({timeout:45000});
    await expect(page.getByRole('button',{name:'Run investigation',exact:true})).toHaveCount(0);
  }
});

test('LIVE sign-in accepts provisioned usernames without demo credentials (configuration fixture)', async ({page}) => {
  await page.route('**/api/config', route => route.fulfill({json:{mode:'LIVE',provider:'gemini',model:'gemini-2.5-flash',live_ready:false,missing:['GEMINI_API_KEY']}}));
  await page.route('**/api/me', route => route.fulfill({status:401,json:{detail:'Sign in'}}));
  let attempted: {username:string,password:string}|undefined;
  await page.route('**/api/auth/login', route => {
    attempted=route.request().postDataJSON();
    return route.fulfill({status:401,json:{detail:'Fixture credential rejection; no provider called'}});
  });
  await page.goto('/');
  await expect(page.getByLabel('Username',{exact:true})).toBeVisible();
  await expect(page.getByLabel('Password',{exact:true})).toHaveValue('');
  await expect(page.getByText(/Demo credentials:/)).toHaveCount(0);
  await expect(page.getByText('Demo workspace',{exact:true})).toHaveCount(0);
  await expect(page.getByText('LIVE configuration incomplete')).toBeVisible();
  await page.getByLabel('Username',{exact:true}).fill('reviewer-provisioned');
  await page.getByLabel('Password',{exact:true}).fill('synthetic-live-test-password');
  await page.getByRole('button',{name:'Enter workspace'}).click();
  await expect(page.getByText('Fixture credential rejection; no provider called')).toBeVisible();
  expect(attempted).toEqual({username:'reviewer-provisioned',password:'synthetic-live-test-password'});
  await page.screenshot({path:path.join(shots,'audit-live-sign-in.png'),fullPage:true});
});

test('unavailable configuration has an explicit error and retry, never a DEMO fallback', async ({page}) => {
  await page.route('**/api/config', route => route.fulfill({status:503,json:{detail:'Synthetic configuration outage'}}));
  await page.goto('/');
  await expect(page.getByRole('button',{name:'Retry connection'})).toBeVisible();
  await expect(page.getByRole('button',{name:'Enter workspace'})).toBeDisabled();
  await expect(page.getByLabel('Username',{exact:true})).toHaveValue('');
  await expect(page.getByLabel('Password',{exact:true})).toHaveValue('');
  await expect(page.getByText('DEMO MODE')).toHaveCount(0);
  await expect(page.getByText('Workspace connection failed. Retry the connection before signing in.')).toBeVisible();
  await page.screenshot({path:path.join(shots,'audit-configuration-error.png'),fullPage:true});
  await page.unroute('**/api/config');
  // Restore the simulated configuration transport; backend journeys are tested separately above.
  await page.route('**/api/config', route => route.fulfill({json:{mode:'DEMO',provider:'openai',model:'fixture',live_ready:false,missing:['OPENAI_API_KEY']}}));
  await page.route('**/api/me', route => route.fulfill({status:401,json:{detail:'Sign in'}}));
  await page.getByRole('button',{name:'Retry connection'}).click();
  await expect(page.getByLabel('Workspace role')).toBeVisible();
  await expect(page.getByRole('button',{name:'Enter workspace'})).toBeEnabled();
});

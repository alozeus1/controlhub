// Playwright E2E skeleton for auth flows.
// Requires app stack running and PLAYWRIGHT_BASE_URL set.
import { test, expect } from '@playwright/test';

const base = process.env.PLAYWRIGHT_BASE_URL || 'http://localhost:3001';

test('local login success (skeleton)', async ({ page }) => {
  await page.goto(`${base}/ui/login`);
  await expect(page.locator('text=Sign In')).toBeVisible();
});

test('local login lockout (skeleton)', async ({ page }) => {
  await page.goto(`${base}/ui/login`);
});

test('password reset flow (skeleton)', async ({ page }) => {
  await page.goto(`${base}/ui/forgot-password`);
});

test('cognito callback flow (skeleton)', async ({ page }) => {
  await page.goto(`${base}/ui/auth/callback#id_token=mock`);
});

test('protected route + logout flow (skeleton)', async ({ page }) => {
  await page.goto(`${base}/ui/dashboard`);
});

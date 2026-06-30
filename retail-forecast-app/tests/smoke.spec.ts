import { test, expect } from '@playwright/test';

test('risk dashboard loads', async ({ page }) => {
  await page.goto('/risk');
  await expect(page.getByText('Demand Risk Dashboard')).toBeVisible({ timeout: 30000 });
  await expect(page.getByText('Stockout Risk')).toBeVisible();
  await expect(page.getByText('Overstock Risk')).toBeVisible();
});

test('genie page loads', async ({ page }) => {
  await page.goto('/genie');
  // Genie panel renders a chat input
  await expect(page.getByRole('textbox')).toBeVisible({ timeout: 30000 });
});

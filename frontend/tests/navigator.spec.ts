import { expect, test } from '@playwright/test';
import { readFile } from 'node:fs/promises';

test('changing household context changes auditable pathways and prepares a real checklist', async ({ page }) => {
  const browserErrors: string[] = [];
  page.on('pageerror', error => browserErrors.push(error.message));
  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'Find support in Singapore', exact: true })).toBeVisible();
  await page.locator('.persona-card').filter({ hasText: 'Individuals & Families' }).click();
  const update = page.getByRole('button', { name: 'Update context' });
  await expect(update).toBeEnabled();
  const bridge = page.locator('.scheme-card').filter({ hasText: 'Household Bridge Grant' });
  const caregiver = page.locator('.scheme-card').filter({ hasText: 'Caregiver Relief' });
  await expect(bridge.locator('.status-badge')).toHaveText('Likely eligible');
  await expect(caregiver.locator('.status-badge')).toHaveText('Not eligible');

  // Pending edits must be explicit; applying them changes the income rule.
  await page.getByRole('spinbutton', { name: 'Monthly household income' }).fill('5400');
  await expect(page.getByRole('status')).toContainText('Your context has changed');
  await expect(bridge.locator('.status-badge')).toHaveText('Likely eligible');
  await update.click();
  await expect(bridge.locator('.status-badge')).toHaveText('Not eligible');
  await expect(page.getByRole('status')).toHaveCount(0);

  await page.getByRole('switch', { name: 'Caregiving responsibility' }).check();
  await update.click();
  await expect(caregiver.locator('.status-badge')).toHaveText('Likely eligible');
  await page.getByRole('button', { name: 'Compare changes' }).click();
  await expect(page.locator('.comparison-heading')).toContainText('2 pathways changed');

  // The failed rule and its cited synthetic source must be inspectable.
  await bridge.getByRole('button', { name: 'View reasoning' }).click();
  const modal = page.getByRole('dialog');
  await expect(modal.getByRole('heading', { name: 'Rules and evidence' })).toBeVisible();
  await expect(modal.locator('.rule-row').filter({ hasText: 'Income per person' })).toContainText('1350');
  await modal.getByRole('button', { name: 'Show evidence for Income per person ≤ S$1,000' }).click();
  await expect(page.getByRole('heading', { name: 'Household Bridge Grant · fictional rules' })).toBeVisible();
  await page.getByRole('button', { name: 'Close evidence' }).click();
  await page.getByRole('button', { name: 'Close entity details' }).click();

  await page.getByRole('checkbox', { name: 'Income not yet known' }).check();
  await update.click();
  await expect(bridge.locator('.status-badge')).toHaveText('Needs review');
  await expect(caregiver.locator('.status-badge')).toHaveText('Needs review');
  const downloaded = page.waitForEvent('download');
  await page.getByRole('button', { name: 'Prepare checklist' }).click();
  const download = await downloaded;
  expect(download.suggestedFilename()).toBe('illustrative-support-checklist.txt');
  const file = await download.path();
  expect(file).toBeTruthy();
  const checklist = await readFile(file!, 'utf8');
  expect(checklist).toContain('Household Bridge Grant');
  expect(checklist).toContain('Income statement');
  expect(checklist).toContain('Synthetic data');
  expect(checklist).toContain('Needs review');

  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.getByRole('heading', { name: 'Household context', exact: true })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth)).toBe(false);
  expect(browserErrors).toEqual([]);
});

test('configuration without local preview shows the Cognito login before requesting citizen data', async ({ page }) => {
  const dataRequests: string[] = [];
  page.on('request', request => { if (request.url().includes('/api/')) dataRequests.push(request.url()); });
  await page.route('**/config.json', route => route.fulfill({ contentType: 'application/json', body: JSON.stringify({ apiUrl: '', region: 'us-east-1', localPreview: false, cognito: { authority: '', clientId: '', domain: '' } }) }));
  await page.goto('/');
  await expect(page.getByRole('button', { name: 'Sign in to explore' })).toBeVisible();
  await expect(page.getByText('Secure sign-in with Amazon Cognito')).toBeVisible();
  await expect(page.getByText('Cognito is not configured.', { exact: false })).toBeVisible();
  expect(dataRequests).toEqual([]);
});

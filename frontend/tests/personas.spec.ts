import { expect, test } from '@playwright/test';
import type { Scenario, Analysis } from '../src/types';

test('all four audiences open their own context, schemes, graph and evidence', async ({ page, request }) => {
  const errors: string[] = [];
  page.on('pageerror', error => errors.push(error.message));
  const catalogue = await (await request.get('/api/scenario')).json() as Scenario;
  await page.goto('/');
  await expect(page.locator('.persona-card')).toHaveCount(4);
  const previousNames: string[] = [];
  for (const persona of catalogue.personas) {
    const scenario = await (await request.get(`/api/scenario?persona=${persona.id}`)).json() as Scenario;
    const response = await request.post('/api/analyze', { data: { persona: persona.id, profile: scenario.profile, question: persona.prompts[0] } });
    expect(response.ok()).toBeTruthy();
    const expected = await response.json() as Analysis;
    await page.locator('.persona-card').filter({ hasText: persona.name }).click();
    await expect(page.getByRole('heading', { name: persona.contextTitle, exact: true })).toBeVisible();
    await expect(page.locator('.scheme-card')).toHaveCount(expected.schemes.length);
    for (const scheme of expected.schemes) {
      const card = page.locator('.scheme-card').filter({ hasText: scheme.name });
      await expect(card).toBeVisible();
      await expect(card.locator('.status-badge')).toHaveText({ 'likely-eligible': 'Likely eligible', 'not-eligible': 'Not eligible', 'needs-review': 'Needs review' }[scheme.status]);
    }
    for (const oldName of previousNames) await expect(page.locator('.scheme-card').filter({ hasText: oldName })).toHaveCount(0);
    const root = scenario.nodes.find(node => ['resident', 'organisation', 'organization', 'researcher', 'institution'].includes(node.type));
    expect(root).toBeTruthy();
    await expect(page.getByRole('button', { name: `${root!.type}: ${root!.label}`, exact: true })).toBeVisible();
    const goal = scenario.nodes.find(node => ['goal', 'need', 'event'].includes(node.type));
    expect(goal).toBeTruthy();
    await expect(page.getByRole('button', { name: `${goal!.type}: ${goal!.label}`, exact: true })).toBeVisible();
    expect(await page.locator('.graph-edge').count()).toBeGreaterThan(0);
    const firstCard = page.locator('.scheme-card').filter({ hasText: expected.schemes[0].name });
    await firstCard.getByRole('button', { name: 'View reasoning' }).click();
    await expect(page.getByRole('dialog').last().locator('.rule-row')).toHaveCount(expected.schemes[0].ruleResults.length);
    await page.getByRole('button', { name: 'Close entity details' }).click();
    previousNames.push(...expected.schemes.map(scheme => scheme.name));
    await page.getByRole('button', { name: 'All audiences', exact: true }).click();
    await expect(page.getByRole('heading', { name: 'Find Government Support', exact: true })).toBeVisible();
  }
  expect(errors).toEqual([]);
});

test('support filters narrow discovery and missing organisation facts require review', async ({ page, request }) => {
  const scenario = await (await request.get('/api/scenario?persona=businesses')).json() as Scenario;
  const baseline = await (await request.post('/api/analyze', { data: { persona: 'businesses', profile: scenario.profile } })).json() as Analysis;
  await page.goto('/');
  await page.locator('.persona-card').filter({ hasText: scenario.persona.name }).click();
  await expect(page.locator('.scheme-card')).toHaveCount(baseline.schemes.length);
  const category = scenario.persona.supportCategories.find(category => {
    const count = baseline.schemes.filter(scheme => scheme.categories.includes(category.id)).length;
    return count > 0 && count < baseline.schemes.length;
  });
  expect(category).toBeTruthy();
  const expected = baseline.schemes.filter(scheme => scheme.categories.includes(category!.id));
  await page.getByRole('region', { name: 'Support type filters' }).getByRole('button', { name: category!.label, exact: true }).click();
  await expect(page.locator('.scheme-card')).toHaveCount(expected.length);
  for (const scheme of baseline.schemes.filter(scheme => !scheme.categories.includes(category!.id))) {
    await expect(page.locator('.scheme-card').filter({ hasText: scheme.name })).toHaveCount(0);
    await expect(page.getByRole('button', { name: `scheme: ${scheme.name}`, exact: true })).toHaveCount(0);
  }
  await page.getByRole('region', { name: 'Support type filters' }).getByRole('button', { name: 'All support', exact: true }).click();
  await expect(page.locator('.scheme-card')).toHaveCount(baseline.schemes.length);
  const missing = scenario.presets.find(preset => /missing|unknown/i.test(preset.label));
  expect(missing).toBeTruthy();
  await page.getByRole('button', { name: missing!.label, exact: true }).click();
  const unknown = await (await request.post('/api/analyze', { data: { persona: 'businesses', profile: missing!.profile } })).json() as Analysis;
  expect(unknown.schemes.some(scheme => scheme.status === 'needs-review')).toBeTruthy();
  for (const scheme of unknown.schemes.filter(scheme => scheme.status === 'needs-review')) {
    await expect(page.locator('.scheme-card').filter({ hasText: scheme.name }).locator('.status-badge')).toHaveText('Needs review');
  }
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.getByRole('heading', { name: scenario.persona.contextTitle, exact: true })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth)).toBe(false);
  await page.getByRole('button', { name: 'All audiences', exact: true }).click();
  await expect(page.locator('.persona-card')).toHaveCount(4);
  expect(await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth)).toBe(false);
});

test('a late response from the previous audience cannot replace the new workspace', async ({ page }) => {
  let releasePrevious!: () => void;
  let capturedPrevious!: () => void;
  const held = new Promise<void>(resolve => { releasePrevious = resolve; });
  const captured = new Promise<void>(resolve => { capturedPrevious = resolve; });
  await page.route('**/api/analyze', async route => {
    if (route.request().postDataJSON().persona === 'businesses') {
      const response = await route.fetch();
      capturedPrevious();
      await held;
      await route.fulfill({ response });
    } else await route.continue();
  });
  await page.goto('/');
  await page.locator('.persona-card').filter({ hasText: 'Businesses & Entrepreneurs' }).click();
  await captured;
  await page.getByRole('button', { name: 'All audiences', exact: true }).click();
  await page.locator('.persona-card').filter({ hasText: 'Researchers & Educational Institutions' }).click();
  await expect(page.getByRole('heading', { name: 'Research & institution context', exact: true })).toBeVisible();
  await expect(page.locator('.scheme-card').filter({ hasText: 'Discovery Catalyst Fund' })).toBeVisible();
  const completed = page.waitForResponse(response => response.url().endsWith('/api/analyze') && response.request().postDataJSON().persona === 'businesses');
  releasePrevious();
  await completed;
  await expect(page.locator('.scheme-card').filter({ hasText: 'Digital Spark Grant' })).toHaveCount(0);
  await expect(page.getByRole('heading', { name: 'Research & institution context', exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Update context', exact: false })).toBeEnabled();
});

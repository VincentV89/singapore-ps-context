import { expect, test, type Page, type Request, type Route } from '@playwright/test';
import { readFileSync } from 'node:fs';
import type { AppConfig, OfficialCatalogue, OfficialScheme, PersonaId } from '../src/types';

// These tests exercise the browser integration with explicit mock authentication
// and mock platform responses. They do not verify Cognito or any live AWS service.
// The public catalogue is the captured agency data used by the deployment.
const catalogue = JSON.parse(readFileSync(new URL('../../data/official/catalogue.json', import.meta.url), 'utf8')) as OfficialCatalogue;
const fixtureIdToken = 'TEST_FIXTURE_COGNITO_ID_TOKEN';
const fixtureAccessToken = 'TEST_FIXTURE_ACCESS_TOKEN_MUST_NOT_AUTHORIZE_PLATFORM';
const config: AppConfig = {
  apiUrl: 'https://context-platform.test', region: 'us-east-1', localPreview: false,
  cognito: { authority: 'https://cognito-idp.us-east-1.amazonaws.com/us-east-1_TESTFIXTURE', clientId: 'test-fixture-client', domain: 'https://test-fixture.auth.us-east-1.amazoncognito.com', scope: 'openid profile email' },
  platform: { mode: 'full', namespaceId: 'test-fixture-namespace', apiUrl: 'https://context-platform.test', region: 'us-east-1', catalogueUrl: '/official/catalogue.json', serveRuntimeArn: 'arn:aws:bedrock-agentcore:us-east-1:123456789012:runtime/test_fixture' },
};
const runtimePattern = /^https:\/\/bedrock-agentcore\.us-east-1\.amazonaws\.com\/runtimes\/.*\/invocations\?qualifier=DEFAULT$/;
const queryPattern = /^https:\/\/context-platform\.test\/namespaces\/test-fixture-namespace\/query$/;
const audienceNames: Record<PersonaId, string> = {
  individuals: 'Individuals & Families', businesses: 'Businesses & Entrepreneurs', community: 'Nonprofits & Community Organisations', research: 'Researchers & Educational Institutions',
};
const contextHeadings: Record<PersonaId, string> = {
  individuals: 'Household context', businesses: 'Business & project context', community: 'Community & project context', research: 'Research & institution context',
};
const corsHeaders = { 'access-control-allow-origin': 'http://localhost:5173', 'access-control-allow-headers': '*', 'access-control-allow-methods': 'POST, OPTIONS' };
type CapturedCall = { url: string; authorization: string | undefined; body: Record<string, unknown> };

function firstScheme(persona: PersonaId) { return catalogue.schemes.find(scheme => scheme.persona === persona)!; }
function personaFromQuery(query: unknown): PersonaId {
  const found = (Object.keys(audienceNames) as PersonaId[]).find(persona => String(query).includes(`Audience: ${audienceNames[persona]}.`));
  if (!found) throw new Error('Test received a platform query without a supported audience.');
  return found;
}
function mockResult(scheme: OfficialScheme) {
  const schemeUri = `https://test-fixture.example/graph/schemes/${scheme.id}`;
  const agencyUri = `https://test-fixture.example/graph/agencies/${scheme.agency.id}`;
  return {
    tier: 3, confidence: { score: 0.81, rationale: 'Explicit mock source evidence' }, partial: false,
    synthesizedAnswer: `TEST FIXTURE RESPONSE: Explore ${scheme.name} and verify the current criteria with ${scheme.agency.name}. [fixture-${scheme.id}-chunk]`,
    supportingContent: [{ chunkId: `fixture-${scheme.id}-chunk`, text: `TEST FIXTURE RETRIEVED PASSAGE for ${scheme.name}. Agency assessment is required.`, sourceDoc: `s3://test-fixture-bucket/documents/${scheme.id}.md` }],
    graphContext: {
      entities: [
        { uri: schemeUri, label: scheme.name, type: 'https://test-fixture.example/SupportScheme', properties: { schemeId: scheme.id, description: 'TEST FIXTURE entity returned by the mock platform.' } },
        { uri: agencyUri, label: scheme.agency.name, type: 'https://test-fixture.example/Agency', properties: {} },
      ],
      relationships: [{ sourceUri: schemeUri, predicateUri: 'https://test-fixture.example/administeredBy', targetUri: agencyUri, predicateLabel: 'administered by' }],
    },
    trace: [{ step: 't3_graph_traverse', status: 'success', durationMs: 23, detail: `TEST FIXTURE graph returned ${scheme.id}`, toolUsed: 'neptune' }],
  };
}
function sseBody(scheme: OfficialScheme) {
  const requestId = `fixture-request-${scheme.id}`;
  return [
    { type: 'step', requestId, timestamp: '2026-10-08T06:30:00Z', payload: { stepName: 't3_graph_traverse', status: 'success', durationMs: 23, detail: `TEST FIXTURE graph returned ${scheme.id}`, toolUsed: 'neptune' } },
    { type: 'done', requestId, timestamp: '2026-10-08T06:30:01Z', payload: { result: mockResult(scheme) } },
  ].map(event => `data: ${JSON.stringify(event)}\r\n\r\n`).join('');
}
async function baseRoutes(page: Page, authenticated = true) {
  await page.route('**/config.json', route => route.fulfill({ contentType: 'application/json', body: JSON.stringify(config) }));
  await page.route('**/official/catalogue.json', route => route.fulfill({ contentType: 'application/json', body: JSON.stringify(catalogue) }));
  if (authenticated) await page.addInitScript(({ authority, clientId, idToken, accessToken }) => {
    // oidc-client-ts serialized User fixture: deliberately distinct token types.
    // No real credentials, token verification or login is performed by this test.
    sessionStorage.setItem(`oidc.user:${authority}:${clientId}`, JSON.stringify({
      id_token: idToken, access_token: accessToken, token_type: 'Bearer', scope: 'openid profile email', expires_at: Math.floor(Date.now() / 1000) + 3600,
      profile: { sub: '00000000-0000-4000-8000-000000000000', email: 'demo-admin@example.test' },
    }));
  }, { authority: config.cognito.authority, clientId: config.cognito.clientId, idToken: fixtureIdToken, accessToken: fixtureAccessToken });
}
async function capture(route: Route, calls: CapturedCall[]) {
  if (route.request().method() === 'OPTIONS') { await route.fulfill({ status: 204, headers: corsHeaders }); return undefined; }
  const body = route.request().postDataJSON() as Record<string, unknown>;
  calls.push({ url: route.request().url(), authorization: route.request().headers().authorization, body });
  return body;
}
async function successfulRoutes(page: Page, calls: CapturedCall[]) {
  await page.route(runtimePattern, async route => {
    const body = await capture(route, calls); if (!body) return;
    await route.fulfill({ contentType: 'text/event-stream', headers: corsHeaders, body: sseBody(firstScheme(personaFromQuery(body.query))) });
  });
  await page.route(queryPattern, async route => {
    const body = await capture(route, calls); if (!body) return;
    const scheme = firstScheme(personaFromQuery(body.query));
    await route.fulfill({ contentType: 'application/json', headers: corsHeaders, body: JSON.stringify({ result: mockResult(scheme), requestId: `fixture-rest-${scheme.id}` }) });
  });
}

test('full mode shows all four official catalogues, actual response graph and trace, with agency assessment', async ({ page }) => {
  const calls: CapturedCall[] = [], browserErrors: string[] = [];
  page.on('pageerror', error => browserErrors.push(error.message));
  await baseRoutes(page); await successfulRoutes(page, calls);
  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'Find support in Singapore', exact: true })).toBeVisible();
  await expect(page.locator('.persona-card')).toHaveCount(4);
  for (const persona of Object.keys(audienceNames) as PersonaId[]) {
    const schemes = catalogue.schemes.filter(scheme => scheme.persona === persona);
    const first = schemes[0];
    await page.locator('.persona-card').filter({ hasText: audienceNames[persona] }).click();
    await expect(page.getByRole('heading', { name: contextHeadings[persona], exact: true })).toBeVisible();
    await expect(page.locator('.scheme-card')).toHaveCount(schemes.length);
    for (const scheme of schemes) {
      const card = page.locator('.scheme-card').filter({ hasText: scheme.name });
      await expect(card.locator('.scheme-agency')).toHaveText(scheme.agency.name);
      await expect(card.locator('.status-badge')).toHaveText('Agency assessment required');
      await expect(card.locator('.rule-progress')).toHaveText('Official agency source');
    }
    await expect(page.getByText('0/0 rules met', { exact: false })).toHaveCount(0);
    await expect(page.locator('.answer-content')).toContainText(`TEST FIXTURE RESPONSE: Explore ${first.name}`);
    await page.locator('.scheme-card').filter({ hasText: first.name }).getByRole('button', { name: 'View source & criteria' }).click();
    const policy = page.getByRole('dialog');
    await expect(policy.getByRole('heading', { name: 'Published criteria' })).toBeVisible();
    const criteria = policy.locator('.detail-section').filter({ has: page.getByRole('heading', { name: 'Published criteria', exact: true }) }).locator('blockquote');
    if (first.eligibilityText) await expect(criteria).toHaveText(first.eligibilityText);
    else await expect(criteria).toHaveText('Full applicant criteria were not included in the captured overview. Consult the agency source and current application call.');
    if (first.lifecycleText) {
      const updates = policy.locator('.detail-section').filter({ has: page.getByRole('heading', { name: 'Programme updates', exact: true }) });
      await expect(updates.locator('blockquote')).toHaveText(first.lifecycleText);
    }
    await expect(policy.getByRole('link', { name: 'Official source', exact: true })).toHaveAttribute('href', new URL(first.sourceUrl).href);
    await expect(policy.getByRole('link', { name: 'Official source', exact: true })).toHaveAttribute('target', '_blank');
    await expect(policy.getByText('Agency assessment required.', { exact: false })).toBeVisible();
    await page.getByRole('button', { name: 'Close programme details' }).click();

    await page.getByRole('button', { name: `scheme: ${first.name}`, exact: true }).click();
    await expect(page.getByRole('dialog').getByText(`Entity ID: https://test-fixture.example/graph/schemes/${first.id}`, { exact: true })).toBeVisible();
    await page.getByRole('button', { name: 'Close entity details' }).click();
    await expect(page.locator('.graph-edge')).toHaveCount(1);
    await page.getByText('Trace the reasoning', { exact: true }).click();
    await expect(page.locator('.reasoning-details')).toContainText(`TEST FIXTURE graph returned ${first.id}`);
    await expect(page.locator('.reasoning-details')).toContainText('23 ms');
    await page.locator('.citation-chips').getByRole('button').first().click();
    const evidence = page.getByRole('dialog');
    await expect(evidence.locator('blockquote')).toHaveText(`TEST FIXTURE RETRIEVED PASSAGE for ${first.name}. Agency assessment is required.`);
    await expect(evidence.getByRole('link', { name: 'Open official source' })).toHaveAttribute('href', new URL(first.sourceUrl).href);
    await page.getByRole('button', { name: 'Close evidence' }).click();
    await page.getByRole('button', { name: 'All audiences', exact: true }).click();
  }
  expect(calls).toHaveLength(4);
  for (const call of calls) {
    expect(call.authorization).toBe(`Bearer ${fixtureIdToken}`);
    expect(call.authorization).not.toContain(fixtureAccessToken);
    expect(call.url).toBe(`${config.platform!.apiUrl}/namespaces/${config.platform!.namespaceId}/query`);
    expect(call.body.mode).toBe('standard');
    expect(call.body.tierOverride).toBe(3);
    expect(call.body.maxResults).toBe(8);
    expect(call.body.timeoutMs).toBe(26000);
    expect(call.body.includeSupporting).toBe(true);
    expect(call.body.options).toBeUndefined();
  }
  expect(browserErrors).toEqual([]);
});

test('editing hypothetical facts changes the platform query and standard mode uses flat REST fields', async ({ page }) => {
  const calls: CapturedCall[] = [];
  await baseRoutes(page); await successfulRoutes(page, calls);
  await page.goto('/');
  await page.locator('.persona-card').filter({ hasText: audienceNames.individuals }).click();
  await expect(page.getByRole('button', { name: 'Update context', exact: false })).toBeEnabled();
  expect(calls[0].body.query).toContain('Monthly household income (S$): 3600');
  await page.getByRole('spinbutton', { name: 'Monthly household income (S$)', exact: true }).fill('9000');
  await expect(page.getByRole('status')).toContainText('Your context has changed');
  await page.getByRole('checkbox', { name: 'Deep context reasoning', exact: true }).uncheck();
  await page.getByRole('button', { name: 'Update context', exact: false }).click();
  await expect(page.getByRole('button', { name: 'Update context', exact: false })).toBeEnabled();
  expect(calls).toHaveLength(2);
  const second = calls[1];
  expect(second.url).toBe(`${config.platform!.apiUrl}/namespaces/${config.platform!.namespaceId}/query`);
  expect(second.authorization).toBe(`Bearer ${fixtureIdToken}`);
  expect(second.body.query).toContain('Monthly household income (S$): 9000');
  expect(second.body.mode).toBe('standard'); expect(second.body.tierOverride).toBe(3); expect(second.body.includeSupporting).toBe(true);
  expect(second.body.options).toBeUndefined();
  await expect(page.locator('.scheme-card .status-badge').first()).toHaveText('Agency assessment required');
  await expect(page.getByRole('status')).toHaveCount(0);
});

test('opaque synthesis document IDs resolve through authenticated KBSearch metadata without replacing the cited passage', async ({ page }) => {
  const calls: CapturedCall[] = [], first = firstScheme('individuals');
  const originalPassage = 'TEST FIXTURE ORIGINAL SYNTHESIS PASSAGE retained after provenance lookup.';
  await baseRoutes(page);
  await page.route(queryPattern, async route => {
    if (!await capture(route, calls)) return;
    const result = mockResult(first);
    result.supportingContent = [{ chunkId: `fixture-${first.id}-chunk`, text: originalPassage, sourceDoc: 'opaque-platform-document-id' }];
    await route.fulfill({ contentType: 'application/json', headers: corsHeaders, body: JSON.stringify({ requestId: 'opaque-provenance-fixture', result }) });
  });
  await page.route('https://context-platform.test/namespaces/test-fixture-namespace/kb/search', async route => {
    if (!await capture(route, calls)) return;
    await route.fulfill({ contentType: 'application/json', headers: corsHeaders, body: JSON.stringify({ chunks: [
      { chunkId: 'other-chunk-from-same-document', sourceDocumentId: 'opaque-platform-document-id', sourceDocumentName: `${first.id}.md`, text: 'TEST FIXTURE different KB passage must not overwrite the original citation.' },
      { chunkId: 'unrelated-chunk', sourceDocumentId: 'different-document-id', sourceDocumentName: 'chas.md', text: 'TEST FIXTURE unrelated source.' },
    ] }) });
  });
  await page.goto('/');
  await page.locator('.persona-card').filter({ hasText: audienceNames.individuals }).click();
  await expect(page.getByRole('button', { name: 'Update context', exact: false })).toBeEnabled();
  await page.locator('.citation-chips').getByRole('button').first().click();
  const evidence = page.getByRole('dialog');
  await expect(evidence.locator('blockquote')).toHaveText(originalPassage);
  await expect(evidence.getByRole('heading', { name: first.sourceTitle, exact: true })).toBeVisible();
  await expect(evidence.getByRole('link', { name: 'Open official source' })).toHaveAttribute('href', new URL(first.sourceUrl).href);
  expect(calls).toHaveLength(2);
  expect(calls[1].url).toBe(`${config.platform!.apiUrl}/namespaces/${config.platform!.namespaceId}/kb/search`);
  expect(calls[1].authorization).toBe(`Bearer ${fixtureIdToken}`);
  expect(calls[1].body.topK).toBe(100);
  expect(calls[1].body.query).toContain('Audience: Individuals & Families.');
});

test('a namespace 403 shows the actual failure without a fabricated platform answer or graph', async ({ page }) => {
  const calls: CapturedCall[] = [];
  await baseRoutes(page);
  await page.route(queryPattern, async route => {
    if (!await capture(route, calls)) return;
    await route.fulfill({ status: 403, contentType: 'application/json', headers: corsHeaders, body: JSON.stringify({ message: 'TEST FIXTURE namespace access denied' }) });
  });
  await page.goto('/');
  await page.locator('.persona-card').filter({ hasText: audienceNames.businesses }).click();
  await expect(page.getByRole('alert')).toContainText('Your account does not have access to this context namespace.');
  await expect(page.locator('.answer-content')).toHaveCount(0);
  await expect(page.locator('.graph-node')).toHaveCount(0);
  await expect(page.locator('.scheme-card')).toHaveCount(0);
  expect(calls).toHaveLength(1); expect(calls[0].authorization).toBe(`Bearer ${fixtureIdToken}`);
});

test('switching audiences cancels the old platform request and prevents a late result replacing the new graph', async ({ page }) => {
  const calls: CapturedCall[] = [];
  let capturedPrevious!: () => void, releasePrevious!: () => void;
  const captured = new Promise<void>(resolve => { capturedPrevious = resolve; });
  const held = new Promise<void>(resolve => { releasePrevious = resolve; });
  await baseRoutes(page);
  await page.route(queryPattern, async route => {
    const body = await capture(route, calls); if (!body) return;
    const persona = personaFromQuery(body.query);
    if (persona === 'businesses') { capturedPrevious(); await held; }
    // The first request has already been aborted by the browser after switching.
    await route.fulfill({ contentType: 'application/json', headers: corsHeaders, body: JSON.stringify({ result: mockResult(firstScheme(persona)) }) }).catch(() => undefined);
  });
  await page.goto('/');
  await page.locator('.persona-card').filter({ hasText: audienceNames.businesses }).click();
  await captured;
  const cancellation = page.waitForEvent('requestfailed', { predicate: (request: Request) => queryPattern.test(request.url()) && String(request.postDataJSON().query).includes(`Audience: ${audienceNames.businesses}.`), timeout: 10000 });
  await page.getByRole('button', { name: 'All audiences', exact: true }).click();
  const cancelled = await cancellation;
  expect(cancelled.failure()?.errorText).toContain('ERR_ABORTED');
  await page.locator('.persona-card').filter({ hasText: audienceNames.research }).click();
  await expect(page.getByRole('heading', { name: contextHeadings.research, exact: true })).toBeVisible();
  await expect(page.locator('.answer-content')).toContainText(firstScheme('research').name);
  releasePrevious();
  await expect(page.locator('.scheme-card').filter({ hasText: firstScheme('businesses').name })).toHaveCount(0);
  await expect(page.getByRole('button', { name: `scheme: ${firstScheme('businesses').name}`, exact: true })).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Update context', exact: false })).toBeEnabled();
});

test('full mode requires a Cognito session before loading any official catalogue or platform context', async ({ page }) => {
  const protectedRequests: string[] = [];
  page.on('request', request => { if (runtimePattern.test(request.url()) || queryPattern.test(request.url()) || request.url().includes('/official/catalogue.json')) protectedRequests.push(request.url()); });
  await baseRoutes(page, false);
  await page.goto('/');
  await expect(page.getByRole('button', { name: 'Sign in to explore' })).toBeVisible();
  await expect(page.getByText('Secure sign-in with Amazon Cognito')).toBeVisible();
  expect(protectedRequests).toEqual([]);
});


test('explicit deep reasoning sends the ID token and actual AgentCore SSE contract after standard context loads', async ({ page }) => {
  const calls: CapturedCall[] = [];
  await baseRoutes(page); await successfulRoutes(page, calls);
  await page.goto('/');
  await page.locator('.persona-card').filter({ hasText: audienceNames.individuals }).click();
  await expect(page.getByRole('button', { name: 'Update context', exact: false })).toBeEnabled();
  await expect(page.getByRole('checkbox', { name: 'Deep context reasoning', exact: true })).not.toBeChecked();
  await page.getByRole('checkbox', { name: 'Deep context reasoning', exact: true }).check();
  await page.getByRole('textbox', { name: 'Ask a question about this context', exact: true }).fill('TEST FIXTURE follow-up about agency requirements.');
  await page.getByRole('button', { name: 'Send question', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Update context', exact: false })).toBeEnabled();
  expect(calls).toHaveLength(2);
  const deep = calls[1];
  expect(runtimePattern.test(deep.url)).toBe(true);
  expect(deep.authorization).toBe(`Bearer ${fixtureIdToken}`);
  expect(deep.body.namespace).toBe(config.platform!.namespaceId);
  expect(deep.body.options).toMatchObject({ mode: 'deep-reasoning', includeSupporting: true });
  expect(deep.body.stream).toBe(true);
  expect(deep.body.query).toContain('TEST FIXTURE follow-up about agency requirements.');
  await page.getByText('Trace the reasoning', { exact: true }).click();
  await expect(page.locator('.reasoning-details')).toContainText('TEST FIXTURE graph returned');
});

test('schema fallback uses nonblank match-all search and preserves real neighboring classes and property endpoints', async ({ page }) => {
  const calls: CapturedCall[] = [], first = firstScheme('individuals');
  const classUri = 'https://test-fixture.example/ontology/Schemes';
  const propertyUri = 'https://test-fixture.example/ontology/schemes_agencyId';
  const referenceUri = 'https://test-fixture.example/ontology/Agency';
  await baseRoutes(page);
  await page.route('**/config.json', route => route.fulfill({ contentType: 'application/json', body: JSON.stringify({ ...config, platform: { ...config.platform!, ontologyId: 'https://test-fixture.example/ontology/' } }) }));
  await page.route(queryPattern, async route => {
    if (!await capture(route, calls)) return;
    const result = mockResult(first); result.graphContext.relationships = [];
    await route.fulfill({ contentType: 'application/json', headers: corsHeaders, body: JSON.stringify({ result }) });
  });
  await page.route('https://context-platform.test/namespaces/test-fixture-namespace/graph/search?**', async route => {
    const url = new URL(route.request().url());
    expect(route.request().headers().authorization).toBe(`Bearer ${fixtureIdToken}`);
    expect(url.searchParams.get('q')).toBe('*');
    expect(url.searchParams.get('ontology_id')).toBe('https://test-fixture.example/ontology/');
    await route.fulfill({ contentType: 'application/json', headers: corsHeaders, body: JSON.stringify({ hits: [{ uri: classUri, label: 'schemes', kind: 'class' }], total_count: 1 }) });
  });
  await page.route('https://context-platform.test/namespaces/test-fixture-namespace/graph/class?**', async route => {
    expect(route.request().headers().authorization).toBe(`Bearer ${fixtureIdToken}`);
    expect(new URL(route.request().url()).searchParams.get('uri')).toBe(classUri);
    await route.fulfill({ contentType: 'application/json', headers: corsHeaders, body: JSON.stringify({
      uri: classUri, kind: 'class', labels: ['schemes'], comments: ['TEST FIXTURE actual-shaped schema vertex.'],
      edges: [
        { direction: 'incoming', predicate: 'http://www.w3.org/2000/01/rdf-schema#domain', predicate_label: 'domain', neighbor: { uri: propertyUri, label: 'agency_id', kind: 'object-property' } },
        { direction: 'outgoing', predicate: 'http://www.w3.org/2000/01/rdf-schema#subClassOf', predicate_label: 'subclass of', neighbor: { uri: referenceUri, label: 'Agency', kind: 'class' } },
        { direction: 'outgoing', predicate: 'http://www.w3.org/2000/01/rdf-schema#label', neighbor: { uri: 'literal:schemes', label: 'schemes', kind: 'literal' } },
      ],
    }) });
  });
  await page.goto('/');
  await page.locator('.persona-card').filter({ hasText: audienceNames.individuals }).click();
  await expect(page.getByRole('button', { name: 'Update context', exact: false })).toBeEnabled();
  await expect(page.getByText('Live Neptune ontology schema. Applicant context remains hypothetical.', { exact: true })).toBeVisible();
  await expect(page.locator('.graph-node')).toHaveCount(3);
  await expect(page.locator('.graph-edge')).toHaveCount(2);
  await page.getByRole('button', { name: 'agency: agency_id', exact: true }).click();
  await expect(page.getByRole('dialog').getByText(`Entity ID: ${propertyUri}`, { exact: true })).toBeVisible();
  await expect(page.getByRole('dialog').getByRole('heading', { name: 'Connected relationships' })).toBeVisible();
  await expect(page.getByRole('dialog').locator('.relationship-row')).toContainText('domain');
  await expect(page.getByRole('dialog').locator('.relationship-row')).toContainText('schemes');
});

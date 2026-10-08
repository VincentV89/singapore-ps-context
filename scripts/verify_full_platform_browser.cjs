#!/usr/bin/env node
/* Live browser verification for the published Singapore full-platform demo.
 *
 * Requires the actual Cognito administrator password in an ignored, mode-0600
 * local file. Every HTTPS response comes from the deployed service through the
 * environment's existing TLS-validating Playwright client. No authentication,
 * platform answers, graph, source chunks or traces are mocked. The relay buffers
 * SSE responses; it verifies the real SSE protocol, not incremental paint timing.
 * No certificate bypass or trust-store changes are used. Tokens, passwords,
 * callback query strings and raw exception messages are never printed or saved.
 *
 * Run after publishing:
 *   SG_PLAYWRIGHT_MODULE=/tmp/sg-demo-browser/node_modules/playwright \
 *   PLAYWRIGHT_CHROMIUM_EXECUTABLE=/usr/bin/chromium \
 *   node scripts/verify_full_platform_browser.cjs
 */
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const ROOT = path.resolve(__dirname, '..');
let stage = 'initialization';

function argumentsFrom(argv) {
  const result = { metadata: path.join(ROOT, 'artifacts/full-platform.json'), credentials: path.join(ROOT, 'artifacts/full-platform-login.local.json'), artifacts: path.join(ROOT, 'artifacts') };
  for (let i = 0; i < argv.length; i++) {
    if (argv[i] === '--help') { result.help = true; continue; }
    const key = { '--metadata': 'metadata', '--credentials': 'credentials', '--artifacts': 'artifacts' }[argv[i]];
    if (!key || !argv[i + 1]) throw new Error('Invalid script arguments.');
    result[key] = path.resolve(argv[++i]);
  }
  const artifactsRoot = path.join(ROOT, 'artifacts');
  for (const target of [result.metadata, result.credentials, result.artifacts]) assert(target === artifactsRoot || target.startsWith(artifactsRoot + path.sep), 'Local verification files must remain in ignored artifacts/.');
  return result;
}
function publicUrl(value) {
  const url = new URL(value);
  assert.equal(url.protocol, 'https:', 'Expected an actual HTTPS service.');
  assert(!url.username && !url.password && !url.search && !url.hash, 'Service endpoints must not contain credentials or query strings.');
  return url;
}
function privateJson(filename, value) {
  fs.writeFileSync(filename, JSON.stringify(value, null, 2) + '\n', { mode: 0o600 });
  fs.chmodSync(filename, 0o600);
}
function check(condition, label) {
  try { assert(condition, label); } catch (error) { error.verificationCheck = label; throw error; }
}
function progress(label) { stage = label; console.log(`[full-platform browser] ${label}`); }
function compactGraph(raw) {
  const entities = Array.isArray(raw) ? raw : Array.isArray(raw?.entities) ? raw.entities : [];
  const relationships = Array.isArray(raw?.relationships) ? raw.relationships : entities.flatMap(entity => Array.isArray(entity.relationships) ? entity.relationships : []);
  return { entities, relationships };
}
function sseEvents(body) {
  const result = [];
  for (const block of body.split(/\r?\n\r?\n/)) {
    const data = block.split(/\r?\n/).filter(line => line.startsWith('data:')).map(line => line.slice(5).trimStart()).join('\n');
    if (!data) continue;
    try { const event = JSON.parse(data); if (event && typeof event === 'object') result.push(event); } catch { /* Keepalives are not result events. */ }
  }
  return result;
}
function safeTrace(trace) {
  return Array.isArray(trace) ? trace.map(step => ({ step: step.step, status: step.status, durationMs: step.durationMs, ...(typeof step.toolUsed === 'string' ? { toolUsed: step.toolUsed } : {}) })) : [];
}
function within(promise, timeoutMs) {
  let timer;
  return Promise.race([promise, new Promise((_, reject) => { timer = setTimeout(() => reject(new Error('Stage timeout.')), timeoutMs); })]).finally(() => clearTimeout(timer));
}

async function main(args) {
  const metadata = JSON.parse(fs.readFileSync(args.metadata, 'utf8'));
  check(metadata.publishedAt && metadata.namespaceId && metadata.serveRuntimeArn, 'Publish the full platform before running this verifier.');
  const website = publicUrl(metadata.websiteUrl);
  const api = publicUrl(metadata.apiUrl);
  const cognitoDomain = publicUrl(metadata.cognito.domain);
  const credentialsMode = fs.statSync(args.credentials).mode;
  check((credentialsMode & 0o077) === 0, 'Administrator credentials must be private (chmod 600).');
  const credentials = JSON.parse(fs.readFileSync(args.credentials, 'utf8'));
  check(credentials.username && credentials.password && credentials.userPoolId === metadata.cognito.userPoolId, 'Administrator credentials do not match the full-platform pool.');
  const playwrightModule = process.env.SG_PLAYWRIGHT_MODULE || require.resolve('playwright', { paths: [path.join(ROOT, 'frontend'), ROOT] });
  const { chromium } = require(playwrightModule);
  const executablePath = process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE || (fs.existsSync('/usr/bin/chromium') ? '/usr/bin/chromium' : undefined);
  const browser = await chromium.launch({ headless: true, ...(executablePath ? { executablePath } : {}), ...(process.env.HTTPS_PROXY ? { proxy: { server: process.env.HTTPS_PROXY } } : {}) });
  const context = await browser.newContext({ viewport: { width: 1600, height: 1050 }, ignoreHTTPSErrors: false });
  const page = await context.newPage();
  page.setDefaultTimeout(30000);
  page.setDefaultNavigationTimeout(60000);
  const report = { passed: false, checkedAt: new Date().toISOString(), website: website.origin, region: metadata.region, namespaceId: metadata.namespaceId, tlsVerification: true, trustStoreChanged: false, mockedPlatformResponses: false, sseRelayBuffered: true, personas: [], runtimeCalls: [], pageErrors: [], relayErrors: [] };
  const actualGraphUris = new Set();
  const actualPassages = new Set();
  let idToken = '', accessToken = '', callbackResolve, deepResponseResolve;
  const callbackPromise = new Promise(resolve => { callbackResolve = resolve; });
  let callbackCaptured = false;
  page.on('pageerror', error => report.pageErrors.push(error.name));
  const reportPath = path.join(args.artifacts, 'full-platform-browser.local.json');
  fs.mkdirSync(args.artifacts, { recursive: true });
  try {
    progress('validate the published full-platform configuration');
    const configResponse = await context.request.get(`${website.origin}/config.json`, { timeout: 30000 });
    check(configResponse.ok(), 'Published configuration did not load.');
    const config = await configResponse.json();
    check(config.localPreview === false && config.platform?.mode === 'full', 'The site is still serving the compact demo configuration.');
    check(config.platform.namespaceId === metadata.namespaceId && config.platform.serveRuntimeArn === metadata.serveRuntimeArn && config.platform.apiUrl === metadata.apiUrl, 'The published full-platform endpoints differ from deployment metadata.');
    check(config.cognito.authority === metadata.cognito.authority && config.cognito.clientId === metadata.cognito.clientId, 'The browser must use the full platform Cognito login.');
    const catalogueResponse = await context.request.get(new URL(config.platform.catalogueUrl, website).href, { timeout: 30000 });
    check(catalogueResponse.ok(), 'The live official catalogue did not load.');
    const catalogue = await catalogueResponse.json();
    const personas = [
      { id: 'individuals', name: 'Individuals & Families', heading: 'Household context' },
      { id: 'businesses', name: 'Businesses & Entrepreneurs', heading: 'Business & project context' },
      { id: 'community', name: 'Nonprofits & Community Organisations', heading: 'Community & project context' },
      { id: 'research', name: 'Researchers & Educational Institutions', heading: 'Research & institution context' },
    ];
    const capturedSchemes = catalogue.schemes;
    check(Array.isArray(capturedSchemes) && capturedSchemes.length === metadata.officialSchemeCount, 'The live programme count differs from the published metadata.');
    report.officialSchemeCount = capturedSchemes.length;
    report.sourceCaptureDate = catalogue.fetchedAt;
    const schemesFor = id => capturedSchemes.filter(scheme => Array.isArray(scheme.persona) ? scheme.persona.includes(id) : scheme.persona === id);

    // Route.fetch uses the existing trusted HTTPS client. Fulfill forwards each
    // actual remote response unchanged. OAuth's real callback is followed by
    // the driver because Chromium's proxy CA is not in its own certificate store.
    await context.route('https://**/*', async route => {
      const request = route.request();
      const url = new URL(request.url());
      const runtimeCall = url.hostname === `bedrock-agentcore.${metadata.region}.amazonaws.com` && url.pathname.endsWith('/invocations') && request.method() === 'POST';
      const standardCall = url.origin === api.origin && url.pathname.endsWith(`/namespaces/${metadata.namespaceId}/query`) && request.method() === 'POST';
      try {
        let response = await route.fetch({ maxRedirects: 0, timeout: runtimeCall ? 240000 : 60000 });
        if (response.status() === 302 && url.origin === cognitoDomain.origin && url.pathname === '/oauth2/authorize') {
          response = await route.fetch({ maxRedirects: 10, timeout: 60000 });
        } else if (response.status() === 302 && url.origin === cognitoDomain.origin && url.pathname === '/login' && request.method() === 'POST') {
          const location = response.headers().location;
          const redirect = location ? new URL(location, url) : undefined;
          if (redirect?.origin === website.origin && redirect.pathname === '/auth/callback' && redirect.searchParams.has('code') && redirect.searchParams.has('state')) {
            callbackCaptured = true; callbackResolve(redirect.href);
            const headers = { ...response.headers() };
            delete headers.location; delete headers['content-length']; delete headers['content-encoding'];
            // This temporary navigation page carries no authentication result.
            // The real code/state callback and PKCE token exchange run below.
            await route.fulfill({ status: 200, headers, body: 'Completing sign-in…' });
            return;
          }
        }
        if (runtimeCall || standardCall) {
          const body = request.postDataJSON();
          const responseText = await response.text();
          const events = runtimeCall ? sseEvents(responseText) : [];
          const done = events.find(event => event.type === 'done');
          const result = runtimeCall ? done?.payload?.result : JSON.parse(responseText).result;
          const graph = compactGraph(result?.graphContext);
          for (const entity of graph.entities) if (typeof entity.uri === 'string') actualGraphUris.add(entity.uri);
          for (const passage of Array.isArray(result?.supportingContent) ? result.supportingContent : []) if (typeof passage.text === 'string') actualPassages.add(passage.text.trim().replace(/\s+/g, ' '));
          const persona = personas.find(item => String(body.query).includes(`Audience: ${item.name}.`));
          const call = {
            persona: persona?.id, status: response.status(), transport: runtimeCall ? 'sse' : 'rest', mode: runtimeCall ? body.options?.mode : body.mode, namespaceMatches: runtimeCall ? body.namespace === metadata.namespaceId : standardCall,
            idTokenMatches: Boolean(idToken && request.headers().authorization === `Bearer ${idToken}`), accessTokenUsed: Boolean(accessToken && request.headers().authorization === `Bearer ${accessToken}`),
            actualSseDone: Boolean(done), sseStepEvents: events.filter(event => event.type === 'step').length, sseErrorEvents: events.filter(event => event.type === 'error').length,
            answerCharacters: typeof result?.synthesizedAnswer === 'string' ? result.synthesizedAnswer.length : 0, supportingPassages: Array.isArray(result?.supportingContent) ? result.supportingContent.length : 0,
            graphEntities: graph.entities.length, graphRelationships: graph.relationships.length, trace: safeTrace(result?.trace), tier: result?.tier,
          };
          report.runtimeCalls.push(call);
          if (runtimeCall && deepResponseResolve) { deepResponseResolve(call); deepResponseResolve = undefined; }
        } else if (url.origin === api.origin && url.pathname.endsWith('/graph/class') && response.ok()) {
          const vertex = await response.json(); if (typeof vertex.uri === 'string') actualGraphUris.add(vertex.uri);
          for (const edge of Array.isArray(vertex.edges) ? vertex.edges : []) if (typeof edge.neighbor?.uri === 'string') actualGraphUris.add(edge.neighbor.uri);
        }
        await route.fulfill({ response });
      } catch (error) {
        report.relayErrors.push({ endpointType: runtimeCall ? 'runtime' : url.origin === cognitoDomain.origin ? 'cognito' : url.origin === api.origin ? 'api' : 'static', errorType: error.name });
        await route.abort('failed').catch(() => undefined);
      }
    });
    await context.route('http://**/*', route => route.abort('blockedbyclient'));

    progress('Cognito hosted login');
    await page.goto(website.href);
    await page.getByRole('button', { name: 'Sign in to explore' }).click();
    await page.locator('input[name="username"]:visible').first().fill(credentials.username);
    await page.locator('input[name="password"]:visible').first().fill(credentials.password);
    await page.locator('input[name="signInSubmitButton"]:visible').first().click();
    const callback = await within(callbackPromise, 45000);
    check(callbackCaptured, 'Cognito did not issue a real authorization callback.');
    progress('real authorization code and PKCE callback');
    await page.goto(callback);
    await page.getByRole('heading', { name: 'Find support in Singapore', exact: true }).waitFor({ timeout: 60000 });
    const tokens = await page.evaluate(() => {
      const key = Object.keys(sessionStorage).find(item => item.startsWith('oidc.user:'));
      const user = key ? JSON.parse(sessionStorage.getItem(key)) : undefined;
      return { id: user?.id_token, access: user?.access_token };
    });
    idToken = tokens.id; accessToken = tokens.access;
    check(idToken && accessToken && idToken !== accessToken, 'The real Cognito token exchange did not produce distinct tokens.');
    report.cognitoHostedLogin = true; report.pkceCallback = true;
    check(await page.locator('.persona-card').count() === 4, 'Expected four live audience entry points.');
    await page.screenshot({ path: path.join(args.artifacts, 'full-platform-entry.png'), fullPage: true });

    for (const persona of personas) {
      progress(`live ${persona.id} audience`);
      const expected = schemesFor(persona.id);
      check(expected.length > 0, 'Each audience needs captured official sources.');
      await page.locator('.persona-card').filter({ hasText: persona.name }).click();
      await page.waitForFunction(() => Boolean(document.querySelector('.scheme-card')) || Boolean(document.querySelector('[role="alert"]')), undefined, { timeout: 240000 });
      check(await page.getByRole('alert').count() === 0, 'The live platform reported an audience query failure.');
      await page.getByRole('heading', { name: persona.heading, exact: true }).waitFor();
      await page.getByRole('button', { name: 'Update context', exact: false }).waitFor({ state: 'visible' });
      check(await page.locator('.scheme-card').count() === expected.length, 'Audience programme cards do not match the live official catalogue.');
      for (const scheme of expected) {
        const card = page.locator('.scheme-card').filter({ hasText: scheme.name });
        check((await card.locator('.scheme-agency').innerText()).trim() === scheme.agency.name, 'The programme card agency must match the official catalogue.');
        check((await card.locator('.status-badge').innerText()).trim() === 'Agency assessment required', 'The programme card must require agency assessment.');
      }
      check((await page.locator('.answer-content').innerText()).trim().length > 20, 'The live platform returned an empty answer.');
      check(await page.getByText('0/0 rules met', { exact: false }).count() === 0, 'Official cards must not claim automated screening.');
      const citations = await page.locator('.citation-chips button').count();
      check(citations > 0, 'The live answer needs actual retrieved supporting passages.');
      await page.locator('.citation-chips button').first().click();
      const evidence = page.getByRole('dialog');
      const passageText = (await evidence.locator('blockquote').innerText()).trim().replace(/\s+/g, ' ');
      check(passageText.length > 20 && actualPassages.has(passageText), 'The displayed source passage must match actual runtime supporting content.');
      const evidenceUrl = await evidence.getByRole('link', { name: 'Open official source' }).getAttribute('href');
      check(capturedSchemes.some(scheme => new URL(scheme.sourceUrl).href === evidenceUrl), 'The cited source URL must resolve through actual platform metadata to the official catalogue.');
      await page.getByRole('button', { name: 'Close evidence' }).click();
      await page.getByText('Trace the reasoning', { exact: true }).click();
      const traceSteps = await page.locator('.reasoning-details li').count();
      check(traceSteps > 0, 'The live query needs its actual execution trace.');
      const actualCall = report.runtimeCalls.findLast(call => call.persona === persona.id);
      check(actualCall && actualCall.trace.length === traceSteps, 'The displayed trace must match the actual runtime result.');
      await page.getByText('Trace the reasoning', { exact: true }).click();
      const allRelationships = page.getByRole('button', { name: 'Show all relationships', exact: true });
      if (await allRelationships.count()) await allRelationships.click();
      const graphNodes = await page.locator('.graph-node').count();
      const graphEdges = await page.locator('.graph-edge').count();
      check(graphNodes > 0 && graphEdges > 0, 'The live graph must contain actual entities and relationships.');
      await page.locator('.graph-node').first().click();
      const entityText = await page.getByRole('dialog').locator('.modal-footer').innerText();
      const entityUri = entityText.match(/Entity ID:\s*(\S+)/)?.[1];
      check(entityUri && actualGraphUris.has(entityUri), 'The rendered graph URI must have been returned by the actual platform.');
      await page.getByRole('button', { name: 'Close entity details' }).click();
      const first = expected[0];
      await page.locator('.scheme-card').filter({ hasText: first.name }).getByRole('button', { name: 'View source & criteria' }).click();
      const sourceLink = await page.getByRole('dialog').getByRole('link', { name: 'Official source', exact: true }).getAttribute('href');
      check(sourceLink === new URL(first.sourceUrl).href, 'The programme detail source must match the official agency URL.');
      await page.getByRole('button', { name: 'Close programme details' }).click();
      await page.screenshot({ path: path.join(args.artifacts, `full-platform-${persona.id}.png`), fullPage: true });
      await page.setViewportSize({ width: 390, height: 844 });
      check(!await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth), 'The mobile audience workspace overflows horizontally.');
      report.personas.push({ id: persona.id, schemes: expected.length, agencyAssessmentOnly: true, citations, officialEvidenceUrl: evidenceUrl, traceSteps, graphNodes, graphEdges, graphUriVerifiedAgainstActualResponse: true, mobileOverflow: false });
      await page.getByRole('button', { name: 'All audiences', exact: true }).click();
      await page.getByRole('heading', { name: 'Find support in Singapore', exact: true }).waitFor();
      check(!await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth), 'The mobile entry page overflows horizontally.');
      if (persona.id === 'research') await page.screenshot({ path: path.join(args.artifacts, 'full-platform-entry-mobile.png'), fullPage: true });
      await page.setViewportSize({ width: 1600, height: 1050 });
    }
    // Diagnose all standard graph/evidence journeys before the longer deep call.
    await page.locator('.persona-card').filter({ hasText: personas[0].name }).click();
    await page.waitForFunction(() => Boolean(document.querySelector('.scheme-card')) || Boolean(document.querySelector('[role="alert"]')), undefined, { timeout: 240000 });
    check(await page.getByRole('alert').count() === 0, 'The standard context reload before deep reasoning failed.');
    progress('live explicit deep household follow-up');
    const deepResponse = new Promise(resolve => { deepResponseResolve = resolve; });
    await page.getByRole('checkbox', { name: 'Deep context reasoning', exact: true }).check();
    await page.getByRole('textbox', { name: 'Ask a question about this context', exact: true }).fill('Compare official household, employment and caregiving support for this hypothetical household. Explain which agency requirements and evidence they should verify, with citations. Do not declare eligibility.');
    await page.getByRole('button', { name: 'Send question', exact: true }).click();
    const actualDeep = await within(deepResponse, 240000);
    check(actualDeep.status === 200 && actualDeep.actualSseDone && !actualDeep.sseErrorEvents, 'The explicit deep follow-up must complete through actual AgentCore SSE.');
    await page.waitForFunction(() => !document.querySelector('.is-updating') || Boolean(document.querySelector('[role="alert"]')), undefined, { timeout: 240000 });
    check(await page.getByRole('alert').count() === 0, 'The explicit deep follow-up reported an application error.');
    check((await page.locator('.answer-content').innerText()).trim().length > 20, 'The explicit deep answer is empty.');
    report.explicitDeepFollowup = true;
    const deepCall = report.runtimeCalls.findLast(call => call.transport === 'sse');
    await page.getByText('Trace the reasoning', { exact: true }).click();
    const deepTraceSteps = await page.locator('.reasoning-details li').count();
    check(deepCall && deepCall.trace.length === deepTraceSteps && deepTraceSteps > 0, 'The deep trace display must match the actual AgentCore result.');
    await page.locator('.citation-chips button').first().click();
    const deepEvidence = page.getByRole('dialog');
    const deepPassage = (await deepEvidence.locator('blockquote').innerText()).trim().replace(/\s+/g, ' ');
    check(actualPassages.has(deepPassage), 'The deep citation passage must match actual AgentCore supporting content.');
    const deepEvidenceUrl = await deepEvidence.getByRole('link', { name: 'Open official source' }).getAttribute('href');
    check(capturedSchemes.some(scheme => new URL(scheme.sourceUrl).href === deepEvidenceUrl), 'The deep citation needs an actual mapped official agency source.');
    await page.getByRole('button', { name: 'Close evidence' }).click();
    report.deepFollowup = { traceSteps: deepTraceSteps, officialEvidenceUrl: deepEvidenceUrl, actualSseDone: true };
    await page.screenshot({ path: path.join(args.artifacts, 'full-platform-deep-followup.png'), fullPage: true });
    const standardCalls = report.runtimeCalls.filter(call => call.transport === 'rest');
    const deepCalls = report.runtimeCalls.filter(call => call.transport === 'sse');
    check(standardCalls.length >= 4 && new Set(standardCalls.map(call => call.persona)).size === 4, 'Expected actual standard Serve queries from all four audiences.');
    check(deepCalls.length >= 1 && report.explicitDeepFollowup, 'Expected an explicit real AgentCore deep-reasoning query.');
    check(report.runtimeCalls.every(call => call.status === 200 && call.mode === (call.transport === 'sse' ? 'deep-reasoning' : 'standard') && call.namespaceMatches && call.idTokenMatches && !call.accessTokenUsed && (call.transport !== 'sse' || call.actualSseDone) && !call.sseErrorEvents && call.answerCharacters > 20 && call.supportingPassages > 0 && call.trace.length > 0), 'The browser requests must use the full platform and its actual grounded results.');
    check(report.pageErrors.length === 0 && report.relayErrors.length === 0, 'The live browser reported application or relay errors.');
    report.passed = true; report.mobileEntryOverflow = false;
    privateJson(reportPath, report);
    console.log(JSON.stringify({ passed: true, cognitoHostedLogin: true, pkceCallback: true, audiences: report.personas.length, actualStandardQueries: standardCalls.length, actualDeepQueries: deepCalls.length, officialProgrammes: report.officialSchemeCount, mockedPlatformResponses: false, mobileOverflow: false, pageErrors: 0 }));
  } catch (error) {
    report.failedStage = stage; report.errorType = error.name;
    if (error.verificationCheck) report.failedCheck = error.verificationCheck;
    if (report.pkceCallback) {
      report.domDiagnostic = await page.evaluate(() => ({ schemeCards: document.querySelectorAll('.scheme-card').length, answerCharacters: document.querySelector('.answer-content')?.textContent?.trim().length || 0, citationChips: document.querySelectorAll('.citation-chips button').length, graphNodes: document.querySelectorAll('.graph-node').length, graphEdges: document.querySelectorAll('.graph-edge').length, alerts: document.querySelectorAll('[role="alert"]').length })).catch(() => undefined);
      await page.screenshot({ path: path.join(args.artifacts, 'full-platform-failure.png'), fullPage: true }).catch(() => undefined);
    }
    privateJson(reportPath, report);
    throw error;
  } finally {
    idToken = ''; accessToken = '';
    await context.unrouteAll({ behavior: 'ignoreErrors' }).catch(() => undefined);
    await browser.close();
  }
}

try {
  const args = argumentsFrom(process.argv.slice(2));
  if (args.help) {
    console.log('Usage: node scripts/verify_full_platform_browser.cjs [--metadata artifacts/full-platform.json] [--credentials artifacts/full-platform-login.local.json] [--artifacts artifacts/]');
    console.log('Requires a published full-mode site and Playwright. Optional SG_PLAYWRIGHT_MODULE and PLAYWRIGHT_CHROMIUM_EXECUTABLE select installed tooling. Live results and screenshots remain ignored under artifacts/.');
  } else main(args).catch(error => { console.error(`Live full-platform verification failed at ${stage} (${error.name}). Details remain in the private local report.`); process.exitCode = 1; });
} catch (error) {
  console.error(`Live full-platform verifier configuration failed (${error.name}).`); process.exitCode = 1;
}

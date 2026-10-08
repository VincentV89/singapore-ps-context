import type { Analysis, AppConfig, Evidence, FullPlatformConfig, GraphEdge, GraphNode, OfficialCatalogue, OfficialScheme, Persona, PersonaId, PlatformTraceStep, Preset, Profile, Scenario, Scheme } from './types';

/** Browser adapter for Context Ontology Accelerator v0.3.4.
 * Public catalogue content supplies browse cards. Answers, trace and graph
 * context come from the deployed platform, never from the compact rules engine.
 */
type Fetcher = typeof fetch;
type RecordValue = Record<string, unknown>;
type PlatformResult = {
  tier: number;
  synthesizedAnswer?: string;
  supportingContent: RecordValue[];
  graphContext?: unknown;
  trace: PlatformTraceStep[];
  partial: boolean;
  confidence?: { score: number; rationale: string };
  ontologyVersion?: string;
  dataSources?: string[];
  resultRows?: RecordValue[];
  queryUsed?: string;
  sparqlGenerated?: string;
  guardrailBlocked?: boolean;
};
type PlatformResponse = { result: PlatformResult; requestId?: string; sessionId?: string };

const categoryLabels: Record<string, string> = {
  'financial-assistance': 'Financial assistance', employment: 'Employment', caregiving: 'Caregiving', disability: 'Disability support', seniors: 'Seniors', healthcare: 'Healthcare', education: 'Education', skills: 'Skills & training', family: 'Family benefits',
  'business-growth': 'Business growth', digitalisation: 'Digitalisation & AI', innovation: 'Innovation', internationalisation: 'International expansion', sustainability: 'Sustainability', financing: 'Financing', community: 'Community projects', 'capability-building': 'Capability building', 'workforce-development': 'Workforce development', arts: 'Arts', research: 'Research funding', collaboration: 'Collaboration',
};

// These inputs are hypothetical applicant context. They are not agency records
// or screening rules, and are never added to the platform's source graph.
const audienceMetadata: Record<PersonaId, { persona: Persona; profile: Profile; presets: Preset[] }> = {
  individuals: {
    persona: { id: 'individuals', name: 'Individuals & Families', tagline: 'Support for everyday life', description: 'Explore Singapore agency information on financial assistance, housing, healthcare, education, skills and family support.', segments: ['Parents', 'Students', 'Seniors', 'Caregivers', 'Jobseekers', 'Persons with disabilities'], contextTitle: 'Household context', profileTitle: 'Hypothetical household', prompts: ['Which Singapore support programmes should this household explore, and what requirements should they check?', 'What information should this household prepare before contacting an agency?', 'Which agencies provide employment, caregiving and household support?'], supportCategories: [], fields: [
      { key: 'householdIncome', label: 'Monthly household income (S$)', type: 'number', allowUnknown: true, min: 0, max: 1000000, step: 0.01 }, { key: 'householdSize', label: 'Household size', type: 'number', allowUnknown: true, min: 1, max: 20 }, { key: 'age', label: 'Age', type: 'number', allowUnknown: true, min: 0, max: 120 },
      { key: 'citizenship', label: 'Residency status', type: 'select', allowUnknown: true, options: [{ value: 'citizen', label: 'Singapore citizen' }, { value: 'permanent-resident', label: 'Permanent resident' }, { value: 'other', label: 'Other resident' }] }, { key: 'employmentStatus', label: 'Employment status', type: 'select', allowUnknown: true, options: [{ value: 'unemployed', label: 'Unemployed' }, { value: 'employed', label: 'Employed' }, { value: 'retired', label: 'Retired' }, { value: 'student', label: 'Student' }] },
      { key: 'caregiver', label: 'Caregiving responsibility', type: 'boolean', allowUnknown: true }, { key: 'disability', label: 'Disability support need', type: 'boolean', allowUnknown: true }, { key: 'recentJobLoss', label: 'Recent job loss', type: 'boolean', allowUnknown: true },
    ] },
    profile: { householdIncome: 3600, householdSize: 4, age: 42, citizenship: 'citizen', employmentStatus: 'unemployed', caregiver: false, disability: false, recentJobLoss: true },
    presets: [
      { id: 'job-loss', label: 'Job loss · household of four', profile: { householdIncome: 3600, householdSize: 4, age: 42, citizenship: 'citizen', employmentStatus: 'unemployed', caregiver: false, disability: false, recentJobLoss: true } },
      { id: 'caregiving', label: 'Caregiving household', profile: { householdIncome: 5400, householdSize: 4, age: 42, citizenship: 'citizen', employmentStatus: 'employed', caregiver: true, disability: false, recentJobLoss: false } },
      { id: 'student', label: 'Student education support', profile: { householdIncome: 4800, householdSize: 4, age: 20, citizenship: 'citizen', employmentStatus: 'student', caregiver: false, disability: false, recentJobLoss: false } },
      { id: 'senior', label: 'Senior healthcare support', profile: { householdIncome: 4800, householdSize: 4, age: 70, citizenship: 'citizen', employmentStatus: 'retired', caregiver: false, disability: false, recentJobLoss: false } },
    ],
  },
  businesses: {
    persona: { id: 'businesses', name: 'Businesses & Entrepreneurs', tagline: 'Grow and transform', description: 'Explore Singapore support for digitalisation, AI adoption, workforce development, innovation, sustainability and international growth.', segments: ['Startup founders', 'SME owners', 'Self-employed', 'Employers', 'Exporters'], contextTitle: 'Business & project context', profileTitle: 'Hypothetical enterprise', prompts: ['Which Singapore agency programmes should this business explore for its project?', 'What applicant and project requirements should this business verify with the agency?', 'What does the current Enterprise Singapore support landscape mean for this project?'], supportCategories: [], fields: [
      { key: 'organizationType', label: 'Business type', type: 'select', allowUnknown: true, options: [{ value: 'sme', label: 'SME' }, { value: 'startup', label: 'Startup' }, { value: 'self-employed', label: 'Self-employed' }, { value: 'enterprise', label: 'Larger enterprise' }] }, { key: 'localRegistration', label: 'Registered in Singapore', type: 'boolean', allowUnknown: true }, { key: 'localOwnership', label: 'Local ownership (%)', type: 'number', allowUnknown: true, min: 0, max: 100, step: 0.1 }, { key: 'employeeCount', label: 'Number of employees', type: 'number', allowUnknown: true, min: 0, max: 100000 }, { key: 'annualRevenue', label: 'Annual revenue (S$)', type: 'number', allowUnknown: true, min: 0, max: 10000000000, step: 0.01 },
      { key: 'projectArea', label: 'Project focus', type: 'select', allowUnknown: true, options: [{ value: 'digitalisation', label: 'Digitalisation' }, { value: 'ai', label: 'AI adoption' }, { value: 'workforce', label: 'Workforce development' }, { value: 'sustainability', label: 'Sustainability' }, { value: 'internationalisation', label: 'International expansion' }, { value: 'rd', label: 'Research & development' }] }, { key: 'coFunding', label: 'Applicant co-funding (%)', type: 'number', allowUnknown: true, min: 0, max: 100, step: 0.1 },
    ] },
    profile: { organizationType: 'sme', localRegistration: true, localOwnership: 60, employeeCount: 25, annualRevenue: 4500000, projectArea: 'digitalisation', coFunding: 40 },
    presets: [
      { id: 'digital-sme', label: 'SME digital transformation', profile: { organizationType: 'sme', localRegistration: true, localOwnership: 60, employeeCount: 25, annualRevenue: 4500000, projectArea: 'digitalisation', coFunding: 40 } },
      { id: 'ai-startup', label: 'Startup adopting AI', profile: { organizationType: 'startup', localRegistration: true, localOwnership: 60, employeeCount: 8, annualRevenue: 800000, projectArea: 'ai', coFunding: 40 } },
      { id: 'green-project', label: 'SME sustainability project', profile: { organizationType: 'sme', localRegistration: true, localOwnership: 60, employeeCount: 25, annualRevenue: 4500000, projectArea: 'sustainability', coFunding: 40 } },
    ],
  },
  community: {
    persona: { id: 'community', name: 'Nonprofits & Community Organisations', tagline: 'Fund social impact', description: 'Explore Singapore agency information on community projects, social services, capability building, arts and youth programmes.', segments: ['Registered charities', 'Social service agencies', 'Voluntary welfare organisations', 'Religious organisations', 'Community initiatives', 'Arts groups'], contextTitle: 'Community & project context', profileTitle: 'Hypothetical organisation', prompts: ['Which Singapore programmes should this community organisation explore?', 'What public-benefit, registration and project requirements should the applicant check?', 'Which Singapore agencies support community capability building and arts projects?'], supportCategories: [], fields: [
      { key: 'organizationType', label: 'Organisation type', type: 'select', allowUnknown: true, options: [{ value: 'registered-charity', label: 'Registered charity' }, { value: 'social-service-agency', label: 'Social service agency' }, { value: 'religious-organisation', label: 'Religious organisation' }, { value: 'community-group', label: 'Community group' }, { value: 'arts-group', label: 'Arts group' }] }, { key: 'localRegistration', label: 'Registered in Singapore', type: 'boolean', allowUnknown: true }, { key: 'registeredCharity', label: 'Registered charity status', type: 'boolean', allowUnknown: true }, { key: 'publicBenefit', label: 'Project has public benefit', type: 'boolean', allowUnknown: true },
      { key: 'projectArea', label: 'Project focus', type: 'select', allowUnknown: true, options: [{ value: 'community', label: 'Community projects' }, { value: 'social-services', label: 'Social services' }, { value: 'capability', label: 'Capability building' }, { value: 'arts', label: 'Arts' }, { value: 'youth', label: 'Youth programmes' }] }, { key: 'projectBudget', label: 'Project budget (S$)', type: 'number', allowUnknown: true, min: 0, max: 10000000, step: 0.01 },
    ] },
    profile: { organizationType: 'registered-charity', localRegistration: true, registeredCharity: true, publicBenefit: true, projectArea: 'social-services', projectBudget: 80000 },
    presets: [
      { id: 'social-service', label: 'Charity social-service project', profile: { organizationType: 'registered-charity', localRegistration: true, registeredCharity: true, publicBenefit: true, projectArea: 'social-services', projectBudget: 80000 } },
      { id: 'capability-project', label: 'Charity capability building', profile: { organizationType: 'registered-charity', localRegistration: true, registeredCharity: true, publicBenefit: true, projectArea: 'capability', projectBudget: 40000 } },
      { id: 'arts-project', label: 'Community arts initiative', profile: { organizationType: 'arts-group', localRegistration: true, registeredCharity: false, publicBenefit: true, projectArea: 'arts', projectBudget: 30000 } },
    ],
  },
  research: {
    persona: { id: 'research', name: 'Researchers & Educational Institutions', tagline: 'Advance knowledge', description: 'Explore Singapore research funding, innovation grants, scholarships and collaboration programmes.', segments: ['University researchers', 'Educators', 'Research institutes', 'Schools', 'Industry-academia partnerships'], contextTitle: 'Research & institution context', profileTitle: 'Hypothetical research team', prompts: ['Which Singapore research and collaboration programmes should this project explore?', 'What institution, applicant and project requirements should this team verify?', 'Which agencies provide research and industry-academia collaboration funding?'], supportCategories: [], fields: [
      { key: 'institutionType', label: 'Institution type', type: 'select', allowUnknown: true, options: [{ value: 'university', label: 'University' }, { value: 'research-institute', label: 'Research institute' }, { value: 'school', label: 'School' }, { value: 'industry-partner', label: 'Industry partner' }] }, { key: 'localRegistration', label: 'Institution registered in Singapore', type: 'boolean', allowUnknown: true }, { key: 'leadApplicant', label: 'Lead applicant', type: 'select', allowUnknown: true, options: [{ value: 'local-researcher', label: 'Local researcher' }, { value: 'educator', label: 'Educator' }, { value: 'industry-lead', label: 'Industry lead' }, { value: 'international-researcher', label: 'International researcher' }] },
      { key: 'projectArea', label: 'Project focus', type: 'select', allowUnknown: true, options: [{ value: 'fundamental-research', label: 'Fundamental research' }, { value: 'applied-research', label: 'Applied research' }, { value: 'education-innovation', label: 'Education innovation' }, { value: 'scholarship', label: 'Scholarship programme' }] }, { key: 'collaboration', label: 'Industry-academia collaboration', type: 'boolean', allowUnknown: true }, { key: 'ethicsApproval', label: 'Required ethics approval obtained', type: 'boolean', allowUnknown: true }, { key: 'projectBudget', label: 'Project budget (S$)', type: 'number', allowUnknown: true, min: 0, max: 100000000, step: 0.01 },
    ] },
    profile: { institutionType: 'university', localRegistration: true, leadApplicant: 'local-researcher', projectArea: 'fundamental-research', collaboration: false, ethicsApproval: true, projectBudget: 250000 },
    presets: [
      { id: 'university-research', label: 'University fundamental research', profile: { institutionType: 'university', localRegistration: true, leadApplicant: 'local-researcher', projectArea: 'fundamental-research', collaboration: false, ethicsApproval: true, projectBudget: 250000 } },
      { id: 'industry-collaboration', label: 'Industry-academia applied research', profile: { institutionType: 'university', localRegistration: true, leadApplicant: 'local-researcher', projectArea: 'applied-research', collaboration: true, ethicsApproval: true, projectBudget: 450000 } },
      { id: 'school-project', label: 'School education innovation', profile: { institutionType: 'school', localRegistration: true, leadApplicant: 'educator', projectArea: 'education-innovation', collaboration: false, ethicsApproval: true, projectBudget: 80000 } },
    ],
  },
};

function isRecord(value: unknown): value is RecordValue { return typeof value === 'object' && value !== null && !Array.isArray(value); }
function stringValue(value: unknown): string | undefined { return typeof value === 'string' && value ? value : undefined; }
function records(value: unknown): RecordValue[] { return Array.isArray(value) ? value.filter(isRecord) : []; }
function labelFromUri(uri: string): string {
  const segment = uri.split(/[\/#]/).pop() || uri;
  let label = segment;
  try { label = decodeURIComponent(segment); } catch { /* A malformed URI can still be displayed verbatim. */ }
  return label.replace(/([a-z])([A-Z])/g, '$1 $2').replace(/[_-]/g, ' ');
}
function safePublicUrl(value: unknown): string | undefined {
  if (typeof value !== 'string') return undefined;
  try { const url = new URL(value); return url.protocol === 'https:' ? url.href : undefined; } catch { return undefined; }
}
function belongsTo(scheme: OfficialScheme, persona: PersonaId) { return Array.isArray(scheme.persona) ? scheme.persona.includes(persona) : scheme.persona === persona; }
function requirePlatform(config: AppConfig): FullPlatformConfig {
  if (config.platform?.mode !== 'full' || !config.platform.apiUrl || !config.platform.namespaceId) throw new Error('The full context platform is not configured.');
  return config.platform;
}

let cachedCatalogue: { url: string; value: OfficialCatalogue } | undefined;
export async function loadOfficialCatalogue(catalogueUrl = '/official/catalogue.json', fetcher: Fetcher = fetch): Promise<OfficialCatalogue> {
  if (cachedCatalogue?.url === catalogueUrl) return cachedCatalogue.value;
  // This object is intentionally public and contains no authentication token.
  const response = await fetcher(catalogueUrl, { cache: 'no-store', credentials: 'omit' });
  if (!response.ok) throw new Error(`Official source catalogue could not be loaded (${response.status}).`);
  const raw: unknown = await response.json();
  if (!isRecord(raw) || !Array.isArray(raw.schemes) || typeof raw.fetchedAt !== 'string') throw new Error('The official source catalogue is malformed.');
  const schemes = raw.schemes.filter((item): item is OfficialScheme => isRecord(item) && typeof item.id === 'string' && typeof item.name === 'string' && typeof item.summary === 'string' && typeof item.eligibilityText === 'string' && typeof item.benefitText === 'string' && typeof item.fetchedAt === 'string' && Array.isArray(item.categories) && item.categories.every(category => typeof category === 'string') && isRecord(item.agency) && typeof item.agency.name === 'string' && Boolean(safePublicUrl(item.sourceUrl)) && (typeof item.persona === 'string' || Array.isArray(item.persona)));
  if (schemes.length !== raw.schemes.length || !schemes.length) throw new Error('The official source catalogue contains incomplete records.');
  const value: OfficialCatalogue = { schemaVersion: typeof raw.schemaVersion === 'number' || typeof raw.schemaVersion === 'string' ? raw.schemaVersion : 1, fetchedAt: raw.fetchedAt, schemes };
  cachedCatalogue = { url: catalogueUrl, value };
  return value;
}

function sourceEvidence(scheme: OfficialScheme): Evidence {
  return { id: `official-${scheme.id}`, title: scheme.sourceTitle || scheme.name, source: scheme.agency.name, excerpt: [scheme.summary, scheme.eligibilityText, scheme.benefitText, scheme.lifecycleText].filter(Boolean).join('\n\n'), updatedAt: scheme.fetchedAt, url: safePublicUrl(scheme.sourceUrl), sourceMode: 'official', schemeId: scheme.id };
}
function personaMetadata(persona: PersonaId, catalogue: OfficialCatalogue): Persona {
  const categories = [...new Set(catalogue.schemes.filter(scheme => belongsTo(scheme, persona)).flatMap(scheme => scheme.categories))];
  return { ...audienceMetadata[persona].persona, supportCategories: categories.map(id => ({ id, label: categoryLabels[id] || labelFromUri(id) })) };
}

export async function loadOfficialScenario(persona: PersonaId, fetcher: Fetcher = fetch, catalogueUrl = '/official/catalogue.json'): Promise<Scenario> {
  const catalogue = await loadOfficialCatalogue(catalogueUrl, fetcher);
  const metadata = audienceMetadata[persona];
  if (!metadata) throw new Error('Choose a supported audience.');
  return {
    persona: personaMetadata(persona, catalogue), personas: (Object.keys(audienceMetadata) as PersonaId[]).map(id => personaMetadata(id, catalogue)),
    scenario: { id: `singapore-support-${persona}`, title: 'SG Support Navigator', timestamp: catalogue.fetchedAt, description: 'Official Singapore agency information with a hypothetical applicant profile. Requirements and decisions remain with the administering agency.', synthetic: false },
    profile: { ...metadata.profile }, presets: metadata.presets.map(preset => ({ ...preset, profile: { ...preset.profile } })), evidence: catalogue.schemes.filter(scheme => belongsTo(scheme, persona)).map(sourceEvidence),
    nodes: [], edges: [], sourceMode: 'official', catalogueFetchedAt: catalogue.fetchedAt,
  };
}

export class PlatformRequestError extends Error {
  constructor(message: string, public readonly status = 0) { super(message); this.name = 'PlatformRequestError'; }
}
async function checkedResponse(response: Response): Promise<Response> {
  if (response.ok) return response;
  let detail = '';
  try { const body: unknown = await response.json(); if (isRecord(body)) detail = stringValue(body.message) || stringValue(body.detail) || stringValue(body.error) || ''; } catch { /* Show status when a service has no JSON error body. */ }
  const message = response.status === 401 ? 'Your platform session has expired. Sign in again.' : response.status === 403 ? 'Your account does not have access to this context namespace.' : detail || `The full context platform returned ${response.status}.`;
  throw new PlatformRequestError(message, response.status);
}
function normalizeTrace(value: unknown): PlatformTraceStep[] {
  return records(value).filter(item => typeof item.step === 'string' && typeof item.status === 'string' && typeof item.durationMs === 'number').map(item => ({ step: String(item.step), status: String(item.status), durationMs: Number(item.durationMs), ...(typeof item.detail === 'string' || isRecord(item.detail) ? { detail: item.detail } : {}), ...(typeof item.toolUsed === 'string' ? { toolUsed: item.toolUsed } : {}), ...(typeof item.wallMs === 'number' ? { wallMs: item.wallMs } : {}) }));
}
function normalizeResponse(raw: unknown): PlatformResponse {
  if (!isRecord(raw) || !isRecord(raw.result)) throw new PlatformRequestError('The full context platform returned a malformed response.');
  const result = raw.result;
  const answer = stringValue(result.synthesizedAnswer);
  const resultRows = records(result.resultRows);
  if (!answer && !resultRows.length) throw new PlatformRequestError('The full context platform returned no answer or structured results.');
  return {
    requestId: stringValue(raw.requestId), sessionId: stringValue(raw.sessionId),
    result: {
      tier: typeof result.tier === 'number' ? result.tier : 0, synthesizedAnswer: answer, supportingContent: records(result.supportingContent), graphContext: result.graphContext, trace: normalizeTrace(result.trace), partial: result.partial === true,
      ...(isRecord(result.confidence) && typeof result.confidence.score === 'number' ? { confidence: { score: result.confidence.score, rationale: stringValue(result.confidence.rationale) || '' } } : {}),
      ontologyVersion: stringValue(result.ontologyVersion), dataSources: Array.isArray(result.dataSources) ? result.dataSources.filter((item): item is string => typeof item === 'string') : [], resultRows,
      queryUsed: stringValue(result.queryUsed), sparqlGenerated: stringValue(result.sparqlGenerated), guardrailBlocked: result.guardrailBlocked === true,
    },
  };
}
function invocationUrl(platform: FullPlatformConfig) {
  if (!platform.serveRuntimeArn || !/^[a-z]{2}-[a-z]+-\d+$/.test(platform.region)) throw new Error('Streaming analysis is not configured for this platform.');
  return `https://bedrock-agentcore.${platform.region}.amazonaws.com/runtimes/${encodeURIComponent(platform.serveRuntimeArn)}/invocations?qualifier=DEFAULT`;
}

/** SSE events follow the upstream AgentCore JSON-in-data protocol. */
async function queryStreaming(platform: FullPlatformConfig, query: string, idToken: string, signal: AbortSignal, fetcher: Fetcher, onStep?: (step: PlatformTraceStep) => void): Promise<PlatformResponse> {
  const requestId = crypto.randomUUID();
  const response = await checkedResponse(await fetcher(invocationUrl(platform), {
    method: 'POST', headers: { Authorization: `Bearer ${idToken}`, 'Content-Type': 'application/json', 'X-Amzn-Bedrock-AgentCore-Runtime-Session-Id': crypto.randomUUID() },
    body: JSON.stringify({ query, namespace: platform.namespaceId, requestId, options: { mode: 'deep-reasoning', includeSupporting: true }, stream: true }), signal,
  }));
  if (!response.body) throw new PlatformRequestError('The platform returned an empty analysis stream.');
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '', completed: PlatformResponse | undefined;
  function handleEvent(block: string) {
    const data = block.split(/\r?\n/).filter(line => line.startsWith('data:')).map(line => line.slice(5).replace(/^ /, '')).join('\n');
    if (!data || data === '[DONE]') return;
    let event: unknown;
    try { event = JSON.parse(data); } catch { return; }
    if (!isRecord(event) || !isRecord(event.payload)) return;
    if (event.type === 'error') throw new PlatformRequestError(stringValue(event.payload.message) || 'Platform analysis failed.', typeof event.payload.statusCode === 'number' ? event.payload.statusCode : 0);
    if (event.type === 'step' && typeof event.payload.stepName === 'string') onStep?.({ step: event.payload.stepName, status: stringValue(event.payload.status) || 'unknown', durationMs: typeof event.payload.durationMs === 'number' ? event.payload.durationMs : 0, detail: stringValue(event.payload.detail), toolUsed: stringValue(event.payload.toolUsed) });
    if (event.type === 'done') completed = normalizeResponse({ result: event.payload.result, requestId: stringValue(event.requestId) || requestId, sessionId: stringValue(event.sessionId) });
  }
  try {
    while (true) {
      const { done, value } = await reader.read();
      buffer += decoder.decode(value, { stream: !done });
      let match = /\r?\n\r?\n/.exec(buffer);
      while (match) { handleEvent(buffer.slice(0, match.index)); buffer = buffer.slice(match.index + match[0].length); match = /\r?\n\r?\n/.exec(buffer); }
      if (done) break;
    }
    if (buffer.trim()) handleEvent(buffer);
  } finally { await reader.cancel().catch(() => undefined); reader.releaseLock(); }
  if (!completed) throw new PlatformRequestError('Platform analysis ended before a completed result arrived.');
  return completed;
}

function displayNodeType(type: string, label: string): string {
  const value = `${label} ${type.split(/[\/#]/).pop() || type}`.toLowerCase();
  if (/agency|ministry|administer/.test(value)) return 'agency';
  if (/scheme|grant|programme|program|subsid|support measure/.test(value)) return 'scheme';
  if (/criteria|criterion|eligib|requirement|rule/.test(value)) return 'rule';
  if (/document|policy|evidence|chunk|source/.test(value)) return 'document';
  if (/household|context|project/.test(value)) return 'context';
  if (/organisation|organization|enterprise|business|charity/.test(value)) return 'organization';
  if (/institution|researcher|university|school/.test(value)) return 'institution';
  if (/person|individual|citizen|resident|family/.test(value)) return 'resident';
  if (/need|goal|category|topic|event/.test(value)) return 'need';
  return 'context';
}
function graphFromContext(raw: unknown): { nodes: GraphNode[]; edges: GraphEdge[] } {
  const entityRecords = Array.isArray(raw) ? records(raw) : isRecord(raw) ? records(raw.entities) : [];
  const nodeMap = new Map<string, GraphNode>();
  for (const entity of entityRecords) {
    const uri = stringValue(entity.uri), label = stringValue(entity.label);
    if (!uri || !label) continue;
    const originalType = stringValue(entity.type) || '';
    const properties = isRecord(entity.properties) ? entity.properties : {};
    const kind = /(?:owl#Class|rdfs#Class)$/.test(originalType) ? 'class' : 'entity';
    nodeMap.set(uri, { id: uri, uri, label, type: displayNodeType(originalType, label), originalType, properties, kind, provenance: 'platform', description: stringValue(properties.description) || stringValue(properties.comment) || `${kind === 'class' ? 'Ontology class' : 'Entity'} returned by the deployed context platform.` });
  }
  const relationshipRecords = isRecord(raw) ? records(raw.relationships) : [];
  for (const entity of entityRecords) for (const edge of records(entity.relationships)) relationshipRecords.push({ ...edge, sourceUri: stringValue(edge.sourceUri) || stringValue(edge.source_uri) || entity.uri });
  const edgeMap = new Map<string, GraphEdge>();
  for (const relationship of relationshipRecords) {
    const source = stringValue(relationship.sourceUri) || stringValue(relationship.source_uri), target = stringValue(relationship.targetUri) || stringValue(relationship.target_uri) || stringValue(relationship.target), predicate = stringValue(relationship.predicateUri) || stringValue(relationship.predicate_uri) || stringValue(relationship.predicate);
    if (!source || !target || !predicate || !nodeMap.has(source) || !nodeMap.has(target)) continue;
    const id = `${source}|${predicate}|${target}`;
    edgeMap.set(id, { id, source, target, predicateUri: predicate, label: stringValue(relationship.predicateLabel) || stringValue(relationship.predicate_label) || labelFromUri(predicate), provenance: 'platform' });
  }
  return { nodes: [...nodeMap.values()], edges: [...edgeMap.values()] };
}

/** Reads actual class vertices if a query did not return a connected graph.
 * This is a schema view, labelled separately from retrieved document context.
 */
async function loadOntologyGraph(platform: FullPlatformConfig, idToken: string, signal: AbortSignal, fetcher: Fetcher): Promise<{ nodes: GraphNode[]; edges: GraphEdge[] }> {
  const base = `${platform.apiUrl.replace(/\/$/, '')}/namespaces/${encodeURIComponent(platform.namespaceId)}`;
  // API Gateway drops blank query values; '*' is the store's match-all query.
  const params = new URLSearchParams({ q: '*', kind: 'class', limit: '24', ...(platform.ontologyId ? { ontology_id: platform.ontologyId } : {}) });
  const headers = { Authorization: `Bearer ${idToken}` };
  const search = await checkedResponse(await fetcher(`${base}/graph/search?${params}`, { headers, signal }));
  const searchResult: unknown = await search.json();
  const hits = isRecord(searchResult) ? records(searchResult.hits).filter(hit => typeof hit.uri === 'string') : [];
  const vertices = await Promise.all(hits.slice(0, 24).map(async hit => {
    const response = await checkedResponse(await fetcher(`${base}/graph/class?${new URLSearchParams({ uri: String(hit.uri) })}`, { headers, signal }));
    const raw: unknown = await response.json();
    return isRecord(raw) ? raw : undefined;
  }));
  const entities: RecordValue[] = [], relationships: RecordValue[] = [];
  for (const vertex of vertices) {
    if (!vertex || typeof vertex.uri !== 'string') continue;
    const label = Array.isArray(vertex.labels) ? stringValue(vertex.labels[0]) : undefined;
    const comment = Array.isArray(vertex.comments) ? stringValue(vertex.comments[0]) : undefined;
    entities.push({ uri: vertex.uri, label: label || labelFromUri(vertex.uri), type: 'http://www.w3.org/2002/07/owl#Class', properties: { description: comment || 'Published ontology class returned by the platform graph API.' } });
    for (const edge of records(vertex.edges)) {
      if (!isRecord(edge.neighbor) || typeof edge.neighbor.uri !== 'string' || typeof edge.predicate !== 'string') continue;
      // Class vertices link to property and reference-class vertices. Keep the
      // returned endpoints so their actual relationships survive normalization.
      const neighbor = edge.neighbor;
      const neighborType = neighbor.kind === 'class' ? 'http://www.w3.org/2002/07/owl#Class' : neighbor.kind === 'object-property' ? 'http://www.w3.org/2002/07/owl#ObjectProperty' : neighbor.kind === 'datatype-property' ? 'http://www.w3.org/2002/07/owl#DatatypeProperty' : undefined;
      if (!neighborType) continue;
      entities.push({ uri: neighbor.uri, label: stringValue(neighbor.label) || labelFromUri(String(neighbor.uri)), type: neighborType, properties: { graphKind: neighbor.kind, description: 'Ontology vertex returned by the platform graph API.' } });
      const incoming = edge.direction === 'incoming' || edge.direction === 'in';
      relationships.push({ sourceUri: incoming ? edge.neighbor.uri : vertex.uri, predicateUri: edge.predicate, targetUri: incoming ? vertex.uri : edge.neighbor.uri, predicateLabel: stringValue(edge.predicate_label) });
    }
  }
  return graphFromContext({ entities, relationships });
}

function relatedScheme(item: RecordValue, catalogue: OfficialCatalogue): OfficialScheme | undefined {
  const metadata = isRecord(item.metadata) ? item.metadata : {};
  const source = [item.sourceDocumentName, item.sourceDoc, item.sourceDocumentId, item.label, metadata.schemeId, metadata.sourceUrl].filter(value => typeof value === 'string').join(' ').toLowerCase();
  const explicitId = stringValue(item.schemeId) || stringValue(metadata.schemeId);
  return catalogue.schemes.find(scheme => explicitId === scheme.id || source.includes(scheme.sourceUrl.toLowerCase()) || source.includes(scheme.name.toLowerCase()) || new RegExp(`(?:^|[/\\\\\\s])${scheme.id.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}(?:\\.|[/\\\\\\s]|$)`, 'i').test(source));
}
/** v0.3.4 synthesis carries sourceDoc as an opaque document ID, while KBSearch
 * exposes that same ID and the source filename. Join only on exact actual IDs;
 * the filename then resolves to the captured catalogue document. The retrieved
 * passage itself always remains the text supplied by the original answer.
 */
async function resolveSupportingProvenance(result: PlatformResult, catalogue: OfficialCatalogue, platform: FullPlatformConfig, query: string, idToken: string, signal: AbortSignal, fetcher: Fetcher, warnings: string[]): Promise<void> {
  const missing = result.supportingContent.filter(item => !relatedScheme(item, catalogue) && (stringValue(item.sourceDocumentId) || stringValue(item.sourceDoc)));
  if (!missing.length) return;
  try {
    const response = await checkedResponse(await fetcher(`${platform.apiUrl.replace(/\/$/, '')}/namespaces/${encodeURIComponent(platform.namespaceId)}/kb/search`, {
      method: 'POST', headers: { Authorization: `Bearer ${idToken}`, 'Content-Type': 'application/json' }, body: JSON.stringify({ query, topK: 100 }), signal,
    }));
    const raw: unknown = await response.json();
    const body = isRecord(raw) && isRecord(raw.result) ? raw.result : raw;
    const namesById = new Map<string, Set<string>>();
    for (const chunk of isRecord(body) ? records(body.chunks) : []) {
      const id = stringValue(chunk.sourceDocumentId), name = stringValue(chunk.sourceDocumentName);
      if (!id || !name) continue;
      const names = namesById.get(id) || new Set<string>(); names.add(name); namesById.set(id, names);
    }
    result.supportingContent = result.supportingContent.map(item => {
      if (relatedScheme(item, catalogue)) return item;
      const id = stringValue(item.sourceDocumentId) || stringValue(item.sourceDoc);
      const names = id ? namesById.get(id) : undefined;
      if (!names || names.size !== 1) return item;
      return { ...item, sourceDocumentName: [...names][0] };
    });
    if (missing.some(item => {
      const id = stringValue(item.sourceDocumentId) || stringValue(item.sourceDoc);
      return !result.supportingContent.some(resolved => (stringValue(resolved.sourceDocumentId) || stringValue(resolved.sourceDoc)) === id && relatedScheme(resolved, catalogue));
    })) warnings.push('Some retrieved passages could not be matched to an official catalogue URL using platform document metadata.');
  } catch (error) {
    if (signal.aborted || error instanceof PlatformRequestError && (error.status === 401 || error.status === 403)) throw error;
    warnings.push('Source document metadata could not be retrieved. Unresolved passages retain their platform document IDs without an inferred official link.');
  }
}
function supportingEvidence(result: PlatformResult, catalogue: OfficialCatalogue): Evidence[] {
  const evidence = new Map<string, Evidence>();
  for (const [index, item] of result.supportingContent.entries()) {
    const text = stringValue(item.text);
    if (!text) continue;
    const scheme = relatedScheme(item, catalogue);
    const metadata = isRecord(item.metadata) ? item.metadata : {};
    const id = stringValue(item.chunkId) || stringValue(item.sourceDocumentId) || `platform-content-${index + 1}`;
    evidence.set(id, { id, title: scheme?.sourceTitle || stringValue(item.sourceDocumentName) || stringValue(item.label) || stringValue(item.sourceDoc) || 'Retrieved source passage', source: scheme?.agency.name || 'Context platform source document', excerpt: text, updatedAt: scheme?.fetchedAt, url: scheme ? safePublicUrl(scheme.sourceUrl) : safePublicUrl(item.sourceUrl) || safePublicUrl(metadata.sourceUrl), sourceDocumentId: stringValue(item.sourceDocumentId) || stringValue(item.sourceDoc), sourceMode: 'platform', schemeId: scheme?.id });
  }
  return [...evidence.values()];
}
function connectedNodeIds(start: string | undefined, edges: GraphEdge[]): string[] {
  if (!start) return [];
  const reached = new Set<string>([start]);
  let frontier = [start];
  for (let depth = 0; depth < 2 && frontier.length; depth++) {
    const next: string[] = [];
    for (const id of frontier) for (const edge of edges) {
      const adjacent = edge.source === id ? edge.target : edge.target === id ? edge.source : undefined;
      if (adjacent && !reached.has(adjacent)) { reached.add(adjacent); next.push(adjacent); }
    }
    frontier = next;
  }
  return [...reached];
}
function officialSchemes(persona: PersonaId, catalogue: OfficialCatalogue, nodes: GraphNode[], edges: GraphEdge[]): Scheme[] {
  return catalogue.schemes.filter(scheme => belongsTo(scheme, persona)).map(scheme => {
    const normalizedName = scheme.name.toLowerCase().replace(/[^a-z0-9]/g, '');
    const node = nodes.find(item => item.kind !== 'class' && (item.id === scheme.sourceUrl || stringValue(item.properties?.schemeId) === scheme.id || item.label.toLowerCase().replace(/[^a-z0-9]/g, '') === normalizedName));
    return { id: scheme.id, name: scheme.name, categories: scheme.categories, agency: scheme.agency.name, status: 'needs-review', reason: 'Agency assessment required. Check the current applicant and project requirements with the administering agency.', benefit: scheme.benefitText || 'See the agency source for the type and extent of support.', ruleResults: [], documentIds: [], evidenceIds: [`official-${scheme.id}`], pathNodeIds: connectedNodeIds(node?.id, edges), graphNodeId: node?.id, summary: scheme.summary, eligibilityText: scheme.eligibilityText, lifecycleText: scheme.lifecycleText, sourceUrl: safePublicUrl(scheme.sourceUrl), applicationUrl: safePublicUrl(scheme.applicationUrl), sourceFetchedAt: scheme.fetchedAt, sourceStatus: scheme.status, verified: scheme.verified, sourceMode: 'official' };
  });
}
function contextQuery(persona: PersonaId, profile: Profile, question: string): string {
  const metadata = audienceMetadata[persona];
  const facts = metadata.persona.fields.map(field => `${field.label}: ${profile[field.key] === null || profile[field.key] === undefined ? 'not supplied' : String(profile[field.key])}`).join('; ');
  const query = `${question.trim() || metadata.persona.prompts[0]}\nAudience: ${metadata.persona.name}. Hypothetical applicant context: ${facts}.\nUse the Singapore agency sources in this namespace. Explain relevant programmes and source requirements; distinguish missing information. Do not declare eligibility or approval. Cite the agency evidence and respect any stated programme transition or closure dates.`;
  if (query.length > 4000) throw new Error('Please shorten the question so it fits the platform query limit.');
  return query;
}

export type OfficialAnalysisRequest = { config: AppConfig; persona: PersonaId; profile: Profile; question: string; idToken: string; mode?: 'standard' | 'deep-reasoning'; signal?: AbortSignal; onStep?: (step: PlatformTraceStep) => void; fetcher?: Fetcher };
export async function analyzeOfficialScenario({ config, persona, profile, question, idToken, mode = 'standard', signal, onStep, fetcher = fetch }: OfficialAnalysisRequest): Promise<Analysis> {
  const platform = requirePlatform(config);
  if (!idToken) throw new PlatformRequestError('Sign in to query the full context platform.', 401);
  const requestSignal = signal ? AbortSignal.any([signal, AbortSignal.timeout(mode === 'deep-reasoning' ? 210000 : 60000)]) : AbortSignal.timeout(mode === 'deep-reasoning' ? 210000 : 60000);
  const catalogue = await loadOfficialCatalogue(platform.catalogueUrl, fetcher);
  const query = contextQuery(persona, profile, question);
  // REST uses flat Smithy fields; the data-layer proxy constructs the nested
  // AgentCore options. Sending nested options here silently drops them.
  const response = mode === 'deep-reasoning' ? await queryStreaming(platform, query, idToken, requestSignal, fetcher, onStep) : normalizeResponse(await (await checkedResponse(await fetcher(`${platform.apiUrl.replace(/\/$/, '')}/namespaces/${encodeURIComponent(platform.namespaceId)}/query`, { method: 'POST', headers: { Authorization: `Bearer ${idToken}`, 'Content-Type': 'application/json' }, body: JSON.stringify({ query, mode: 'standard', includeSupporting: true }), signal: requestSignal }))).json());
  if (mode === 'standard') response.result.trace.forEach(step => onStep?.(step));
  const result = response.result;
  let graph = graphFromContext(result.graphContext);
  let graphKind: Analysis['graphKind'] = graph.nodes.length ? 'retrieved-context' : 'empty';
  const warnings: string[] = ['Applicant inputs are hypothetical. This service provides source information; agencies assess eligibility and approve applications.'];
  if (!graph.edges.length && platform.ontologyId) {
    try { const schemaGraph = await loadOntologyGraph(platform, idToken, requestSignal, fetcher); if (schemaGraph.nodes.length) { graph = schemaGraph; graphKind = 'ontology-schema'; } }
    catch (error) { if (error instanceof PlatformRequestError && (error.status === 401 || error.status === 403)) throw error; if (signal?.aborted) throw error; warnings.push('The ontology graph could not be loaded. The answer and execution trace below are from the platform query.'); }
  }
  if (!graph.nodes.length) warnings.push('This query returned no graph entities. No graph relationships have been inferred for display.');
  if (result.partial) warnings.push('The platform marked this answer as partial. Review the source evidence and execution trace.');
  if (result.guardrailBlocked) warnings.push('The platform blocked this response with its content guardrail.');
  await resolveSupportingProvenance(result, catalogue, platform, query, idToken, requestSignal, fetcher, warnings);
  const citations = supportingEvidence(result, catalogue);
  const schemes = officialSchemes(persona, catalogue, graph.nodes, graph.edges);
  const answer = result.synthesizedAnswer || JSON.stringify(result.resultRows, null, 2);
  const income = profile.householdIncome, size = profile.householdSize;
  return {
    schemes, summary: `${schemes.length} source-backed programmes to explore. Agency assessment is required.`,
    metrics: { perCapitaIncome: typeof income === 'number' && typeof size === 'number' && size > 0 ? income / size : null, likelyEligible: 0, notEligible: 0, needsReview: schemes.length, rulesEvaluated: 0, graphNodes: graph.nodes.length, graphEdges: graph.edges.length, contextEntities: graph.nodes.length },
    reasoning: result.trace.map((step, index) => ({ step: index + 1, title: step.step.replace(/[_-]/g, ' '), detail: `${step.status} · ${step.durationMs} ms${step.detail ? ` · ${typeof step.detail === 'string' ? step.detail : JSON.stringify(step.detail)}` : ''}`, nodeIds: [], evidenceIds: [] })),
    citations, answer, engine: { graph: graphKind === 'ontology-schema' ? 'Neptune ontology schema' : 'Context platform graph', synthesis: 'Amazon Bedrock · full platform', accelerator: 'AWS Context Ontology Accelerator · Scan → Model → Serve' }, warnings, affectedNodeIds: [], highlightedEdgeIds: graph.edges.map(edge => edge.id),
    sourceMode: 'official', platformTrace: result.trace, graphNodes: graph.nodes, graphEdges: graph.edges, graphKind,
    context: { requestId: response.requestId, sessionId: response.sessionId, tier: result.tier, confidence: result.confidence, partial: result.partial, ontologyVersion: result.ontologyVersion, dataSources: result.dataSources, resultRows: result.resultRows, queryUsed: result.queryUsed, sparqlGenerated: result.sparqlGenerated, mode },
  };
}

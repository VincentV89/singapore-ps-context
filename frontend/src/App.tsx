import { useCallback, useEffect, useRef, useState } from 'react';
import type { User, UserManager } from 'oidc-client-ts';
import { Activity, ArrowLeft, BriefcaseBusiness, Building2, GraduationCap, ArrowDown, ArrowRight, ArrowUpRight, BookOpen, Check, CheckCircle2, ChevronDown, ChevronRight, CircleHelp, Download, FileCheck2, GitCompareArrows, HeartHandshake, Info, Layers3, LoaderCircle, LockKeyhole, LogOut, Network, RotateCcw, Send, ShieldCheck, Sparkles, Users, X, XCircle } from 'lucide-react';
import { createAuth, getAuthenticatedUser, isLocalPreview, signOut } from './auth';
import { Graph } from './Graph';
import { Brand } from './Brand';
import { analyzeOfficialScenario, loadOfficialScenario, PlatformRequestError } from './platform';
import type { Analysis, AppConfig, Evidence, GraphNode, Persona, PersonaId, Profile, ProfileValue, Scenario, Scheme, PlatformTraceStep } from './types';

const money = (n: number | null) => n === null ? 'Unknown' : `S$${n.toLocaleString('en-SG', { maximumFractionDigits: 2 })}`;
const schemeStatus = (scheme: Scheme) => scheme.sourceMode === 'official' ? 'Agency assessment required' : statusLabel[scheme.status];
const statusLabel = { 'likely-eligible': 'Likely eligible', 'not-eligible': 'Not eligible', 'needs-review': 'Needs review' };
const audienceCatalog: Persona[] = [
  { id: 'individuals', name: 'Individuals & Families', tagline: 'Support for everyday life', description: 'Navigate financial assistance, housing, healthcare, education, skills and family support.', segments: ['Parents', 'Students', 'Seniors', 'Caregivers', 'Jobseekers', 'Persons with disabilities'], contextTitle: 'Citizen context', profileTitle: 'Illustrative household', prompts: ['What support could this household receive?'], supportCategories: [], fields: [] },
  { id: 'businesses', name: 'Businesses & Entrepreneurs', tagline: 'Grow and transform', description: 'Explore digitalisation, AI adoption, workforce, R&D, sustainability and international growth.', segments: ['Startup founders', 'SME owners', 'Self-employed', 'Employers', 'Exporters'], contextTitle: 'Business context', profileTitle: 'Illustrative enterprise', prompts: ['What support could this business receive?'], supportCategories: [], fields: [] },
  { id: 'community', name: 'Nonprofits & Community Organisations', tagline: 'Fund social impact', description: 'Find support for community projects, social services, capability building, arts and youth programmes.', segments: ['Charities', 'Social service agencies', 'Community initiatives', 'Religious organisations', 'Arts groups'], contextTitle: 'Community context', profileTitle: 'Illustrative organisation', prompts: ['What support could this organisation receive?'], supportCategories: [], fields: [] },
  { id: 'research', name: 'Researchers & Educational Institutions', tagline: 'Advance knowledge', description: 'Discover research funding, innovation grants, scholarships and collaboration programmes.', segments: ['University researchers', 'Educators', 'Research institutes', 'Industry-academia partnerships'], contextTitle: 'Research context', profileTitle: 'Illustrative research team', prompts: ['What support could this research team receive?'], supportCategories: [], fields: [] },
];
const audienceIcons = { individuals: Users, businesses: BriefcaseBusiness, community: HeartHandshake, research: GraduationCap };


function App() {
  const [config, setConfig] = useState<AppConfig | null>(null);
  const [manager, setManager] = useState<UserManager | null>(null);
  const [user, setUser] = useState<User | null>(null);
  const [authReady, setAuthReady] = useState(false);
  const [authError, setAuthError] = useState('');
  const [personaId, setPersonaId] = useState<PersonaId | null>(null);
  const [personas, setPersonas] = useState<Persona[]>(audienceCatalog);
  const [supportFilter, setSupportFilter] = useState('');
  const [scenario, setScenario] = useState<Scenario | null>(null);
  const [profile, setProfile] = useState<Profile | null>(null);
  const [appliedProfile, setAppliedProfile] = useState<Profile | null>(null);
  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  const [baseline, setBaseline] = useState<Analysis | null>(null);
  const [activePreset, setActivePreset] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [question, setQuestion] = useState('');
  const [lastQuestion, setLastQuestion] = useState('');
  const [useBedrock, setUseBedrock] = useState(false);
  const [selectedScheme, setSelectedScheme] = useState<string | null>(null);
  const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null);
  const [selectedPolicy, setSelectedPolicy] = useState<Scheme | null>(null);
  const [selectedEvidence, setSelectedEvidence] = useState<Evidence | null>(null);
  const [showHow, setShowHow] = useState(false);
  const [showComparison, setShowComparison] = useState(false);
  const [checklistReady, setChecklistReady] = useState(false);
  const answerRef = useRef<HTMLDivElement>(null);
  const requestVersion = useRef(0);
  const platformController = useRef<AbortController | null>(null);
  const [platformSteps, setPlatformSteps] = useState<PlatformTraceStep[]>([]);
  const personaRef = useRef<PersonaId | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const response = await fetch('/config.json', { cache: 'no-store' });
        if (!response.ok) throw new Error('Application configuration could not be loaded.');
        const cfg: AppConfig = await response.json();
        const auth = createAuth(cfg);
        const authenticated = await getAuthenticatedUser(auth);
        if (!cancelled) { setConfig(cfg); setManager(auth); setUser(authenticated); }
      } catch (e) { if (!cancelled) setAuthError(e instanceof Error ? e.message : 'Sign-in could not be completed.'); }
      finally { if (!cancelled) setAuthReady(true); }
    })();
    return () => { cancelled = true; };
  }, []);

  const request = useCallback(async <T,>(path: string, body?: unknown): Promise<T> => {
    if (!config) throw new Error('Application configuration is not ready.');
    const authUser = manager ? await manager.getUser() : user;
    if (!isLocalPreview(config) && (!authUser || authUser.expired)) {
      setUser(null);
      throw new Error('Your session has expired. Sign in again to continue.');
    }
    const headers: Record<string, string> = { 'Content-Type': 'application/json' };
    if (authUser?.access_token) headers.Authorization = `Bearer ${authUser.access_token}`;
    const response = await fetch(`${config.apiUrl.replace(/\/$/, '')}${path}`, { method: body ? 'POST' : 'GET', headers, ...(body ? { body: JSON.stringify(body) } : {}), signal: AbortSignal.timeout(60000) });
    if (!response.ok) {
      if (response.status === 401) { setUser(null); throw new Error('Your session has expired. Sign in again to continue.'); }
      let detail = '';
      try { const data = await response.json(); detail = typeof data.detail === 'string' ? data.detail : typeof data.error === 'string' ? data.error : ''; } catch { /* HTTP status is sufficient for errors without JSON. */ }
      throw new Error(detail || `The service returned ${response.status}. Please try again.`);
    }
    return response.json();
  }, [config, manager, user]);

  const isFull = config?.platform?.mode === 'full';
  const runPlatform = async (audience: PersonaId, nextProfile: Profile, nextQuestion: string, deep = false) => {
    if (!config) throw new Error('Platform configuration is not ready.');
    const authUser = manager ? await manager.getUser() : user;
    if (!authUser?.id_token || authUser.expired) { setUser(null); throw new Error('Sign in to query the full platform.'); }
    platformController.current?.abort();
    const controller = new AbortController(); platformController.current = controller; setPlatformSteps([]);
    try { return await analyzeOfficialScenario({ config, persona: audience, profile: nextProfile, question: nextQuestion, idToken: authUser.id_token, mode: deep ? 'deep-reasoning' : 'standard', signal: controller.signal, onStep: step => { if (platformController.current === controller) setPlatformSteps(steps => [...steps, step]); } }); }
    catch (e) { if (e instanceof PlatformRequestError && e.status === 401) setUser(null); throw e; }
  };
  const updateGraph = (result: Analysis) => {
    if (result.sourceMode === 'official') setScenario(current => current ? { ...current, nodes: result.graphNodes || [], edges: result.graphEdges || [] } : current);
  };
  const sourceBadge = isFull ? 'Singapore agency sources · Demonstration' : 'Synthetic data · Illustrative policy';
  const allowed = Boolean(config && (user || isLocalPreview(config)));
  const clearWorkspace = () => {
    platformController.current?.abort(); setPlatformSteps([]);
    setScenario(null); setProfile(null); setAppliedProfile(null); setAnalysis(null); setBaseline(null);
    setActivePreset(''); setError(''); setQuestion(''); setLastQuestion(''); setSupportFilter('');
    setSelectedScheme(null); setSelectedNode(null); setSelectedEvidence(null); setShowComparison(false);
    setChecklistReady(false); setUseBedrock(false); setSelectedPolicy(null); setShowHow(false);
  };
  const choosePersona = async (id: PersonaId) => {
    const version = ++requestVersion.current;
    personaRef.current = id; setPersonaId(id); clearWorkspace(); setBusy(true);
    try {
      const data = isFull ? await loadOfficialScenario(id, fetch, config!.platform!.catalogueUrl) : await request<Scenario>(`/api/scenario?persona=${encodeURIComponent(id)}`);
      if (version !== requestVersion.current) return;
      setScenario(data); setPersonas(data.personas?.length ? data.personas : audienceCatalog);
      setProfile(data.profile); setAppliedProfile(data.profile); setActivePreset(data.presets[0]?.id || '');
      const prompt = data.persona.prompts[0]; setLastQuestion(prompt);
      const result = isFull ? await runPlatform(id, data.profile, prompt) : await request<Analysis>('/api/analyze', { persona: id, profile: data.profile, question: prompt, useBedrock: false });
      if (version !== requestVersion.current) return;
      setAnalysis(result); setBaseline(result); updateGraph(result);
    } catch (e) { if (version === requestVersion.current) setError(e instanceof Error ? e.message : 'The audience workspace could not be loaded.'); }
    finally { if (version === requestVersion.current) setBusy(false); }
  };
  const allAudiences = () => {
    ++requestVersion.current; personaRef.current = null; setPersonaId(null); setBusy(false); clearWorkspace();
  };
  useEffect(() => {
    if (!allowed) { platformController.current?.abort(); ++requestVersion.current; personaRef.current = null; setPersonaId(null); setBusy(false); }
  }, [allowed]);

  useEffect(() => {
    if (!manager) return;
    const expired = () => setUser(null);
    const loaded = (next: User) => setUser(next);
    manager.events.addUserLoaded(loaded); manager.events.addUserSignedOut(expired); manager.events.addAccessTokenExpired(expired);
    return () => { manager.events.removeUserLoaded(loaded); manager.events.removeUserSignedOut(expired); manager.events.removeAccessTokenExpired(expired); };
  }, [manager]);

  useEffect(() => {
    if (!(selectedNode || selectedEvidence || selectedPolicy || showHow)) return;
    const close = (e: KeyboardEvent) => {
      if (e.key === 'Escape') { if(selectedPolicy) setSelectedPolicy(null); else if(selectedEvidence) setSelectedEvidence(null); else { setSelectedNode(null); setShowHow(false); } }
      if (e.key === 'Tab') {
        const modals = document.querySelectorAll('.detail-modal');
        const modal = modals[modals.length - 1];
        const focusable = modal?.querySelectorAll<HTMLElement>('button:not([disabled]), a[href], input:not([disabled]), select:not([disabled]), [tabindex="0"]');
        if (focusable?.length) { const first = focusable[0], last = focusable[focusable.length-1]; if(e.shiftKey && document.activeElement===first) { e.preventDefault(); last.focus(); } else if(!e.shiftKey && document.activeElement===last) { e.preventDefault(); first.focus(); } }
      }
    };
    window.addEventListener('keydown', close); return () => window.removeEventListener('keydown', close);
  }, [selectedNode, selectedEvidence, selectedPolicy, showHow]);

  const analyze = async (nextProfile = profile, nextQuestion = lastQuestion) => {
    const audience = personaRef.current;
    if (!nextProfile || !audience || busy) return;
    const version = ++requestVersion.current;
    setBusy(true); setError(''); setChecklistReady(false);
    try {
      const result = isFull ? await runPlatform(audience, nextProfile, nextQuestion, useBedrock) : await request<Analysis>('/api/analyze', { persona: audience, profile: nextProfile, question: nextQuestion, useBedrock });
      if (version !== requestVersion.current) return;
      setAnalysis(result); updateGraph(result); setAppliedProfile(nextProfile); setLastQuestion(nextQuestion); setQuestion('');
    } catch (e) { if (version === requestVersion.current) setError(e instanceof Error ? e.message : 'Context could not be evaluated.'); }
    finally { if (version === requestVersion.current) setBusy(false); }
  };

  const selectPreset = (id: string) => {
    const preset = scenario?.presets.find(p => p.id === id);
    if (!preset || busy) return;
    setProfile(preset.profile); setActivePreset(id); setSelectedScheme(null);
    void analyze(preset.profile);
  };
  const updateProfile = (field: string, value: ProfileValue) => {
    if (!profile) return;
    setProfile({ ...profile, [field]: value }); setActivePreset('');
  };
  const evidenceById = (id: string) => scenario?.evidence.find(e => e.id === id) || analysis?.citations.find(e => e.id === id);
  const onNode = (node: GraphNode) => {
    if (node.type === 'scheme') setSelectedScheme(current => current === node.id ? null : node.id);
    setSelectedNode(node);
  };
  const downloadChecklist = () => {
    if (!analysis || !scenario) return;
    const relevant = analysis.schemes.filter(s => s.status !== 'not-eligible' && (!supportFilter || s.categories.includes(supportFilter)));
    const text = ['SG SUPPORT NAVIGATOR — SUPPORT RESEARCH', isFull ? 'Public agency sources with hypothetical applicant context. Verify criteria and current application calls with each agency.' : 'Synthetic data · Illustrative policy. This is not an application or official eligibility decision.', `Audience: ${scenario.persona.name}`, `Support type: ${scenario.persona.supportCategories.find(c => c.id === supportFilter)?.label || 'All support'}`, `Prepared: ${new Date().toISOString()}`, '', ...relevant.flatMap(s => [s.name, `Status: ${schemeStatus(s)}`, `Reason: ${s.reason}`, ...(isFull ? [] : ['Documents to prepare:']), ...s.documentIds.map(id => `  - ${scenario.nodes.find(n => n.id === id)?.label || id}`), s.sourceUrl ? `Official source: ${s.sourceUrl}` : '', s.sourceFetchedAt ? `Retrieved: ${s.sourceFetchedAt}` : '', 'Source evidence:', ...s.evidenceIds.map(id => { const e = evidenceById(id); return e ? `  - ${e.title}: ${e.excerpt}` : `  - ${id}`; }), '']), 'Engine:', `${analysis.engine.graph}; ${analysis.engine.accelerator}; synthesis: ${analysis.engine.synthesis}`].join('\n');
    const url = URL.createObjectURL(new Blob([text], { type: 'text/plain;charset=utf-8' }));
    const link = document.createElement('a'); link.href = url; link.download = isFull ? 'singapore-support-source-links.txt' : 'illustrative-support-checklist.txt'; link.click(); URL.revokeObjectURL(url); setChecklistReady(true);
  };

  if (!authReady) return <div className="full-loader"><Brand/><LoaderCircle className="spin" size={26}/><p>Connecting your context workspace…</p></div>;
  if (!allowed) return <div className="login-page"><header className="login-header"><Brand/><span className="synthetic-pill"><span/>{sourceBadge}</span></header><main className="login-content"><div className="login-copy"><div className="eyebrow">A SINGAPORE PUBLIC SECTOR DEMO</div><h1>Singapore support,<br/><em>connected.</em></h1><p>People, businesses and organisations have different needs. Connect their context with public support and policy evidence to reveal a clearer path forward.</p><button className="primary-button login-button" onClick={() => manager?.signinRedirect().catch(e => setAuthError(e.message))} disabled={!manager}><LockKeyhole size={17}/>Sign in to explore<ArrowRight size={17}/></button><div className="login-security"><ShieldCheck size={15}/>Secure sign-in with Amazon Cognito</div>{authError && <div role="alert" className="error-banner">{authError}</div>}{!manager && !authError && <div className="error-banner">Cognito is not configured. Add the deployed user pool settings to config.json.</div>}<div className="login-platform"><span>Built with</span><b>AWS Context Ontology Accelerator</b></div></div><div className="login-art" aria-hidden="true"><div className="art-ring ring-one"/><div className="art-ring ring-two"/><div className="art-ring ring-three"/><svg viewBox="0 0 620 600"><defs><linearGradient id="login-line"><stop stopColor="#ff98a3"/><stop offset="1" stopColor="#93c8f6"/></linearGradient></defs><g stroke="url(#login-line)" strokeWidth="1" fill="none" opacity=".6"><path d="M310 290L140 150M310 290L470 160M310 290L500 385M310 290L340 480M310 290L130 410M140 150L470 160M470 160L500 385M500 385L340 480M340 480L130 410M130 410L140 150"/></g>{[{x:310,y:290,label:'CONTEXT',icon:Users},{x:140,y:150,label:'PEOPLE',icon:Activity},{x:470,y:160,label:'SUPPORT',icon:HeartHandshake},{x:500,y:385,label:'ELIGIBILITY',icon:ShieldCheck},{x:340,y:480,label:'EVIDENCE',icon:FileCheck2},{x:130,y:410,label:'ORGANISATIONS',icon:Layers3}].map(({x,y,label,icon:Icon},i)=><g key={label} transform={`translate(${x},${y})`}><circle r={i===0?58:36} fill={i===0?'#f6f8fc':'#142637'} stroke="#8ac5a9" strokeWidth={i===0?0:1}/><foreignObject x={i===0?-16:-11} y={i===0?-21:-12} width="40" height="36"><Icon size={i===0?32:22} color={i===0?'#142637':'#bcdbc8'}/></foreignObject><text y={i===0?31:61} textAnchor="middle" fill={i===0?'#142637':'#bfccd8'} className="login-art-label">{label}</text></g>)}</svg><span className="art-caption">CONNECTIONS BECOME UNDERSTANDING.</span></div></main><footer className="login-footer">SG Support Navigator <span>{isFull ? 'An independent demonstration using public agency information. Not an official government service.' : 'Illustrative services and thresholds. No real personal or organisational records.'}</span></footer></div>;

  const activePersona = scenario?.persona || personas.find(p => p.id === personaId);
  const PersonaIcon = audienceIcons[personaId || 'individuals'];
  const visibleSchemes = analysis?.schemes.filter(s => !supportFilter || s.categories.includes(supportFilter)) || [];
  const visibleNodeIds = new Set(visibleSchemes.flatMap(s => [s.id, ...s.pathNodeIds]));
  const graphNodes = supportFilter && !isFull ? scenario?.nodes.filter(n => visibleNodeIds.has(n.id)) || [] : scenario?.nodes || [];
  const graphEdges = supportFilter && !isFull ? scenario?.edges.filter(e => visibleNodeIds.has(e.source) && visibleNodeIds.has(e.target)) || [] : scenario?.edges || [];
  const prompts = activePersona?.prompts || [];
  const selected = analysis?.schemes.find(s => s.id === selectedScheme);
  const currentScheme = selectedNode ? analysis?.schemes.find(s => s.id === selectedNode.id || s.graphNodeId === selectedNode.id || s.pathNodeIds.includes(selectedNode.id)) : null;
  const changed = analysis && baseline ? analysis.schemes.filter(s => baseline.schemes.find(b => b.id === s.id)?.status !== s.status).length : 0;
  const contextDirty = Boolean(profile && appliedProfile && JSON.stringify(profile) !== JSON.stringify(appliedProfile));
  return <div className="app-shell">
    <header className="app-header"><Brand/><nav aria-label="Main navigation"><button className="nav-active" onClick={allAudiences}>Find support</button><button onClick={() => setShowHow(true)}>How it works<ArrowUpRight size={12}/></button></nav><div className="header-right"><span className="synthetic-pill"><span/>{sourceBadge}</span><button className="account-button" title="Sign out" aria-label="Sign out" onClick={() => { void signOut(manager, config!); }}><span className="avatar">{user ? String(user.profile.email || user.profile.given_name || 'D').slice(0,1).toUpperCase() : 'D'}</span><span>{user ? 'Demo workspace' : 'Local preview'}</span><LogOut size={14}/></button></div></header>
    <main>
      {!personaId ? <AudienceLanding official={isFull} personas={personas} onChoose={id => void choosePersona(id)}/> : <>
      <div className="audience-navigation"><button className="back-audiences" onClick={allAudiences}><ArrowLeft size={15}/>All audiences</button><div className="audience-switcher" aria-label="Change audience">{personas.map(p => { const Icon = audienceIcons[p.id]; return <button key={p.id} aria-pressed={p.id === personaId} className={p.id === personaId ? 'selected' : ''} onClick={() => void choosePersona(p.id)}><Icon size={14}/><span>{p.id === 'individuals' ? 'Individuals & Families' : p.id === 'businesses' ? 'Businesses' : p.id === 'community' ? 'Nonprofits & Community' : 'Research & Education'}</span></button>; })}</div></div>
      <section className="hero persona-hero"><div><div className="eyebrow"><span className="small-line"/>GOVERNMENT SUPPORT · CONTEXT, CONNECTED</div><h1>{activePersona?.name}</h1><p>{activePersona?.description}</p></div><div className="hero-mark"><span className="live-dot"/><span>Powered by context<br/><b>Grounded in evidence</b></span><Network size={36} strokeWidth={1}/></div></section>
      <div className="scenario-bar"><div className="scenario-label"><Layers3 size={16}/><span>EXPLORE A SCENARIO</span></div><div className="preset-buttons">{scenario?.presets.map(p => <button key={p.id} className={activePreset === p.id ? 'selected' : ''} disabled={busy} onClick={() => selectPreset(p.id)}>{p.label}{activePreset === p.id && <Check size={13}/>}</button>)}</div><button className="reset-button" disabled={busy || !scenario} onClick={() => { if (scenario) { setProfile(scenario.profile); setActivePreset(scenario.presets[0]?.id || ''); setSelectedScheme(null); void analyze(scenario.profile); } }}><RotateCcw size={13}/>Reset</button></div>
      {error && <div className="error-banner" role="alert"><Info size={17}/>{error}<button className="text-button" onClick={() => personaId && void choosePersona(personaId)}>Retry</button></div>}
      {scenario && analysis && <section className="support-filter-bar" aria-label="Support type filters"><div className="support-filter-heading"><span>What kind of support are you looking for?</span><small>Optional · explore a support type</small></div><div className="support-filter-chips"><button aria-pressed={!supportFilter} className={!supportFilter ? 'selected' : ''} onClick={() => { setSupportFilter(''); setSelectedScheme(null); setSelectedNode(null); setSelectedEvidence(null); setChecklistReady(false); }}>All support</button>{scenario.persona.supportCategories.map(category => <button key={category.id} aria-pressed={supportFilter === category.id} className={supportFilter === category.id ? 'selected' : ''} onClick={() => { setSupportFilter(current => current === category.id ? '' : category.id); setSelectedScheme(null); setSelectedNode(null); setSelectedEvidence(null); setChecklistReady(false); }}>{category.label}</button>)}</div><div className="filter-result" aria-live="polite">Showing {visibleSchemes.length} of {analysis.schemes.length} {isFull ? 'published programmes' : 'illustrative pathways'}{supportFilter && <button className="text-button" onClick={() => { setSupportFilter(''); setSelectedScheme(null); setSelectedNode(null); setSelectedEvidence(null); setChecklistReady(false); }}>Clear filter<X size={12}/></button>}</div></section>}
      {contextDirty && <div className="pending-banner" role="status"><Info size={15}/><span>Your context has changed. Update context to refresh the graph, support pathways and assistant.</span><button className="text-button" disabled={busy} onClick={()=>void analyze()}>Apply changes<ArrowRight size={13}/></button></div>}
      {!scenario || !profile || !analysis ? <div className="workspace-loader"><LoaderCircle className="spin" size={27}/><h2>{error ? 'The workspace could not be loaded' : 'Connecting your context'}</h2><p>{error ? 'Use Retry to reconnect to the demo service.' : 'Loading the ontology, evidence and support pathways.'}</p>{isFull && platformSteps.length > 0 && <ol className="platform-progress" aria-live="polite">{platformSteps.map((step, i) => <li key={`${i}-${step.step}`}><span>{step.step.replace(/[_-]/g, ' ')}</span><small>{step.status} · {step.durationMs} ms</small></li>)}</ol>}</div> : <>
      <div id="workspace" className={`workspace ${busy ? 'is-updating' : ''}`}>
        <section className="panel context-panel"><div className="panel-heading"><div><div className="eyebrow">THE STARTING POINT</div><h2>{activePersona?.contextTitle}</h2></div><span className="round-icon"><PersonaIcon size={17}/></span></div><div className="resident-card"><span className="resident-avatar"><PersonaIcon size={20}/></span><div><strong>{activePersona?.profileTitle}</strong><small>Synthetic context · Singapore</small></div><span className="tiny-tag">DEMO</span></div>
          <form onSubmit={e => { e.preventDefault(); void analyze(); }}>
            <div className="context-form descriptor-form">{scenario.persona.fields.map(field => {
              const value = profile[field.key];
              if (field.type === 'boolean') return <div className="descriptor-toggle" key={field.key}><label className="toggle-row"><span>{field.label}</span><input type="checkbox" role="switch" checked={value === true} disabled={busy || value === null} onChange={e => updateProfile(field.key, e.target.checked)}/><span className="toggle-track"/></label>{field.allowUnknown && <label className="unknown-toggle"><input type="checkbox" aria-label={field.key === 'householdIncome' ? 'Income not yet known' : `${field.label} not yet known`} checked={value === null} disabled={busy} onChange={e => updateProfile(field.key, e.target.checked ? null : scenario.profile[field.key] ?? false)}/>Not yet known</label>}</div>;
              if (field.type === 'select') return <label className="select-field" key={field.key}>{field.label}<div><select aria-label={field.label} value={value === null ? '' : String(value ?? '')} disabled={busy} onChange={e => updateProfile(field.key, e.target.value === '' ? null : e.target.value)}>{field.allowUnknown && <option value="">Not yet known</option>}{field.options?.map(option => <option key={option.value} value={option.value}>{option.label}</option>)}</select><ChevronDown size={14}/></div></label>;
              return <div className="descriptor-number" key={field.key}><label className="input-label" htmlFor={`field-${field.key}`}>{field.label}</label><input id={`field-${field.key}`} aria-label={field.label} type="number" min={field.min} max={field.max} step={field.step ?? 1} value={value === null ? '' : Number(value ?? 0)} disabled={busy || value === null} onChange={e => updateProfile(field.key, e.target.value === '' ? null : Number(e.target.value))}/>{field.allowUnknown && <label className="unknown-toggle"><input type="checkbox" aria-label={field.key === 'householdIncome' ? 'Income not yet known' : `${field.label} not yet known`} checked={value === null} disabled={busy} onChange={e => updateProfile(field.key, e.target.checked ? null : scenario.profile[field.key] ?? 0)}/>Not yet known</label>}</div>;
            })}</div>{personaId === 'individuals' && <div className="per-capita"><span>Income per household member<small>Context derived from your inputs</small></span><strong>{money(profile.householdIncome === null || profile.householdSize === null ? null : Number(profile.householdIncome) / Math.max(1, Number(profile.householdSize)))}<small>/ month</small></strong></div>}<button className="primary-button update-button" type="submit" disabled={busy}>{busy ? <LoaderCircle size={16} className="spin"/> : <Sparkles size={16}/>}Update context<ArrowRight size={16}/></button><p className="context-hint">Change a fact. Discover how the pathway changes.</p>
          </form>
        </section>
        <div className="graph-column"><Graph key={personaId} nodes={graphNodes} edges={graphEdges} caption={isFull ? (analysis.graphKind === 'ontology-schema' ? 'Live Neptune ontology schema. Applicant context remains hypothetical.' : 'Entities and relationships returned by the live platform for this question.') : supportFilter ? `Support type: ${scenario.persona.supportCategories.find(c => c.id === supportFilter)?.label}. Eligibility stays based on your context.` : 'Follow the connections from your context to support, rules and evidence.'} highlighted={analysis.highlightedEdgeIds} selectedScheme={isFull ? analysis.schemes.find(s => s.id === selectedScheme)?.graphNodeId || null : selectedScheme} selectedNode={selectedNode?.id || null} onNode={onNode}/><div className="intelligence-strip"><div><span className="metric-icon"><Network size={18}/></span><strong>{analysis.metrics.contextEntities}<small>context entities</small></strong></div><div><span className="metric-icon"><ShieldCheck size={18}/></span><strong>{isFull ? analysis.context?.tier || '—' : analysis.metrics.rulesEvaluated}<small>{isFull ? 'resolution tier' : 'rules evaluated'}</small></strong></div><div><span className="metric-icon"><BookOpen size={18}/></span><strong>{scenario.evidence.length}<small>evidence sources</small></strong></div><span className="engine-chip"><span className="live-dot"/>{analysis.engine.graph}</span></div></div>
      </div>
      <div className="results-layout">
        <section className="support-section"><div className="section-heading"><div><div className="eyebrow">FROM CONTEXT TO ACTION</div><h2>Your support pathways <span className="number-badge">{visibleSchemes.length}</span></h2><p>{isFull ? 'Published programmes to explore with their administering agencies.' : 'Every recommendation has a traceable reason.'}</p></div>{!isFull && <button className={`secondary-button compare-button ${showComparison ? 'active' : ''}`} onClick={() => setShowComparison(v => !v)}><GitCompareArrows size={15}/>{showComparison ? 'Hide comparison' : 'Compare changes'}{changed > 0 && <span className="change-count">{changed}</span>}</button>}</div>
          {showComparison && baseline && <div className="comparison-panel"><div className="comparison-heading"><GitCompareArrows size={16}/><strong>Compared with the starting context</strong><span>{changed ? `${changed} pathway${changed === 1 ? '' : 's'} changed` : 'No eligibility changes yet'}</span></div>{visibleSchemes.map(s => <div className="comparison-row" key={s.id}><span>{s.name}</span><span className={`mini-status ${baseline.schemes.find(b => b.id === s.id)?.status}`}>{statusLabel[baseline.schemes.find(b => b.id === s.id)?.status || s.status]}</span><ArrowRight size={13}/><span className={`mini-status ${s.status}`}>{statusLabel[s.status]}</span></div>)}</div>}
          <div className="scheme-grid">{visibleSchemes.map((scheme, i) => <SchemeCard key={scheme.id} scheme={scheme} index={i} selected={selectedScheme === scheme.id} onSelect={() => setSelectedScheme(current => current === scheme.id ? null : scheme.id)} onDetails={() => { setSelectedScheme(scheme.id); if (isFull) { setSelectedPolicy(scheme); return; } const node = scenario.nodes.find(n => n.id === scheme.id); if (node) setSelectedNode(node); }} />)}</div>
          {visibleSchemes.length === 0 && <div className="empty-support"><CircleHelp size={25}/><h3>{isFull ? 'No captured programmes in this support type' : 'No illustrative pathways in this support type yet'}</h3><p>Try another support type or view all support. {isFull ? 'This catalogue covers a selected set of official public sources.' : 'This demo includes a curated set of fictional schemes.'}</p><button className="secondary-button" onClick={() => setSupportFilter('')}>Show all support<ArrowRight size={14}/></button></div>}
          <div className="checklist-panel"><span className="checklist-icon"><FileCheck2 size={22}/></span><div><strong>A clearer next step</strong><p>{isFull ? 'Save the official source links and criteria to discuss with the agency.' : 'Prepare a checklist of documents and the evidence behind your pathways.'}</p></div><button className="secondary-button" disabled={!visibleSchemes.some(s => s.status !== 'not-eligible')} onClick={downloadChecklist}><Download size={14}/>{checklistReady ? 'Download again' : isFull ? 'Save source links' : 'Prepare checklist'}</button></div>
        </section>
        <section className="panel assistant-panel" ref={answerRef}><div className="panel-heading"><div><div className="eyebrow">ASK WITH CONTEXT</div><h2>Your context assistant</h2></div><span className="assistant-symbol"><Sparkles size={19}/></span></div><div className="assistant-grounding"><ShieldCheck size={13}/>Grounded in the graph and cited evidence</div><div className="question-bubble">{lastQuestion}</div><div className="answer-body" aria-live="polite"><div className="answer-label"><span className="assistant-mini"><Sparkles size={12}/></span>CONTEXT INTELLIGENCE{busy && <LoaderCircle className="spin" size={13}/>}</div><AnswerText answer={analysis.answer} citations={analysis.citations} onEvidence={setSelectedEvidence}/></div><div className="citation-chips">{analysis.citations.slice(0,4).map((e,i) => <button key={e.id} onClick={() => setSelectedEvidence(e)}><BookOpen size={11}/><span>{i+1}</span>{e.title}<ArrowUpRight size={10}/></button>)}</div><details className="reasoning-details"><summary><Layers3 size={13}/>Trace the reasoning<ChevronDown size={13}/></summary><ol>{analysis.reasoning.map(step => <li key={step.step}><strong>{step.title}</strong><p>{step.detail}</p>{step.evidenceIds.slice(0,2).map(id => <button key={id} className="text-button" onClick={() => { const e=evidenceById(id); if(e) setSelectedEvidence(e); }}><BookOpen size={10}/>Evidence</button>)}</li>)}</ol></details><div className="assistant-bottom"><div className="suggested-prompts">{prompts.slice(1).map(prompt => <button key={prompt} disabled={busy} onClick={() => void analyze(profile,prompt)}>{prompt}<ArrowUpRight size={11}/></button>)}</div><form className="ask-form" onSubmit={e => { e.preventDefault(); if(question.trim()) void analyze(profile, question.trim()); }}><input aria-label="Ask a question about this context" placeholder="Ask about this context…" maxLength={1200} value={question} disabled={busy} onChange={e => setQuestion(e.target.value)}/><button aria-label="Send question" disabled={busy || !question.trim()}><Send size={16}/></button></form><div className="synthesis-control"><label><input type="checkbox" checked={useBedrock} disabled={busy} onChange={e => setUseBedrock(e.target.checked)}/>{isFull ? 'Deep context reasoning' : 'Use Amazon Bedrock synthesis'}</label><span title={analysis.engine.accelerator}>{isFull ? 'Amazon Bedrock · AgentCore' : analysis.engine.synthesis === 'Amazon Bedrock' ? 'Amazon Bedrock' : 'Deterministic'}</span></div></div></section>
      </div>
      {analysis.warnings?.length > 0 && <div className="warnings"><Info size={14}/><span>{analysis.warnings.join(' ')}</span></div>}
      <div className="demo-note"><Info size={15}/><p><strong>A demonstration of connected intelligence.</strong> {isFull ? 'Programme information comes from dated Singapore agency sources. Applicant profiles are hypothetical. Agency assessment, current calls and full application criteria determine eligibility. This is an independent demonstration, not an official government service.' : 'These services, thresholds and benefits are fictional. Recommendations explain illustrative rules and are not official eligibility decisions. No real personal or organisational data is used.'}</p></div>
      </>}
      </>}
    </main>
    <footer className="app-footer"><span>SG Support Navigator <span className="footer-dot">·</span> Singapore public sector demo</span><a href="https://github.com/aws/context-ontology-accelerator" target="_blank" rel="noreferrer">AWS Context Ontology Accelerator<ArrowUpRight size={12}/></a><span>Amazon Web Services <span className="footer-dot">·</span> {config?.region}</span></footer>
    {selectedNode && <div className="modal-backdrop" onClick={() => setSelectedNode(null)}><section className="detail-modal" role="dialog" aria-modal="true" aria-labelledby="node-title" onClick={e=>e.stopPropagation()}><div className="modal-heading"><div><div className="eyebrow">{selectedNode.type.toUpperCase()} · CONNECTED ENTITY</div><h2 id="node-title">{selectedNode.label}</h2></div><button className="icon-button" autoFocus aria-label="Close entity details" onClick={()=>setSelectedNode(null)}><X size={20}/></button></div><p className="modal-description">{selectedNode.description || 'This entity connects audience context to support pathways in the illustrative ontology.'}</p>{currentScheme && <><div className="detail-status"><StatusIcon status={currentScheme.status}/><span className={`status-badge ${currentScheme.status}`}>{schemeStatus(currentScheme)}</span><span>{currentScheme.agency}</span></div><p className="scheme-reason">{currentScheme.reason}</p>{currentScheme.ruleResults.length > 0 && <div className="detail-section"><h3>Rules and evidence</h3>{currentScheme.ruleResults.map(rule=><div key={rule.id} className="rule-row"><span className={`rule-icon ${rule.result}`}>{rule.result==='pass'?<CheckCircle2 size={17}/>:rule.result==='fail'?<XCircle size={17}/>:<CircleHelp size={17}/>}</span><div><strong>{rule.label}</strong><small>Observed: {formatValue(rule.actual)} <span>·</span> Required: {rule.operator} {formatValue(rule.expected)}</small></div><button aria-label={`Show evidence for ${rule.label}`} className="icon-button" onClick={()=>{const e=evidenceById(rule.evidenceId);if(e)setSelectedEvidence(e);}}><BookOpen size={16}/></button></div>)}</div>}{currentScheme.documentIds.length > 0 && <div className="detail-section"><h3>Documents to prepare</h3><div className="document-list">{currentScheme.documentIds.map(id=><span key={id}><FileCheck2 size={15}/>{scenario?.nodes.find(n=>n.id===id)?.label || id}</span>)}</div></div>}{currentScheme.sourceMode === 'official' && <button className="secondary-button" onClick={() => { setSelectedNode(null); setSelectedPolicy(currentScheme); }}>View official criteria<ArrowUpRight size={14}/></button>}</>}{!currentScheme && <div className="detail-section"><h3>Connected relationships</h3>{scenario?.edges.filter(e=>e.source===selectedNode.id||e.target===selectedNode.id).map(edge=><button key={edge.id} className="relationship-row" onClick={()=>{const next=scenario.nodes.find(n=>n.id===(edge.source===selectedNode.id?edge.target:edge.source));if(next)onNode(next);}}><span>{edge.label}</span><strong>{scenario.nodes.find(n=>n.id===(edge.source===selectedNode.id?edge.target:edge.source))?.label}</strong><ChevronRight size={15}/></button>)}</div>}<div className="modal-footer"><Network size={14}/><span>Entity ID: {selectedNode.id}</span><span>{isFull ? 'Live platform graph' : 'Synthetic ontology'}</span></div></section></div>}
    {selectedPolicy && <div className="modal-backdrop" onClick={() => setSelectedPolicy(null)}><section className="detail-modal" role="dialog" aria-modal="true" aria-labelledby="policy-title" onClick={e => e.stopPropagation()}><div className="modal-heading"><div><div className="eyebrow">PUBLISHED PROGRAMME · OFFICIAL SOURCE</div><h2 id="policy-title">{selectedPolicy.name}</h2></div><button className="icon-button" autoFocus aria-label="Close programme details" onClick={() => setSelectedPolicy(null)}><X size={20}/></button></div><span className="source-pill">{selectedPolicy.agency}</span><p className="modal-description">{selectedPolicy.summary}</p><div className="detail-section"><h3>Published criteria</h3><blockquote>{selectedPolicy.eligibilityText || 'Full applicant criteria were not included in the captured overview. Consult the agency source and current application call.'}</blockquote></div><div className="detail-section"><h3>Support described by the agency</h3><p>{selectedPolicy.benefit}</p></div>{selectedPolicy.lifecycleText && <div className="detail-section"><h3>Programme updates</h3><blockquote>{selectedPolicy.lifecycleText}</blockquote></div>}<p className="evidence-disclaimer">Agency assessment required. Check full criteria, current calls and application requirements with the agency.</p><div className="policy-links">{selectedPolicy.sourceUrl && <a className="secondary-button" href={selectedPolicy.sourceUrl} target="_blank" rel="noreferrer">Official source<ArrowUpRight size={14}/></a>}{selectedPolicy.applicationUrl && <a className="secondary-button" href={selectedPolicy.applicationUrl} target="_blank" rel="noreferrer">Application information<ArrowUpRight size={14}/></a>}</div><div className="modal-footer"><span>Source status: {selectedPolicy.sourceStatus}</span><span>Retrieved {selectedPolicy.sourceFetchedAt?.slice(0,10)}</span></div></section></div>}
    {selectedEvidence && <div className="modal-backdrop evidence-backdrop" onClick={()=>setSelectedEvidence(null)}><section className="detail-modal evidence-modal" role="dialog" aria-modal="true" aria-labelledby="evidence-title" onClick={e=>e.stopPropagation()}><div className="modal-heading"><div><div className="eyebrow">SOURCE EVIDENCE</div><h2 id="evidence-title">{selectedEvidence.title}</h2></div><button className="icon-button" autoFocus aria-label="Close evidence" onClick={()=>setSelectedEvidence(null)}><X size={20}/></button></div><span className="source-pill"><BookOpen size={14}/>{selectedEvidence.source}</span><blockquote>{selectedEvidence.excerpt}</blockquote><div className="evidence-disclaimer"><Info size={16}/>{isFull ? 'Retrieved source evidence. Verify the full criteria and current programme status with the administering agency.' : 'This is a synthetic policy source prepared for this demo. It does not describe an official Singapore government scheme.'}{selectedEvidence.url && <a href={selectedEvidence.url} target="_blank" rel="noreferrer">Open official source<ArrowUpRight size={14}/></a>}</div><div className="modal-footer"><span>Evidence ID: {selectedEvidence.id}</span>{selectedEvidence.updatedAt&&<span>{isFull ? 'Retrieved' : 'Updated'} {selectedEvidence.updatedAt.slice(0,10)}</span>}</div></section></div>}
    {showHow && <div className="modal-backdrop" onClick={()=>setShowHow(false)}><section className="detail-modal how-modal" role="dialog" aria-modal="true" aria-labelledby="how-title" onClick={e=>e.stopPropagation()}><div className="modal-heading"><div><div className="eyebrow">BEHIND THE EXPERIENCE</div><h2 id="how-title">Context makes the connection.</h2></div><button className="icon-button" autoFocus aria-label="Close explanation" onClick={()=>setShowHow(false)}><X size={20}/></button></div><p className="modal-description">The same fact can tell a different story when connected to a household, business, community project or research team and its policy rules.</p><div className="how-steps">{(isFull ? [{n:'01',title:'Scan official sources',text:'Official policy snapshots and programme tables are registered, scanned and reviewed in the platform.'},{n:'02',title:'Model the relationships',text:'A Singapore support ontology grounds model induction. Reviewed ontology proposals and mappings connect agencies, programmes, audiences and source evidence.'},{n:'03',title:'Serve connected context',text:'The live service retrieves graph, structured and document context through Neptune, the virtual graph and OpenSearch. Its execution trace shows which steps actually ran.'},{n:'04',title:'Verify with the agency',text:'Amazon Bedrock explains retrieved evidence. Public programme discovery supports navigation; the administering agency makes eligibility and funding decisions.'}] : [{n:'01',title:'Connect the context',text:'Importable ontologies describe people, organisations, goals, support schemes, eligibility rules, documents and agencies.'},{n:'02',title:'Traverse the graph',text:'RDF and SPARQL connect the selected audience’s facts with the relevant support pathways using accelerator graph traversal patterns.'},{n:'03',title:'Evaluate and explain',text:'Explicit rules produce pass, fail or unknown results. Every pathway traces to synthetic policy evidence.'},{n:'04',title:'Synthesize with evidence',text:'The assistant explains graph findings deterministically, with optional Amazon Bedrock synthesis when available.'}]).map(step=><div key={step.n}><span>{step.n}</span><div><strong>{step.title}</strong><p>{step.text}</p></div></div>)}</div><a className="secondary-button accelerator-link" href="https://github.com/aws/context-ontology-accelerator" target="_blank" rel="noreferrer">Explore the accelerator<ArrowUpRight size={15}/></a></section></div>}
  </div>;
}
function AudienceLanding({ personas, onChoose, official }: { official?: boolean; personas: Persona[]; onChoose: (id: PersonaId) => void }) {
  return <section className="audience-landing" aria-labelledby="find-support-title"><div className="audience-intro"><div className="eyebrow"><span className="small-line"/>SINGAPORE PUBLIC SECTOR · CONNECTED SUPPORT</div><h1 id="find-support-title">Find support in <em>Singapore</em></h1><p>Discover grants, subsidies and funding pathways through connected context.</p><span className="audience-intro-hint">Choose who you’re finding support for</span></div><div className="audience-cards">{personas.map((persona, i) => { const Icon = audienceIcons[persona.id]; return <button className={`persona-card audience-card audience-${persona.id}`} key={persona.id} onClick={() => onChoose(persona.id)}><div className="audience-card-top"><span className="audience-icon"><Icon size={28} strokeWidth={1.5}/></span><span className="audience-number">0{i + 1}</span></div><h2>{persona.name}</h2><strong>{persona.tagline}</strong><p>{persona.description}</p><div className="audience-segments">{persona.segments.slice(0, 5).map(segment => <span key={segment}>{segment}</span>)}</div><div className="audience-card-footer"><span>Explore support pathways</span><ArrowUpRight size={18}/></div></button>; })}</div><div className="audience-bottom-note"><span className="live-dot"/><span>One connected model. Four starting points.</span><small>{official ? 'Official agency information · Hypothetical applicant profiles · Source dates included' : 'All schemes, thresholds and records in this demo are synthetic.'}</small></div></section>;
}
function StatusIcon({status}:{status:Scheme['status']}) { return status==='likely-eligible'?<CheckCircle2 size={16}/>:status==='not-eligible'?<XCircle size={16}/>:<CircleHelp size={16}/>; }
function formatValue(value: unknown): string { if(value===null||value===undefined)return 'unknown';if(typeof value==='boolean')return value?'yes':'no';if(Array.isArray(value))return value.join(' or ');return String(value).replace(/\|/g,' or '); }
function AnswerText({ answer, citations, onEvidence }: { answer: string; citations: Evidence[]; onEvidence: (e: Evidence)=>void }) {
  return <div className="answer-content">{answer.split(/(?<=\])\s+/).map((paragraph,i)=><p key={i}>{paragraph.split(/(\[[^\]]+\])/).map((part,j)=>{
    const id=part.startsWith('[')&&part.endsWith(']')?part.slice(1,-1):'';
    const index=citations.findIndex(e=>e.id===id);
    return index>=0?<button key={j} className="inline-citation" title={citations[index].title} onClick={()=>onEvidence(citations[index])}>[{index+1}]</button>:part;
  })}</p>)}</div>;
}
function SchemeCard({scheme,index,selected,onSelect,onDetails}:{scheme:Scheme;index:number;selected:boolean;onSelect:()=>void;onDetails:()=>void}) {
  const passed=scheme.ruleResults.filter(r=>r.result==='pass').length;
  return <article className={`scheme-card ${scheme.status} ${selected?'selected':''}`}><div className="scheme-top"><span className="scheme-number">0{index+1}</span><span className={`status-badge ${scheme.status}`}><StatusIcon status={scheme.status}/>{schemeStatus(scheme)}</span></div><button className="scheme-title" onClick={onSelect}>{scheme.name}<Network size={16}/></button><div className="scheme-agency">{scheme.agency}</div><p className="scheme-card-reason">{scheme.reason}</p><div className="benefit-line"><HeartHandshake size={14}/><span>{typeof scheme.benefit === 'string' ? scheme.benefit : JSON.stringify(scheme.benefit)}</span></div><div className="scheme-bottom"><span className="rule-progress"><span>{scheme.ruleResults.map(r=><i key={r.id} className={r.result}/>)}</span>{scheme.sourceMode === 'official' ? 'Official agency source' : `${passed}/${scheme.ruleResults.length} rules met`}</span><button onClick={onDetails}>{scheme.sourceMode === 'official' ? 'View source & criteria' : 'View reasoning'}<ArrowUpRight size={13}/></button></div></article>;
}
export default App;

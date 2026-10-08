import { useCallback, useEffect, useRef, useState } from 'react';
import type { User, UserManager } from 'oidc-client-ts';
import { Activity, ArrowDown, ArrowRight, ArrowUpRight, BookOpen, Check, CheckCircle2, ChevronDown, ChevronRight, CircleHelp, Download, FileCheck2, GitCompareArrows, HeartHandshake, Info, Layers3, LoaderCircle, LockKeyhole, LogOut, Network, RotateCcw, Send, ShieldCheck, Sparkles, Users, X, XCircle } from 'lucide-react';
import { createAuth, getAuthenticatedUser, isLocalPreview, signOut } from './auth';
import { Graph } from './Graph';
import type { Analysis, AppConfig, Evidence, GraphNode, Profile, Scenario, Scheme } from './types';

const money = (n: number | null) => n === null ? 'Unknown' : `S$${n.toLocaleString('en-SG', { maximumFractionDigits: 2 })}`;
const statusLabel = { 'likely-eligible': 'Likely eligible', 'not-eligible': 'Not eligible', 'needs-review': 'Needs review' };
const prompts = ['What support could this household receive?', 'Why is the household eligible?', 'Why does Caregiver Relief not match?'];
const initialQuestion = prompts[0];

function Brand() { return <a className="brand" href="/" aria-label="Life Events Navigator home"><span className="brand-symbol"><Network size={24}/></span><span>life<span className="brand-light">events</span><small>CONTEXT INTELLIGENCE</small></span></a>; }
function App() {
  const [config, setConfig] = useState<AppConfig | null>(null);
  const [manager, setManager] = useState<UserManager | null>(null);
  const [user, setUser] = useState<User | null>(null);
  const [authReady, setAuthReady] = useState(false);
  const [authError, setAuthError] = useState('');
  const [scenario, setScenario] = useState<Scenario | null>(null);
  const [profile, setProfile] = useState<Profile | null>(null);
  const [appliedProfile, setAppliedProfile] = useState<Profile | null>(null);
  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  const [baseline, setBaseline] = useState<Analysis | null>(null);
  const [activePreset, setActivePreset] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [question, setQuestion] = useState('');
  const [lastQuestion, setLastQuestion] = useState(initialQuestion);
  const [useBedrock, setUseBedrock] = useState(false);
  const [selectedScheme, setSelectedScheme] = useState<string | null>(null);
  const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null);
  const [selectedEvidence, setSelectedEvidence] = useState<Evidence | null>(null);
  const [showHow, setShowHow] = useState(false);
  const [showComparison, setShowComparison] = useState(false);
  const [checklistReady, setChecklistReady] = useState(false);
  const answerRef = useRef<HTMLDivElement>(null);
  const initialized = useRef(false);

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

  const allowed = Boolean(config && (user || isLocalPreview(config)));
  useEffect(() => {
    if (!allowed || initialized.current) return;
    initialized.current = true;
    setBusy(true);
    (async () => {
      try {
        const data = await request<Scenario>('/api/scenario');
        setScenario(data); setProfile(data.profile); setAppliedProfile(data.profile); setActivePreset(data.presets[0]?.id || '');
        const result = await request<Analysis>('/api/analyze', { profile: data.profile, question: initialQuestion, useBedrock: false });
        setAnalysis(result); setBaseline(result);
      } catch (e) { setError(e instanceof Error ? e.message : 'The scenario could not be loaded.'); initialized.current = false; }
      finally { setBusy(false); }
    })();
  }, [allowed, request]);

  useEffect(() => {
    if (!manager) return;
    const expired = () => setUser(null);
    const loaded = (next: User) => setUser(next);
    manager.events.addUserLoaded(loaded); manager.events.addUserSignedOut(expired); manager.events.addAccessTokenExpired(expired);
    return () => { manager.events.removeUserLoaded(loaded); manager.events.removeUserSignedOut(expired); manager.events.removeAccessTokenExpired(expired); };
  }, [manager]);

  useEffect(() => {
    if (!(selectedNode || selectedEvidence || showHow)) return;
    const close = (e: KeyboardEvent) => {
      if (e.key === 'Escape') { if(selectedEvidence) setSelectedEvidence(null); else { setSelectedNode(null); setShowHow(false); } }
      if (e.key === 'Tab') {
        const modals = document.querySelectorAll('.detail-modal');
        const modal = modals[modals.length - 1];
        const focusable = modal?.querySelectorAll<HTMLElement>('button:not([disabled]), a[href], input:not([disabled]), select:not([disabled]), [tabindex="0"]');
        if (focusable?.length) { const first = focusable[0], last = focusable[focusable.length-1]; if(e.shiftKey && document.activeElement===first) { e.preventDefault(); last.focus(); } else if(!e.shiftKey && document.activeElement===last) { e.preventDefault(); first.focus(); } }
      }
    };
    window.addEventListener('keydown', close); return () => window.removeEventListener('keydown', close);
  }, [selectedNode, selectedEvidence, showHow]);

  const analyze = async (nextProfile = profile, nextQuestion = lastQuestion) => {
    if (!nextProfile || busy) return;
    setBusy(true); setError(''); setChecklistReady(false);
    try {
      const result = await request<Analysis>('/api/analyze', { profile: nextProfile, question: nextQuestion, useBedrock });
      setAnalysis(result); setAppliedProfile(nextProfile); setLastQuestion(nextQuestion); setQuestion('');
    } catch (e) { setError(e instanceof Error ? e.message : 'Context could not be evaluated.'); }
    finally { setBusy(false); }
  };

  const selectPreset = (id: string) => {
    const preset = scenario?.presets.find(p => p.id === id);
    if (!preset || busy) return;
    setProfile(preset.profile); setActivePreset(id); setSelectedScheme(null);
    void analyze(preset.profile);
  };
  const updateProfile = <K extends keyof Profile>(field: K, value: Profile[K]) => {
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
    const relevant = analysis.schemes.filter(s => s.status !== 'not-eligible');
    const text = ['LIFE EVENTS NAVIGATOR — ILLUSTRATIVE CHECKLIST', 'Synthetic data · Illustrative policy. This is not an application or official eligibility decision.', `Prepared: ${new Date().toISOString()}`, '', ...relevant.flatMap(s => [s.name, `Status: ${statusLabel[s.status]}`, `Reason: ${s.reason}`, 'Documents to prepare:', ...s.documentIds.map(id => `  - ${scenario.nodes.find(n => n.id === id)?.label || id}`), 'Rule evidence:', ...s.evidenceIds.map(id => { const e = evidenceById(id); return e ? `  - ${e.title}: ${e.excerpt}` : `  - ${id}`; }), '']), 'Engine:', `${analysis.engine.graph}; ${analysis.engine.accelerator}; synthesis: ${analysis.engine.synthesis}`].join('\n');
    const url = URL.createObjectURL(new Blob([text], { type: 'text/plain;charset=utf-8' }));
    const link = document.createElement('a'); link.href = url; link.download = 'illustrative-support-checklist.txt'; link.click(); URL.revokeObjectURL(url); setChecklistReady(true);
  };

  if (!authReady) return <div className="full-loader"><Brand/><LoaderCircle className="spin" size={26}/><p>Connecting your context workspace…</p></div>;
  if (!allowed) return <div className="login-page"><header className="login-header"><Brand/><span className="synthetic-pill"><span/>Synthetic data · Illustrative policy</span></header><main className="login-content"><div className="login-copy"><div className="eyebrow">A SINGAPORE PUBLIC SECTOR DEMO</div><h1>Services that see<br/>the <em>whole picture.</em></h1><p>A life change rarely fits into one form. Connect citizen context, public services and policy evidence to reveal a clearer path forward.</p><button className="primary-button login-button" onClick={() => manager?.signinRedirect().catch(e => setAuthError(e.message))} disabled={!manager}><LockKeyhole size={17}/>Sign in to explore<ArrowRight size={17}/></button><div className="login-security"><ShieldCheck size={15}/>Secure sign-in with Amazon Cognito</div>{authError && <div role="alert" className="error-banner">{authError}</div>}{!manager && !authError && <div className="error-banner">Cognito is not configured. Add the deployed user pool settings to config.json.</div>}<div className="login-platform"><span>Built with</span><b>AWS Context Ontology Accelerator</b></div></div><div className="login-art" aria-hidden="true"><div className="art-ring ring-one"/><div className="art-ring ring-two"/><div className="art-ring ring-three"/><svg viewBox="0 0 620 600"><defs><linearGradient id="login-line"><stop stopColor="#aedea7"/><stop offset="1" stopColor="#74cdbb"/></linearGradient></defs><g stroke="url(#login-line)" strokeWidth="1" fill="none" opacity=".6"><path d="M310 290L140 150M310 290L470 160M310 290L500 385M310 290L340 480M310 290L130 410M140 150L470 160M470 160L500 385M500 385L340 480M340 480L130 410M130 410L140 150"/></g>{[{x:310,y:290,label:'CITIZEN',icon:Users},{x:140,y:150,label:'LIFE EVENTS',icon:Activity},{x:470,y:160,label:'SUPPORT',icon:HeartHandshake},{x:500,y:385,label:'ELIGIBILITY',icon:ShieldCheck},{x:340,y:480,label:'EVIDENCE',icon:FileCheck2},{x:130,y:410,label:'HOUSEHOLD',icon:Layers3}].map(({x,y,label,icon:Icon},i)=><g key={label} transform={`translate(${x},${y})`}><circle r={i===0?58:36} fill={i===0?'#c7e7a6':'#142637'} stroke="#8ac5a9" strokeWidth={i===0?0:1}/><foreignObject x={i===0?-16:-11} y={i===0?-21:-12} width="40" height="36"><Icon size={i===0?32:22} color={i===0?'#142637':'#bcdbc8'}/></foreignObject><text y={i===0?31:61} textAnchor="middle" fill={i===0?'#142637':'#bfccd8'} className="login-art-label">{label}</text></g>)}</svg><span className="art-caption">CONNECTIONS BECOME UNDERSTANDING.</span></div></main><footer className="login-footer">Life Events Navigator <span>Illustrative services and thresholds. No real citizen records.</span></footer></div>;

  const selected = analysis?.schemes.find(s => s.id === selectedScheme);
  const currentScheme = selectedNode ? analysis?.schemes.find(s => s.id === selectedNode.id || s.pathNodeIds.includes(selectedNode.id)) : null;
  const changed = analysis && baseline ? analysis.schemes.filter(s => baseline.schemes.find(b => b.id === s.id)?.status !== s.status).length : 0;
  const contextDirty = Boolean(profile && appliedProfile && JSON.stringify(profile) !== JSON.stringify(appliedProfile));
  return <div className="app-shell">
    <header className="app-header"><Brand/><nav aria-label="Main navigation"><a className="nav-active" href="#workspace">Explore context</a><button onClick={() => setShowHow(true)}>How it works<ArrowUpRight size={12}/></button></nav><div className="header-right"><span className="synthetic-pill"><span/>Synthetic data · Illustrative policy</span><button className="account-button" title="Sign out" aria-label="Sign out" onClick={() => { void signOut(manager, config!); }}><span className="avatar">{user ? String(user.profile.email || user.profile.given_name || 'D').slice(0,1).toUpperCase() : 'D'}</span><span>{user ? 'Demo workspace' : 'Local preview'}</span><LogOut size={14}/></button></div></header>
    <main>
      <section className="hero"><div><div className="eyebrow"><span className="small-line"/>LIFE EVENTS NAVIGATOR · CITIZEN SERVICES, CONNECTED</div><h1>One life change.<br className="mobile-only"/> <em>A clearer path forward.</em></h1><p>See how a household’s changing circumstances connect to the right support.</p></div><div className="hero-mark"><span className="live-dot"/><span>Powered by context<br/><b>Grounded in evidence</b></span><Network size={36} strokeWidth={1}/></div></section>
      <div className="scenario-bar"><div className="scenario-label"><Layers3 size={16}/><span>EXPLORE A LIFE EVENT</span></div><div className="preset-buttons">{scenario?.presets.map(p => <button key={p.id} className={activePreset === p.id ? 'selected' : ''} disabled={busy} onClick={() => selectPreset(p.id)}>{p.label}{activePreset === p.id && <Check size={13}/>}</button>)}</div><button className="reset-button" disabled={busy || !scenario} onClick={() => { if (scenario) { setProfile(scenario.profile); setActivePreset(scenario.presets[0]?.id || ''); setSelectedScheme(null); void analyze(scenario.profile); } }}><RotateCcw size={13}/>Reset</button></div>
      {error && <div className="error-banner" role="alert"><Info size={17}/>{error}<button className="text-button" onClick={() => profile ? void analyze() : window.location.reload()}>Retry</button></div>}
      {contextDirty && <div className="pending-banner" role="status"><Info size={15}/><span>Your context has changed. Update context to refresh the graph, support pathways and assistant.</span><button className="text-button" disabled={busy} onClick={()=>void analyze()}>Apply changes<ArrowRight size={13}/></button></div>}
      {!scenario || !profile || !analysis ? <div className="workspace-loader"><LoaderCircle className="spin" size={27}/><h2>{error ? 'The workspace could not be loaded' : 'Connecting citizen context'}</h2><p>{error ? 'Use Retry to reconnect to the demo service.' : 'Loading the ontology, evidence and support pathways.'}</p></div> : <>
      <div id="workspace" className={`workspace ${busy ? 'is-updating' : ''}`}>
        <section className="panel context-panel"><div className="panel-heading"><div><div className="eyebrow">THE STARTING POINT</div><h2>Citizen context</h2></div><span className="round-icon"><Users size={17}/></span></div><div className="resident-card"><span className="resident-avatar"><Users size={20}/></span><div><strong>Illustrative household</strong><small>Resident R-001 · Singapore</small></div><span className="tiny-tag">DEMO</span></div>
          <form onSubmit={e => { e.preventDefault(); void analyze(); }}>
            <div className="context-form"><label className="input-label">Monthly household income<span>SGD</span></label><div className="money-input"><span>S$</span><input id="income" aria-label="Monthly household income" type="number" min="0" max="1000000" step="100" value={profile.householdIncome ?? ''} disabled={busy || profile.householdIncome === null} onChange={e => updateProfile('householdIncome', e.target.value === '' ? null : Number(e.target.value))}/></div><label className="unknown-toggle"><input type="checkbox" checked={profile.householdIncome === null} disabled={busy} onChange={e => updateProfile('householdIncome', e.target.checked ? null : scenario.profile.householdIncome)}/>Income not yet known</label>
              <div className="two-fields"><label>Household size<input aria-label="Household size" type="number" min="1" max="20" value={profile.householdSize} disabled={busy} onChange={e => updateProfile('householdSize', Number(e.target.value))}/></label><label>Resident age<input aria-label="Resident age" type="number" min="1" max="120" value={profile.age} disabled={busy} onChange={e => updateProfile('age', Number(e.target.value))}/></label></div>
              <label className="select-field">Residency<div><select aria-label="Residency" value={profile.citizenship} disabled={busy} onChange={e => updateProfile('citizenship', e.target.value)}><option value="citizen">Singapore citizen</option><option value="permanent-resident">Permanent resident</option><option value="other">Other residency</option></select><ChevronDown size={14}/></div></label>
              <label className="select-field">Employment<div><select aria-label="Employment" value={profile.employmentStatus} disabled={busy} onChange={e => updateProfile('employmentStatus', e.target.value)}><option value="unemployed">Not currently employed</option><option value="employed">Employed</option><option value="retired">Retired</option><option value="student">Student</option></select><ChevronDown size={14}/></div></label>
              <div className="context-toggles">{([{field:'recentJobLoss',label:'Recent job transition'}, {field:'caregiver',label:'Caregiving responsibilities'}, {field:'disability',label:'Accessibility support needs'}] as const).map(item => <label key={item.field} className="toggle-row"><span>{item.label}</span><input type="checkbox" role="switch" checked={profile[item.field]} disabled={busy} onChange={e => updateProfile(item.field, e.target.checked)}/><span className="toggle-track"/></label>)}</div>
            </div><div className="per-capita"><span>Income per household member<small>Context derived from your inputs</small></span><strong>{money(profile.householdIncome === null ? null : profile.householdIncome / Math.max(1, profile.householdSize))}<small>/ month</small></strong></div><button className="primary-button update-button" type="submit" disabled={busy}>{busy ? <LoaderCircle size={16} className="spin"/> : <Sparkles size={16}/>}Update context<ArrowRight size={16}/></button><p className="context-hint">Change a fact. Discover how the pathway changes.</p>
          </form>
        </section>
        <div className="graph-column"><Graph nodes={scenario.nodes} edges={scenario.edges} highlighted={analysis.highlightedEdgeIds} selectedScheme={selectedScheme} selectedNode={selectedNode?.id || null} onNode={onNode}/><div className="intelligence-strip"><div><span className="metric-icon"><Network size={18}/></span><strong>{analysis.metrics.contextEntities}<small>context entities</small></strong></div><div><span className="metric-icon"><ShieldCheck size={18}/></span><strong>{analysis.metrics.rulesEvaluated}<small>rules evaluated</small></strong></div><div><span className="metric-icon"><BookOpen size={18}/></span><strong>{scenario.evidence.length}<small>evidence sources</small></strong></div><span className="engine-chip"><span className="live-dot"/>{analysis.engine.graph}</span></div></div>
      </div>
      <div className="results-layout">
        <section className="support-section"><div className="section-heading"><div><div className="eyebrow">FROM CONTEXT TO ACTION</div><h2>Your support pathways <span className="number-badge">{analysis.schemes.length}</span></h2><p>Every recommendation has a traceable reason.</p></div><button className={`secondary-button compare-button ${showComparison ? 'active' : ''}`} onClick={() => setShowComparison(v => !v)}><GitCompareArrows size={15}/>{showComparison ? 'Hide comparison' : 'Compare changes'}{changed > 0 && <span className="change-count">{changed}</span>}</button></div>
          {showComparison && baseline && <div className="comparison-panel"><div className="comparison-heading"><GitCompareArrows size={16}/><strong>Compared with the starting household</strong><span>{changed ? `${changed} pathway${changed === 1 ? '' : 's'} changed` : 'No eligibility changes yet'}</span></div>{analysis.schemes.map(s => <div className="comparison-row" key={s.id}><span>{s.name}</span><span className={`mini-status ${baseline.schemes.find(b => b.id === s.id)?.status}`}>{statusLabel[baseline.schemes.find(b => b.id === s.id)?.status || s.status]}</span><ArrowRight size={13}/><span className={`mini-status ${s.status}`}>{statusLabel[s.status]}</span></div>)}</div>}
          <div className="scheme-grid">{analysis.schemes.map((scheme, i) => <SchemeCard key={scheme.id} scheme={scheme} index={i} selected={selectedScheme === scheme.id} onSelect={() => setSelectedScheme(current => current === scheme.id ? null : scheme.id)} onDetails={() => { setSelectedScheme(scheme.id); const node = scenario.nodes.find(n => n.id === scheme.id); if (node) setSelectedNode(node); }} />)}</div>
          <div className="checklist-panel"><span className="checklist-icon"><FileCheck2 size={22}/></span><div><strong>A clearer next step</strong><p>Prepare a checklist of documents and the evidence behind your pathways.</p></div><button className="secondary-button" onClick={downloadChecklist}><Download size={14}/>{checklistReady ? 'Download again' : 'Prepare checklist'}</button></div>
        </section>
        <section className="panel assistant-panel" ref={answerRef}><div className="panel-heading"><div><div className="eyebrow">ASK WITH CONTEXT</div><h2>Your context assistant</h2></div><span className="assistant-symbol"><Sparkles size={19}/></span></div><div className="assistant-grounding"><ShieldCheck size={13}/>Grounded in the graph and cited evidence</div><div className="question-bubble">{lastQuestion}</div><div className="answer-body" aria-live="polite"><div className="answer-label"><span className="assistant-mini"><Sparkles size={12}/></span>CONTEXT INTELLIGENCE{busy && <LoaderCircle className="spin" size={13}/>}</div><AnswerText answer={analysis.answer} citations={analysis.citations} onEvidence={setSelectedEvidence}/></div><div className="citation-chips">{analysis.citations.slice(0,4).map((e,i) => <button key={e.id} onClick={() => setSelectedEvidence(e)}><BookOpen size={11}/><span>{i+1}</span>{e.title}<ArrowUpRight size={10}/></button>)}</div><details className="reasoning-details"><summary><Layers3 size={13}/>Trace the reasoning<ChevronDown size={13}/></summary><ol>{analysis.reasoning.map(step => <li key={step.step}><strong>{step.title}</strong><p>{step.detail}</p>{step.evidenceIds.slice(0,2).map(id => <button key={id} className="text-button" onClick={() => { const e=evidenceById(id); if(e) setSelectedEvidence(e); }}><BookOpen size={10}/>Evidence</button>)}</li>)}</ol></details><div className="assistant-bottom"><div className="suggested-prompts">{prompts.slice(1).map(prompt => <button key={prompt} disabled={busy} onClick={() => void analyze(profile,prompt)}>{prompt}<ArrowUpRight size={11}/></button>)}</div><form className="ask-form" onSubmit={e => { e.preventDefault(); if(question.trim()) void analyze(profile, question.trim()); }}><input aria-label="Ask a question about this household" placeholder="Ask about this household…" maxLength={1200} value={question} disabled={busy} onChange={e => setQuestion(e.target.value)}/><button aria-label="Send question" disabled={busy || !question.trim()}><Send size={16}/></button></form><div className="synthesis-control"><label><input type="checkbox" checked={useBedrock} disabled={busy} onChange={e => setUseBedrock(e.target.checked)}/>Use Amazon Bedrock synthesis</label><span title={analysis.engine.accelerator}>{analysis.engine.synthesis === 'Amazon Bedrock' ? 'Amazon Bedrock' : 'Deterministic'}</span></div></div></section>
      </div>
      {analysis.warnings?.length > 0 && <div className="warnings"><Info size={14}/><span>{analysis.warnings.join(' ')}</span></div>}
      <div className="demo-note"><Info size={15}/><p><strong>A demonstration of connected intelligence.</strong> These services, thresholds and benefits are fictional. Recommendations explain illustrative rules and are not official eligibility decisions. No real citizen data is used.</p></div>
      </>}
    </main>
    <footer className="app-footer"><span>Life Events Navigator <span className="footer-dot">·</span> Singapore public sector demo</span><a href="https://github.com/aws/context-ontology-accelerator" target="_blank" rel="noreferrer">AWS Context Ontology Accelerator<ArrowUpRight size={12}/></a><span>Amazon Web Services <span className="footer-dot">·</span> {config?.region}</span></footer>
    {selectedNode && <div className="modal-backdrop" onClick={() => setSelectedNode(null)}><section className="detail-modal" role="dialog" aria-modal="true" aria-labelledby="node-title" onClick={e=>e.stopPropagation()}><div className="modal-heading"><div><div className="eyebrow">{selectedNode.type.toUpperCase()} · CONNECTED ENTITY</div><h2 id="node-title">{selectedNode.label}</h2></div><button className="icon-button" autoFocus aria-label="Close entity details" onClick={()=>setSelectedNode(null)}><X size={20}/></button></div><p className="modal-description">{selectedNode.description || 'This entity connects resident context to support pathways in the illustrative ontology.'}</p>{currentScheme && <><div className="detail-status"><StatusIcon status={currentScheme.status}/><span className={`status-badge ${currentScheme.status}`}>{statusLabel[currentScheme.status]}</span><span>{currentScheme.agency}</span></div><p className="scheme-reason">{currentScheme.reason}</p><div className="detail-section"><h3>Rules and evidence</h3>{currentScheme.ruleResults.map(rule=><div key={rule.id} className="rule-row"><span className={`rule-icon ${rule.result}`}>{rule.result==='pass'?<CheckCircle2 size={17}/>:rule.result==='fail'?<XCircle size={17}/>:<CircleHelp size={17}/>}</span><div><strong>{rule.label}</strong><small>Observed: {formatValue(rule.actual)} <span>·</span> Required: {rule.operator} {formatValue(rule.expected)}</small></div><button aria-label={`Show evidence for ${rule.label}`} className="icon-button" onClick={()=>{const e=evidenceById(rule.evidenceId);if(e)setSelectedEvidence(e);}}><BookOpen size={16}/></button></div>)}</div><div className="detail-section"><h3>Documents to prepare</h3><div className="document-list">{currentScheme.documentIds.map(id=><span key={id}><FileCheck2 size={15}/>{scenario?.nodes.find(n=>n.id===id)?.label || id}</span>)}</div></div></>}{!currentScheme && <div className="detail-section"><h3>Connected relationships</h3>{scenario?.edges.filter(e=>e.source===selectedNode.id||e.target===selectedNode.id).map(edge=><button key={edge.id} className="relationship-row" onClick={()=>{const next=scenario.nodes.find(n=>n.id===(edge.source===selectedNode.id?edge.target:edge.source));if(next)onNode(next);}}><span>{edge.label}</span><strong>{scenario.nodes.find(n=>n.id===(edge.source===selectedNode.id?edge.target:edge.source))?.label}</strong><ChevronRight size={15}/></button>)}</div>}<div className="modal-footer"><Network size={14}/><span>Entity ID: {selectedNode.id}</span><span>Synthetic ontology</span></div></section></div>}
    {selectedEvidence && <div className="modal-backdrop evidence-backdrop" onClick={()=>setSelectedEvidence(null)}><section className="detail-modal evidence-modal" role="dialog" aria-modal="true" aria-labelledby="evidence-title" onClick={e=>e.stopPropagation()}><div className="modal-heading"><div><div className="eyebrow">SOURCE EVIDENCE</div><h2 id="evidence-title">{selectedEvidence.title}</h2></div><button className="icon-button" autoFocus aria-label="Close evidence" onClick={()=>setSelectedEvidence(null)}><X size={20}/></button></div><span className="source-pill"><BookOpen size={14}/>{selectedEvidence.source}</span><blockquote>{selectedEvidence.excerpt}</blockquote><div className="evidence-disclaimer"><Info size={16}/>This is a synthetic policy source prepared for this demo. It does not describe an official Singapore government scheme.</div><div className="modal-footer"><span>Evidence ID: {selectedEvidence.id}</span>{selectedEvidence.updatedAt&&<span>Updated {selectedEvidence.updatedAt.slice(0,10)}</span>}</div></section></div>}
    {showHow && <div className="modal-backdrop" onClick={()=>setShowHow(false)}><section className="detail-modal how-modal" role="dialog" aria-modal="true" aria-labelledby="how-title" onClick={e=>e.stopPropagation()}><div className="modal-heading"><div><div className="eyebrow">BEHIND THE EXPERIENCE</div><h2 id="how-title">Context makes the connection.</h2></div><button className="icon-button" autoFocus aria-label="Close explanation" onClick={()=>setShowHow(false)}><X size={20}/></button></div><p className="modal-description">The same income figure can tell a different story when connected to household size, a job transition, caregiving and policy rules.</p><div className="how-steps">{[{n:'01',title:'Connect the context',text:'An importable ontology describes residents, households, life events, services, rules, documents and agencies.'},{n:'02',title:'Traverse the graph',text:'RDF and SPARQL connect a resident’s facts with the relevant support pathways using accelerator graph traversal patterns.'},{n:'03',title:'Evaluate and explain',text:'Explicit rules produce pass, fail or unknown results. Every pathway traces to synthetic policy evidence.'},{n:'04',title:'Synthesize with evidence',text:'The assistant explains graph findings deterministically, with optional Amazon Bedrock synthesis when available.'}].map(step=><div key={step.n}><span>{step.n}</span><div><strong>{step.title}</strong><p>{step.text}</p></div></div>)}</div><a className="secondary-button accelerator-link" href="https://github.com/aws/context-ontology-accelerator" target="_blank" rel="noreferrer">Explore the accelerator<ArrowUpRight size={15}/></a></section></div>}
  </div>;
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
  return <article className={`scheme-card ${scheme.status} ${selected?'selected':''}`}><div className="scheme-top"><span className="scheme-number">0{index+1}</span><span className={`status-badge ${scheme.status}`}><StatusIcon status={scheme.status}/>{statusLabel[scheme.status]}</span></div><button className="scheme-title" onClick={onSelect}>{scheme.name}<Network size={16}/></button><div className="scheme-agency">{scheme.agency}</div><p className="scheme-card-reason">{scheme.reason}</p><div className="benefit-line"><HeartHandshake size={14}/><span>{typeof scheme.benefit === 'string' ? scheme.benefit : JSON.stringify(scheme.benefit)}</span></div><div className="scheme-bottom"><span className="rule-progress"><span>{scheme.ruleResults.map(r=><i key={r.id} className={r.result}/>)}</span>{passed}/{scheme.ruleResults.length} rules met</span><button onClick={onDetails}>View reasoning<ArrowUpRight size={13}/></button></div></article>;
}
export default App;

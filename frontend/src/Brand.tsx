/** A custom Singapore island mark; this is not an agency or government logo. */
export function Brand() {
  return <a className="brand sg-brand" href="/" aria-label="SG Support Navigator home">
    <span className="brand-symbol sg-brand-symbol" aria-hidden="true">
      <svg viewBox="0 0 48 48" width="40" height="40" fill="none">
        <path d="m6 27 4-5 5-1 3-5 5 1 4-3 5 3 1 4 5 1 5 6-5 4-5-1-4 4-5-2-4 1-3-4-6 1Z" fill="currentColor"/>
        <path d="m14 26 8-4 10 3-8 5-10-4Z" stroke="#bd2339" strokeWidth="1.3" strokeLinejoin="round"/>
        <circle cx="14" cy="26" r="2" fill="#bd2339"/><circle cx="22" cy="22" r="2" fill="#bd2339"/>
        <circle cx="32" cy="25" r="2" fill="#bd2339"/><circle cx="24" cy="30" r="2" fill="#bd2339"/>
        <path d="m11 36 3 1m19-1 3-1" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/>
      </svg>
    </span>
    <span className="brand-wordmark"><span className="brand-title"><b>SG</b> Support <span className="brand-light">Navigator</span></span><small>SINGAPORE · CONTEXT INTELLIGENCE</small></span>
  </a>;
}

export default Brand;

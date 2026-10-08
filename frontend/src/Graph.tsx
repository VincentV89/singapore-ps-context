import { useMemo, useState } from 'react';
import { Expand, Focus, Minus, Plus } from 'lucide-react';
import type { GraphEdge, GraphNode } from './types';

const columns = ['resident', 'household', 'event', 'scheme', 'rule', 'document', 'agency'];
const colors: Record<string, string> = { resident: '#e4f5b6', household: '#e4f5b6', event: '#94ccff', scheme: '#6de0bc', rule: '#b8a5eb', document: '#e4ba81', agency: '#a7b9d2' };
const columnLabels = ['RESIDENT', 'HOUSEHOLD', 'LIFE EVENT', 'SUPPORT SCHEME', 'ELIGIBILITY', 'EVIDENCE', 'AGENCY'];
function labelLines(node: GraphNode) {
  const label = node.type === 'agency' ? node.label.replace(/^Demo /, '') : node.label;
  if (label.length <= 23) return [label];
  const words = label.split(' '); let line = ''; const lines: string[] = [];
  for (const word of words) { if ((line + ' ' + word).trim().length > 23 && line) { lines.push(line); line = word; } else line = `${line} ${word}`.trim(); }
  if (line) lines.push(line);
  return lines.slice(0, 2).map((s, i) => i === 1 && lines.length > 2 ? s.slice(0, 21) + '…' : s);
}
export function Graph({ nodes, edges, highlighted, selectedScheme, selectedNode, onNode }: { nodes: GraphNode[]; edges: GraphEdge[]; highlighted: string[]; selectedScheme: string | null; selectedNode: string | null; onNode: (node: GraphNode) => void }) {
  const [allPaths, setAllPaths] = useState(false);
  const [zoom, setZoom] = useState(1);
  const [expanded, setExpanded] = useState(false);
  const selectedPath = useMemo(() => {
    if (!selectedScheme) return null;
    const relevant = new Set<string>([selectedScheme]);
    const chosenEdges = new Set<string>();
    for (const edge of edges) if (edge.source === selectedScheme || edge.target === selectedScheme) { relevant.add(edge.source); relevant.add(edge.target); chosenEdges.add(edge.id); }
    for (const edge of edges) if (relevant.has(edge.source) && ['rule', 'document'].includes(nodes.find(n => n.id === edge.source)?.type || '')) { relevant.add(edge.target); chosenEdges.add(edge.id); }
    for (const edge of edges) if (relevant.has(edge.target) && ['household', 'resident'].includes(nodes.find(n => n.id === edge.source)?.type || '')) { relevant.add(edge.source); chosenEdges.add(edge.id); }
    return { relevant, chosenEdges };
  }, [selectedScheme, edges, nodes]);
  const visibleColumns = allPaths || selectedScheme ? columns : ['resident', 'household', 'event', 'scheme', 'agency'];
  const contentHeight = allPaths ? Math.max(555, Math.max(...columns.map(type => nodes.filter(n => n.type === type).length)) * 70 + 110) : 555;
  const positioned = useMemo(() => {
    const map = new Map<string, { x: number; y: number; node: GraphNode }>();
    const groups = visibleColumns.map(type => nodes.filter(n => (n.type === type || (type === 'event' && n.type === 'lifeEvent')) && (allPaths || !selectedPath || selectedPath.relevant.has(n.id))));
    groups.forEach((group, col) => group.forEach((node, row) => map.set(node.id, { x: 70 + col * (940 / (visibleColumns.length - 1)), y: 64 + (row + 0.5) * ((contentHeight - 110) / Math.max(group.length, 1)), node })));
    return map;
  }, [nodes, allPaths, selectedPath, visibleColumns.join(','), contentHeight]);
  const highlightSet = useMemo(() => new Set(highlighted), [highlighted]);
  const activeEdges = selectedPath?.chosenEdges ?? highlightSet;
  const activeNodes = useMemo(() => {
    const active = new Set<string>();
    edges.filter(e => activeEdges.has(e.id)).forEach(e => { active.add(e.source); active.add(e.target); });
    return active;
  }, [edges, activeEdges]);
  return <section className={`panel graph-panel ${expanded ? 'graph-expanded' : ''}`} aria-label="Interactive knowledge graph">
    <div className="panel-heading"><div><div className="eyebrow">CONNECTED CONTEXT</div><h2>The knowledge graph <span className="live-dot" /></h2></div><div className="graph-tools"><button className={`icon-button ${allPaths ? 'active' : ''}`} title={allPaths ? 'Show relevant paths' : 'Show all relationships'} aria-label={allPaths ? 'Show relevant paths' : 'Show all relationships'} onClick={() => setAllPaths(v => !v)}><Focus size={17}/></button><button className="icon-button" title={expanded ? 'Close expanded graph' : 'Expand graph'} aria-label={expanded ? 'Close expanded graph' : 'Expand graph'} onClick={() => setExpanded(v => !v)}><Expand size={16}/></button></div></div>
    <div className="graph-caption">Follow the connections from a life event to support, rules and evidence.</div>
    <div className={`graph-canvas ${allPaths ? 'full-ontology' : ''}`}>
      <svg style={allPaths ? { minHeight: contentHeight * .8, maxHeight: 'none', aspectRatio: `1080/${contentHeight}` } : undefined} viewBox={`0 0 ${1080 / zoom} ${contentHeight / zoom}`} role="img" aria-label={`Knowledge graph with ${nodes.length} entities and ${edges.length} relationships. Select a node to explore its context.`}>
        <defs><pattern id="grid" width="24" height="24" patternUnits="userSpaceOnUse"><circle cx="1" cy="1" r=".6" fill="#29374a"/></pattern><filter id="glow"><feGaussianBlur stdDeviation="3"/></filter><linearGradient id="edge-gradient"><stop stopColor="#aee5af"/><stop offset="1" stopColor="#70cccd"/></linearGradient></defs>
        <rect width="1080" height={contentHeight} fill="url(#grid)"/>
        {visibleColumns.map((column, i) => <g key={column}><text x={70 + i * (940 / (visibleColumns.length - 1))} y="29" textAnchor="middle" className="graph-column-label">{columnLabels[columns.indexOf(column)]}</text><line x1={70 + i * (940 / (visibleColumns.length - 1))} x2={70 + i * (940 / (visibleColumns.length - 1))} y1="48" y2="529" stroke="#233043" strokeWidth=".7" strokeDasharray="2 7"/></g>)}
        {edges.map(edge => {
          const source = positioned.get(edge.source), target = positioned.get(edge.target);
          if (!source || !target) return null;
          const active = activeEdges.has(edge.id);
          const dx = Math.abs(target.x - source.x) * 0.5;
          const path = `M ${source.x + 18} ${source.y} C ${source.x + 18 + dx} ${source.y}, ${target.x - 18 - dx} ${target.y}, ${target.x - 18} ${target.y}`;
          return <g key={edge.id} className={active ? 'graph-edge active' : 'graph-edge'} opacity={active ? 1 : .36}><title>{edge.label}</title>{active && <path d={path} stroke="#6de0bc" strokeWidth="5" fill="none" opacity=".12" filter="url(#glow)"/>}<path d={path} stroke={active ? 'url(#edge-gradient)' : '#758baa'} strokeWidth={active ? '1.5' : '1'} fill="none"/></g>;
        })}
        {[...positioned.values()].map(({ node, x, y }) => {
          const active = activeNodes.has(node.id);
          const selected = selectedNode === node.id || selectedScheme === node.id;
          const color = colors[node.type] || '#a7b9d2';
          return <g key={node.id} role="button" tabIndex={0} aria-label={`${node.type}: ${node.label}`} onClick={() => onNode(node)} onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onNode(node); } }} className={`graph-node ${selected ? 'selected' : ''}`} transform={`translate(${x},${y})`} opacity={allPaths || active || selected ? 1 : .53}>
            <title>{node.label}{node.description ? ` — ${node.description}` : ''}</title>
            {active && <circle r="26" fill={color} opacity=".035"/>}
            <circle r="18" fill="#131e2e" stroke={color} strokeWidth={selected ? 2.5 : active ? 1.5 : .8}/>
            <circle r="5" fill={color}/><circle r="9" fill="none" stroke={color} opacity=".28"/>
            <rect x="-68" y="24" width="136" height={labelLines(node).length > 1 ? 32 : 20} rx="4" fill="#101a28" opacity=".97"/>
            <text x="0" y="38" textAnchor="middle" fill={active || selected ? '#e3ebf5' : '#a6b7cd'} className="graph-node-label">{labelLines(node).map((line,i)=><tspan key={i} x="0" dy={i?12:0}>{line}</tspan>)}</text>
          </g>;
        })}
      </svg>
      <div className="graph-controls"><button className="icon-button" aria-label="Zoom out" disabled={zoom === 1} onClick={() => setZoom(z => Math.max(1, z - .15))}><Minus size={14}/></button><span>{Math.round(zoom * 100)}%</span><button className="icon-button" aria-label="Zoom in" disabled={zoom >= 1.45} onClick={() => setZoom(z => Math.min(1.45, z + .15))}><Plus size={14}/></button></div>
      <div className="graph-status"><span className="live-dot"/>{selectedScheme ? 'Selected support pathway' : allPaths ? 'Complete ontology' : 'Context-relevant pathways'}</div>
    </div>
    <div className="graph-footer"><span><i style={{ background: '#6de0bc' }}/>{activeEdges.size} connected relationships</span><span>{nodes.length} entities · {edges.length} relationships</span><span className="graph-tip">Select any node to inspect</span></div>
  </section>;
}

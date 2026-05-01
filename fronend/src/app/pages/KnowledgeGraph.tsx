import { useMemo, useState } from 'react';
import { FileText, Newspaper, Gavel, FlaskConical, Building2, CheckCircle2, ExternalLink, X, Info } from 'lucide-react';
import { Card, Chip, Confidence, SectionTitle } from '../components/shared';
import { PageShell } from '../components/PageShell';
import { analysisEvidenceCards, companyDisplayName, loadCompanyAnalysis } from '../lib/analysis';

const nodes = [
  { id: 'company', label: 'BHP Group', x: 50, y: 50, kind: 'entity', desc: 'Parent company entity resolved via ABR.' },
  { id: 'claim1', label: 'Operates near Bilby habitat', x: 22, y: 22, kind: 'claim', desc: 'Extracted spatial claim regarding proximity to vulnerable species.' },
  { id: 'claim2', label: 'Tailings within 1km of creek', x: 78, y: 26, kind: 'claim', desc: 'Identified risk regarding hydrological overlap.' },
  { id: 'claim3', label: 'Habitat restoration: 142ha', x: 80, y: 78, kind: 'claim', desc: 'Company self-reported positive biodiversity impact.' },
  { id: 'claim4', label: 'Turbidity breach reported', x: 20, y: 78, kind: 'claim', desc: 'Negative environmental event flagged by state regulator.' },
  { id: 's1', label: 'EPBC filing 2025/09421', x: 8, y: 8, kind: 'source', src: 'gov', desc: 'Federal environmental referral document.' },
  { id: 's2', label: 'CSIRO Pilbara survey', x: 8, y: 34, kind: 'source', src: 'science', desc: 'Peer-reviewed ecological survey data.' },
  { id: 's3', label: 'WA EPA audit', x: 8, y: 88, kind: 'source', src: 'audit', desc: 'State-level environmental protection authority audit.' },
  { id: 's4', label: 'BHP Sustainability Report', x: 92, y: 88, kind: 'source', src: 'report', desc: 'Annual corporate sustainability disclosure.' },
  { id: 's5', label: 'ABC News article', x: 92, y: 8, kind: 'source', src: 'news', desc: 'Public media report on local community concerns.' },
];

const edges = [
  ['company', 'claim1'], ['company', 'claim2'], ['company', 'claim3'], ['company', 'claim4'],
  ['s1', 'claim1'], ['s2', 'claim1'], ['s5', 'claim2'], ['s3', 'claim4'], ['s4', 'claim3'],
];

const sourceIcon = (k?: string) => k === 'gov' ? Gavel : k === 'science' ? FlaskConical : k === 'audit' ? FileText : k === 'news' ? Newspaper : FileText;

const fallbackTimeline = [
  { date: '14 Apr 2026', title: 'Expansion referral lodged', source: 'EPBC Act', conf: 95 },
  { date: '02 Apr 2026', title: 'Restoration milestone claim', source: 'BHP Sustainability Report', conf: 88 },
  { date: '21 Mar 2026', title: 'Turbidity breach observation', source: 'WA EPA audit', conf: 82 },
  { date: '02 Mar 2026', title: 'Species survey finding', source: 'CSIRO', conf: 78 },
];

export function KnowledgeGraph() {
  const [activeNode, setActiveNode] = useState<typeof nodes[0] | null>(null);
  const analysis = useMemo(() => loadCompanyAnalysis(), []);
  const evidenceCards = useMemo(() => analysisEvidenceCards(analysis), [analysis]);
  const companyName = companyDisplayName(analysis);
  const graphNodes = useMemo(
    () => nodes.map(node => node.id === 'company' ? { ...node, label: companyName } : node),
    [companyName],
  );
  const timeline = evidenceCards.length
    ? evidenceCards.map(item => ({
        date: item.date,
        title: item.title,
        source: item.source,
        conf: item.conf,
      }))
    : fallbackTimeline;

  return (
    <PageShell sectionMarker="§ 03 · KNOWLEDGE GRAPH" coords="PROVENANCE · CLAIM-CHAIN · TEMPORAL">
      <div className="flex items-end justify-between mb-4">
        <div>
          <div className="text-[11px] uppercase tracking-wider text-stone-400">Knowledge Graph</div>
          <div className="text-[22px] text-stone-900">Source <span className="italic text-emerald-700">provenance</span> & claim chains</div>
        </div>
        <div className="flex gap-2">
          <Chip tone="emerald"><CheckCircle2 size={11} /> 8 verified</Chip>
          <Chip tone="amber">2 corroborating</Chip>
          <Chip tone="stone">Temporal</Chip>
        </div>
      </div>

      <Card className="p-0 overflow-hidden">
        <div className="relative h-[520px] bg-[radial-gradient(ellipse_at_top,rgba(16,185,129,0.06),transparent_60%),radial-gradient(ellipse_at_bottom,rgba(59,130,246,0.06),transparent_60%)]">
          <svg className="absolute inset-0 w-full h-full">
            {edges.map(([a, b], i) => {
              const A = graphNodes.find(n => n.id === a)!;
              const B = graphNodes.find(n => n.id === b)!;
              return <line key={i} x1={`${A.x}%`} y1={`${A.y}%`} x2={`${B.x}%`} y2={`${B.y}%`} stroke="#d6d3d1" strokeWidth="1.5" strokeDasharray="4 4" />;
            })}
          </svg>
          {graphNodes.map(n => {
            const style = { left: `${n.x}%`, top: `${n.y}%` } as const;
            if (n.kind === 'entity') return (
              <button key={n.id} onClick={() => setActiveNode(n)} className="absolute -translate-x-1/2 -translate-y-1/2 hover:scale-105 transition-transform z-10" style={style}>
                <div className={`px-4 py-2.5 bg-stone-900 text-white rounded-xl shadow-lg inline-flex items-center gap-2 ${activeNode?.id === n.id ? 'ring-2 ring-emerald-500' : ''}`}>
                  <Building2 size={14} /><span className="text-[13px]">{n.label}</span>
                </div>
              </button>
            );
            if (n.kind === 'claim') return (
              <button key={n.id} onClick={() => setActiveNode(n)} className="absolute -translate-x-1/2 -translate-y-1/2 hover:scale-105 transition-transform z-10" style={style}>
                <div className={`px-3 py-1.5 bg-amber-50 text-amber-800 rounded-lg border border-amber-200 text-[12px] max-w-[160px] text-center shadow-sm ${activeNode?.id === n.id ? 'ring-2 ring-emerald-500' : ''}`}>{n.label}</div>
              </button>
            );
            const Icon = sourceIcon(n.src);
            return (
              <button key={n.id} onClick={() => setActiveNode(n)} className="absolute -translate-x-1/2 -translate-y-1/2 hover:scale-105 transition-transform z-10" style={style}>
                <div className={`px-2.5 py-1.5 bg-white border border-stone-200 rounded-lg text-[11px] text-stone-700 inline-flex items-center gap-1.5 shadow-sm ${activeNode?.id === n.id ? 'ring-2 ring-emerald-500' : ''}`}>
                  <Icon size={12} className="text-emerald-600" /> {n.label}
                </div>
              </button>
            );
          })}
          
          {/* Node Info Popover */}
          {activeNode && (
            <div className="absolute top-4 right-4 w-72 bg-white/95 backdrop-blur-sm border border-stone-200 rounded-xl shadow-xl p-4 z-20 animate-in fade-in slide-in-from-right-4">
              <div className="flex justify-between items-start mb-2">
                <div className="flex items-center gap-2">
                  <Info size={14} className="text-emerald-600" />
                  <div className="text-[10px] font-mono tracking-[0.2em] uppercase text-stone-500">{activeNode.kind} node</div>
                </div>
                <button onClick={() => setActiveNode(null)} className="text-stone-400 hover:text-stone-900"><X size={14} /></button>
              </div>
              <div className="text-[15px] text-stone-900 font-medium tracking-tight mb-2 leading-tight">{activeNode.label}</div>
              <div className="text-[12px] text-stone-600 leading-relaxed mb-4">{activeNode.desc}</div>
              
              <div className="pt-3 border-t border-stone-100 flex items-center justify-between">
                <div className="text-[10px] text-stone-400">Node ID: {activeNode.id}</div>
                {activeNode.kind === 'source' && <a className="text-[11px] text-emerald-700 hover:underline inline-flex items-center gap-1 cursor-pointer">View source <ExternalLink size={10} /></a>}
              </div>
            </div>
          )}

          <div className="absolute bottom-3 left-4 flex gap-3 text-[11px] text-stone-500 bg-white/80 backdrop-blur px-3 py-2 rounded-lg border border-stone-200">
            <span className="inline-flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-stone-900" /> Entity</span>
            <span className="inline-flex items-center gap-1"><span className="w-2 h-2 rounded-sm bg-amber-400" /> Claim</span>
            <span className="inline-flex items-center gap-1"><span className="w-2 h-2 rounded-sm bg-emerald-500" /> Source</span>
          </div>
        </div>
      </Card>

      <div className="grid grid-cols-12 gap-5 mt-6">
        <Card className="col-span-12 md:col-span-7 p-6">
          <SectionTitle title="Evidence timeline" />
          <div className="relative pl-5">
            <div className="absolute left-1.5 top-1 bottom-1 w-px bg-stone-200" />
            {timeline.map((t, i) => (
              <div key={i} className="relative mb-5 last:mb-0">
                <div className="absolute -left-[13px] top-1 w-2.5 h-2.5 rounded-full bg-emerald-500 ring-4 ring-white" />
                <div className="text-[11px] text-stone-500">{t.date}</div>
                <div className="text-[13px] text-stone-900">{t.title}</div>
                <div className="flex items-center gap-2 mt-1">
                  <Chip tone="blue">{t.source}</Chip>
                  <Confidence value={t.conf} />
                </div>
              </div>
            ))}
          </div>
        </Card>

        <Card className="col-span-12 md:col-span-5 p-6">
          <SectionTitle title="Claim → source traceability" />
          <div className="space-y-3">
            {[
              { claim: 'Operates near Bilby habitat', chain: ['EPBC filing 2025/09421', 'CSIRO survey'], conf: 92 },
              { claim: 'Tailings within 1km of creek', chain: ['WA EPA audit', 'Satellite imagery 22-03'], conf: 86 },
              { claim: 'Habitat restoration 142ha', chain: ['BHP Sustainability Report'], conf: 74 },
            ].map((c, i) => (
              <div key={i} className="p-3 bg-stone-50 rounded-xl">
                <div className="text-[13px] text-stone-900">{c.claim}</div>
                <div className="mt-1.5 text-[11px] text-stone-500 flex flex-wrap gap-1 items-center">
                  {c.chain.map((s, j) => (
                    <span key={j} className="inline-flex items-center gap-1">
                      <span className="px-1.5 py-0.5 bg-white border border-stone-200 rounded">{s}</span>
                      {j < c.chain.length - 1 && <span>→</span>}
                    </span>
                  ))}
                </div>
                <div className="mt-2 flex items-center justify-between">
                  <Confidence value={c.conf} />
                  <a className="text-[11px] text-emerald-700 hover:underline inline-flex items-center gap-1">Audit trail <ExternalLink size={10} /></a>
                </div>
              </div>
            ))}
          </div>
        </Card>
      </div>
    </PageShell>
  );
}

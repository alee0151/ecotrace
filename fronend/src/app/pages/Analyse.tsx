import { useMemo } from 'react';
import {
  Bird,
  Droplets,
  ExternalLink,
  FileText,
  Trees,
} from 'lucide-react';
import { Card, Chip, Confidence, SectionTitle } from '../components/shared';
import { analysisEvidenceCards, companyDisplayName, loadCompanyAnalysis } from '../lib/analysis';

const fallbackEvidence = [
  { id: 'e1', type: 'EPBC', title: 'EPBC 2025/09421 - Expansion referral', date: '14 Apr 2026', conf: 92, source: 'Dept of Climate Change' },
  { id: 'e2', type: 'Audit', title: 'Turbidity breach, Port Hedland shipping channel', date: '21 Mar 2026', conf: 86, source: 'WA EPA' },
  { id: 'e3', type: 'Science', title: 'Greater Bilby population decline - Pilbara survey', date: '02 Mar 2026', conf: 78, source: 'CSIRO' },
  { id: 'e4', type: 'News', title: 'Traditional Owners raise concern over cultural site', date: '10 Feb 2026', conf: 72, source: 'ABC News' },
];

const fallbackTimeline = [
  { date: '14 Apr 2026', title: 'Expansion referral lodged', source: 'EPBC Act', conf: 95 },
  { date: '02 Apr 2026', title: 'Restoration milestone claim', source: 'BHP Sustainability Report', conf: 88 },
  { date: '21 Mar 2026', title: 'Turbidity breach observation', source: 'WA EPA audit', conf: 82 },
  { date: '02 Mar 2026', title: 'Species survey finding', source: 'CSIRO', conf: 78 },
];

const fallbackTraceability = [
  { claim: 'Operates near Bilby habitat', chain: ['EPBC filing 2025/09421', 'CSIRO survey'], conf: 92 },
  { claim: 'Tailings within 1km of creek', chain: ['WA EPA audit', 'Satellite imagery 22-03'], conf: 86 },
  { claim: 'Habitat restoration 142ha', chain: ['BHP Sustainability Report'], conf: 74 },
];

export function Analyse() {
  const analysis = useMemo(() => loadCompanyAnalysis(), []);
  const backendEvidence = useMemo(() => analysisEvidenceCards(analysis), [analysis]);
  const displayEvidence = backendEvidence.length ? backendEvidence : fallbackEvidence;
  const companyName = companyDisplayName(analysis);
  const reportSignals = analysis?.reports?.evidence_count ?? 0;
  const newsSignals = analysis?.news?.evidence?.length ?? 0;
  const timeline = backendEvidence.length
    ? backendEvidence.map(item => ({
        date: item.date,
        title: item.title,
        source: item.source,
        conf: item.conf,
      }))
    : fallbackTimeline;
  const traceability = backendEvidence.length
    ? backendEvidence.slice(0, 3).map(item => ({
        claim: item.title,
        chain: [item.source, item.type].filter(Boolean),
        conf: item.conf,
      }))
    : fallbackTraceability;

  return (
    <div className="min-h-[calc(100vh-65px)] bg-gradient-to-b from-[#f5f3ee] via-[#eef1ec] to-[#e3ebe4]">
      <div className="max-w-6xl mx-auto px-6 py-8">
        <div className="text-[10px] font-mono tracking-[0.25em] uppercase text-stone-500 mb-3">§ 02 · ANALYSE</div>
        <div className="flex flex-col md:flex-row md:items-end md:justify-between gap-4 mb-6">
          <div>
            <div className="text-[11px] uppercase tracking-wider text-stone-400">Analyse · {companyName}</div>
            <div className="text-[26px] text-stone-900">Evidence analysis</div>
          </div>
          <div className="flex flex-wrap gap-2">
            <Chip tone="emerald">{displayEvidence.length} evidence records</Chip>
            <Chip tone="blue">{reportSignals} report signals</Chip>
            <Chip tone="stone">{newsSignals} news signals</Chip>
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <Card className="p-4">
            <div className="flex items-center gap-2 text-stone-600 text-[12px]"><Trees size={14} /> Total evidence</div>
            <div className="text-[26px] text-stone-900 mt-1">{displayEvidence.length}</div>
            <div className="text-[11px] text-stone-500">{backendEvidence.length ? 'from latest backend analysis' : 'demo evidence records'}</div>
          </Card>
          <Card className="p-4">
            <div className="flex items-center gap-2 text-stone-600 text-[12px]"><Bird size={14} /> Report signals</div>
            <div className="text-[26px] text-stone-900 mt-1">{reportSignals}</div>
            <div className="text-[11px] text-stone-500">uploaded report evidence records</div>
          </Card>
          <Card className="p-4">
            <div className="flex items-center gap-2 text-stone-600 text-[12px]"><Droplets size={14} /> News signals</div>
            <div className="text-[26px] text-stone-900 mt-1">{newsSignals}</div>
            <div className="text-[11px] text-stone-500">news evidence records</div>
          </Card>
        </div>

        <div className="grid grid-cols-12 gap-5 mt-6">
          <Card className="col-span-12 md:col-span-7 p-6">
            <SectionTitle title="Evidence timeline" />
            <div className="relative pl-5">
              <div className="absolute left-1.5 top-1 bottom-1 w-px bg-stone-200" />
              {timeline.map((item, index) => (
                <div key={`${item.title}-${index}`} className="relative mb-5 last:mb-0">
                  <div className="absolute -left-[13px] top-1 w-2.5 h-2.5 rounded-full bg-emerald-500 ring-4 ring-white" />
                  <div className="text-[11px] text-stone-500">{item.date}</div>
                  <div className="text-[13px] text-stone-900">{item.title}</div>
                  <div className="flex items-center gap-2 mt-1">
                    <Chip tone="blue">{item.source}</Chip>
                    <Confidence value={item.conf} />
                  </div>
                </div>
              ))}
            </div>
          </Card>

          <Card className="col-span-12 md:col-span-5 p-6">
            <SectionTitle title="Claim → source traceability" />
            <div className="space-y-3">
              {traceability.map((item, index) => (
                <div key={`${item.claim}-${index}`} className="p-3 bg-stone-50 rounded-xl">
                  <div className="text-[13px] text-stone-900">{item.claim}</div>
                  <div className="mt-1.5 text-[11px] text-stone-500 flex flex-wrap gap-1 items-center">
                    {item.chain.map((source, chainIndex) => (
                      <span key={`${source}-${chainIndex}`} className="inline-flex items-center gap-1">
                        <span className="px-1.5 py-0.5 bg-white border border-stone-200 rounded">{source}</span>
                        {chainIndex < item.chain.length - 1 && <span>→</span>}
                      </span>
                    ))}
                  </div>
                  <div className="mt-2 flex items-center justify-between">
                    <Confidence value={item.conf} />
                    <a className="text-[11px] text-emerald-700 hover:underline inline-flex items-center gap-1 cursor-pointer">
                      Audit trail <ExternalLink size={10} />
                    </a>
                  </div>
                </div>
              ))}
            </div>
          </Card>
        </div>

        <div className="mt-6">
          <SectionTitle title="Claim-linked evidence" />
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {displayEvidence.map(e => (
              <Card key={e.id} className="p-4">
                <div className="flex items-center gap-2 mb-1.5">
                  <Chip tone={e.type === 'Report' ? 'blue' : e.type === 'News' ? 'stone' : e.type === 'EPBC' ? 'rose' : e.type === 'Audit' ? 'amber' : e.type === 'Science' ? 'blue' : 'stone'}>{e.type}</Chip>
                  <div className="text-[11px] text-stone-500">{e.date}</div>
                </div>
                <div className="text-[14px] text-stone-900">{e.title}</div>
                <div className="text-[12px] text-stone-500">
                  {e.source}{'location' in e && e.location ? ` · ${e.location}` : ''}
                </div>
                <div className="mt-2 flex items-center justify-between gap-3">
                  <Confidence value={e.conf} />
                  {'url' in e && e.url ? (
                    <a href={e.url} target="_blank" rel="noreferrer" className="text-[11px] text-emerald-700 inline-flex items-center gap-1 hover:underline">
                      Open source <ExternalLink size={10} />
                    </a>
                  ) : (
                    <span className="text-[11px] text-stone-400 inline-flex items-center gap-1">
                      <FileText size={10} /> Source captured
                    </span>
                  )}
                </div>
              </Card>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

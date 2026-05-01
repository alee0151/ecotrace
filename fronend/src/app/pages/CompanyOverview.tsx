import { useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router';
import Slider from 'react-slick';
import {
  Building2, CheckCircle2, Download, Star, TrendingUp, AlertTriangle, ChevronDown, ChevronLeft, ChevronRight,
  X, Info, MapPin, FileText, ShieldCheck, Sparkles, Calendar, Globe2, Gavel, Newspaper,
  ExternalLink, GitBranch, Map, Search, Eye, FileCheck2, Compass, Activity, AlertCircle,
  RefreshCw, BarChart3, ScanSearch, Layers, Bell, FileBarChart2, Users2, Factory, Radio,
  Database, ClipboardCheck, ArrowRight, Plus, Minus,
} from 'lucide-react';
import { Card, Chip, RiskBadge } from '../components/shared';
import { analysisEvidenceCards, companyDisplayName, companyProfileFromAnalysis, loadCompanyAnalysis } from '../lib/analysis';

type PageId = 'analyse' | 'knowledge';

const SCORE = 82;
const CHANGE_30D = 7;
const PEER_PERCENTILE = 88;
const CONFIDENCE = 91;
const COVERAGE = 74;
const SOURCES = 18;

const trend12mo = [62, 64, 63, 66, 68, 70, 71, 72, 75, 78, 80, 82];

const composition = [
  { key: 'ops', label: 'Direct operations risk', value: 22, color: '#0f766e', desc: 'On-site footprint near sensitive ecosystems' },
  { key: 'supply', label: 'Supply chain risk', value: 18, color: '#0891b2', desc: 'Tier-1/2 supplier-linked exposure' },
  { key: 'protected', label: 'Protected area proximity', value: 14, color: '#65a30d', desc: 'Distance to RAMSAR / KBA / IUCN sites' },
  { key: 'species', label: 'Threatened species sensitivity', value: 12, color: '#ca8a04', desc: 'Overlap with IUCN red-listed habitats' },
  { key: 'controversy', label: 'Controversy / news signal', value: 9, color: '#ea580c', desc: 'Adverse media & enforcement actions' },
  { key: 'disclosure', label: 'Disclosure weakness', value: 7, color: '#9333ea', desc: 'Gaps vs TNFD/SBTN expected disclosures' },
];

const peers = [
  { name: 'Rio Tinto', score: 79, pct: 84, conf: 89 },
  { name: 'Fortescue', score: 71, pct: 72, conf: 86 },
  { name: 'BHP Group', score: 82, pct: 88, conf: 91, self: true },
  { name: 'Vale SA', score: 85, pct: 92, conf: 83 },
];
const peerMedian = 80;

const sourceMix = [
  { type: 'Government', n: 6, color: 'bg-emerald-500' },
  { type: 'Filings', n: 4, color: 'bg-blue-500' },
  { type: 'NGO', n: 3, color: 'bg-amber-500' },
  { type: 'Media', n: 3, color: 'bg-rose-500' },
  { type: 'Geospatial', n: 2, color: 'bg-purple-500' },
];

const timeline = [
  { d: '24 Apr 2026', icon: Database, tone: 'emerald', t: 'New evidence ingested', sub: '3 EPA filings auto-resolved' },
  { d: '21 Apr 2026', icon: TrendingUp, tone: 'rose', t: 'Score revised +7', sub: 'Supplier-linked spatial overlap detected' },
  { d: '14 Apr 2026', icon: Factory, tone: 'amber', t: 'Supplier risk flag', sub: 'Tier-2 mill within 4km of KBA' },
  { d: '08 Apr 2026', icon: MapPin, tone: 'orange', t: 'Protected-area overlap confirmed', sub: '5 km buffer · RAMSAR wetland' },
  { d: '02 Apr 2026', icon: FileBarChart2, tone: 'stone', t: 'TNFD report exported', sub: 'Distributed to 2 analysts' },
];

const findings = [
  { icon: MapPin, tone: 'rose', metric: '47%', label: 'of mapped sites within 10km of biodiversity-sensitive areas', why: 'Spatial overlap drives most regulatory and reputational exposure.' },
  { icon: Factory, tone: 'amber', metric: '+18 pts', label: 'of total score from supplier-linked exposure', why: 'Supply-chain risk is opaque to most disclosures — uplift in audit cost likely.' },
  { icon: Newspaper, tone: 'orange', metric: '+34%', label: 'rise in regulatory & news mentions this quarter', why: 'Adverse signal momentum often precedes enforcement.' },
  { icon: ClipboardCheck, tone: 'blue', metric: '62%', label: 'disclosure completeness vs sector median 78%', why: 'TNFD-readiness gap may impact ESG ratings & cost of capital.' },
];

const tnfd = [
  { phase: 'Locate', icon: Compass, status: 'On track', tone: 'emerald', metric: '88% sites mapped', sub: '12 sensitive regions identified' },
  { phase: 'Evaluate', icon: ScanSearch, status: 'In progress', tone: 'blue', metric: '6 dependencies', sub: '4 priority impacts logged' },
  { phase: 'Assess', icon: AlertTriangle, status: 'Action needed', tone: 'amber', metric: '3 material risks', sub: 'Spatial · supplier · disclosure' },
  { phase: 'Prepare', icon: ShieldCheck, status: 'Behind', tone: 'rose', metric: '54% readiness', sub: 'TNFD draft due Q3 2026' },
];

const orbitChips = [
  { label: 'Protected area overlap', icon: MapPin, angle: -75 },
  { label: 'Supplier exposure', icon: Factory, angle: -25 },
  { label: 'Regulatory signal', icon: Gavel, angle: 25 },
  { label: 'Species sensitivity', icon: Activity, angle: 75 },
];

const exposureTags = ['Mining & Resources', 'High water dependency', 'Spatial-intensive', 'TNFD-applicable', 'Scope 3 supplier-linked'];

const navAnchors = [
  { id: 0, label: 'Risk intelligence' },
  { id: 1, label: 'Executive summary' },
  { id: 2, label: 'Score composition' },
  { id: 3, label: 'TNFD snapshot' },
  { id: 4, label: 'Key findings' },
  { id: 5, label: 'Peer comparison' },
  { id: 6, label: 'Evidence quality' },
  { id: 7, label: 'Provenance' },
  { id: 8, label: 'What changed' },
  { id: 9, label: 'Explain this score' },
];

function Sparkline({ data, color = '#dc2626' }: { data: number[]; color?: string }) {
  const max = Math.max(...data), min = Math.min(...data);
  const w = 140, h = 36, pad = 2;
  const pts = data.map((v, i) => {
    const x = pad + (i * (w - pad * 2)) / (data.length - 1);
    const y = h - pad - ((v - min) / (max - min || 1)) * (h - pad * 2);
    return `${x},${y}`;
  }).join(' ');
  return (
    <svg width={w} height={h} className="overflow-visible">
      <polyline fill="none" stroke={color} strokeWidth="1.5" points={pts} />
      <polyline fill={color} fillOpacity="0.08" stroke="none" points={`${pad},${h - pad} ${pts} ${w - pad},${h - pad}`} />
      <circle cx={w - pad} cy={h - pad - ((data[data.length - 1] - min) / (max - min || 1)) * (h - pad * 2)} r="2.5" fill={color} />
    </svg>
  );
}

function RadialGauge({ value }: { value: number }) {
  const r = 92, c = 2 * Math.PI * r;
  const offset = c - (value / 100) * c;
  let segOffset = 0;
  return (
    <div className="relative w-[240px] h-[240px]">
      <svg width="240" height="240" className="-rotate-90">
        <circle cx="120" cy="120" r={r} stroke="#e7e5e4" strokeWidth="14" fill="none" />
        <circle cx="120" cy="120" r={r} stroke="url(#scoreGrad)" strokeWidth="14" fill="none"
          strokeLinecap="round" strokeDasharray={c} strokeDashoffset={offset} />
        {composition.map((s) => {
          const len = (s.value / 100) * c;
          const dash = `${len} ${c}`;
          const off = -segOffset;
          segOffset += len;
          return <circle key={s.key} cx="120" cy="120" r={r - 18} stroke={s.color} strokeWidth="4"
            fill="none" strokeDasharray={dash} strokeDashoffset={off} opacity="0.85" />;
        })}
        <defs>
          <linearGradient id="scoreGrad" x1="0" x2="1" y1="0" y2="1">
            <stop offset="0%" stopColor="#10b981" />
            <stop offset="50%" stopColor="#f59e0b" />
            <stop offset="100%" stopColor="#e11d48" />
          </linearGradient>
        </defs>
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <div className="text-[11px] uppercase tracking-[0.18em] text-stone-500">Risk score</div>
        <div className="text-[64px] leading-none tracking-tight text-stone-900">{value}</div>
        <div className="text-[11px] text-stone-500 mt-1">/ 100 · Elevated</div>
      </div>
    </div>
  );
}

function MetricExplain({ children }: { children: React.ReactNode }) {
  return <div className="text-[10.5px] text-stone-500 leading-snug mt-1">{children}</div>;
}

function SliderArrow({ direction, onClick }: { direction: 'prev' | 'next'; onClick?: () => void }) {
  return (
    <button
      onClick={onClick}
      className={`absolute top-1/2 -translate-y-1/2 z-10 w-10 h-10 rounded-full bg-white shadow-lg border border-stone-200 hover:bg-stone-50 flex items-center justify-center text-stone-700 hover:text-emerald-700 transition-colors ${
        direction === 'prev' ? '-left-5' : '-right-5'
      }`}
    >
      {direction === 'prev' ? <ChevronLeft size={20} /> : <ChevronRight size={20} />}
    </button>
  );
}

function SlideCard({ title, badge, children }: {
  title: string; badge?: React.ReactNode; children: React.ReactNode;
}) {
  return (
    <Card className="!h-auto min-h-[600px] p-8 mx-2">
      <div className="flex items-center gap-2 mb-6 pb-4 border-b border-stone-100">
        <div className="text-[18px] text-stone-900">{title}</div>
        {badge}
      </div>
      <div className="text-[14px]">{children}</div>
    </Card>
  );
}

export function CompanyOverview() {
  const navigate = useNavigate();
  const analysis = useMemo(() => loadCompanyAnalysis(), []);
  const evidenceCards = useMemo(() => analysisEvidenceCards(analysis), [analysis]);
  const companyName = companyDisplayName(analysis);
  const profile = useMemo(() => companyProfileFromAnalysis(analysis), [analysis]);
  const abn = profile.abn;
  const [showWatchlist, setShowWatchlist] = useState(false);
  const [showExport, setShowExport] = useState(false);
  const [pageState, setPageState] = useState<'ready' | 'loading' | 'empty' | 'error'>('ready');
  const [currentSlide, setCurrentSlide] = useState(0);
  const sliderRef = useRef<Slider>(null);

  if (pageState === 'loading') return <LoadingState onCancel={() => setPageState('ready')} />;
  if (pageState === 'empty') return <EmptyState onRetry={() => setPageState('ready')} />;
  if (pageState === 'error') return <ErrorState onRetry={() => setPageState('ready')} />;

  return (
    <div className="min-h-screen bg-gradient-to-b from-[#f5f3ee] via-[#eef1ec] to-[#e3ebe4]">
      <div className="max-w-[1400px] mx-auto px-6 py-6">

        {/* === COMPANY HEADER === */}
        <Card className="p-5 mb-5 bg-white">
          <div className="flex items-start gap-4 flex-wrap">
            <div className="w-14 h-14 rounded-2xl bg-gradient-to-br from-stone-900 to-stone-700 text-white flex items-center justify-center shrink-0">
              <Building2 size={26} />
            </div>
            <div className="flex-1 min-w-[260px]">
              <div className="flex items-center gap-2 flex-wrap">
                <div className="text-[20px] text-stone-900 leading-tight">{companyName}</div>
                <Chip tone="emerald"><CheckCircle2 size={11} /> ABR verified</Chip>
                <Chip tone="blue">{analysis?.resolution?.normalized_name || 'ASX: BHP'}</Chip>
                <Chip tone="stone">Public</Chip>
                <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[11px] bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200">
                  <Radio size={10} /> High coverage
                </span>
              </div>
              <div className="text-[12.5px] text-stone-500 mt-1.5 flex items-center gap-3 flex-wrap">
                <span>{abn ? `ABN ${abn}` : 'ABN pending'}</span>
                <span className="w-1 h-1 rounded-full bg-stone-300" />
                <span className="inline-flex items-center gap-1"><Factory size={11} /> {profile.sector}</span>
                <span className="w-1 h-1 rounded-full bg-stone-300" />
                <span className="inline-flex items-center gap-1"><MapPin size={11} /> {profile.state}{profile.postcode ? ` ${profile.postcode}` : ''}</span>
                <span className="w-1 h-1 rounded-full bg-stone-300" />
                <span className="inline-flex items-center gap-1"><RefreshCw size={11} /> {evidenceCards.length ? `${evidenceCards.length} live evidence records` : 'Updated 2h ago'}</span>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <button onClick={() => navigate('/app/knowledge')} className="inline-flex items-center gap-1.5 px-3 h-9 rounded-lg border border-emerald-200 bg-emerald-50 hover:bg-emerald-100 text-emerald-800 text-[13px]"><GitBranch size={14} /> Knowledge</button>
              <button onClick={() => navigate('/app/analyse')} className="inline-flex items-center gap-1.5 px-3 h-9 rounded-lg border border-emerald-200 bg-emerald-50 hover:bg-emerald-100 text-emerald-800 text-[13px]"><Map size={14} /> Analyse</button>
              <button onClick={() => setShowWatchlist(true)} className="inline-flex items-center gap-1.5 px-3 h-9 rounded-lg bg-stone-900 text-white hover:bg-stone-800 text-[13px]"><Star size={14} /> Watchlist</button>
            </div>
          </div>
        </Card>

        {/* === PROFILE & EXPOSURE ROW === */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-5 mb-5">
          <Card className="p-5">
            <div className="text-[11px] uppercase tracking-[0.18em] text-stone-500 mb-3">Profile</div>
            <div className="text-[13px] text-stone-700 leading-relaxed">
              {companyName} is resolved through ABR and analysed against configured news sources plus any uploaded company reports.
            </div>
            <div className="grid grid-cols-2 gap-3 mt-4 text-[12px]">
              <div><div className="text-stone-500">ABN status</div><div className="text-stone-900">{analysis?.resolution?.abn_status || 'Verified'}</div></div>
              <div><div className="text-stone-500">State</div><div className="text-stone-900">{profile.state}</div></div>
              <div><div className="text-stone-500">Evidence records</div><div className="text-stone-900">{profile.evidenceCount}</div></div>
              <div><div className="text-stone-500">News candidates</div><div className="text-stone-900">{profile.newsCandidateCount}</div></div>
            </div>
          </Card>

          <Card className="p-5">
            <div className="text-[11px] uppercase tracking-[0.18em] text-stone-500 mb-3">Exposure tags</div>
            <div className="flex flex-wrap gap-1.5">
              {exposureTags.map(t => <Chip key={t} tone="emerald">{t}</Chip>)}
            </div>
          </Card>
        </div>

        {/* === SLIDER ROW === */}
        <div className="mb-5">
            <div className="mb-3 px-2">
              <div className="flex items-center justify-between mb-2">
                <div className="text-[11px] uppercase tracking-[0.18em] text-stone-500">
                  Section {currentSlide + 1} of {navAnchors.length}
                </div>
                <div className="text-[12px] text-stone-600">{navAnchors[currentSlide]?.label}</div>
              </div>
              <div className="h-1 bg-stone-100 rounded-full overflow-hidden">
                <div
                  className="h-full bg-gradient-to-r from-emerald-600 to-emerald-500 transition-all duration-500"
                  style={{ width: `${((currentSlide + 1) / navAnchors.length) * 100}%` }}
                />
              </div>
            </div>
            <Slider
              ref={sliderRef}
              dots={false}
              infinite={false}
              speed={500}
              slidesToShow={1}
              slidesToScroll={1}
              beforeChange={(_, next) => setCurrentSlide(next)}
              arrows={true}
              prevArrow={<SliderArrow direction="prev" />}
              nextArrow={<SliderArrow direction="next" />}
            >
              {/* SLIDE 0: Risk intelligence */}
              <div>
                <SlideCard title="Risk intelligence" badge={<Chip tone="emerald">Nature Risk</Chip>}>
              <div className="flex items-center gap-6 flex-wrap pt-4">
                <div className="relative">
                  <RadialGauge value={SCORE} />
                  {/* orbiting chips */}
                  {orbitChips.map((c) => {
                    const Icon = c.icon;
                    const rad = (c.angle * Math.PI) / 180;
                    const x = 120 + 145 * Math.cos(rad);
                    const y = 120 + 145 * Math.sin(rad);
                    return (
                      <div key={c.label} className="absolute hidden xl:flex items-center gap-1 px-2 py-1 rounded-full bg-white shadow-sm border border-stone-200 text-[10.5px] text-stone-700 whitespace-nowrap"
                        style={{ left: x, top: y, transform: 'translate(-50%, -50%)' }}>
                        <Icon size={10} className="text-emerald-700" /> {c.label}
                      </div>
                    );
                  })}
                </div>

                <div className="flex-1 min-w-[280px] space-y-3">
                  <div className="flex items-center gap-2 flex-wrap">
                    <RiskBadge level="High" />
                    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-rose-50 text-rose-700 text-[11px] ring-1 ring-rose-200">
                      <TrendingUp size={11} /> +{CHANGE_30D} in 30 days
                    </span>
                  </div>
                  <div className="text-[13px] text-stone-700 leading-relaxed">
                    Elevated biodiversity risk based on location overlap, supplier exposure, and recent evidence ingested over the last quarter.
                  </div>

                  <div className="grid grid-cols-2 gap-3">
                    <div className="p-3 rounded-xl bg-white/70 border border-stone-100">
                      <div className="flex items-center gap-1.5 text-[10.5px] uppercase tracking-wider text-stone-500"><BarChart3 size={11} /> 12-mo trend</div>
                      <Sparkline data={trend12mo} />
                      <MetricExplain>Deteriorating — score rose from 62 → 82 over 12 months.</MetricExplain>
                    </div>
                    <div className="p-3 rounded-xl bg-white/70 border border-stone-100">
                      <div className="flex items-center gap-1.5 text-[10.5px] uppercase tracking-wider text-stone-500"><Users2 size={11} /> Peer percentile</div>
                      <div className="text-[28px] leading-none tracking-tight text-stone-900 mt-1">{PEER_PERCENTILE}<span className="text-[14px] text-stone-400">th</span></div>
                      <MetricExplain>Higher risk than {PEER_PERCENTILE}% of sector peers.</MetricExplain>
                    </div>
                    <div className="p-3 rounded-xl bg-white/70 border border-stone-100">
                      <div className="flex items-center gap-1.5 text-[10.5px] uppercase tracking-wider text-stone-500"><ShieldCheck size={11} /> Confidence</div>
                      <div className="flex items-center gap-2 mt-1">
                        <div className="text-[22px] leading-none text-stone-900">{CONFIDENCE}%</div>
                        <div className="flex-1 h-1.5 bg-stone-100 rounded-full overflow-hidden">
                          <div className="h-full bg-emerald-500" style={{ width: `${CONFIDENCE}%` }} />
                        </div>
                      </div>
                      <MetricExplain>Recent, traceable, multi-source evidence.</MetricExplain>
                    </div>
                    <div className="p-3 rounded-xl bg-white/70 border border-stone-100">
                      <div className="flex items-center gap-1.5 text-[10.5px] uppercase tracking-wider text-stone-500"><Database size={11} /> Data coverage</div>
                      <div className="flex items-center gap-2 mt-1">
                        <div className="text-[22px] leading-none text-stone-900">{COVERAGE}%</div>
                        <div className="flex-1 h-1.5 bg-stone-100 rounded-full overflow-hidden">
                          <div className="h-full bg-blue-500" style={{ width: `${COVERAGE}%` }} />
                        </div>
                      </div>
                      <MetricExplain>{SOURCES} sources resolved · supplier data partial.</MetricExplain>
                    </div>
                  </div>
                </div>
              </div>
                </SlideCard>
              </div>

              {/* SLIDE 1: Executive summary */}
              <div>
                <SlideCard title="Executive summary" badge={<Chip tone="stone">For investors</Chip>}>
              <ul className="space-y-2.5 text-[13px] text-stone-700 pt-3">
                <li className="flex gap-2"><span className="w-1.5 h-1.5 rounded-full bg-rose-500 mt-1.5 shrink-0" />
                  <span><b className="text-stone-900">Main signal:</b> Iron-ore expansion in the Pilbara has materially increased spatial overlap with three protected ecosystems.</span></li>
                <li className="flex gap-2"><span className="w-1.5 h-1.5 rounded-full bg-amber-500 mt-1.5 shrink-0" />
                  <span><b className="text-stone-900">Recent change:</b> Supplier-linked exposure rose +18 pts after a Tier-2 mill in Brazil was geolocated within 4 km of a KBA.</span></li>
                <li className="flex gap-2"><span className="w-1.5 h-1.5 rounded-full bg-blue-500 mt-1.5 shrink-0" />
                  <span><b className="text-stone-900">Why it matters:</b> EU CSRD and TNFD alignment gaps may widen ESG-rating spreads and raise cost of capital by 8–14 bps.</span></li>
              </ul>
              <div className="flex flex-wrap gap-1.5 mt-4">
                {['Regulatory', 'Supply Chain', 'Spatial', 'Reputational', 'Disclosure Gap'].map(m =>
                  <Chip key={m} tone="amber">{m}</Chip>)}
              </div>
                </SlideCard>
              </div>

              {/* SLIDE 2: Score composition */}
              <div>
                <SlideCard title="Score composition" badge={<Chip tone="stone">82 pts total</Chip>}>
              <MetricExplain>Each segment shows how many points of the total risk score come from that driver.</MetricExplain>
              <div className="mt-4 flex h-3 rounded-full overflow-hidden border border-stone-100">
                {composition.map(s => (
                  <div key={s.key} title={`${s.value} pts from ${s.label}`}
                    style={{ width: `${(s.value / SCORE) * 100}%`, background: s.color }} />
                ))}
              </div>
              <div className="grid grid-cols-2 gap-3 mt-4">
                {composition.map(s => (
                  <div key={s.key} className="flex items-start gap-2 p-3 rounded-lg bg-stone-50">
                    <span className="w-2.5 h-2.5 rounded-sm mt-1 shrink-0" style={{ background: s.color }} />
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center justify-between gap-2">
                        <div className="text-[12.5px] text-stone-900 truncate">{s.label}</div>
                        <div className="text-[12.5px] text-stone-700 tabular-nums">{s.value} pts</div>
                      </div>
                      <div className="text-[11px] text-stone-500 leading-snug">{s.desc}</div>
                    </div>
                  </div>
                ))}
              </div>
                </SlideCard>
              </div>

              {/* SLIDE 3: TNFD snapshot */}
              <div>
                <SlideCard title="TNFD snapshot" badge={<Chip tone="emerald">LEAP framework</Chip>}>
              <div className="grid grid-cols-2 gap-3 pt-3">
                {tnfd.map(p => {
                  const Icon = p.icon;
                  const tones: Record<string, string> = {
                    emerald: 'from-emerald-50 to-white border-emerald-100 text-emerald-700',
                    blue: 'from-blue-50 to-white border-blue-100 text-blue-700',
                    amber: 'from-amber-50 to-white border-amber-100 text-amber-700',
                    rose: 'from-rose-50 to-white border-rose-100 text-rose-700',
                  };
                  return (
                    <div key={p.phase} className={`p-4 rounded-xl bg-gradient-to-br ${tones[p.tone]} border`}>
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2">
                          <Icon size={15} />
                          <div className="text-[13px] text-stone-900">{p.phase}</div>
                        </div>
                        <div className="text-[10.5px] uppercase tracking-wider">{p.status}</div>
                      </div>
                      <div className="text-[20px] leading-none tracking-tight text-stone-900 mt-3">{p.metric}</div>
                      <div className="text-[11.5px] text-stone-600 mt-1">{p.sub}</div>
                    </div>
                  );
                })}
              </div>
                </SlideCard>
              </div>

              {/* SLIDE 4: Key findings */}
              <div>
                <SlideCard title="Key findings" badge={<Chip tone="stone">4 insights</Chip>}>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3 pt-3">
                {findings.map((f, i) => {
                  const Icon = f.icon;
                  const tones: Record<string, string> = {
                    rose: 'bg-rose-50 text-rose-700', amber: 'bg-amber-50 text-amber-700',
                    orange: 'bg-orange-50 text-orange-700', blue: 'bg-blue-50 text-blue-700',
                  };
                  return (
                    <div key={i} className="p-4 rounded-xl border border-stone-100 bg-white">
                      <div className="flex items-center gap-2">
                        <div className={`w-7 h-7 rounded-lg flex items-center justify-center ${tones[f.tone]}`}><Icon size={14} /></div>
                        <div className="text-[22px] leading-none tracking-tight text-stone-900">{f.metric}</div>
                      </div>
                      <div className="text-[12.5px] text-stone-700 mt-2 leading-snug">{f.label}</div>
                      <div className="text-[11px] text-stone-500 mt-2 leading-snug italic">Why investors care: {f.why}</div>
                    </div>
                  );
                })}
              </div>
                </SlideCard>
              </div>

              {/* SLIDE 5: Peer comparison */}
              <div>
                <SlideCard title="Peer comparison" badge={<Chip tone="stone">Sector-matched</Chip>}>
              <MetricExplain>Peers selected by GICS sector overlap and market-cap band. Median = {peerMedian}.</MetricExplain>
              <div className="space-y-2.5 mt-4">
                {peers.map(p => (
                  <div key={p.name} className={`flex items-center gap-3 p-3 rounded-lg ${p.self ? 'bg-emerald-50 border border-emerald-200' : 'bg-stone-50'}`}>
                    <div className={`text-[12.5px] w-32 ${p.self ? 'text-emerald-800 font-medium' : 'text-stone-700'}`}>
                      {p.name} {p.self && <span className="text-[10px]">(this)</span>}
                    </div>
                    <div className="flex-1 relative h-2 bg-white rounded-full overflow-hidden">
                      <div className="absolute top-0 bottom-0 w-px bg-stone-400" style={{ left: `${peerMedian}%` }} />
                      <div className={`h-full rounded-full ${p.self ? 'bg-emerald-600' : 'bg-stone-400'}`} style={{ width: `${p.score}%` }} />
                    </div>
                    <div className="text-[12px] tabular-nums text-stone-700 w-12 text-right">{p.score}</div>
                    <div className="text-[10.5px] tabular-nums text-stone-500 w-14 text-right">{p.pct}th pct</div>
                    <div className="text-[10.5px] tabular-nums text-stone-500 w-14 text-right">{p.conf}% conf</div>
                  </div>
                ))}
              </div>
                </SlideCard>
              </div>

              {/* SLIDE 6: Evidence quality */}
              <div>
                <SlideCard title="Evidence quality" badge={<Chip tone="stone">{SOURCES} sources</Chip>}>
                  <MetricExplain>{SOURCES} sources contributing to this assessment.</MetricExplain>
                  <div className="mt-4">
                    <div className="text-[10.5px] uppercase tracking-wider text-stone-500 mb-1.5">Source mix</div>
                    <div className="flex h-2.5 rounded-full overflow-hidden border border-stone-100">
                      {sourceMix.map(s => <div key={s.type} className={s.color} style={{ width: `${(s.n / SOURCES) * 100}%` }} title={`${s.type}: ${s.n}`} />)}
                    </div>
                    <div className="mt-2 grid grid-cols-1 gap-1">
                      {sourceMix.map(s => (
                        <div key={s.type} className="flex items-center gap-2 text-[11.5px] text-stone-600">
                          <span className={`w-2 h-2 rounded-sm ${s.color}`} />
                          <span className="flex-1">{s.type}</span>
                          <span className="tabular-nums">{s.n}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                  <div className="mt-4 pt-4 border-t border-stone-100">
                    <div className="text-[10.5px] uppercase tracking-wider text-stone-500 mb-2">Recency</div>
                    <div className="grid grid-cols-4 gap-1">
                      {[3, 6, 5, 4].map((n, i) => (
                        <div key={i} className="flex flex-col items-center">
                          <div className="w-full bg-emerald-200 rounded-sm" style={{ height: `${n * 6}px` }} />
                          <div className="text-[9.5px] text-stone-500 mt-1">{['<30d', '<90d', '<1y', '>1y'][i]}</div>
                        </div>
                      ))}
                    </div>
                  </div>
                  <div className="mt-4 pt-4 border-t border-stone-100 flex items-center justify-between text-[12px]">
                    <span className="text-stone-600">Verified</span>
                    <span className="text-emerald-700">14 / 18 (78%)</span>
                  </div>
                </SlideCard>
              </div>

              {/* SLIDE 7: Provenance */}
              <div>
                <SlideCard title="Provenance" badge={<Chip tone="emerald">Auditable</Chip>}>
                  <MetricExplain>Every claim is traceable to its underlying source document.</MetricExplain>
                  <div className="space-y-3 mt-4 text-[12.5px]">
                    <div className="flex items-center justify-between"><span className="text-stone-600">Traceable claims</span><span className="text-stone-900 tabular-nums">{evidenceCards.length || 142}</span></div>
                    <div className="flex items-center justify-between"><span className="text-stone-600">News evidence</span><span className="text-emerald-700 tabular-nums">{analysis?.news?.evidence?.length ?? 0}</span></div>
                    <div className="flex items-center justify-between"><span className="text-stone-600">Report evidence</span><span className="text-emerald-700 tabular-nums">{analysis?.reports?.evidence_count ?? 0}</span></div>
                    <div className="flex items-center justify-between"><span className="text-stone-600">Avg extraction conf.</span><span className="text-stone-900 tabular-nums">{evidenceCards.length ? `${Math.round(evidenceCards.reduce((sum, item) => sum + item.conf, 0) / evidenceCards.length)}%` : '94%'}</span></div>
                  </div>
                  <button onClick={() => navigate('/app/knowledge')} className="mt-4 w-full inline-flex items-center justify-center gap-1.5 h-9 rounded-lg border border-stone-200 hover:bg-stone-50 text-[12.5px] text-stone-800">
                    <FileCheck2 size={13} /> Open full audit trail
                  </button>
                </SlideCard>
              </div>

              {/* SLIDE 8: What changed */}
              <div>
                <SlideCard title="What changed" badge={<Chip tone="stone">Last 30d</Chip>}>
                  <div className="mt-4 relative">
                    <div className="absolute left-[11px] top-2 bottom-2 w-px bg-stone-200" />
                    <div className="space-y-3">
                      {timeline.map((e, i) => {
                        const Icon = e.icon;
                        const tones: Record<string, string> = {
                          emerald: 'bg-emerald-100 text-emerald-700', rose: 'bg-rose-100 text-rose-700',
                          amber: 'bg-amber-100 text-amber-700', orange: 'bg-orange-100 text-orange-700',
                          stone: 'bg-stone-100 text-stone-700',
                        };
                        return (
                          <div key={i} className="flex gap-3 relative">
                            <div className={`w-6 h-6 rounded-full flex items-center justify-center shrink-0 ${tones[e.tone]} ring-2 ring-white relative z-10`}>
                              <Icon size={11} />
                            </div>
                            <div className="flex-1 min-w-0">
                              <div className="text-[12.5px] text-stone-900 leading-tight">{e.t}</div>
                              <div className="text-[11px] text-stone-500">{e.sub}</div>
                              <div className="text-[10px] text-stone-400 mt-0.5 inline-flex items-center gap-1"><Calendar size={9} /> {e.d}</div>
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                </SlideCard>
              </div>

              {/* SLIDE 9: Explain this score */}
              <div>
                <SlideCard title="Explain this score" badge={<Chip tone="emerald"><Sparkles size={10} /> Investor-friendly</Chip>}>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4 pt-3">
                  <div>
                    <div className="text-[11px] uppercase tracking-wider text-rose-600 mb-2 flex items-center gap-1"><Plus size={11} /> What raised the score</div>
                    <ul className="space-y-1.5 text-[12.5px] text-stone-700">
                      <li>• New supplier-linked spatial evidence (+12)</li>
                      <li>• EPBC referral filed Apr 2026 (+4)</li>
                      <li>• Adverse media uptick (+3)</li>
                    </ul>
                  </div>
                  <div>
                    <div className="text-[11px] uppercase tracking-wider text-emerald-700 mb-2 flex items-center gap-1"><Minus size={11} /> What lowered the score</div>
                    <ul className="space-y-1.5 text-[12.5px] text-stone-700">
                      <li>• Restoration milestone — 142 ha replanted (−2)</li>
                      <li>• Improved disclosure on water (−1)</li>
                    </ul>
                  </div>
                  <div>
                    <div className="text-[11px] uppercase tracking-wider text-amber-600 mb-2 flex items-center gap-1"><AlertCircle size={11} /> Where data is incomplete</div>
                    <ul className="space-y-1.5 text-[12.5px] text-stone-700">
                      <li>• Tier-3 supplier mapping (38% resolved)</li>
                      <li>• Latin-American site geocoding</li>
                    </ul>
                  </div>
                  <div>
                    <div className="text-[11px] uppercase tracking-wider text-stone-600 mb-2 flex items-center gap-1"><Layers size={11} /> Direct vs inferred</div>
                    <div className="flex h-3 rounded-full overflow-hidden border border-stone-100">
                      <div className="bg-emerald-500" style={{ width: '64%' }} />
                      <div className="bg-stone-300" style={{ width: '36%' }} />
                    </div>
                    <div className="flex justify-between text-[11px] text-stone-500 mt-1.5">
                      <span>64% direct evidence</span><span>36% inferred</span>
                    </div>
                  </div>
              </div>
                </SlideCard>
              </div>
            </Slider>
        </div>

        {/* === ANALYST ACTIONS ROW === */}
        <Card className="p-5 bg-gradient-to-br from-stone-50 to-emerald-50/40">
          <div className="text-[14px] text-stone-900 mb-1">Analyst actions</div>
          <div className="text-[11px] text-amber-700 inline-flex items-center gap-1 mb-3"><Bell size={11} /> 2 alerts triggered in past 90 days</div>
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-2">
            <button onClick={() => setShowWatchlist(true)} className="inline-flex items-center justify-center gap-1.5 h-9 rounded-lg bg-white border border-stone-200 hover:bg-stone-50 text-[12px]"><Star size={12} /> Watchlist</button>
            <button onClick={() => setShowExport(true)} className="inline-flex items-center justify-center gap-1.5 h-9 rounded-lg bg-stone-900 text-white hover:bg-stone-800 text-[12px]"><Download size={12} /> Export PDF</button>
            <button className="inline-flex items-center justify-center gap-1.5 h-9 rounded-lg bg-white border border-stone-200 hover:bg-stone-50 text-[12px]"><Users2 size={12} /> Compare peers</button>
            <button className="inline-flex items-center justify-center gap-1.5 h-9 rounded-lg bg-white border border-stone-200 hover:bg-stone-50 text-[12px]"><FileText size={12} /> TNFD report</button>
            <button onClick={() => navigate('/app/knowledge')} className="inline-flex items-center justify-center gap-1.5 h-9 rounded-lg border border-emerald-200 bg-emerald-50 hover:bg-emerald-100 text-emerald-800 text-[12px]"><Eye size={12} /> View evidence</button>
          </div>
          <div className="mt-3 pt-3 border-t border-stone-200/60 flex flex-wrap gap-1">
            <button onClick={() => setPageState('loading')} className="text-[10px] text-stone-400 hover:text-stone-700">· loading</button>
            <button onClick={() => setPageState('empty')} className="text-[10px] text-stone-400 hover:text-stone-700">· empty</button>
            <button onClick={() => setPageState('error')} className="text-[10px] text-stone-400 hover:text-stone-700">· error</button>
          </div>
        </Card>
      </div>

      {/* === MODALS === */}
      {showWatchlist && <WatchlistModal companyName={companyName} onClose={() => setShowWatchlist(false)} />}
      {showExport && <ExportModal companyName={companyName} onClose={() => setShowExport(false)} />}
    </div>
  );
}

function WatchlistModal({ companyName, onClose }: { companyName: string; onClose: () => void }) {
  const [freq, setFreq] = useState('weekly');
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-stone-900/40 backdrop-blur-sm" onClick={onClose} />
      <div className="relative w-full max-w-md bg-white rounded-2xl shadow-2xl overflow-hidden">
        <div className="p-5 border-b border-stone-100 flex items-center justify-between">
          <div className="flex items-center gap-2 text-stone-900 text-[14px]">
            <Star size={16} className="text-emerald-600" /> Add to watchlist
          </div>
          <button onClick={onClose} className="w-7 h-7 flex items-center justify-center rounded-full text-stone-400 hover:bg-stone-100"><X size={14} /></button>
        </div>
        <div className="p-5 space-y-4">
          <p className="text-[13px] text-stone-600">Track <b className="text-stone-900">{companyName}</b> and receive alerts when its biodiversity risk score, evidence base, or coverage changes materially.</p>
          <div>
            <div className="text-[11px] uppercase tracking-wider text-stone-500 mb-2">Alert frequency</div>
            <div className="grid grid-cols-3 gap-2">
              {['daily', 'weekly', 'on change'].map(f => (
                <button key={f} onClick={() => setFreq(f)} className={`h-9 rounded-lg border text-[12.5px] capitalize ${freq === f ? 'border-emerald-500 bg-emerald-50 text-emerald-800' : 'border-stone-200 text-stone-700 hover:bg-stone-50'}`}>{f}</button>
              ))}
            </div>
          </div>
          <div>
            <div className="text-[11px] uppercase tracking-wider text-stone-500 mb-2">Email</div>
            <input type="email" placeholder="analyst@firm.com" className="w-full px-3 h-9 rounded-lg border border-stone-200 text-[13px] focus:outline-none focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500" />
          </div>
          <button onClick={onClose} className="w-full h-10 rounded-lg bg-emerald-700 hover:bg-emerald-800 text-white text-[13px]">Add to watchlist</button>
        </div>
      </div>
    </div>
  );
}

function ExportModal({ companyName, onClose }: { companyName: string; onClose: () => void }) {
  const [sections, setSections] = useState({ hero: true, summary: true, composition: true, tnfd: true, findings: true, peers: false, evidence: true, timeline: false });
  const toggle = (k: keyof typeof sections) => setSections(s => ({ ...s, [k]: !s[k] }));
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-stone-900/40 backdrop-blur-sm" onClick={onClose} />
      <div className="relative w-full max-w-md bg-white rounded-2xl shadow-2xl overflow-hidden">
        <div className="p-5 border-b border-stone-100 flex items-center justify-between">
          <div className="flex items-center gap-2 text-stone-900 text-[14px]"><Download size={16} className="text-emerald-600" /> Export PDF</div>
          <button onClick={onClose} className="w-7 h-7 flex items-center justify-center rounded-full text-stone-400 hover:bg-stone-100"><X size={14} /></button>
        </div>
        <div className="p-5 space-y-4">
          <p className="text-[13px] text-stone-600">Generate an investor-ready PDF dossier for <b className="text-stone-900">{companyName}</b>.</p>
          <div>
            <div className="text-[11px] uppercase tracking-wider text-stone-500 mb-2">Include sections</div>
            <div className="grid grid-cols-2 gap-2">
              {Object.entries(sections).map(([k, v]) => (
                <label key={k} className="flex items-center gap-2 text-[12.5px] text-stone-700 cursor-pointer p-2 rounded-md hover:bg-stone-50">
                  <input type="checkbox" checked={v} onChange={() => toggle(k as keyof typeof sections)} className="accent-emerald-600" /> <span className="capitalize">{k}</span>
                </label>
              ))}
            </div>
          </div>
          <div className="flex gap-2">
            <button onClick={onClose} className="flex-1 h-10 rounded-lg border border-stone-200 text-[13px] text-stone-700 hover:bg-stone-50">Cancel</button>
            <button onClick={onClose} className="flex-1 h-10 rounded-lg bg-stone-900 text-white text-[13px] hover:bg-stone-800 inline-flex items-center justify-center gap-1.5"><Download size={13} /> Export</button>
          </div>
        </div>
      </div>
    </div>
  );
}

function LoadingState({ onCancel }: { onCancel: () => void }) {
  return (
    <div className="min-h-screen bg-gradient-to-b from-[#f5f3ee] via-[#eef1ec] to-[#e3ebe4] p-6">
      <div className="max-w-[1400px] mx-auto space-y-5">
        <div className="h-20 rounded-2xl bg-white border border-stone-200 animate-pulse" />
        <div className="grid grid-cols-12 gap-5">
          <div className="col-span-3 space-y-5">
            {[1, 2, 3].map(i => <div key={i} className="h-32 rounded-2xl bg-white border border-stone-200 animate-pulse" />)}
          </div>
          <div className="col-span-6 space-y-5">
            <div className="h-72 rounded-2xl bg-white border border-stone-200 animate-pulse flex items-center justify-center">
              <div className="text-[13px] text-stone-500 inline-flex items-center gap-2"><RefreshCw size={14} className="animate-spin" /> Resolving evidence sources…</div>
            </div>
            {[1, 2].map(i => <div key={i} className="h-44 rounded-2xl bg-white border border-stone-200 animate-pulse" />)}
          </div>
          <div className="col-span-3 space-y-5">
            {[1, 2, 3].map(i => <div key={i} className="h-32 rounded-2xl bg-white border border-stone-200 animate-pulse" />)}
          </div>
        </div>
        <button onClick={onCancel} className="text-[12px] text-stone-500 hover:text-stone-800">Cancel</button>
      </div>
    </div>
  );
}

function EmptyState({ onRetry }: { onRetry: () => void }) {
  return (
    <div className="min-h-screen bg-gradient-to-b from-[#f5f3ee] via-[#eef1ec] to-[#e3ebe4] p-6 flex items-center justify-center">
      <Card className="p-10 max-w-lg text-center">
        <div className="w-14 h-14 rounded-2xl bg-stone-100 text-stone-500 flex items-center justify-center mx-auto"><Search size={26} /></div>
        <div className="text-[18px] text-stone-900 mt-4">No evidence found yet</div>
        <p className="text-[13px] text-stone-600 mt-2 leading-relaxed">We couldn't locate biodiversity-relevant filings, geospatial overlays, or supplier records for this company. Try expanding the time window or adding a manual source.</p>
        <div className="flex gap-2 justify-center mt-5">
          <button onClick={onRetry} className="h-9 px-4 rounded-lg border border-stone-200 text-[13px] hover:bg-stone-50">Back</button>
          <button className="h-9 px-4 rounded-lg bg-emerald-700 text-white text-[13px] hover:bg-emerald-800 inline-flex items-center gap-1.5"><Plus size={13} /> Add a source</button>
        </div>
      </Card>
    </div>
  );
}

function ErrorState({ onRetry }: { onRetry: () => void }) {
  return (
    <div className="min-h-screen bg-gradient-to-b from-[#f5f3ee] via-[#eef1ec] to-[#e3ebe4] p-6 flex items-center justify-center">
      <Card className="p-10 max-w-lg text-center border-rose-200">
        <div className="w-14 h-14 rounded-2xl bg-rose-50 text-rose-600 flex items-center justify-center mx-auto"><AlertCircle size={26} /></div>
        <div className="text-[18px] text-stone-900 mt-4">We couldn't resolve some data sources</div>
        <p className="text-[13px] text-stone-600 mt-2 leading-relaxed">One or more upstream providers returned an error. Partial intelligence may be available — retry to attempt resolution again.</p>
        <div className="flex gap-2 justify-center mt-5">
          <button onClick={onRetry} className="h-9 px-4 rounded-lg border border-stone-200 text-[13px] hover:bg-stone-50">Continue with partial data</button>
          <button onClick={onRetry} className="h-9 px-4 rounded-lg bg-stone-900 text-white text-[13px] hover:bg-stone-800 inline-flex items-center gap-1.5"><RefreshCw size={13} /> Retry</button>
        </div>
      </Card>
    </div>
  );
}

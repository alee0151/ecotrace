import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router';
import {
  Activity,
  AlertTriangle,
  ArrowRight,
  BarChart3,
  Bell,
  Building2,
  CheckCircle2,
  ClipboardCheck,
  Compass,
  Database,
  Download,
  ExternalLink,
  FileBarChart2,
  FileCheck2,
  FileText,
  Globe2,
  Leaf,
  Map as MapIcon,
  MapPin,
  Newspaper,
  RefreshCw,
  ScanSearch,
  Search,
  ShieldCheck,
  Sparkles,
  Star,
  X,
  type LucideIcon,
} from 'lucide-react';
import { Card, Chip, RiskBadge, SectionTitle } from '../components/shared';
import {
  allEvidenceRecords,
  analysisEvidenceCards,
  companyDisplayName,
  companyProfileFromAnalysis,
  confidencePercent,
  loadCompanyAnalysis,
  type BackendCompanyAnalysis,
  type BackendEvidenceRecord,
  type BackendSpatialAnalysis,
} from '../lib/analysis';
import {
  generateReport,
  getSpatialAnalysisForQuery,
  reportHtmlUrl,
  sendPersistedReportEmail,
} from '../../lib/api';

type Tone = 'stone' | 'emerald' | 'blue' | 'amber' | 'rose' | 'purple' | 'sky';

const toneStyles: Record<Tone, { icon: string; soft: string; bar: string; text: string }> = {
  stone: {
    icon: 'bg-stone-100 text-stone-700',
    soft: 'bg-stone-50 border-stone-200',
    bar: 'bg-stone-500',
    text: 'text-stone-700',
  },
  emerald: {
    icon: 'bg-emerald-50 text-emerald-700',
    soft: 'bg-emerald-50 border-emerald-200',
    bar: 'bg-emerald-500',
    text: 'text-emerald-700',
  },
  blue: {
    icon: 'bg-blue-50 text-blue-700',
    soft: 'bg-blue-50 border-blue-200',
    bar: 'bg-blue-500',
    text: 'text-blue-700',
  },
  amber: {
    icon: 'bg-amber-50 text-amber-700',
    soft: 'bg-amber-50 border-amber-200',
    bar: 'bg-amber-500',
    text: 'text-amber-700',
  },
  rose: {
    icon: 'bg-rose-50 text-rose-700',
    soft: 'bg-rose-50 border-rose-200',
    bar: 'bg-rose-500',
    text: 'text-rose-700',
  },
  purple: {
    icon: 'bg-purple-50 text-purple-700',
    soft: 'bg-purple-50 border-purple-200',
    bar: 'bg-purple-500',
    text: 'text-purple-700',
  },
  sky: {
    icon: 'bg-sky-50 text-sky-700',
    soft: 'bg-sky-50 border-sky-200',
    bar: 'bg-sky-500',
    text: 'text-sky-700',
  },
};

function clamp(value: number, min = 0, max = 100) {
  return Math.max(min, Math.min(max, value));
}

function formatNumber(value: number | undefined | null) {
  if (typeof value !== 'number' || !Number.isFinite(value)) return 'N/A';
  return new Intl.NumberFormat('en-AU').format(value);
}

function formatDate(value?: string | null) {
  if (!value) return 'Latest analysis';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleDateString('en-AU', { day: '2-digit', month: 'short', year: 'numeric' });
}

function spatialScore(spatial: BackendSpatialAnalysis | null | undefined) {
  const score = spatial?.species_threat_score;
  if (typeof score !== 'number' || !Number.isFinite(score)) return null;
  return Math.round(clamp(score));
}

function sourceLabel(value?: string | null) {
  if (!value) return 'Evidence';
  return value
    .replace(/[_-]+/g, ' ')
    .replace(/\b\w/g, letter => letter.toUpperCase());
}

function evidenceTitle(record: BackendEvidenceRecord) {
  return record.biodiversity_signal || record.evidence_type || 'Biodiversity evidence';
}

function evidenceLocation(record: BackendEvidenceRecord) {
  return record.location || 'Location not stated';
}

function categoryTone(category?: string | null): Tone {
  const normalized = (category || '').toUpperCase();
  if (normalized === 'CR') return 'rose';
  if (normalized === 'EN') return 'amber';
  if (normalized === 'VU') return 'blue';
  return 'stone';
}

function riskDriverTone(value: number): Tone {
  if (value >= 75) return 'rose';
  if (value >= 50) return 'amber';
  if (value >= 25) return 'blue';
  return 'emerald';
}

function sourceMix(analysis: BackendCompanyAnalysis | null, records: BackendEvidenceRecord[]) {
  const counts = new Map<string, number>();
  const add = (label: string, amount = 1) => counts.set(label, (counts.get(label) || 0) + amount);

  records.forEach(record => add(sourceLabel(record.source_type)));
  if (analysis?.news?.candidates?.length || analysis?.news?.candidate_count) {
    add('News candidates', analysis.news.candidates?.length || analysis.news.candidate_count || 0);
  }
  if (analysis?.analysed_reports?.length) add('Uploaded reports', analysis.analysed_reports.length);
  if (analysis?.spatial_analysis?.status === 'success') add('ALA spatial layer', 1);

  return Array.from(counts.entries())
    .map(([label, count]) => ({ label, count }))
    .sort((a, b) => b.count - a.count);
}

function mergeSpatialIntoAnalysis(
  current: BackendCompanyAnalysis | null,
  spatial: BackendSpatialAnalysis,
): BackendCompanyAnalysis | null {
  if (!current) return null;
  if (current.query_id && spatial.query_id && current.query_id !== spatial.query_id) return current;
  return { ...current, spatial_analysis: spatial };
}

function persistCompanyAnalysis(analysis: BackendCompanyAnalysis | null) {
  if (!analysis || typeof window === 'undefined') return;
  window.localStorage.setItem('company_analysis', JSON.stringify(analysis));
}

function MetricCard({
  icon: Icon,
  label,
  value,
  detail,
  tone = 'stone',
}: {
  icon: LucideIcon;
  label: string;
  value: string;
  detail: string;
  tone?: Tone;
}) {
  return (
    <Card className="p-5">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="text-[12px] text-stone-500">{label}</div>
          <div className="mt-1 text-[28px] leading-none text-stone-950 tabular-nums">{value}</div>
        </div>
        <div className={`h-10 w-10 rounded-lg flex items-center justify-center ${toneStyles[tone].icon}`}>
          <Icon size={19} />
        </div>
      </div>
      <div className="mt-3 text-[12px] leading-relaxed text-stone-600">{detail}</div>
    </Card>
  );
}

function SignalBar({
  label,
  value,
  detail,
  tone,
}: {
  label: string;
  value: number;
  detail: string;
  tone: Tone;
}) {
  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between gap-3">
        <div className="text-[13px] text-stone-900">{label}</div>
        <div className={`text-[12px] tabular-nums ${toneStyles[tone].text}`}>{Math.round(value)}/100</div>
      </div>
      <div className="h-2 rounded-full bg-stone-100 overflow-hidden">
        <div className={`h-full rounded-full ${toneStyles[tone].bar}`} style={{ width: `${clamp(value)}%` }} />
      </div>
      <div className="text-[11.5px] leading-relaxed text-stone-500">{detail}</div>
    </div>
  );
}

function EmptyState({ onSearch }: { onSearch: () => void }) {
  return (
    <div className="min-h-screen bg-[#f5f3ee] p-6 flex items-center justify-center">
      <Card className="max-w-lg p-8 text-center">
        <div className="mx-auto h-14 w-14 rounded-lg bg-stone-100 text-stone-500 flex items-center justify-center">
          <Search size={25} />
        </div>
        <div className="mt-4 text-[20px] text-stone-950">No company analysis selected</div>
        <p className="mt-2 text-[13px] leading-relaxed text-stone-600">
          Run an entity search or evidence analysis first. The investor overview will then combine ABR resolution,
          extracted evidence, and Layer A spatial biodiversity scoring.
        </p>
        <button
          onClick={onSearch}
          className="mt-5 inline-flex h-10 items-center justify-center gap-1.5 rounded-lg bg-stone-900 px-4 text-[13px] text-white hover:bg-stone-800"
        >
          <Search size={14} /> Start search
        </button>
      </Card>
    </div>
  );
}

export function CompanyOverview() {
  const navigate = useNavigate();
  const [analysis, setAnalysis] = useState<BackendCompanyAnalysis | null>(() => loadCompanyAnalysis());
  const [showWatchlist, setShowWatchlist] = useState(false);
  const [showExport, setShowExport] = useState(false);
  const [spatialBusy, setSpatialBusy] = useState(false);
  const [spatialError, setSpatialError] = useState<string | null>(null);

  const queryId = useMemo(() => {
    if (analysis?.query_id) return analysis.query_id;
    if (typeof window === 'undefined') return null;
    return window.localStorage.getItem('query_id');
  }, [analysis?.query_id]);

  useEffect(() => {
    if (!queryId) return;

    let cancelled = false;
    let timer: number | undefined;
    let attempts = 0;

    const loadSpatial = async () => {
      try {
        const data = await getSpatialAnalysisForQuery(queryId);
        if (cancelled) return;

        window.localStorage.setItem('latest_spatial_analysis', JSON.stringify(data));
        setAnalysis(current => {
          const merged = mergeSpatialIntoAnalysis(current, data);
          persistCompanyAnalysis(merged);
          return merged;
        });

        if (data.status === 'loading' && attempts < 2) {
          attempts += 1;
          timer = window.setTimeout(loadSpatial, 5000);
        }
      } catch (error) {
        if (!cancelled) {
          setSpatialError(error instanceof Error ? error.message : 'Spatial analysis is unavailable.');
        }
      }
    };

    void loadSpatial();
    return () => {
      cancelled = true;
      if (timer) window.clearTimeout(timer);
    };
  }, [queryId]);

  const refreshSpatial = async () => {
    if (!queryId) return;
    setSpatialBusy(true);
    setSpatialError(null);
    try {
      const data = await getSpatialAnalysisForQuery(queryId, true);
      window.localStorage.setItem('latest_spatial_analysis', JSON.stringify(data));
      setAnalysis(current => {
        const merged = mergeSpatialIntoAnalysis(current, data);
        persistCompanyAnalysis(merged);
        return merged;
      });
    } catch (error) {
      setSpatialError(error instanceof Error ? error.message : 'Spatial analysis is unavailable.');
    } finally {
      setSpatialBusy(false);
    }
  };

  const evidenceRecords = useMemo(() => allEvidenceRecords(analysis), [analysis]);
  const evidenceCards = useMemo(() => analysisEvidenceCards(analysis), [analysis]);
  const profile = useMemo(() => companyProfileFromAnalysis(analysis), [analysis]);
  const companyName = companyDisplayName(analysis);
  const spatial = analysis?.spatial_analysis;
  const layerScore = spatialScore(spatial);
  const score = profile.score;
  const riskLevel = profile.riskLevel;
  const threatCount = spatial?.threatened_species_count ?? 0;
  const assessedSpecies = spatial?.iucn_assessed_species ?? 0;
  const uniqueSpecies = spatial?.unique_species_count ?? 0;
  const alaRecords = spatial?.total_ala_records ?? 0;
  const sourceSummary = sourceMix(analysis, evidenceRecords);
  const avgConfidence = evidenceRecords.length
    ? Math.round(evidenceRecords.reduce((sum, record) => sum + confidencePercent(record), 0) / evidenceRecords.length)
    : profile.confidence;
  const newsCandidates = analysis?.news?.candidates?.length || analysis?.news?.candidate_count || 0;
  const reportEvidence = analysis?.reports?.evidence_count || analysis?.reports?.evidence?.length || 0;
  const riskEvidence = evidenceRecords.filter(record => (record.evidence_type || '').toLowerCase().includes('risk')).length;
  const actionEvidence = evidenceRecords.filter(record => {
    const type = (record.evidence_type || '').toLowerCase();
    const signal = (record.biodiversity_signal || '').toLowerCase();
    return /action|mitigation|restoration|rehabilitation|offset/.test(`${type} ${signal}`);
  }).length;
  const entityResolved = Boolean(analysis?.resolution?.abr?.success || analysis?.resolution?.abn);

  const drivers = [
    {
      label: 'Spatial biodiversity exposure',
      value: layerScore ?? (spatial?.status === 'loading' ? 25 : 0),
      detail: spatial?.status === 'success'
        ? `${threatCount} threatened species across ${assessedSpecies || uniqueSpecies} assessed species at the inferred site.`
        : spatial?.status === 'loading'
          ? 'Layer A is still resolving ALA and IUCN data for this entity.'
          : 'No completed Layer A result is attached to this company yet.',
    },
    {
      label: 'Extracted evidence pressure',
      value: clamp(riskEvidence * 24 + evidenceRecords.length * 8 - actionEvidence * 8),
      detail: `${riskEvidence} risk record${riskEvidence === 1 ? '' : 's'} and ${actionEvidence} mitigation record${actionEvidence === 1 ? '' : 's'} found in news or uploaded reports.`,
    },
    {
      label: 'Market and regulatory attention',
      value: clamp(newsCandidates * 12 + evidenceRecords.filter(record => record.source_type === 'news').length * 10),
      detail: `${newsCandidates} candidate article${newsCandidates === 1 ? '' : 's'} were screened for biodiversity relevance.`,
    },
    {
      label: 'Disclosure coverage gap',
      value: clamp((analysis?.analysed_reports?.length ? 45 : 70) - reportEvidence * 6 + (evidenceRecords.length ? 10 : 0)),
      detail: analysis?.analysed_reports?.length
        ? `${analysis.analysed_reports.length} uploaded report${analysis.analysed_reports.length === 1 ? '' : 's'} checked with ${reportEvidence} extracted signal${reportEvidence === 1 ? '' : 's'}.`
        : 'No uploaded company report is attached, so disclosure confidence is limited.',
    },
  ];

  const investorSummary = [
    entityResolved
      ? `${companyName} is resolved to ${analysis?.resolution?.abn ? `ABN ${analysis.resolution.abn}` : 'an ABR entity'}, giving investors a clean legal-entity anchor for evidence attribution.`
      : `${companyName} has not been fully resolved to an ABR entity, so entity attribution should be reviewed before investment use.`,
    spatial?.status === 'success'
      ? `Layer A spatial analysis returned ${formatNumber(alaRecords)} ALA occurrence records, ${formatNumber(uniqueSpecies)} unique species, and a ${layerScore}/100 species threat score.`
      : spatial?.status === 'loading'
        ? 'Spatial analysis has started and will enrich the overview when the ALA and IUCN result is ready.'
        : 'Spatial exposure is not yet available, which leaves a material gap in nature-risk assessment.',
    evidenceRecords.length
      ? `${evidenceRecords.length} extracted evidence record${evidenceRecords.length === 1 ? '' : 's'} support the current view, with average extraction confidence of ${avgConfidence}%.`
      : 'No extracted evidence records are available yet; investors should request filings, site disclosures, and recent controversy checks.',
  ];

  const dueDiligenceQuestions = [
    threatCount > 0
      ? `Which operating assets or suppliers overlap the ${threatCount} threatened species signal?`
      : 'Can management provide site-level biodiversity exposure and species-screening evidence?',
    reportEvidence > 0
      ? 'Do the extracted report claims align with external news and spatial signals?'
      : 'Can the company provide its latest sustainability, TNFD, or rehabilitation reporting?',
    newsCandidates > 0
      ? 'Which candidate news items require analyst confirmation before committee use?'
      : 'Should a broader regulatory and adverse-media search be run before investment memo sign-off?',
  ];

  const tnfdStages = [
    {
      phase: 'Locate',
      icon: Compass,
      tone: spatial?.status === 'success' ? 'emerald' : spatial?.status === 'loading' ? 'blue' : 'amber',
      status: spatial?.status === 'success' ? 'Mapped' : spatial?.status === 'loading' ? 'Running' : 'Gap',
      metric: spatial?.inferred_location?.label || spatial?.location?.label || 'Site pending',
      detail: spatial?.status === 'success'
        ? `${spatial.location?.radius_km || spatial.inferred_location?.radius_km || 10} km radius used for Layer A.`
        : 'Needs a resolved operating location or inferred entity site.',
    },
    {
      phase: 'Evaluate',
      icon: ScanSearch,
      tone: evidenceRecords.length ? 'emerald' : 'amber',
      status: evidenceRecords.length ? 'Evidence found' : 'Sparse',
      metric: `${evidenceRecords.length} evidence records`,
      detail: 'News and uploaded reports are converted into traceable biodiversity signals.',
    },
    {
      phase: 'Assess',
      icon: AlertTriangle,
      tone: score >= 70 ? 'rose' : score >= 45 ? 'amber' : 'emerald',
      status: `${riskLevel} risk`,
      metric: `${score}/100 score`,
      detail: 'Risk reflects spatial threat first, then evidence pressure and disclosure coverage.',
    },
    {
      phase: 'Prepare',
      icon: FileBarChart2,
      tone: analysis?.analysed_reports?.length ? 'blue' : 'amber',
      status: analysis?.analysed_reports?.length ? 'Report-backed' : 'Needs disclosure',
      metric: `${analysis?.analysed_reports?.length || 0} reports checked`,
      detail: 'Export the current evidence pack for investor committee review.',
    },
  ] as const;

  if (!analysis) {
    return <EmptyState onSearch={() => navigate('/app/search')} />;
  }

  return (
    <div className="min-h-screen bg-[#f5f3ee]">
      <div className="max-w-[1380px] mx-auto px-6 py-6 space-y-6">
        <section className="rounded-2xl border border-stone-200 bg-white p-6 shadow-sm">
          <div className="flex flex-col gap-5 lg:flex-row lg:items-start lg:justify-between">
            <div className="flex gap-4">
              <div className="h-14 w-14 rounded-lg bg-stone-950 text-white flex items-center justify-center shrink-0">
                <Building2 size={26} />
              </div>
              <div>
                <div className="flex flex-wrap items-center gap-2">
                  <div className="text-[28px] leading-tight text-stone-950">{companyName}</div>
                  <RiskBadge level={riskLevel} />
                  <Chip tone={entityResolved ? 'emerald' : 'amber'}>
                    <CheckCircle2 size={11} /> {entityResolved ? 'Entity resolved' : 'Needs entity review'}
                  </Chip>
                  <Chip tone={spatial?.status === 'success' ? 'blue' : 'stone'}>
                    <MapPin size={11} /> Spatial {spatial?.status || 'pending'}
                  </Chip>
                </div>
                <div className="mt-2 flex flex-wrap items-center gap-3 text-[13px] text-stone-600">
                  <span>ABN {profile.abn}</span>
                  <span>{profile.sector}</span>
                  <span>{profile.state}{profile.postcode ? ` ${profile.postcode}` : ''}</span>
                  <span>{analysis.search_queries?.length || 0} generated search queries</span>
                </div>
              </div>
            </div>

            <div className="flex flex-wrap gap-2">
              <button
                onClick={() => navigate('/app/analyse')}
                className="inline-flex h-9 items-center justify-center gap-1.5 rounded-lg border border-stone-200 bg-white px-3 text-[13px] text-stone-800 hover:bg-stone-50"
              >
                <FileCheck2 size={14} /> Evidence
              </button>
              <button
                onClick={() => navigate('/app/spatial')}
                className="inline-flex h-9 items-center justify-center gap-1.5 rounded-lg border border-stone-200 bg-white px-3 text-[13px] text-stone-800 hover:bg-stone-50"
              >
                <MapIcon size={14} /> Spatial
              </button>
              <button
                onClick={() => void refreshSpatial()}
                disabled={!queryId || spatialBusy}
                className="inline-flex h-9 items-center justify-center gap-1.5 rounded-lg border border-emerald-200 bg-emerald-50 px-3 text-[13px] text-emerald-800 hover:bg-emerald-100 disabled:cursor-not-allowed disabled:opacity-60"
              >
                <RefreshCw size={14} className={spatialBusy ? 'animate-spin' : ''} /> Refresh
              </button>
              <button
                onClick={() => setShowExport(true)}
                className="inline-flex h-9 items-center justify-center gap-1.5 rounded-lg bg-stone-950 px-3 text-[13px] text-white hover:bg-stone-800"
              >
                <Download size={14} /> Export
              </button>
            </div>
          </div>
          {spatialError && (
            <div className="mt-4 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-[12px] text-amber-800">
              Spatial refresh failed: {spatialError}
            </div>
          )}
        </section>

        <section className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
          <MetricCard
            icon={BarChart3}
            label="Biodiversity risk score"
            value={`${score}/100`}
            detail={layerScore !== null ? 'Driven by Layer A spatial species threat scoring.' : 'Estimated from evidence pressure until spatial scoring completes.'}
            tone={score >= 70 ? 'rose' : score >= 45 ? 'amber' : 'emerald'}
          />
          <MetricCard
            icon={Building2}
            label="Entity confidence"
            value={`${profile.confidence}%`}
            detail={entityResolved ? 'ABR identity gives evidence a legal entity anchor.' : 'Entity resolution needs analyst review before reliance.'}
            tone={entityResolved ? 'emerald' : 'amber'}
          />
          <MetricCard
            icon={Leaf}
            label="Threatened species"
            value={spatial?.status === 'success' ? String(threatCount) : 'Pending'}
            detail={spatial?.status === 'success' ? `${assessedSpecies || uniqueSpecies} IUCN-assessed species in the spatial screen.` : 'Awaiting Layer A spatial enrichment.'}
            tone={threatCount >= 10 ? 'rose' : threatCount >= 3 ? 'amber' : 'blue'}
          />
          <MetricCard
            icon={Database}
            label="Evidence base"
            value={`${evidenceRecords.length}`}
            detail={`${newsCandidates} news candidates, ${reportEvidence} report-derived signals, ${sourceSummary.length} source groups.`}
            tone={evidenceRecords.length ? 'blue' : 'amber'}
          />
        </section>

        <section className="grid grid-cols-1 gap-6 xl:grid-cols-[1.35fr_0.65fr]">
          <Card className="p-6">
            <SectionTitle title="Investor read" action={<Chip tone="stone">Entity + evidence + spatial</Chip>} />
            <div className="grid gap-4 lg:grid-cols-[0.7fr_1fr]">
              <div className="flex flex-col items-center justify-center rounded-xl border border-stone-200 bg-stone-50 p-5">
                <div className="text-[12px] text-stone-500">Current nature-risk view</div>
                <div className="mt-2 text-[72px] leading-none text-stone-950 tabular-nums">{score}</div>
                <div className="mt-2"><RiskBadge level={riskLevel} /></div>
                <div className="mt-4 h-2 w-full overflow-hidden rounded-full bg-stone-200">
                  <div
                    className={`h-full ${score >= 70 ? 'bg-rose-500' : score >= 45 ? 'bg-amber-500' : 'bg-emerald-500'}`}
                    style={{ width: `${score}%` }}
                  />
                </div>
                <div className="mt-3 text-center text-[11.5px] leading-relaxed text-stone-500">
                  Score uses spatial risk where available and evidence pressure when spatial data is still pending.
                </div>
              </div>
              <div className="space-y-3">
                {investorSummary.map((item, index) => (
                  <div key={item} className="flex gap-3 rounded-lg border border-stone-200 bg-white p-3">
                    <div className={`mt-0.5 h-6 w-6 rounded-lg flex items-center justify-center ${index === 0 ? toneStyles.emerald.icon : index === 1 ? toneStyles.blue.icon : toneStyles.amber.icon}`}>
                      {index === 0 ? <Building2 size={13} /> : index === 1 ? <MapPin size={13} /> : <FileText size={13} />}
                    </div>
                    <div className="text-[13px] leading-relaxed text-stone-700">{item}</div>
                  </div>
                ))}
              </div>
            </div>
          </Card>

          <Card className="p-6">
            <SectionTitle title="Investor questions" action={<Sparkles size={16} className="text-amber-600" />} />
            <div className="space-y-3">
              {dueDiligenceQuestions.map((question, index) => (
                <div key={question} className="flex gap-3">
                  <div className="h-6 w-6 shrink-0 rounded-lg bg-stone-100 text-stone-700 flex items-center justify-center text-[12px]">
                    {index + 1}
                  </div>
                  <div className="text-[13px] leading-relaxed text-stone-700">{question}</div>
                </div>
              ))}
            </div>
          </Card>
        </section>

        <section className="grid grid-cols-1 gap-6 xl:grid-cols-[0.9fr_1.1fr]">
          <Card className="p-6">
            <SectionTitle title="Risk drivers" action={<Chip tone="amber">{drivers.length} signals</Chip>} />
            <div className="space-y-5">
              {drivers.map(driver => {
                const tone = riskDriverTone(driver.value);
                return (
                  <SignalBar
                    key={driver.label}
                    label={driver.label}
                    value={driver.value}
                    detail={driver.detail}
                    tone={tone}
                  />
                );
              })}
            </div>
          </Card>

          <Card className="p-6">
            <SectionTitle
              title="Spatial exposure"
              action={
                <Chip tone={spatial?.status === 'success' ? 'emerald' : spatial?.status === 'loading' ? 'blue' : 'amber'}>
                  {spatial?.status || 'pending'}
                </Chip>
              }
            />
            <div className="grid gap-4 lg:grid-cols-[0.85fr_1.15fr]">
              <div className="rounded-xl border border-stone-200 bg-[#edf7f1] p-4">
                <div className="flex items-center gap-2 text-[13px] text-stone-900">
                  <MapPin size={15} className="text-emerald-700" />
                  {spatial?.inferred_location?.label || spatial?.location?.label || `${profile.state} inferred context`}
                </div>
                <div className="mt-3 grid grid-cols-2 gap-3">
                  <div>
                    <div className="text-[11px] text-stone-500">ALA records</div>
                    <div className="text-[22px] text-stone-950 tabular-nums">{formatNumber(alaRecords)}</div>
                  </div>
                  <div>
                    <div className="text-[11px] text-stone-500">Unique species</div>
                    <div className="text-[22px] text-stone-950 tabular-nums">{formatNumber(uniqueSpecies)}</div>
                  </div>
                  <div>
                    <div className="text-[11px] text-stone-500">Threat score</div>
                    <div className="text-[22px] text-stone-950 tabular-nums">{layerScore !== null ? `${layerScore}/100` : 'N/A'}</div>
                  </div>
                  <div>
                    <div className="text-[11px] text-stone-500">Radius</div>
                    <div className="text-[22px] text-stone-950 tabular-nums">
                      {spatial?.location?.radius_km || spatial?.inferred_location?.radius_km || 10} km
                    </div>
                  </div>
                </div>
                <div className="mt-3 text-[11.5px] leading-relaxed text-stone-600">
                  Source: {spatial?.inferred_location?.source || spatial?.location?.source || 'ABR inferred location and ALA Biocache'}
                </div>
              </div>

              <div>
                <div className="text-[12px] text-stone-500">Threat mix</div>
                <div className="mt-3 space-y-2">
                  {Object.entries(spatial?.score_breakdown || {}).length ? (
                    Object.entries(spatial?.score_breakdown || {}).map(([label, value]) => (
                      <SignalBar
                        key={label}
                        label={sourceLabel(label)}
                        value={clamp(Number(value))}
                        detail="Weighted contribution from IUCN threat category counts."
                        tone={riskDriverTone(Number(value))}
                      />
                    ))
                  ) : (
                    <div className="rounded-lg border border-dashed border-stone-300 p-4 text-[13px] leading-relaxed text-stone-600">
                      Score breakdown is not available yet. Refresh spatial analysis after the Layer A job completes.
                    </div>
                  )}
                </div>
              </div>
            </div>
          </Card>
        </section>

        <section className="grid grid-cols-1 gap-6 xl:grid-cols-[1.15fr_0.85fr]">
          <Card className="p-6">
            <SectionTitle title="Evidence dossier" action={<Chip tone="blue">{evidenceCards.length} records</Chip>} />
            {evidenceCards.length ? (
              <div className="space-y-3">
                {evidenceRecords.slice(0, 5).map((record, index) => {
                  const conf = confidencePercent(record);
                  const tone = conf >= 80 ? 'emerald' : conf >= 60 ? 'blue' : 'amber';
                  return (
                    <div key={`${evidenceTitle(record)}-${index}`} className="rounded-lg border border-stone-200 bg-white p-4">
                      <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
                        <div>
                          <div className="flex flex-wrap items-center gap-2">
                            <Chip tone={record.source_type === 'news' ? 'sky' : 'purple'}>{sourceLabel(record.source_type)}</Chip>
                            <Chip tone={tone}>{conf}% confidence</Chip>
                            {record.source_date && <span className="text-[11.5px] text-stone-500">{formatDate(record.source_date)}</span>}
                          </div>
                          <div className="mt-2 text-[14px] text-stone-950">{evidenceTitle(record)}</div>
                          <div className="mt-1 flex flex-wrap gap-3 text-[12px] text-stone-600">
                            <span className="inline-flex items-center gap-1"><MapPin size={12} /> {evidenceLocation(record)}</span>
                            <span className="inline-flex items-center gap-1"><Activity size={12} /> {record.activity_type || 'Activity not classified'}</span>
                            <span className="inline-flex items-center gap-1"><FileText size={12} /> {record.source || 'Source not stated'}</span>
                          </div>
                        </div>
                        {record.source_url && (
                          <a
                            href={record.source_url}
                            target="_blank"
                            rel="noreferrer"
                            className="inline-flex h-8 shrink-0 items-center justify-center gap-1 rounded-lg border border-stone-200 px-2.5 text-[12px] text-stone-700 hover:bg-stone-50"
                          >
                            <ExternalLink size={12} /> Source
                          </a>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            ) : (
              <div className="rounded-lg border border-dashed border-stone-300 p-5 text-[13px] leading-relaxed text-stone-600">
                No extracted evidence records are attached yet. Upload reports or run the evidence analysis flow to populate investor-grade claims.
              </div>
            )}
          </Card>

          <Card className="p-6">
            <SectionTitle title="Source coverage" action={<Chip tone="stone">{sourceSummary.length} groups</Chip>} />
            <div className="space-y-3">
              {sourceSummary.length ? sourceSummary.map((source, index) => {
                const tones: Tone[] = ['emerald', 'blue', 'amber', 'rose', 'purple', 'sky'];
                const tone = tones[index % tones.length];
                const total = sourceSummary.reduce((sum, item) => sum + item.count, 0);
                return (
                  <div key={source.label}>
                    <div className="flex items-center justify-between text-[12.5px]">
                      <span className="text-stone-700">{source.label}</span>
                      <span className="text-stone-500 tabular-nums">{source.count}</span>
                    </div>
                    <div className="mt-1.5 h-2 rounded-full bg-stone-100 overflow-hidden">
                      <div className={`h-full ${toneStyles[tone].bar}`} style={{ width: `${(source.count / Math.max(1, total)) * 100}%` }} />
                    </div>
                  </div>
                );
              }) : (
                <div className="rounded-lg border border-dashed border-stone-300 p-4 text-[13px] text-stone-600">
                  Source mix will appear when evidence, reports, or spatial data are attached.
                </div>
              )}
            </div>
            <div className="mt-5 rounded-lg border border-stone-200 bg-stone-50 p-4">
              <div className="flex items-center gap-2 text-[13px] text-stone-950">
                <ShieldCheck size={15} className="text-emerald-700" /> Evidence reliability
              </div>
              <div className="mt-2 text-[12px] leading-relaxed text-stone-600">
                Average extraction confidence is {avgConfidence}%. Use the source links and report export before treating these signals as final investment committee evidence.
              </div>
            </div>
          </Card>
        </section>

        <section className="grid grid-cols-1 gap-6 xl:grid-cols-[0.75fr_1.25fr]">
          <Card className="p-6">
            <SectionTitle title="Entity analysis" action={<Chip tone={entityResolved ? 'emerald' : 'amber'}>{analysis.resolution?.abn_status || 'ABR'}</Chip>} />
            <div className="space-y-3 text-[13px]">
              {[
                ['Legal name', analysis.resolution?.legal_name || companyName],
                ['Normalised name', analysis.resolution?.normalized_name || companyName],
                ['ABN', analysis.resolution?.abn || 'Not available'],
                ['ABN status', analysis.resolution?.abn_status || analysis.resolution?.abr?.abn_status || 'Not available'],
                ['Input type', sourceLabel(analysis.resolution?.input_type)],
                ['Database query', queryId || 'Not persisted'],
              ].map(([label, value]) => (
                <div key={label} className="flex items-start justify-between gap-4 border-b border-stone-100 pb-2 last:border-0">
                  <span className="text-stone-500">{label}</span>
                  <span className="text-right text-stone-950">{value}</span>
                </div>
              ))}
            </div>
          </Card>

          <Card className="p-6">
            <SectionTitle title="TNFD investor snapshot" action={<Chip tone="emerald">LEAP</Chip>} />
            <div className="grid gap-3 md:grid-cols-2">
              {tnfdStages.map(stage => {
                const Icon = stage.icon;
                return (
                  <div key={stage.phase} className={`rounded-lg border p-4 ${toneStyles[stage.tone].soft}`}>
                    <div className="flex items-center justify-between gap-3">
                      <div className="flex items-center gap-2">
                        <div className={`h-8 w-8 rounded-lg flex items-center justify-center ${toneStyles[stage.tone].icon}`}>
                          <Icon size={15} />
                        </div>
                        <div>
                          <div className="text-[13px] text-stone-950">{stage.phase}</div>
                          <div className={`text-[11px] ${toneStyles[stage.tone].text}`}>{stage.status}</div>
                        </div>
                      </div>
                    </div>
                    <div className="mt-3 text-[16px] text-stone-950">{stage.metric}</div>
                    <div className="mt-1 text-[11.5px] leading-relaxed text-stone-600">{stage.detail}</div>
                  </div>
                );
              })}
            </div>
          </Card>
        </section>

        <section className="grid grid-cols-1 gap-6 xl:grid-cols-[1fr_0.8fr]">
          <Card className="p-6">
            <SectionTitle title="Threatened species watchlist" action={<Chip tone="rose">{spatial?.threatened_species?.length || 0} species</Chip>} />
            {spatial?.threatened_species?.length ? (
              <div className="overflow-x-auto">
                <table className="w-full min-w-[680px] text-left text-[12.5px]">
                  <thead className="border-b border-stone-200 text-stone-500">
                    <tr>
                      <th className="py-2 pr-3 font-normal">Species</th>
                      <th className="py-2 pr-3 font-normal">IUCN</th>
                      <th className="py-2 pr-3 font-normal">Records</th>
                      <th className="py-2 pr-3 font-normal">Investor relevance</th>
                    </tr>
                  </thead>
                  <tbody>
                    {spatial.threatened_species.slice(0, 6).map(species => {
                      const tone = categoryTone(species.iucn_category);
                      return (
                        <tr key={species.scientific_name} className="border-b border-stone-100 last:border-0">
                          <td className="py-3 pr-3">
                            <div className="text-stone-950">{species.common_name || species.scientific_name}</div>
                            <div className="text-[11px] italic text-stone-500">{species.scientific_name}</div>
                          </td>
                          <td className="py-3 pr-3"><Chip tone={tone}>{species.iucn_category || 'N/A'}</Chip></td>
                          <td className="py-3 pr-3 tabular-nums text-stone-700">{formatNumber(species.record_count)}</td>
                          <td className="py-3 pr-3 text-stone-600">
                            Site-level exposure should be tested against habitat sensitivity, offset obligations, and permit conditions.
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="rounded-lg border border-dashed border-stone-300 p-5 text-[13px] leading-relaxed text-stone-600">
                No threatened species list is attached yet. This area will populate from Layer A once IUCN enrichment succeeds.
              </div>
            )}
          </Card>

          <Card className="p-6">
            <SectionTitle title="Analyst actions" action={<Bell size={16} className="text-amber-600" />} />
            <div className="space-y-3">
              {[
                { icon: Star, label: 'Add to watchlist', detail: 'Track score, evidence, and spatial changes.', action: () => setShowWatchlist(true), tone: 'emerald' as Tone },
                { icon: Download, label: 'Export investor report', detail: 'Generate a PDF-ready evidence dossier.', action: () => setShowExport(true), tone: 'stone' as Tone },
                { icon: Newspaper, label: 'Review evidence', detail: 'Open the evidence analysis workspace.', action: () => navigate('/app/analyse'), tone: 'blue' as Tone },
                { icon: Globe2, label: 'Inspect spatial layer', detail: 'Validate inferred site context and species mix.', action: () => navigate('/app/spatial'), tone: 'amber' as Tone },
              ].map(item => {
                const Icon = item.icon;
                return (
                  <button
                    key={item.label}
                    onClick={item.action}
                    className="w-full rounded-lg border border-stone-200 bg-white p-3 text-left hover:bg-stone-50"
                  >
                    <div className="flex items-center gap-3">
                      <div className={`h-9 w-9 rounded-lg flex items-center justify-center ${toneStyles[item.tone].icon}`}>
                        <Icon size={16} />
                      </div>
                      <div className="flex-1">
                        <div className="text-[13px] text-stone-950">{item.label}</div>
                        <div className="text-[11.5px] text-stone-500">{item.detail}</div>
                      </div>
                      <ArrowRight size={14} className="text-stone-400" />
                    </div>
                  </button>
                );
              })}
            </div>
          </Card>
        </section>
      </div>

      {showWatchlist && <WatchlistModal companyName={companyName} onClose={() => setShowWatchlist(false)} />}
      {showExport && <ExportModal companyName={companyName} queryId={queryId} analysis={analysis} onClose={() => setShowExport(false)} />}
    </div>
  );
}

function WatchlistModal({ companyName, onClose }: { companyName: string; onClose: () => void }) {
  const [freq, setFreq] = useState('weekly');
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-stone-900/40 backdrop-blur-sm" onClick={onClose} />
      <div className="relative w-full max-w-md overflow-hidden rounded-2xl bg-white shadow-2xl">
        <div className="flex items-center justify-between border-b border-stone-100 p-5">
          <div className="flex items-center gap-2 text-[14px] text-stone-950">
            <Star size={16} className="text-emerald-600" /> Add to watchlist
          </div>
          <button
            onClick={onClose}
            className="flex h-7 w-7 items-center justify-center rounded-full text-stone-400 hover:bg-stone-100"
            aria-label="Close watchlist modal"
          >
            <X size={14} />
          </button>
        </div>
        <div className="space-y-4 p-5">
          <p className="text-[13px] leading-relaxed text-stone-600">
            Track <b className="text-stone-950">{companyName}</b> when biodiversity risk, evidence coverage, or spatial exposure changes.
          </p>
          <div>
            <div className="mb-2 text-[11px] uppercase text-stone-500">Alert frequency</div>
            <div className="grid grid-cols-3 gap-2">
              {['daily', 'weekly', 'on change'].map(option => (
                <button
                  key={option}
                  onClick={() => setFreq(option)}
                  className={`h-9 rounded-lg border text-[12.5px] capitalize ${
                    freq === option
                      ? 'border-emerald-500 bg-emerald-50 text-emerald-800'
                      : 'border-stone-200 text-stone-700 hover:bg-stone-50'
                  }`}
                >
                  {option}
                </button>
              ))}
            </div>
          </div>
          <div>
            <div className="mb-2 text-[11px] uppercase text-stone-500">Email</div>
            <input
              type="email"
              placeholder="analyst@firm.com"
              className="h-9 w-full rounded-lg border border-stone-200 px-3 text-[13px] focus:border-emerald-500 focus:outline-none focus:ring-1 focus:ring-emerald-500"
            />
          </div>
          <button onClick={onClose} className="h-10 w-full rounded-lg bg-emerald-700 text-[13px] text-white hover:bg-emerald-800">
            Add to watchlist
          </button>
        </div>
      </div>
    </div>
  );
}

function ExportModal({
  companyName,
  queryId,
  analysis,
  onClose,
}: {
  companyName: string;
  queryId: string | null;
  analysis: BackendCompanyAnalysis | null;
  onClose: () => void;
}) {
  const [email, setEmail] = useState('');
  const [emailStatus, setEmailStatus] = useState<'idle' | 'generating' | 'sending' | 'sent' | 'error'>('idle');
  const [reportId, setReportId] = useState<string | null>(() => {
    if (typeof window === 'undefined' || !queryId) return null;
    return window.localStorage.getItem(`report_id:${queryId}`);
  });
  const [message, setMessage] = useState<string | null>(null);

  const ensureReport = async () => {
    if (!queryId) {
      setEmailStatus('error');
      setMessage('Run a company search first so Seeco has a query_id to report on.');
      return null;
    }
    if (reportId) return reportId;

    setEmailStatus('generating');
    setMessage('Generating investor report...');
    const generated = await generateReport(queryId, analysis || undefined);
    const nextReportId = generated.report_id;
    setReportId(nextReportId);
    window.localStorage.setItem(`report_id:${queryId}`, nextReportId);
    setEmailStatus('idle');
    setMessage('Report generated and saved.');
    return nextReportId;
  };

  const openReport = async () => {
    try {
      const nextReportId = await ensureReport();
      if (!nextReportId) return;
      window.open(reportHtmlUrl(nextReportId), '_blank', 'noopener,noreferrer');
    } catch (error) {
      setEmailStatus('error');
      setMessage(error instanceof Error ? error.message : 'Could not generate report.');
    }
  };

  const saveAsPdf = async () => {
    try {
      const nextReportId = await ensureReport();
      if (!nextReportId) return;
      window.open(reportHtmlUrl(nextReportId, true), '_blank', 'noopener,noreferrer');
      setMessage('Choose Save as PDF in the print dialog.');
    } catch (error) {
      setEmailStatus('error');
      setMessage(error instanceof Error ? error.message : 'Could not prepare PDF export.');
    }
  };

  const emailReport = async () => {
    if (!email.trim()) {
      setEmailStatus('error');
      setMessage('Enter an analyst email address.');
      return;
    }
    try {
      const nextReportId = await ensureReport();
      if (!nextReportId) return;
      setEmailStatus('sending');
      setMessage(null);
      const result = await sendPersistedReportEmail(nextReportId, email.trim());
      setEmailStatus('sent');
      setMessage(result.delivery === 'outbox' ? 'Report saved to backend outbox for local delivery.' : `Report emailed to ${result.to}.`);
    } catch (error) {
      setEmailStatus('error');
      setMessage(error instanceof Error ? error.message : 'Could not send report email.');
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-stone-900/40 backdrop-blur-sm" onClick={onClose} />
      <div className="relative w-full max-w-md overflow-hidden rounded-2xl bg-white shadow-2xl">
        <div className="flex items-center justify-between border-b border-stone-100 p-5">
          <div className="flex items-center gap-2 text-[14px] text-stone-950">
            <Download size={16} className="text-emerald-600" /> Export investor dossier
          </div>
          <button
            onClick={onClose}
            className="flex h-7 w-7 items-center justify-center rounded-full text-stone-400 hover:bg-stone-100"
            aria-label="Close export modal"
          >
            <X size={14} />
          </button>
        </div>
        <div className="space-y-4 p-5">
          <p className="text-[13px] leading-relaxed text-stone-600">
            Generate a report for <b className="text-stone-950">{companyName}</b> using the current entity, evidence, and spatial analysis payload.
          </p>
          <div className="flex flex-wrap gap-1.5">
            <Chip tone="emerald"><Building2 size={11} /> Entity</Chip>
            <Chip tone="blue"><FileText size={11} /> Evidence</Chip>
            <Chip tone="amber"><MapPin size={11} /> Spatial</Chip>
            <Chip tone="stone"><ClipboardCheck size={11} /> TNFD snapshot</Chip>
          </div>
          <div>
            <div className="mb-2 text-[11px] uppercase text-stone-500">Email report</div>
            <div className="flex gap-2">
              <input
                type="email"
                value={email}
                onChange={event => setEmail(event.target.value)}
                placeholder="analyst@firm.com"
                className="h-10 flex-1 rounded-lg border border-stone-200 px-3 text-[13px] focus:border-emerald-500 focus:outline-none focus:ring-1 focus:ring-emerald-500"
              />
              <button
                onClick={emailReport}
                disabled={emailStatus === 'sending'}
                className="inline-flex h-10 items-center justify-center rounded-lg bg-emerald-700 px-3 text-[13px] text-white hover:bg-emerald-800 disabled:bg-stone-300"
              >
                {emailStatus === 'sending' ? <RefreshCw size={14} className="animate-spin" /> : 'Send'}
              </button>
            </div>
            {message && (
              <div className={`mt-2 text-[12px] ${emailStatus === 'error' ? 'text-rose-700' : 'text-emerald-700'}`}>
                {message}
              </div>
            )}
          </div>
          <div className="flex gap-2">
            <button onClick={onClose} className="h-10 flex-1 rounded-lg border border-stone-200 text-[13px] text-stone-700 hover:bg-stone-50">
              Cancel
            </button>
            <button onClick={openReport} disabled={emailStatus === 'generating'} className="inline-flex h-10 flex-1 items-center justify-center gap-1.5 rounded-lg border border-stone-200 text-[13px] text-stone-700 hover:bg-stone-50 disabled:bg-stone-100">
              <FileText size={13} /> Open
            </button>
            <button onClick={saveAsPdf} disabled={emailStatus === 'generating'} className="inline-flex h-10 flex-1 items-center justify-center gap-1.5 rounded-lg bg-stone-950 text-[13px] text-white hover:bg-stone-800 disabled:bg-stone-400">
              <Download size={13} /> PDF
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

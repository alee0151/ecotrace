import { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router';
import {
  ArrowRight,
  Barcode,
  Building2,
  CheckCircle2,
  CircleDot,
  FileText,
  Flame,
  Leaf,
  Loader2,
  MapPin,
  Search,
  ShieldCheck,
  Sparkles,
  TrendingUp,
} from 'lucide-react';
import { Card, Chip, Confidence, RiskBadge } from '../components/shared';
import { ImageWithFallback } from '../components/figma/ImageWithFallback';
import {
  allEvidenceRecords,
  companyProfileFromAnalysis,
  evidenceAnalysisComplete,
  riskLevelFromScore,
  type BackendCompanyAnalysis,
  type BackendNewsCandidate,
} from '../lib/analysis';
import {
  analyseCompanyWithReports,
  getSpatialAnalysisForQuery,
  resolveCompanyForAnalysis,
  search as searchEntity,
  type SearchResult,
  type SpatialLayerAResponse,
} from '../../lib/api';

const HERO_IMG = 'https://images.unsplash.com/photo-1758702160898-6f96d1db5b73?crop=entropy&cs=tinysrgb&fit=max&fm=jpg&q=80&w=1600';

const suggestions = [
  { label: 'Woolworths', abn: '88 000 014 675', sector: 'Retail', score: 36 },
  { label: 'BHP Group', abn: '49 004 028 077', sector: 'Mining', score: 68 },
  { label: 'Coles Group', abn: '11 004 089 936', sector: 'Retail', score: 41 },
  { label: 'Bega Cheese', abn: '81 008 358 503', sector: 'Food & Beverage', score: 54 },
];

const betterChoices = [
  { brand: 'Five:am Organics', score: 82, level: 'Low' as const, note: 'Certified regenerative dairy, low land-use footprint.' },
  { brand: 'Barambah Organics', score: 78, level: 'Low' as const, note: 'Supplier traceability to farm-gate; minimal protected area overlap.' },
  { brand: 'Pure Harvest', score: 71, level: 'Medium' as const, note: 'Plant-based alternative with 38% lower biodiversity pressure.' },
];

const companyProgressSteps = [
  'Resolving ABN and legal entity',
  'Generating targeted search queries',
  'Searching news evidence',
  'Scanning uploaded reports',
  'Extracting biodiversity evidence',
  'Running spatial species analysis',
];

const TopoSvg = ({ className = '' }: { className?: string }) => (
  <svg className={className} viewBox="0 0 800 400" preserveAspectRatio="none" fill="none">
    {[0, 1, 2, 3, 4, 5, 6].map(i => (
      <path key={i} d={`M0 ${60 + i * 45} Q 200 ${20 + i * 50}, 400 ${80 + i * 40} T 800 ${50 + i * 45}`} stroke="currentColor" strokeWidth="1" opacity={0.18 - i * 0.015} />
    ))}
  </svg>
);

type SearchMode = 'barcode' | 'brand' | 'company';

type CompanyResolutionPreview = {
  legal_name?: string;
  normalized_name?: string;
  abn?: string;
  state?: string;
  postcode?: string;
  abr?: { success?: boolean; message?: string };
};

type ResolvedEntity = {
  brand: string;
  product: string;
  parent: string;
  abn: string;
  score: number;
  source?: string;
  imageUrl?: string;
};

type PersistedConsumerSearch = {
  mode: SearchMode;
  value: string;
  queryId: string | null;
  resolutionPreview: CompanyResolutionPreview | null;
  analysis: BackendCompanyAnalysis | null;
  resolved: ResolvedEntity | null;
  spatialAnalysis: SpatialLayerAResponse | null;
};

const CONSUMER_SEARCH_STORAGE_KEY = 'consumer_search_state';
const LATEST_SPATIAL_STORAGE_KEY = 'latest_spatial_analysis';

function readPersistedConsumerSearch(): PersistedConsumerSearch | null {
  if (typeof window === 'undefined') return null;

  try {
    const raw = window.localStorage.getItem(CONSUMER_SEARCH_STORAGE_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

function readLatestSpatialAnalysis(): SpatialLayerAResponse | null {
  if (typeof window === 'undefined') return null;

  try {
    const raw = window.localStorage.getItem(LATEST_SPATIAL_STORAGE_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

function persistConsumerSearch(state: PersistedConsumerSearch) {
  if (typeof window === 'undefined') return;

  window.localStorage.setItem(CONSUMER_SEARCH_STORAGE_KEY, JSON.stringify(state));
}

function spatialScore(layerA: SpatialLayerAResponse | null | undefined): number | null {
  const score = layerA?.combined_biodiversity_score ?? layerA?.species_threat_score;
  if (typeof score !== 'number' || !Number.isFinite(score)) return null;
  return Math.max(0, Math.min(100, Math.round(score)));
}

function mergeAnalysisWithSpatial(
  analysis: BackendCompanyAnalysis | null,
  layerA: SpatialLayerAResponse,
): BackendCompanyAnalysis | null {
  if (!analysis) return null;
  if (analysis.query_id && layerA.query_id && analysis.query_id !== layerA.query_id) return analysis;
  if (
    typeof analysis.spatial_analysis?.combined_biodiversity_score === 'number' &&
    typeof layerA.combined_biodiversity_score !== 'number'
  ) {
    return analysis;
  }
  return { ...analysis, spatial_analysis: layerA };
}

async function waitForSpatialAnalysis(queryId: string, maxAttempts = 36): Promise<SpatialLayerAResponse | null> {
  for (let attempt = 0; attempt < maxAttempts; attempt += 1) {
    const data = await getSpatialAnalysisForQuery(queryId);
    if (data.status === 'success' || data.status === 'failed') return data;
    await new Promise(resolve => window.setTimeout(resolve, 5000));
  }
  return null;
}

function buildSearchBody(searchMode: SearchMode, searchValue: string) {
  if (searchMode === 'barcode') return { barcode: searchValue, brand: '', company_or_abn: '' };
  if (searchMode === 'brand') return { barcode: '', brand: searchValue, company_or_abn: '' };
  return { barcode: '', brand: '', company_or_abn: searchValue };
}

function ownedCompanyAnalysisTarget(result: SearchResult): string | null {
  return (
    result.company?.abn ||
    result.abn_verification?.abn ||
    result.company?.legal_name ||
    result.abn_verification?.legal_name ||
    result.legal_owner ||
    result.brand_owner ||
    result.manufacturer ||
    null
  );
}

function resolutionPreviewFromSearchResult(result: SearchResult, fallback: string): CompanyResolutionPreview {
  return {
    legal_name: result.company?.legal_name || result.abn_verification?.legal_name || result.legal_owner || result.brand_owner || fallback,
    normalized_name: result.abn_verification?.legal_name || result.company?.legal_name || result.legal_owner || result.brand_clean || fallback,
    abn: result.company?.abn || result.abn_verification?.abn,
    state: result.company?.state || result.abn_verification?.state,
    postcode: result.company?.postcode || result.abn_verification?.postcode,
    abr: {
      success: Boolean(result.company?.abn || result.abn_verification?.success),
      message: result.message,
    },
  };
}

function resolvedEntityFromSearchResult(result: SearchResult, fallback: string): ResolvedEntity {
  return {
    brand: result.brand?.brand_name || result.brand_clean || result.brand_owner || result.brand_raw || result.input_value || fallback,
    product: result.product?.product_name || result.company?.legal_name || result.brand?.brand_name || result.input_value || 'Unknown product',
    parent: result.company?.legal_name || result.legal_owner || result.manufacturer || result.abn_verification?.legal_name || result.brand_owner || 'Unknown company',
    abn: result.company?.abn || result.abn_verification?.abn || 'N/A',
    score: result.confidence || 50,
    source: result.source,
    imageUrl: result.product?.image_url,
  };
}

function evidenceReason(record: ReturnType<typeof allEvidenceRecords>[number]) {
  const signal = record.biodiversity_signal || record.evidence_type || 'Biodiversity evidence';
  const location = record.location ? ` in ${record.location}` : '';
  const source = record.source ? ` Source: ${record.source}.` : '';
  const type = record.evidence_type ? ` (${record.evidence_type})` : '';
  return `${signal}${location}${type}.${source}`.replace(/\s+/g, ' ').trim();
}

export function ConsumerSearch() {
  const navigate = useNavigate();
  const initialSearch = useRef(readPersistedConsumerSearch()).current;
  const initialSpatial = useRef<SpatialLayerAResponse | null>((() => {
    if (!evidenceAnalysisComplete(initialSearch?.analysis || null, initialSearch?.queryId)) return null;
    const latest = initialSearch?.spatialAnalysis || readLatestSpatialAnalysis();
    if (!latest?.query_id || !initialSearch?.queryId || latest.query_id === initialSearch.queryId) return latest;
    return null;
  })()).current;
  const [mode, setMode] = useState<SearchMode>(initialSearch?.mode || 'company');
  const [value, setValue] = useState(initialSearch?.value || '');
  const [reportFiles, setReportFiles] = useState<File[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [progressStep, setProgressStep] = useState(0);
  const [queryId, setQueryId] = useState<string | null>(() => initialSearch?.queryId || localStorage.getItem('query_id'));
  const [resolutionPreview, setResolutionPreview] = useState<CompanyResolutionPreview | null>(initialSearch?.resolutionPreview || null);
  const [analysis, setAnalysis] = useState<BackendCompanyAnalysis | null>(initialSearch?.analysis || null);
  const [resolved, setResolved] = useState<ResolvedEntity | null>(initialSearch?.resolved || null);
  const [spatialAnalysis, setSpatialAnalysis] = useState<SpatialLayerAResponse | null>(initialSpatial || null);
  const [error, setError] = useState<string | null>(null);

  const resultsRef = useRef<HTMLDivElement>(null);
  const evidenceRecords = allEvidenceRecords(analysis);
  const newsCandidates: BackendNewsCandidate[] = analysis?.news?.candidates || [];
  const canShowSpatialAnalysis = evidenceAnalysisComplete(analysis, queryId);
  const awaitingInlineSpatial = isLoading && progressStep >= 5;
  const effectiveSpatialAnalysis = canShowSpatialAnalysis
    ? spatialAnalysis || analysis?.spatial_analysis
    : null;
  const assessedSpatialScore = spatialScore(effectiveSpatialAnalysis);

  const evidenceScoreReasons = analysis
    ? evidenceRecords.length
      ? [
          ...evidenceRecords.slice(0, 2).map(evidenceReason),
          newsCandidates.length
            ? `News reviewed: ${newsCandidates.slice(0, 2).map(candidate => candidate.title || candidate.source || 'candidate article').join('; ')}.`
            : `${evidenceRecords.length} extracted evidence record${evidenceRecords.length === 1 ? '' : 's'} found.`,
        ].slice(0, 3)
      : [
          'ABR resolution completed for the legal entity.',
          analysis.uploaded_reports?.length
            ? 'Uploaded reports were checked, but no high-confidence biodiversity evidence was extracted.'
            : 'No report was uploaded, so report evidence was not analysed.',
          newsCandidates.length
            ? `News candidate reviewed: ${newsCandidates[0]?.title || newsCandidates[0]?.source || 'candidate article'}.`
            : analysis.news?.candidate_count
              ? `${analysis.news.candidate_count} news candidate${analysis.news.candidate_count === 1 ? '' : 's'} found for review.`
              : 'No high-confidence news evidence was returned by the configured sources.',
        ]
    : [
        'Company identity is resolved first through ABR.',
        'News and report evidence will appear here after analysis completes.',
        'Upload a company report to include document-based evidence.',
      ];
  const scoreReasons = assessedSpatialScore !== null && effectiveSpatialAnalysis?.status === 'success'
    ? [
        `The combined biodiversity score is ${assessedSpatialScore}/100, using Layer A species threat plus extracted evidence pressure.`,
        ...evidenceScoreReasons,
      ].slice(0, 3)
    : evidenceScoreReasons;

  useEffect(() => {
    if (!resolved) return;

    persistConsumerSearch({
      mode,
      value,
      queryId,
      resolutionPreview,
      analysis,
      resolved,
      spatialAnalysis,
    });
  }, [analysis, mode, queryId, resolutionPreview, resolved, spatialAnalysis, value]);

  useEffect(() => {
    if (!queryId) return;
    if (isLoading) return;
    if (!canShowSpatialAnalysis) {
      setSpatialAnalysis(null);
      return;
    }

    let cancelled = false;
    let poll: number | undefined;

    const loadSpatialScore = () => {
      getSpatialAnalysisForQuery(queryId)
        .then((data) => {
          if (cancelled) return;

          setSpatialAnalysis(data);

          const score = spatialScore(data);
          if (data.status === 'success' && score !== null) {
            window.localStorage.setItem(LATEST_SPATIAL_STORAGE_KEY, JSON.stringify(data));
            setResolved((current) => current ? { ...current, score } : current);
            setAnalysis((current) => {
              const next = mergeAnalysisWithSpatial(current, data);
              if (next) {
                window.localStorage.setItem('company_analysis', JSON.stringify(next));
              }
              return next;
            });
          } else if (data.status === 'loading') {
            poll = window.setTimeout(loadSpatialScore, 5000);
          }
        })
        .catch((err) => {
          console.debug('Spatial biodiversity score request failed', err);
        });
    };

    loadSpatialScore();

    return () => {
      cancelled = true;
      if (poll) window.clearTimeout(poll);
    };
  }, [canShowSpatialAnalysis, isLoading, queryId]);

  const scrollToResults = () => {
    setTimeout(() => {
      resultsRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }, 100);
  };

  const resolveCompany = async (searchValue: string) => {
    const resolveForm = new FormData();
    resolveForm.append('company_or_abn', searchValue);
    const resolveData = await resolveCompanyForAnalysis(resolveForm);

    const preview = resolveData.resolution || {};
    if (resolveData.query_id) {
      localStorage.setItem('query_id', resolveData.query_id);
      setQueryId(resolveData.query_id);
    }
    if (resolveData.resolved_company_id) {
      localStorage.setItem('company_id', resolveData.resolved_company_id);
    }
    setResolutionPreview(preview);
    setProgressStep(1);
    setResolved({
      brand: preview.normalized_name || searchValue,
      product: preview.legal_name || preview.normalized_name || searchValue,
      parent: preview.legal_name || 'Unknown company',
      abn: preview.abn || 'N/A',
      score: 45,
      source: 'ABR company resolution',
    });
    scrollToResults();
  };

  const analyseCompany = async (searchValue: string, displayResolved?: Partial<ResolvedEntity>) => {
    const formData = new FormData();
    formData.append('company_or_abn', searchValue);
    formData.append('news_limit', '3');
    formData.append('max_llm_results', '10');
    formData.append('max_report_chunks', '3');
    formData.append('australia_only', 'true');
    reportFiles.forEach(file => formData.append('reports', file));

    setProgressStep(reportFiles.length ? 3 : 2);
    const data = await analyseCompanyWithReports(formData);

    if (data.query_id) {
      localStorage.setItem('query_id', data.query_id);
      setQueryId(data.query_id);
    }
    if (data.resolved_company_id) {
      localStorage.setItem('company_id', data.resolved_company_id);
    }
    setProgressStep(4);
    setProgressStep(5);

    const spatial = data.query_id ? await waitForSpatialAnalysis(data.query_id) : null;
    const analysisWithSpatial = spatial?.status === 'success'
      ? mergeAnalysisWithSpatial(data, spatial) || data
      : data;
    if (spatial) {
      setSpatialAnalysis(spatial);
      if (spatial.status === 'success') {
        window.localStorage.setItem(LATEST_SPATIAL_STORAGE_KEY, JSON.stringify(spatial));
      }
    }
    localStorage.setItem('company_analysis', JSON.stringify(analysisWithSpatial));
    setAnalysis(analysisWithSpatial);

    const profile = companyProfileFromAnalysis(analysisWithSpatial);
    const resolution = data.resolution || {};
    setResolved({
      brand: displayResolved?.brand || resolution.normalized_name || searchValue,
      product: displayResolved?.product || resolution.legal_name || resolution.normalized_name || searchValue,
      parent: resolution.legal_name || displayResolved?.parent || 'Unknown company',
      abn: resolution.abn || displayResolved?.abn || 'N/A',
      score: spatial?.status === 'success' ? spatialScore(spatial) ?? profile.score : profile.score,
      source: displayResolved?.source || 'ABR + news APIs + uploaded reports',
      imageUrl: displayResolved?.imageUrl,
    });
    scrollToResults();
  };

  const resolveGenericSearch = async (searchMode: SearchMode, searchValue: string) => {
    const data = await searchEntity(buildSearchBody(searchMode, searchValue));
    if (!data.query_id) {
      throw new Error('Search completed, but no query_id was returned.');
    }

    localStorage.setItem('query_id', data.query_id);
    setQueryId(data.query_id);
    if (data.resolved_ids?.company_id) {
      localStorage.setItem('company_id', data.resolved_ids.company_id);
    }
    const result = data.result;
    if (!result) {
      throw new Error('No matching result found.');
    }

    const resolvedEntity = resolvedEntityFromSearchResult(result, searchValue);
    setResolved(resolvedEntity);
    setResolutionPreview(resolutionPreviewFromSearchResult(result, searchValue));
    scrollToResults();

    const ownerTarget = ownedCompanyAnalysisTarget(result);
    if (ownerTarget) {
      setProgressStep(1);
      await analyseCompany(ownerTarget, {
        ...resolvedEntity,
        source: `${result.source || 'Entity resolution'} + owner company analysis`,
      });
    }
  };

  const resolveWithValue = async (searchMode: SearchMode, rawValue: string) => {
    const searchValue = rawValue.trim();
    setError(null);

    if (!searchValue) {
      setError('Please enter a barcode, brand, company name, or ABN.');
      return;
    }

    try {
      setIsLoading(true);
      setProgressStep(0);
      setAnalysis(null);
      setResolutionPreview(null);
      setSpatialAnalysis(null);

      if (searchMode === 'company') {
        await resolveCompany(searchValue);
        await analyseCompany(searchValue);
      } else {
        await resolveGenericSearch(searchMode, searchValue);
      }
    } catch (err) {
      console.error(err);
      setError(err instanceof Error ? err.message : 'Error connecting to backend. Please check the server is running.');
    } finally {
      setProgressStep(0);
      setIsLoading(false);
    }
  };

  const resolve = () => resolveWithValue(mode, value);

  return (
    <div className="-m-0 bg-gradient-to-b from-[#f5f3ee] via-[#eef1ec] to-[#e3ebe4] min-h-[calc(100vh-65px)]">
      <section className="relative overflow-hidden">
        <div className="absolute inset-0">
          <ImageWithFallback src={HERO_IMG} alt="forest canopy" className="w-full h-full object-cover" />
          <div className="absolute inset-0 bg-gradient-to-b from-stone-950/80 via-stone-900/70 to-[#f5f3ee]" />
          <div className="absolute inset-0 opacity-25">
            <svg className="w-full h-full" preserveAspectRatio="none">
              <defs>
                <pattern id="searchGrid" width="60" height="60" patternUnits="userSpaceOnUse">
                  <path d="M 60 0 L 0 0 0 60" fill="none" stroke="#d6d3d1" strokeWidth="0.4" />
                </pattern>
              </defs>
              <rect width="100%" height="100%" fill="url(#searchGrid)" />
            </svg>
          </div>
        </div>

        <div className="relative z-10 max-w-4xl mx-auto px-8 pt-16 pb-20">
          <div className="flex items-center gap-3 mb-5 text-emerald-200/80 font-mono text-[11px] tracking-[0.2em]">
            <span className="w-8 h-px bg-emerald-300/60" />
            <span>01 - RESOLVE & SCORE</span>
          </div>

          <h1 className="text-[40px] md:text-[52px] leading-[1.05] tracking-tight text-white max-w-2xl">
            What's the real impact
            <span className="block italic text-emerald-200 font-light">of what you buy?</span>
          </h1>

          <p className="mt-5 text-stone-200/85 text-[15px] max-w-xl leading-relaxed">
            Scan a barcode, search a brand, or look up a company. We'll resolve the legal entity and score its biodiversity impact.
          </p>

          <div className="mt-9 bg-white rounded-2xl shadow-2xl p-1.5 border border-white/10">
            <div className="flex gap-1 p-1 bg-stone-50 rounded-xl">
              {([
                { id: 'barcode', label: 'Barcode', icon: Barcode },
                { id: 'brand', label: 'Brand', icon: Sparkles },
                { id: 'company', label: 'Company / ABN', icon: Building2 },
              ] as const).map(t => {
                const Icon = t.icon;
                const active = mode === t.id;
                return (
                  <button
                    key={t.id}
                    onClick={() => { setMode(t.id); setValue(''); setError(null); }}
                    className={`flex-1 inline-flex items-center justify-center gap-2 px-3 py-2.5 rounded-lg text-[13px] tracking-tight transition ${
                      active ? 'bg-white text-stone-900 shadow-sm' : 'text-stone-500 hover:text-stone-900'
                    }`}
                  >
                    <Icon size={14} /> {t.label}
                  </button>
                );
              })}
            </div>

            <div className="flex items-center gap-2 p-2">
              <Search size={16} className="text-stone-400 ml-2" />
              <input
                value={value}
                onChange={e => setValue(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && !isLoading && resolve()}
                placeholder={mode === 'barcode' ? '9 310072 011691' : mode === 'brand' ? 'e.g. Dairy Farmers, Tim Tam' : 'Company name or ABN'}
                className="flex-1 h-11 bg-transparent outline-none text-[14px] text-stone-800 placeholder:text-stone-400"
              />
              <button
                onClick={resolve}
                disabled={isLoading}
                className="inline-flex items-center gap-1.5 px-5 h-10 bg-emerald-500 hover:bg-emerald-400 disabled:bg-stone-300 disabled:text-stone-600 text-stone-950 rounded-lg text-[13px] shadow-[0_8px_24px_-8px_rgba(16,185,129,0.6)]"
              >
                {isLoading ? <><Loader2 size={14} className="animate-spin" /> Analysing</> : <>Analyse <ArrowRight size={14} /></>}
              </button>
            </div>

            {error && (
              <div className="mx-2 mb-1 px-3 py-2 rounded-lg bg-rose-50 border border-rose-200 text-[12px] text-rose-700">
                {error}
              </div>
            )}

            <div className="mx-2 mb-2 p-3 rounded-xl bg-stone-50 border border-dashed border-stone-200 group hover:bg-stone-100 hover:border-stone-300 transition-colors cursor-pointer text-center relative">
              <input
                type="file"
                accept=".pdf,.txt,.md,.markdown,.csv,.json,.html,.htm"
                multiple
                onChange={event => setReportFiles(Array.from(event.target.files || []))}
                className="absolute inset-0 opacity-0 cursor-pointer w-full h-full"
              />
              <div className="flex flex-col items-center justify-center gap-1.5 pointer-events-none">
                <div className="w-8 h-8 rounded-full bg-white shadow-sm flex items-center justify-center text-emerald-600 group-hover:scale-110 transition-transform">
                  <FileText size={14} />
                </div>
                <div className="text-[12px] font-medium text-stone-700">
                  {reportFiles.length ? `${reportFiles.length} report${reportFiles.length === 1 ? '' : 's'} selected` : 'Upload annual or sustainability reports'}
                </div>
                <div className="text-[10px] text-stone-400">PDF, text, HTML, CSV or JSON. Reports are analysed with company search.</div>
              </div>
            </div>
          </div>

          <div className="mt-6 pt-5 border-t border-white/15 flex flex-wrap items-center gap-x-8 gap-y-2 text-white/80">
            <div className="font-mono text-[10px] tracking-[0.2em] text-white/50">INDEXED SOURCES</div>
            {['EPBC Act', 'ABR', 'CSIRO', 'TNFD', 'IUCN'].map(s => (
              <span key={s} className="text-[11px] tracking-tight">{s}</span>
            ))}
          </div>
        </div>
      </section>

      <section className="max-w-5xl mx-auto px-8 py-14">
        {isLoading && (
          <Card className="p-5 mb-6 border-emerald-100">
            <div className="flex flex-col md:flex-row md:items-start md:justify-between gap-4">
              <div>
                <div className="font-mono text-[10px] uppercase tracking-[0.2em] text-emerald-700">Analysis running</div>
                <div className="text-[17px] text-stone-900 mt-1">
                  {resolutionPreview?.legal_name || resolutionPreview?.normalized_name || value || 'Resolving company'}
                </div>
                <div className="text-[12px] text-stone-500 mt-1">
                  {resolutionPreview?.abn ? `ABN ${resolutionPreview.abn}` : 'Checking ABR first, then evidence sources'}
                  {resolutionPreview?.state ? ` - ${resolutionPreview.state}` : ''}
                </div>
              </div>
              <Chip tone={resolutionPreview?.abr?.success ? 'emerald' : 'amber'}>
                {resolutionPreview ? 'Company resolved' : 'Resolving company'}
              </Chip>
            </div>

            {awaitingInlineSpatial && (
              <div className="mt-3 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-[12px] text-amber-800">
                Waiting for Layer A spatial scoring before showing the final biodiversity score.
              </div>
            )}

            <div className="mt-4 grid grid-cols-1 md:grid-cols-6 gap-2">
              {companyProgressSteps.map((step, index) => {
                const done = index < progressStep;
                const active = index === progressStep;
                return (
                  <div
                    key={step}
                    className={`min-h-16 rounded-xl border px-3 py-2 text-[11px] transition ${
                      done
                        ? 'bg-emerald-50 border-emerald-200 text-emerald-800'
                        : active
                          ? 'bg-white border-emerald-300 text-stone-900 shadow-sm'
                          : 'bg-stone-50 border-stone-100 text-stone-400'
                    }`}
                  >
                    <div className="flex items-center gap-1.5">
                      <span className={`w-2 h-2 rounded-full ${done ? 'bg-emerald-500' : active ? 'bg-amber-500 animate-pulse' : 'bg-stone-300'}`} />
                      <span className="font-mono text-[9px] tracking-[0.16em]">0{index + 1}</span>
                    </div>
                    <div className="mt-1 leading-snug">{step}</div>
                  </div>
                );
              })}
            </div>
          </Card>
        )}

        {!resolved && (
          <div className="space-y-10">
            <div>
              <div className="flex items-end justify-between mb-5">
                <div>
                  <div className="flex items-center gap-2 text-[11px] tracking-[0.2em] uppercase text-emerald-700 font-mono mb-1">
                    <Flame size={12} /> 02 - TRENDING
                  </div>
                  <h2 className="text-[22px] tracking-tight text-stone-900">What Australians are searching</h2>
                </div>
              </div>

              <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                {suggestions.map((s, i) => {
                  const color = s.score >= 65 ? 'text-rose-600' : s.score >= 45 ? 'text-amber-600' : 'text-emerald-600';
                  return (
                    <button
                      key={s.label}
                      onClick={() => {
                        setMode('company');
                        setValue(s.abn);
                        resolveWithValue('company', s.abn);
                      }}
                      className="group relative p-5 bg-white border border-stone-200 hover:border-emerald-400 hover:shadow-md rounded-2xl text-left transition"
                    >
                      <div className="font-mono text-[9px] tracking-[0.2em] text-stone-400 mb-3">0{i + 1} / 04</div>
                      <div className={`text-[32px] leading-none tracking-tight ${color}`}>{s.score}</div>
                      <div className="mt-3 text-[14px] text-stone-900 truncate">{s.label}</div>
                      <div className="text-[11px] text-stone-500 mt-0.5">{s.sector}</div>
                      <div className="mt-4 pt-3 border-t border-dashed border-stone-200 flex items-center justify-between">
                        <span className="text-[10px] text-stone-400 font-mono">ABN {s.abn.slice(0, 8)}...</span>
                        <ArrowRight size={12} className="text-stone-400 group-hover:text-emerald-600 group-hover:translate-x-0.5 transition" />
                      </div>
                    </button>
                  );
                })}
              </div>
            </div>

            <div className="relative grid grid-cols-1 md:grid-cols-3 gap-4">
              {[
                { icon: ShieldCheck, title: 'Verified to ABR', text: 'Every brand is resolved to a real Australian Business Registry entity.' },
                { icon: MapPin, title: 'Evidence-first', text: 'Reports and news are separated so unrelated local files are not reused.' },
                { icon: Leaf, title: 'Plain English', text: 'We explain the score from extracted evidence and reviewed candidates.' },
              ].map((f, i) => {
                const Icon = f.icon;
                return (
                  <div key={f.title} className="relative p-6 bg-white border border-stone-200 rounded-2xl overflow-hidden">
                    <TopoSvg className="absolute inset-0 w-full h-full text-emerald-800 pointer-events-none" />
                    <div className="relative">
                      <div className="font-mono text-[10px] tracking-[0.2em] text-stone-400 mb-3">0{i + 1} - {f.title.toUpperCase().split(' ')[0]}</div>
                      <div className="w-10 h-10 rounded-lg bg-emerald-50 text-emerald-700 flex items-center justify-center mb-3"><Icon size={18} /></div>
                      <div className="text-[15px] text-stone-900 tracking-tight">{f.title}</div>
                      <div className="text-[12px] text-stone-600 mt-1.5 leading-relaxed">{f.text}</div>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {resolved && (
          <div ref={resultsRef} className="space-y-6 scroll-mt-24">
            <div className="flex items-center gap-2 text-[11px] tracking-[0.2em] uppercase text-emerald-700 font-mono">
              <CheckCircle2 size={12} /> 02 - RESOLVED
            </div>

            <Card className="p-6">
              <div className="flex items-start gap-4">
                <div className="w-14 h-14 rounded-xl bg-gradient-to-br from-emerald-100 to-blue-100 flex items-center justify-center">
                  <Leaf size={24} className="text-emerald-600" />
                </div>
                <div className="flex-1">
                  <div className="flex items-center gap-2 flex-wrap">
                    <div className="font-mono text-[10px] uppercase tracking-[0.2em] text-stone-400">Resolved entity</div>
                    <Chip tone="emerald"><CheckCircle2 size={11} /> ABR verified</Chip>
                  </div>
                  <div className="text-[18px] text-stone-900 mt-0.5 tracking-tight">{resolved.product}</div>
                  {resolved.imageUrl && (
                    <img src={resolved.imageUrl} alt={resolved.product} className="mt-3 w-24 h-24 object-cover rounded-xl border border-stone-200" />
                  )}
                  <div className="text-[13px] text-stone-600">
                    Brand <span className="text-stone-900">{resolved.brand}</span> - Owned by <span className="text-stone-900">{resolved.parent}</span> - ABN {resolved.abn}
                  </div>
                  {analysis && (
                    <div className="mt-2 flex flex-wrap gap-1.5">
                      <Chip tone="stone">{analysis.search_queries?.length || 0} generated queries</Chip>
                      <Chip tone="stone">{analysis.news?.candidate_count || newsCandidates.length || 0} news candidates</Chip>
                      <Chip tone={analysis.analysed_reports?.length ? 'blue' : 'stone'}>
                        {analysis.analysed_reports?.length || 0} uploaded reports checked
                      </Chip>
                    </div>
                  )}
                  <div className="mt-2"><Confidence value={Math.min(100, Math.max(0, resolved.score))} /></div>
                </div>
                <div className="flex items-center gap-2">
                  <button onClick={() => navigate('/app/spatial')} className="inline-flex items-center gap-1.5 px-3.5 h-9 bg-emerald-700 hover:bg-emerald-800 text-white rounded-lg text-sm">
                    Spatial analysis <MapPin size={14} />
                  </button>
                  <button onClick={() => navigate('/app/overview')} className="inline-flex items-center gap-1.5 px-3.5 h-9 bg-stone-900 hover:bg-stone-800 text-white rounded-lg text-sm">
                    View full report <ArrowRight size={14} />
                  </button>
                </div>
              </div>
            </Card>

            {analysis && (
              <Card className="p-6">
                <div className="flex items-start justify-between gap-4">
                  <div>
                    <div className="font-mono text-[10px] uppercase tracking-[0.2em] text-stone-400">Analysis pipeline</div>
                    <div className="text-[18px] text-stone-900 mt-1">{analysis.resolution?.legal_name || analysis.resolution?.normalized_name}</div>
                    <div className="text-[12px] text-stone-500 mt-1">
                      {analysis.search_queries?.length || 0} search queries - {analysis.news?.candidate_count || 0} news candidates - {analysis.analysed_reports?.length || 0} report files checked
                    </div>
                  </div>
                  <Chip tone={analysis.resolution?.abr?.success ? 'emerald' : 'amber'}>
                    {analysis.resolution?.abr?.success ? 'ABR resolved' : 'ABR needs review'}
                  </Chip>
                </div>

                <div className="mt-4 grid grid-cols-1 md:grid-cols-3 gap-3">
                  {(analysis.pipeline_steps || []).map(step => (
                    <div key={step} className="h-10 px-3 rounded-lg bg-stone-50 border border-stone-100 flex items-center gap-2 text-[12px] text-stone-700">
                      <CheckCircle2 size={13} className="text-emerald-600 shrink-0" />
                      <span className="truncate">{step}</span>
                    </div>
                  ))}
                </div>

                <div className="mt-5 grid grid-cols-1 md:grid-cols-3 gap-3">
                  <div className="rounded-xl border border-stone-100 bg-stone-50 p-4">
                    <div className="font-mono text-[10px] uppercase tracking-[0.2em] text-stone-400">Generated queries</div>
                    <div className="text-[26px] text-stone-900 mt-1">{analysis.search_queries?.length || 0}</div>
                    <div className="text-[11px] text-stone-500 mt-1">all sent to configured news providers</div>
                  </div>
                  <div className="rounded-xl border border-stone-100 bg-stone-50 p-4">
                    <div className="font-mono text-[10px] uppercase tracking-[0.2em] text-stone-400">Reviewed candidates</div>
                    <div className="text-[26px] text-stone-900 mt-1">{newsCandidates.length || analysis.news?.candidate_count || 0}</div>
                    <div className="text-[11px] text-stone-500 mt-1">ranked for LLM extraction</div>
                  </div>
                  <div className="rounded-xl border border-stone-100 bg-stone-50 p-4">
                    <div className="font-mono text-[10px] uppercase tracking-[0.2em] text-stone-400">Evidence records</div>
                    <div className="text-[26px] text-stone-900 mt-1">{evidenceRecords.length}</div>
                    <div className="text-[11px] text-stone-500 mt-1">from news and uploaded reports</div>
                  </div>
                </div>

                {evidenceRecords.length > 0 && (
                  <div className="mt-5 grid grid-cols-1 md:grid-cols-2 gap-4">
                    {evidenceRecords.slice(0, 4).map((record, index) => (
                      <div key={`${record.source_type || 'evidence'}-${record.source_url || record.source || index}`} className="p-4 rounded-xl border border-stone-100 bg-white">
                        <div className="flex items-center gap-2 mb-2">
                          <Chip tone={record.source_type === 'report' ? 'blue' : 'stone'}>{record.source_type || 'evidence'}</Chip>
                          <span className="text-[11px] text-stone-400 truncate">{record.source}</span>
                        </div>
                        <div className="text-[13px] text-stone-900">{record.biodiversity_signal || 'Biodiversity evidence found'}</div>
                        <div className="text-[12px] text-stone-500 mt-1">{record.location || 'Location not specified'} - {record.evidence_type || 'unknown evidence type'}</div>
                        <div className="mt-2"><Confidence value={Math.round(((record.confidence || record.llm_confidence || 0.5) <= 1 ? (record.confidence || record.llm_confidence || 0.5) * 100 : (record.confidence || record.llm_confidence || 50)))} /></div>
                      </div>
                    ))}
                  </div>
                )}

                {newsCandidates.length > 0 && (
                  <div className="mt-5">
                    <div className="font-mono text-[10px] uppercase tracking-[0.2em] text-stone-400 mb-2">News candidates reviewed</div>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                      {newsCandidates.slice(0, 4).map((candidate, index) => (
                        <a
                          key={`${candidate.url || candidate.title || 'candidate'}-${index}`}
                          href={candidate.url}
                          target="_blank"
                          rel="noreferrer"
                          className="block p-4 rounded-xl border border-stone-100 bg-stone-50 hover:bg-white hover:border-emerald-200 transition"
                        >
                          <div className="flex items-center gap-2 mb-1">
                            <Chip tone="stone">news</Chip>
                            <span className="text-[11px] text-stone-400 truncate">{candidate.source || candidate.source_type || 'Source'}</span>
                          </div>
                          <div className="text-[13px] text-stone-900 leading-snug">{candidate.title || 'Untitled candidate'}</div>
                          {candidate.snippet && <div className="text-[12px] text-stone-500 mt-1 line-clamp-2">{candidate.snippet}</div>}
                        </a>
                      ))}
                    </div>
                  </div>
                )}
              </Card>
            )}

            <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
              <Card className="p-6 md:col-span-1">
                <div className="font-mono text-[10px] uppercase tracking-[0.2em] text-stone-400 mb-2">Biodiversity score</div>
                <div className="flex items-end gap-2">
                  <div className="text-[64px] leading-none tracking-tight text-amber-600">{resolved.score}</div>
                  <div className="text-stone-500 mb-2">/100</div>
                </div>
                <div className="mt-2"><RiskBadge level={riskLevelFromScore(resolved.score)} /></div>
                <div className="mt-4 h-2 bg-stone-100 rounded-full overflow-hidden">
                  <div className="h-full bg-gradient-to-r from-emerald-500 via-amber-400 to-rose-500" style={{ width: `${resolved.score}%` }} />
                </div>
                <div className="mt-2 flex justify-between text-[10px] text-stone-400 font-mono">
                  <span>0 - LOW</span><span>50</span><span>100 - CRITICAL</span>
                </div>
              </Card>

              <Card className="p-6 md:col-span-2">
                <div className="flex items-center gap-2 mb-3">
                  <ShieldCheck size={16} className="text-emerald-600" />
                  <div className="text-[13px] uppercase tracking-wider text-stone-500">Why this score</div>
                </div>
                <ul className="space-y-2.5">
                  {scoreReasons.map((reason, index) => (
                    <li key={`${reason}-${index}`} className="flex gap-3 text-[13px] text-stone-700">
                      <CircleDot size={14} className={`${index === 0 ? 'text-amber-500' : index === 1 ? 'text-emerald-500' : 'text-orange-500'} mt-0.5 shrink-0`} />
                      {reason}
                    </li>
                  ))}
                </ul>
              </Card>
            </div>

            {mode !== 'company' && (
              <div>
                <div className="flex items-end justify-between mb-4">
                  <div>
                    <div className="flex items-center gap-2 text-[11px] tracking-[0.2em] uppercase text-emerald-700 font-mono mb-1">
                      <Sparkles size={12} /> 03 - BETTER CHOICES
                    </div>
                    <h2 className="text-[22px] tracking-tight text-stone-900">Kinder to nature, in the same category</h2>
                  </div>
                  <TrendingUp size={16} className="text-emerald-600" />
                </div>

                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                  {betterChoices.map((b, i) => (
                    <Card key={b.brand} className="p-5 hover:shadow-md transition">
                      <div className="font-mono text-[10px] tracking-[0.2em] text-stone-400 mb-2">ALT - 0{i + 1}</div>
                      <div className="flex items-center justify-between mb-2">
                        <div className="text-[14px] tracking-tight text-stone-900">{b.brand}</div>
                        <RiskBadge level={b.level} />
                      </div>
                      <div className="flex items-end gap-1 mb-2">
                        <div className="text-[32px] leading-none tracking-tight text-emerald-700">{b.score}</div>
                        <div className="text-[11px] text-stone-400 mb-1">score</div>
                      </div>
                      <div className="text-[12px] text-stone-600 leading-relaxed">{b.note}</div>
                    </Card>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </section>
    </div>
  );
}

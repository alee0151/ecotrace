import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router';
import {
  AlertTriangle,
  Bell,
  Building2,
  ChevronDown,
  Clock3,
  Database,
  ExternalLink,
  Factory,
  Leaf,
  MapPin,
  RefreshCw,
  Search,
  Shield,
  Trash2,
  TrendingDown,
  TrendingUp,
} from 'lucide-react';
import { Chip, InfoTip, RiskBadge, type RiskLevel } from '../components/shared';
import type { CompanyWatchlistRecord } from '../../lib/api';
import type { BackendCompanyAnalysis } from '../lib/analysis';
import {
  currentUserIdentity,
  loadCompanyWatchlistForCurrentUser,
  removeCompanyWatchlistForCurrentUser,
} from '../lib/companyWatchlist';

type SortKey = 'risk' | 'date' | 'name';
type AlertStatus = 'Increasing' | 'Stable' | 'Decreasing';

const riskLevelFromScore = (score?: number | null): RiskLevel => {
  const value = score ?? 0;
  if (value >= 85) return 'Critical';
  if (value >= 65) return 'High';
  if (value >= 35) return 'Medium';
  return 'Low';
};

const formatDate = (value?: string | null) => {
  if (!value) return 'Not synced';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat('en-AU', {
    day: '2-digit',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date);
};

const scoreTrend = (company: CompanyWatchlistRecord): AlertStatus => {
  const previous = Number(company.metadata_json?.previous_score ?? company.risk_score ?? 0);
  const current = company.risk_score ?? 0;
  if (current - previous >= 4) return 'Increasing';
  if (previous - current >= 4) return 'Decreasing';
  return 'Stable';
};

const footprintLocations: Record<string, Array<{ label: string; type: string; x: number; y: number }>> = {
  bhp: [
    { label: 'Pilbara WA', type: 'Region', x: 24, y: 40 },
    { label: 'Olympic Dam SA', type: 'Asset', x: 52, y: 62 },
    { label: 'Bowen Basin QLD', type: 'Region', x: 68, y: 36 },
  ],
  'rio tinto': [
    { label: 'Pilbara WA', type: 'Region', x: 26, y: 42 },
    { label: 'Weipa QLD', type: 'Asset', x: 70, y: 24 },
    { label: 'Gladstone QLD', type: 'Asset', x: 72, y: 48 },
  ],
  woolworths: [
    { label: 'National supplier base', type: 'Supply chain', x: 48, y: 44 },
    { label: 'Murray-Darling Basin', type: 'Region', x: 58, y: 66 },
  ],
  coles: [
    { label: 'National supplier base', type: 'Supply chain', x: 48, y: 44 },
    { label: 'Northern Australia', type: 'Region', x: 56, y: 25 },
  ],
  fortescue: [
    { label: 'Chichester Hub', type: 'Asset', x: 25, y: 40 },
    { label: 'Solomon Hub', type: 'Asset', x: 30, y: 44 },
    { label: 'Pilbara WA', type: 'Region', x: 28, y: 47 },
  ],
};

function footprintFor(company: CompanyWatchlistRecord) {
  const key = Object.keys(footprintLocations).find((name) =>
    company.company_name.toLowerCase().includes(name),
  );
  if (key) return footprintLocations[key];
  return [
    { label: company.region || 'Registered operating region', type: 'Company footprint', x: 52, y: 48 },
  ];
}

function companyAnalysisTarget(company: CompanyWatchlistRecord): string {
  return (company.abn || company.company_name).trim();
}

function analysisSnapshotFor(company: CompanyWatchlistRecord): BackendCompanyAnalysis | null {
  const snapshot = company.metadata_json?.analysis_snapshot;
  if (!snapshot || typeof snapshot !== 'object') return null;
  return snapshot as BackendCompanyAnalysis;
}

function overviewSnapshotFor(company: CompanyWatchlistRecord): BackendCompanyAnalysis {
  const savedSnapshot = analysisSnapshotFor(company);
  if (savedSnapshot) return savedSnapshot;

  const metadata = company.metadata_json || {};
  return {
    query_id: company.query_id || null,
    resolution: {
      legal_name: company.company_name,
      normalized_name: company.company_name,
      input_value: company.company_name,
      abn: company.abn || null,
      state: typeof metadata.state === 'string' ? metadata.state : null,
      postcode: typeof metadata.postcode === 'string' ? metadata.postcode : null,
      abr: {
        success: Boolean(company.abn),
        message: 'Loaded from company watchlist',
      },
    },
    news: {
      candidate_count: typeof metadata.news_candidate_count === 'number' ? metadata.news_candidate_count : 0,
      candidates: [],
      evidence: [],
    },
    reports: {
      evidence_count: 0,
      evidence: [],
    },
    analysed_reports: [],
  };
}

export function Watchlist() {
  const navigate = useNavigate();
  const identity = useMemo(() => currentUserIdentity(), []);
  const [companies, setCompanies] = useState<CompanyWatchlistRecord[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [query, setQuery] = useState('');
  const [riskFilter, setRiskFilter] = useState<'All' | RiskLevel>('All');
  const [sort, setSort] = useState<SortKey>('risk');
  const [loading, setLoading] = useState(true);
  const [source, setSource] = useState<'backend' | 'local'>('local');
  const [message, setMessage] = useState<string | null>(null);

  const loadWatchlist = async () => {
    setLoading(true);
    setMessage(null);
    try {
      const result = await loadCompanyWatchlistForCurrentUser();
      setCompanies(result.records);
      setSource(result.source);
      setSelectedId((current) => current && result.records.some((record) => record.watchlist_id === current)
        ? current
        : result.records[0]?.watchlist_id ?? null);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Could not load watchlist.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadWatchlist();
  }, []);

  const filteredCompanies = useMemo(() => {
    const lowered = query.trim().toLowerCase();
    const rows = companies.filter((company) => {
      const matchesQuery = !lowered || [
        company.company_name,
        company.abn || '',
        company.industry || '',
        company.region || '',
      ].some((value) => value.toLowerCase().includes(lowered));
      const matchesRisk = riskFilter === 'All' || riskLevelFromScore(company.risk_score) === riskFilter;
      return matchesQuery && matchesRisk;
    });

    return rows.sort((a, b) => {
      if (sort === 'date') return new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime();
      if (sort === 'name') return a.company_name.localeCompare(b.company_name);
      return (b.risk_score ?? 0) - (a.risk_score ?? 0);
    });
  }, [companies, query, riskFilter, sort]);

  const selectedCompany = companies.find((company) => company.watchlist_id === selectedId) ?? filteredCompanies[0] ?? null;
  const averageRisk = companies.length
    ? Math.round(companies.reduce((total, company) => total + (company.risk_score ?? 0), 0) / companies.length)
    : 0;
  const highRiskCount = companies.filter((company) => ['High', 'Critical'].includes(riskLevelFromScore(company.risk_score))).length;
  const alertCount = companies.filter((company) => company.alerts_enabled).length;

  const removeCompany = async (company: CompanyWatchlistRecord) => {
    const confirmed = window.confirm(`Remove ${company.company_name} from your watchlist?`);
    if (!confirmed) return;
    await removeCompanyWatchlistForCurrentUser(company.watchlist_id);
    setCompanies((current) => current.filter((record) => record.watchlist_id !== company.watchlist_id));
    if (selectedId === company.watchlist_id) setSelectedId(null);
    setMessage(`${company.company_name} removed from your watchlist.`);
  };

  const openCompanyOverview = (company: CompanyWatchlistRecord) => {
    const snapshot = overviewSnapshotFor(company);
    window.localStorage.setItem('company_analysis', JSON.stringify(snapshot));
    if (snapshot.query_id) window.localStorage.setItem('query_id', snapshot.query_id);
    if (snapshot.spatial_analysis) {
      window.localStorage.setItem('latest_spatial_analysis', JSON.stringify(snapshot.spatial_analysis));
    }
    navigate('/app/overview');
  };

  const analyseLatest = (company: CompanyWatchlistRecord) => {
    navigate(`/app/analyse?company=${encodeURIComponent(companyAnalysisTarget(company))}&autorun=1`);
  };

  return (
    <div className="min-h-screen bg-stone-50">
      <div className="mx-auto max-w-[1500px] space-y-5 px-5 py-5">
        <section className="rounded-lg border border-stone-200 bg-white p-4 shadow-sm">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
            <div>
              <div className="flex flex-wrap items-center gap-2">
                <div className="text-[22px] font-semibold text-stone-950">Company watchlist</div>
                <Chip tone={source === 'backend' ? 'emerald' : 'amber'}>
                  <Database className="size-3" /> {source === 'backend' ? 'Database synced' : 'Local fallback'}
                </Chip>
              </div>
              <div className="mt-1 text-[13px] text-stone-600">
                User-scoped monitoring for {identity.email || identity.userId || 'local demo user'}.
              </div>
            </div>
            <div className="flex flex-wrap gap-2">
              <button
                onClick={() => void loadWatchlist()}
                className="inline-flex h-9 items-center gap-2 rounded-lg border border-stone-200 bg-white px-3 text-[12px] text-stone-700 hover:bg-stone-50"
              >
                <RefreshCw className="size-4" /> Refresh
              </button>
              <button
                onClick={() => navigate('/app/overview')}
                className="inline-flex h-9 items-center gap-2 rounded-lg bg-emerald-700 px-3 text-[12px] text-white hover:bg-emerald-800"
              >
                <Building2 className="size-4" /> Add from overview
              </button>
            </div>
          </div>

          <div className="mt-4 grid gap-3 md:grid-cols-4">
            <SummaryCard label="Watched companies" value={String(companies.length)} icon={Building2} />
            <SummaryCard label="Average risk" value={companies.length ? `${averageRisk}/100` : 'N/A'} icon={AlertTriangle} />
            <SummaryCard label="High-risk companies" value={String(highRiskCount)} icon={TrendingUp} />
            <SummaryCard label="Alerts enabled" value={String(alertCount)} icon={Bell} />
          </div>
        </section>

        {message && (
          <div className="rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-2 text-[13px] text-emerald-800">
            {message}
          </div>
        )}

        <section className="grid gap-5 xl:grid-cols-[minmax(420px,0.9fr)_minmax(0,1.1fr)]">
          <div className="rounded-lg border border-stone-200 bg-white p-4 shadow-sm">
            <div className="mb-4 flex flex-col gap-3">
              <div className="relative">
                <Search className="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-stone-400" />
                <input
                  value={query}
                  onChange={(event) => setQuery(event.target.value)}
                  placeholder="Search watched company"
                  className="h-10 w-full rounded-lg border border-stone-200 bg-stone-50 pl-9 pr-3 text-[13px] outline-none focus:border-emerald-500 focus:bg-white focus:ring-2 focus:ring-emerald-100"
                />
              </div>
              <div className="flex flex-wrap items-center gap-2">
                {(['All', 'Low', 'Medium', 'High', 'Critical'] as const).map((level) => (
                  <button
                    key={level}
                    onClick={() => setRiskFilter(level)}
                    className={`h-8 rounded-lg px-3 text-[12px] transition ${
                      riskFilter === level ? 'bg-emerald-700 text-white' : 'border border-stone-200 text-stone-600 hover:bg-stone-50'
                    }`}
                  >
                    {level}
                  </button>
                ))}
                <label className="relative ml-auto">
                  <select
                    value={sort}
                    onChange={(event) => setSort(event.target.value as SortKey)}
                    className="h-8 appearance-none rounded-lg border border-stone-200 bg-white pl-3 pr-8 text-[12px] text-stone-700 outline-none focus:border-emerald-500"
                  >
                    <option value="risk">Risk score</option>
                    <option value="date">Last updated</option>
                    <option value="name">Company name</option>
                  </select>
                  <ChevronDown className="pointer-events-none absolute right-2 top-1/2 size-3.5 -translate-y-1/2 text-stone-400" />
                </label>
              </div>
            </div>

            {loading ? (
              <div className="rounded-lg border border-stone-200 bg-stone-50 p-5 text-[13px] text-stone-500">
                Loading your company watchlist...
              </div>
            ) : companies.length === 0 ? (
              <EmptyWatchlist onAdd={() => navigate('/app/overview')} />
            ) : filteredCompanies.length === 0 ? (
              <div className="rounded-lg border border-dashed border-stone-300 bg-stone-50 p-5 text-[13px] text-stone-500">
                No watched companies match the current filters.
              </div>
            ) : (
              <div className="space-y-2">
                {filteredCompanies.map((company) => {
                  const selected = selectedCompany?.watchlist_id === company.watchlist_id;
                  const trend = scoreTrend(company);
                  const TrendIcon = trend === 'Increasing' ? TrendingUp : trend === 'Decreasing' ? TrendingDown : Clock3;
                  return (
                    <button
                      key={company.watchlist_id}
                      onClick={() => setSelectedId(company.watchlist_id)}
                      className={`w-full rounded-lg border p-3 text-left transition ${
                        selected ? 'border-emerald-500 bg-emerald-50' : 'border-stone-200 bg-white hover:bg-stone-50'
                      }`}
                    >
                      <div className="flex items-start gap-3">
                        <div className="flex size-10 shrink-0 items-center justify-center rounded-lg bg-stone-900 text-[12px] font-semibold text-white">
                          {company.company_name.slice(0, 2).toUpperCase()}
                        </div>
                        <div className="min-w-0 flex-1">
                          <div className="truncate text-[13px] font-semibold text-stone-950">{company.company_name}</div>
                          <div className="mt-1 flex flex-wrap items-center gap-2 text-[11px] text-stone-500">
                            <span>{company.industry || 'Industry unavailable'}</span>
                            <span className="h-1 w-1 rounded-full bg-stone-300" />
                            <span>{company.region || 'Region unavailable'}</span>
                          </div>
                          <div className="mt-2 flex flex-wrap items-center gap-2">
                            <RiskBadge level={riskLevelFromScore(company.risk_score)} label={`${company.risk_score ?? 'N/A'}/100`} />
                            <Chip tone={company.alerts_enabled ? 'emerald' : 'stone'}>
                              <Bell className="size-3" /> {company.alerts_enabled ? 'Alerts on' : 'Alerts off'}
                            </Chip>
                            <span className="inline-flex items-center gap-1 text-[11px] text-stone-500">
                              <TrendIcon className="size-3" /> {trend}
                            </span>
                          </div>
                        </div>
                      </div>
                    </button>
                  );
                })}
              </div>
            )}
          </div>

          <CompanyMonitorPanel
            company={selectedCompany}
            onRemove={selectedCompany ? () => void removeCompany(selectedCompany) : undefined}
            onOpenOverview={selectedCompany ? () => openCompanyOverview(selectedCompany) : undefined}
            onAnalyseLatest={selectedCompany ? () => analyseLatest(selectedCompany) : undefined}
          />
        </section>
      </div>
    </div>
  );
}

function CompanyMonitorPanel({
  company,
  onRemove,
  onOpenOverview,
  onAnalyseLatest,
}: {
  company: CompanyWatchlistRecord | null;
  onRemove?: () => void;
  onOpenOverview?: () => void;
  onAnalyseLatest?: () => void;
}) {
  if (!company) {
    return (
      <div className="rounded-lg border border-stone-200 bg-white p-6 shadow-sm">
        <div className="rounded-lg border border-dashed border-stone-300 bg-stone-50 p-6 text-center text-[13px] text-stone-500">
          Select a watched company to view its monitoring dashboard.
        </div>
      </div>
    );
  }

  const metadata = company.metadata_json || {};
  const locations = footprintFor(company);
  const trend = scoreTrend(company);
  const trendTone = trend === 'Increasing' ? 'text-rose-700' : trend === 'Decreasing' ? 'text-emerald-700' : 'text-stone-600';

  return (
    <div className="space-y-5">
      <section className="rounded-lg border border-stone-200 bg-white p-4 shadow-sm">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <div className="text-[20px] font-semibold text-stone-950">{company.company_name}</div>
              <RiskBadge level={riskLevelFromScore(company.risk_score)} />
            </div>
            <div className="mt-1 text-[12px] text-stone-500">
              ABN {company.abn || 'not available'} · Added {formatDate(company.created_at)}
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            <button
              onClick={onOpenOverview}
              className="inline-flex h-9 items-center gap-2 rounded-lg border border-stone-200 px-3 text-[12px] text-stone-700 hover:bg-stone-50"
            >
              <ExternalLink className="size-4" /> Open overview
            </button>
            <button
              onClick={onAnalyseLatest}
              className="inline-flex h-9 items-center gap-2 rounded-lg bg-emerald-700 px-3 text-[12px] text-white hover:bg-emerald-800"
            >
              <RefreshCw className="size-4" /> Analyse latest
            </button>
            <button
              onClick={onRemove}
              className="inline-flex h-9 items-center gap-2 rounded-lg border border-rose-200 px-3 text-[12px] text-rose-700 hover:bg-rose-50"
            >
              <Trash2 className="size-4" /> Remove
            </button>
          </div>
        </div>

        <div className="mt-4 grid gap-3 md:grid-cols-4">
          <SummaryCard label="Risk score" value={company.risk_score != null ? `${company.risk_score}/100` : 'N/A'} icon={AlertTriangle} />
          <SummaryCard label="Risk trend" value={trend} icon={trend === 'Increasing' ? TrendingUp : trend === 'Decreasing' ? TrendingDown : Clock3} className={trendTone} />
          <SummaryCard label="Threatened species" value={String(metadata.threatened_species_count ?? 'N/A')} icon={Leaf} />
          <SummaryCard label="Evidence reports" value={String(metadata.report_count ?? 'N/A')} icon={Shield} />
        </div>

        {company.notes && (
          <div className="mt-4 rounded-lg border border-stone-200 bg-stone-50 p-3 text-[12px] text-stone-600">
            {company.notes}
          </div>
        )}
      </section>

      <section className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_320px]">
        <div className="relative min-h-[360px] overflow-hidden rounded-lg border border-stone-200 bg-gradient-to-br from-emerald-50 via-sky-50 to-stone-100 shadow-sm">
          <div
            className="absolute inset-0 opacity-50"
            style={{
              backgroundImage:
                'linear-gradient(to right, rgba(120,113,108,0.12) 1px, transparent 1px), linear-gradient(to bottom, rgba(120,113,108,0.12) 1px, transparent 1px)',
              backgroundSize: '34px 34px',
            }}
          />
          <svg className="absolute inset-0 h-full w-full" viewBox="0 0 800 420" preserveAspectRatio="none">
            <path d="M80 250 C170 120 280 150 365 215 C455 285 570 130 715 190" fill="none" stroke="rgba(14,116,144,0.35)" strokeWidth="24" />
            <path d="M120 95 L330 60 L430 155 L390 270 L180 245 Z" fill="rgba(16,185,129,0.12)" stroke="rgba(5,150,105,0.55)" strokeWidth="2" strokeDasharray="6 4" />
            <path d="M500 105 L720 120 L680 310 L485 280 Z" fill="rgba(245,158,11,0.12)" stroke="rgba(217,119,6,0.55)" strokeWidth="2" strokeDasharray="5 5" />
          </svg>
          <div className="absolute left-4 top-4 rounded-lg bg-white/95 px-3 py-2 shadow-sm ring-1 ring-stone-200">
            <div className="flex items-center gap-2 text-[12px] font-semibold text-stone-900">
              <Building2 className="size-4 text-emerald-700" />
              Company footprint
            </div>
            <div className="mt-1 text-[11px] text-stone-500">{company.region || 'Operating region unavailable'}</div>
          </div>
          {locations.map((location) => (
            <div
              key={`${location.label}-${location.type}`}
              className="absolute -translate-x-1/2 -translate-y-1/2 rounded-full bg-stone-900 p-1.5 text-white shadow-lg ring-2 ring-white"
              style={{ left: `${location.x}%`, top: `${location.y}%` }}
              title={`${location.label} · ${location.type}`}
            >
              {location.type === 'Asset' ? <Factory className="size-4" /> : <MapPin className="size-4" />}
            </div>
          ))}
          <div className="absolute bottom-4 left-4 flex flex-wrap gap-2 rounded-lg bg-white/95 p-2 text-[11px] text-stone-600 shadow-sm ring-1 ring-stone-200">
            {locations.map((location) => (
              <span key={location.label} className="flex items-center gap-1">
                <MapPin className="size-3 text-emerald-600" /> {location.label}
              </span>
            ))}
          </div>
        </div>

        <div className="rounded-lg border border-stone-200 bg-white p-4 shadow-sm">
          <div className="mb-3 flex items-center gap-2 text-[14px] font-semibold text-stone-950">
            Biodiversity indicators
            <InfoTip text="Company-level indicators are captured from the analysis at the time it is added to the watchlist." />
          </div>
          <div className="space-y-3">
            <IndicatorRow label="Spatial status" value={String(metadata.spatial_status || 'pending')} />
            <IndicatorRow label="News candidates" value={String(metadata.news_candidate_count ?? 'N/A')} />
            <IndicatorRow label="Reports reviewed" value={String(metadata.report_count ?? 'N/A')} />
            <IndicatorRow label="Confidence" value={metadata.confidence != null ? `${metadata.confidence}%` : 'N/A'} />
            <IndicatorRow label="State" value={String(metadata.state || 'N/A')} />
            <IndicatorRow label="Postcode" value={String(metadata.postcode || 'N/A')} />
          </div>
          <div className="mt-4 rounded-lg border border-stone-200 bg-stone-50 p-3">
            <div className="mb-1 flex items-center gap-2 text-[12px] font-semibold text-stone-900">
              <Bell className="size-4 text-amber-600" /> Alert rule
            </div>
            <div className="text-[12px] leading-relaxed text-stone-600">
              Alerts are enabled for major score changes, new biodiversity evidence, and spatial context updates for this company.
            </div>
          </div>
        </div>
      </section>
    </div>
  );
}

function EmptyWatchlist({ onAdd }: { onAdd: () => void }) {
  return (
    <div className="rounded-lg border border-dashed border-stone-300 bg-stone-50 p-6 text-center">
      <div className="mx-auto flex size-12 items-center justify-center rounded-lg bg-white text-stone-500 ring-1 ring-stone-200">
        <Building2 className="size-6" />
      </div>
      <div className="mt-3 text-[15px] font-semibold text-stone-950">No companies watched yet</div>
      <div className="mx-auto mt-1 max-w-sm text-[13px] leading-relaxed text-stone-600">
        Run or open a company analysis, then add that company from the Company Overview page.
      </div>
      <button
        onClick={onAdd}
        className="mt-4 inline-flex h-9 items-center gap-2 rounded-lg bg-emerald-700 px-3 text-[12px] text-white hover:bg-emerald-800"
      >
        <Building2 className="size-4" /> Go to Company Overview
      </button>
    </div>
  );
}

function SummaryCard({
  label,
  value,
  icon: Icon,
  className = '',
}: {
  label: string;
  value: string;
  icon: typeof Building2;
  className?: string;
}) {
  return (
    <div className="rounded-lg border border-stone-200 bg-white p-3">
      <div className="mb-1 flex items-center gap-1.5 text-[11px] text-stone-500">
        <Icon className="size-3.5 text-emerald-700" />
        {label}
      </div>
      <div className={`text-[20px] font-semibold text-stone-950 ${className}`}>{value}</div>
    </div>
  );
}

function IndicatorRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between gap-3 border-b border-stone-100 pb-2 text-[12px] last:border-0">
      <span className="text-stone-500">{label}</span>
      <span className="text-right font-medium text-stone-900">{value}</span>
    </div>
  );
}

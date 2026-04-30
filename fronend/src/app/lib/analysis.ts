export type BackendEvidenceRecord = {
  location?: string | null;
  activity_type?: string | null;
  biodiversity_signal?: string;
  evidence_type?: string;
  source_type?: string;
  source?: string;
  source_url?: string;
  source_date?: string | null;
  confidence?: number;
  llm_confidence?: number;
};

export type BackendCompanyAnalysis = {
  query_id?: string | null;
  database_error?: string | null;
  pipeline_steps?: string[];
  resolution?: {
    input_value?: string;
    alias_abn?: string | null;
    legal_name?: string;
    normalized_name?: string;
    abn?: string | null;
    state?: string | null;
    postcode?: string | null;
    abr?: {
      success?: boolean;
      message?: string;
    };
  };
  search_queries?: string[];
  uploaded_reports?: string[];
  analysed_reports?: string[];
  reports_deleted_after_analysis?: boolean;
  news?: {
    candidate_count?: number;
    evidence?: BackendEvidenceRecord[];
  };
  reports?: {
    evidence_count?: number;
    evidence?: BackendEvidenceRecord[];
  };
};

export type EvidenceCardData = {
  id: string;
  type: 'Report' | 'News' | 'Evidence';
  title: string;
  date: string;
  conf: number;
  source: string;
  location?: string | null;
  url?: string;
};

export type EvidenceMapSite = {
  id: string;
  name: string;
  state: string;
  level: 'Low' | 'Medium' | 'High' | 'Critical';
  x: number;
  y: number;
  type: string;
  km: number;
  evidenceTitle: string;
  confidence: number;
  sourceType: string;
};

export function loadCompanyAnalysis(): BackendCompanyAnalysis | null {
  if (typeof window === 'undefined') return null;

  try {
    const raw = window.localStorage.getItem('company_analysis');
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

export function companyDisplayName(analysis: BackendCompanyAnalysis | null): string {
  return (
    analysis?.resolution?.legal_name ||
    analysis?.resolution?.normalized_name ||
    analysis?.resolution?.input_value ||
    'BHP Group Limited'
  );
}

export function confidencePercent(record: BackendEvidenceRecord): number {
  const raw = record.confidence ?? record.llm_confidence ?? 0.5;
  return Math.round(raw <= 1 ? raw * 100 : raw);
}

export function analysisEvidenceCards(
  analysis: BackendCompanyAnalysis | null,
): EvidenceCardData[] {
  if (!analysis) return [];

  const records = [
    ...(analysis.reports?.evidence || []),
    ...(analysis.news?.evidence || []),
  ];

  return records.map((record, index) => {
    const isReport = record.source_type === 'report';
    return {
      id: `${record.source_type || 'evidence'}-${index}`,
      type: isReport ? 'Report' : record.source_type === 'news' ? 'News' : 'Evidence',
      title: record.biodiversity_signal || record.evidence_type || 'Biodiversity evidence',
      date: record.source_date || 'Latest analysis',
      conf: confidencePercent(record),
      source: record.source || (isReport ? 'Uploaded report' : 'News source'),
      location: record.location,
      url: record.source_url,
    };
  });
}

function locationToMapPosition(location: string): { x: number; y: number; state: string } {
  const normalized = location.toLowerCase();

  if (normalized.includes('pilbara')) return { x: 28, y: 38, state: 'WA' };
  if (normalized.includes('south australia') || normalized.includes(' sa')) return { x: 54, y: 64, state: 'SA' };
  if (normalized.includes('queensland') || normalized.includes(' qld')) return { x: 70, y: 48, state: 'QLD' };
  if (normalized.includes('western australia') || normalized.includes(' wa')) return { x: 30, y: 48, state: 'WA' };
  if (normalized.includes('victoria') || normalized.includes(' vic')) return { x: 62, y: 78, state: 'VIC' };
  if (normalized.includes('new south wales') || normalized.includes(' nsw')) return { x: 68, y: 70, state: 'NSW' };
  if (normalized.includes('tasmania') || normalized.includes(' tas')) return { x: 66, y: 90, state: 'TAS' };
  if (normalized.includes('northern territory') || normalized.includes(' nt')) return { x: 47, y: 38, state: 'NT' };

  return { x: 50, y: 58, state: 'AU' };
}

export function analysisMapSites(
  analysis: BackendCompanyAnalysis | null,
): EvidenceMapSite[] {
  if (!analysis) return [];

  const records = [
    ...(analysis.news?.evidence || []),
    ...(analysis.reports?.evidence || []),
  ].filter(record => record.location);

  const seen = new Set<string>();
  return records.flatMap((record, index) => {
    const location = record.location;
    if (!location) return [];

    const key = location.toLowerCase();
    if (seen.has(key)) return [];
    seen.add(key);

    const position = locationToMapPosition(location);
    const confidence = confidencePercent(record);
    const isRisk = (record.evidence_type || '').toLowerCase().includes('risk');
    const level: EvidenceMapSite['level'] = confidence >= 85 && isRisk ? 'Critical' : confidence >= 70 ? 'High' : confidence >= 50 ? 'Medium' : 'Low';

    return [{
      id: `backend-site-${index}`,
      name: location,
      state: position.state,
      level,
      x: position.x,
      y: position.y,
      type: record.activity_type || record.evidence_type || 'Evidence',
      km: Number((Math.max(0.8, (100 - confidence) / 18)).toFixed(1)),
      evidenceTitle: record.biodiversity_signal || 'Biodiversity evidence',
      confidence,
      sourceType: record.source_type || 'evidence',
    }];
  });
}

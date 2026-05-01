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

export type BackendNewsCandidate = {
  title?: string;
  snippet?: string;
  source?: string;
  published_date?: string | null;
  url?: string;
  source_type?: string;
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
    candidates?: BackendNewsCandidate[];
    evidence?: BackendEvidenceRecord[];
  };
  reports?: {
    evidence_count?: number;
    evidence?: BackendEvidenceRecord[];
  };
};

export type RiskLevel = 'Low' | 'Medium' | 'High' | 'Critical';

export type CompanyProfile = {
  name: string;
  abn: string;
  state: string;
  postcode: string;
  sector: string;
  score: number;
  riskLevel: RiskLevel;
  confidence: number;
  evidenceCount: number;
  newsCandidateCount: number;
  reportCount: number;
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

export function allEvidenceRecords(analysis: BackendCompanyAnalysis | null): BackendEvidenceRecord[] {
  if (!analysis) return [];
  return [
    ...(analysis.reports?.evidence || []),
    ...(analysis.news?.evidence || []),
  ];
}

export function riskLevelFromScore(score: number): RiskLevel {
  if (score >= 85) return 'Critical';
  if (score >= 70) return 'High';
  if (score >= 45) return 'Medium';
  return 'Low';
}

export function biodiversityScore(analysis: BackendCompanyAnalysis | null): number {
  if (!analysis) return 45;

  const records = allEvidenceRecords(analysis);
  const riskRecords = records.filter(record =>
    (record.evidence_type || '').toLowerCase().includes('risk')
  );
  const actionRecords = records.filter(record =>
    (record.evidence_type || '').toLowerCase().includes('action')
  );
  const newsCandidates = analysis.news?.candidates?.length || analysis.news?.candidate_count || 0;
  const reportSignals = analysis.reports?.evidence_count || 0;

  let score = 35;
  score += Math.min(25, riskRecords.length * 10);
  score += Math.min(15, Math.max(0, newsCandidates - records.length) * 3);
  score += Math.min(15, reportSignals * 5);
  score -= Math.min(15, actionRecords.length * 5);

  return Math.max(15, Math.min(95, Math.round(score)));
}

export function companySector(analysis: BackendCompanyAnalysis | null): string {
  const text = [
    analysis?.resolution?.legal_name,
    analysis?.resolution?.normalized_name,
    analysis?.resolution?.input_value,
    ...(allEvidenceRecords(analysis).map(record => record.activity_type || '')),
  ].join(' ').toLowerCase();

  if (/(bhp|rio|fortescue|mining|coal|iron ore|copper|nickel)/.test(text)) return 'Mining & Resources';
  if (/(coles|woolworths|aldi|retail|supermarket|grocery)/.test(text)) return 'Food Retail';
  if (/(bega|dairy|food|cheese|agriculture|farm)/.test(text)) return 'Food & Agriculture';
  if (/(energy|gas|oil|power)/.test(text)) return 'Energy';
  return 'Company';
}

export function companyProfileFromAnalysis(analysis: BackendCompanyAnalysis | null): CompanyProfile {
  const score = biodiversityScore(analysis);
  const evidenceCount = allEvidenceRecords(analysis).length;
  const newsCandidateCount = analysis?.news?.candidates?.length || analysis?.news?.candidate_count || 0;

  return {
    name: companyDisplayName(analysis),
    abn: analysis?.resolution?.abn || 'N/A',
    state: analysis?.resolution?.state || 'Australia',
    postcode: analysis?.resolution?.postcode || '',
    sector: companySector(analysis),
    score,
    riskLevel: riskLevelFromScore(score),
    confidence: evidenceCount ? Math.min(95, 70 + evidenceCount * 5) : analysis?.resolution?.abr?.success ? 70 : 45,
    evidenceCount,
    newsCandidateCount,
    reportCount: analysis?.analysed_reports?.length || 0,
  };
}

export function confidencePercent(record: BackendEvidenceRecord): number {
  const raw = record.confidence ?? record.llm_confidence ?? 0.5;
  return Math.round(raw <= 1 ? raw * 100 : raw);
}

export function analysisEvidenceCards(
  analysis: BackendCompanyAnalysis | null,
): EvidenceCardData[] {
  if (!analysis) return [];

  const records = allEvidenceRecords(analysis);

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

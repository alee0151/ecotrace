import {
  addCompanyToWatchlist,
  deleteCompanyFromWatchlist,
  getCompanyWatchlist,
  type AddCompanyWatchlistRequest,
  type CompanyWatchlistRecord,
} from '../../lib/api';
import {
  companyDisplayName,
  companyProfileFromAnalysis,
  type BackendCompanyAnalysis,
} from './analysis';

const LOCAL_WATCHLIST_PREFIX = 'seeco_company_watchlist_user_v2';

export function currentUserIdentity() {
  const userId = window.localStorage.getItem('seeco_user_id') || '';
  const email = window.localStorage.getItem('seeco_verified_email') || '';
  const fallbackKey = email || 'local-demo-user';
  return { userId, email, fallbackKey };
}

function localKey(fallbackKey: string) {
  return `${LOCAL_WATCHLIST_PREFIX}:${fallbackKey}`;
}

export function loadLocalCompanyWatchlist(fallbackKey: string): CompanyWatchlistRecord[] {
  try {
    const raw = window.localStorage.getItem(localKey(fallbackKey));
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
}

function saveLocalCompanyWatchlist(fallbackKey: string, records: CompanyWatchlistRecord[]) {
  window.localStorage.setItem(localKey(fallbackKey), JSON.stringify(records));
}

export function analysisToCompanyWatchlistPayload(
  analysis: BackendCompanyAnalysis,
): Omit<AddCompanyWatchlistRequest, 'user_id'> {
  const profile = companyProfileFromAnalysis(analysis);
  const resolution = analysis.resolution || {};
  const resolvedCompanyId =
    analysis.resolved_company_id ||
    (typeof resolution.company_id === 'string' ? resolution.company_id : null);

  return {
    company_id: resolvedCompanyId || null,
    query_id: analysis.query_id || null,
    company_name: companyDisplayName(analysis),
    abn: profile.abn === 'N/A' ? null : profile.abn,
    industry: profile.sector,
    region: profile.location,
    risk_score: profile.score,
    risk_level: profile.riskLevel,
    alerts_enabled: true,
    metadata: {
      source: 'company_overview',
      confidence: profile.confidence,
      state: profile.state,
      postcode: profile.postcode,
      spatial_status: analysis.spatial_analysis?.status,
      threatened_species_count: analysis.spatial_analysis?.threatened_species_count,
      news_candidate_count: profile.newsCandidateCount,
      report_count: profile.reportCount,
      analysis_snapshot: analysis,
    },
  };
}

export async function loadCompanyWatchlistForCurrentUser() {
  const identity = currentUserIdentity();
  if (identity.userId) {
    try {
      const response = await getCompanyWatchlist(identity.userId);
      return { records: response.companies, source: 'backend' as const };
    } catch {
      return {
        records: loadLocalCompanyWatchlist(identity.fallbackKey),
        source: 'local' as const,
      };
    }
  }

  return {
    records: loadLocalCompanyWatchlist(identity.fallbackKey),
    source: 'local' as const,
  };
}

export async function saveCompanyWatchlistForCurrentUser(
  payload: Omit<AddCompanyWatchlistRequest, 'user_id'>,
) {
  const identity = currentUserIdentity();
  if (identity.userId) {
    try {
      const response = await addCompanyToWatchlist({ ...payload, user_id: identity.userId });
      return { record: response.company, source: 'backend' as const };
    } catch {
      // Fall through to local persistence so a disconnected DB does not block demos.
    }
  }

  const records = loadLocalCompanyWatchlist(identity.fallbackKey);
  const existingIndex = records.findIndex((record) => {
    const sameCompanyId = payload.company_id && record.company_id === payload.company_id;
    const sameAbn = payload.abn && record.abn === payload.abn;
    const sameName = record.company_name.toLowerCase() === payload.company_name.toLowerCase();
    return Boolean(sameCompanyId || sameAbn || sameName);
  });
  const now = new Date().toISOString();
  const nextRecord: CompanyWatchlistRecord = {
    watchlist_id: existingIndex >= 0 ? records[existingIndex].watchlist_id : `local-${Date.now()}`,
    user_id: identity.userId || identity.fallbackKey,
    company_id: payload.company_id || null,
    query_id: payload.query_id || null,
    company_name: payload.company_name,
    abn: payload.abn || null,
    industry: payload.industry || null,
    region: payload.region || null,
    risk_score: payload.risk_score ?? null,
    risk_level: payload.risk_level || null,
    alerts_enabled: payload.alerts_enabled ?? true,
    notes: payload.notes || null,
    metadata_json: payload.metadata || {},
    created_at: existingIndex >= 0 ? records[existingIndex].created_at : now,
    updated_at: now,
  };

  const nextRecords = existingIndex >= 0
    ? records.map((record, index) => index === existingIndex ? nextRecord : record)
    : [nextRecord, ...records];
  saveLocalCompanyWatchlist(identity.fallbackKey, nextRecords);
  return { record: nextRecord, source: 'local' as const };
}

export async function removeCompanyWatchlistForCurrentUser(watchlistId: string) {
  const identity = currentUserIdentity();
  if (identity.userId && !watchlistId.startsWith('local-')) {
    try {
      await deleteCompanyFromWatchlist(identity.userId, watchlistId);
      return { source: 'backend' as const };
    } catch {
      // Also remove locally if the backend is unavailable.
    }
  }

  const records = loadLocalCompanyWatchlist(identity.fallbackKey);
  saveLocalCompanyWatchlist(
    identity.fallbackKey,
    records.filter((record) => record.watchlist_id !== watchlistId),
  );
  return { source: 'local' as const };
}

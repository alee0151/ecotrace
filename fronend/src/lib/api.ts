/**
 * api.ts — Centralised EcoTrace API client
 *
 * All fetch calls to the FastAPI backend go through this file.
 * During development the Vite proxy rewrites /api/* → http://127.0.0.1:8000/api/*
 * so no CORS issues and no hard-coded host in component code.
 *
 * In production set VITE_API_BASE_URL to your deployed backend URL.
 */

const BASE = import.meta.env.VITE_API_BASE_URL ?? '';

// ─── helpers ────────────────────────────────────────────────────────────────

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { Accept: 'application/json' },
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error((body as { detail?: string }).detail ?? `GET ${path} failed (${res.status})`);
  }
  return res.json() as Promise<T>;
}

async function post<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const errBody = await res.json().catch(() => ({}));
    throw new Error((errBody as { detail?: string }).detail ?? `POST ${path} failed (${res.status})`);
  }
  return res.json() as Promise<T>;
}

async function postForm<T>(path: string, form: FormData): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: 'POST',
    body: form,
  });
  if (!res.ok) {
    const errBody = await res.json().catch(() => ({}));
    throw new Error((errBody as { detail?: string }).detail ?? `POST ${path} failed (${res.status})`);
  }
  return res.json() as Promise<T>;
}

export function apiUrl(path: string): string {
  return `${BASE}${path}`;
}

export interface IucnCacheStatus {
  state: 'empty' | 'loading' | 'ready' | 'failed';
  count: number;
  started_at?: string | null;
  finished_at?: string | null;
  error?: string | null;
  source?: string | null;
  cache_file?: string;
}

export const warmIucnCache = () => get<IucnCacheStatus>('/api/spatial/iucn-cache?warm=true');

export interface RequestVerificationResponse {
  status: 'sent';
  email: string;
  delivery: 'smtp' | 'outbox';
  path?: string;
  verification?: {
    verification_id: string;
    requested_at: string;
    expires_at: string;
  };
}

export interface ConfirmVerificationResponse {
  status: 'verified';
  verification: {
    verification_id: string;
    user_id: string;
    email: string;
    return_to: string;
    verified_at: string;
  };
}

export const requestEmailVerification = (email: string, returnTo: string) =>
  post<RequestVerificationResponse>('/api/auth/request-verification', {
    email,
    return_to: returnTo,
  });

export const confirmEmailVerification = (token: string) =>
  post<ConfirmVerificationResponse>('/api/auth/confirm-verification', { token });

// ─── shared types ────────────────────────────────────────────────────────────

export interface SearchRequest {
  user_id?: string;
  barcode?: string;
  brand?: string;
  company_or_abn?: string;
}

export interface SearchResponse {
  query_id: string;
  status: string;
  input_type: 'barcode' | 'brand' | 'company_or_abn';
  input_value: string;
  resolution_status: 'pending' | 'resolved' | 'failed';
  resolved_ids?: {
    company_id?: string | null;
    brand_id?: string | null;
    product_id?: string | null;
  };
  pipeline_steps: string[];
  result: SearchResult;
}

export interface SearchResult {
  input_type: string;
  input_value: string;
  status: string;
  source: string;
  confidence: number;
  // company flow
  company?: {
    legal_name?: string;
    abn?: string;
    state?: string;
    postcode?: string;
    abn_status?: string;
    gst_registered?: boolean;
  };
  // brand / barcode flows
  brand?: { brand_name?: string };
  brand_raw?: string;
  brand_clean?: string;
  brand_owner?: string;
  product?: {
    product_name?: string;
    image_url?: string;
    categories?: string;
    barcode?: string;
  };
  manufacturer?: string;
  trademark?: Record<string, unknown>;
  legal_owner?: string;
  abn_verification?: {
    legal_name?: string;
    abn?: string;
    state?: string;
    postcode?: string;
    abn_status?: string;
    success?: boolean;
  };
  // scoring (added by future report layer)
  risk_score?: number;
  biodiversity_score?: number;
  score?: number;
  risk_factors?: Array<{ color?: string; text?: string; description?: string }>;
  alternatives?: Array<{
    brand?: string;
    brand_name?: string;
    score?: number;
    biodiversity_score?: number;
    risk_level?: string;
    level?: string;
    note?: string;
    description?: string;
  }>;
  better_choices?: SearchResult['alternatives'];
  message?: string;
}

export interface AbnResult {
  success: boolean;
  source: string;
  abn?: string;
  legal_name?: string;
  state?: string;
  postcode?: string;
  abn_status?: string;
  gst_registered?: boolean;
  verified?: boolean;
  message?: string;
}

export interface SearchQueryRecord {
  query_id: string;
  user_id?: string;
  input_type: string;
  input_value: string;
  resolution_status: string;
  resolved_company_id?: string;
  resolved_brand_id?: string;
  resolved_product_id?: string;
  submitted_at: string;
}

export interface UploadResponse {
  message: string;
  filename?: string;
}

export interface CompanyAnalysisResolveResponse {
  status: string;
  query_id?: string | null;
  resolved_company_id?: string | null;
  database_error?: string | null;
  pipeline_steps?: string[];
  resolution?: Record<string, unknown>;
}

export interface CompanyAnalysisResponse extends CompanyAnalysisResolveResponse {
  uploaded_reports?: string[];
  analysed_reports?: string[];
  reports_deleted_after_analysis?: boolean;
  search_queries?: string[];
  news?: Record<string, unknown>;
  reports?: Record<string, unknown>;
}

export interface SpatialSpeciesRecord {
  scientific_name: string;
  common_name?: string | null;
  taxon_rank?: string | null;
  record_count: number;
  iucn_category?: string | null;
  iucn_category_name?: string | null;
  threat_weight: number;
  iucn_url?: string | null;
}

export interface SpatialLayerAResponse {
  status: 'success' | 'loading' | 'failed';
  generated_at?: string;
  started_at?: string;
  error?: string;
  query_id?: string;
  query?: {
    query_id: string;
    input_type: string;
    input_value: string;
    resolution_status: string;
  };
  company?: {
    company_id: string;
    legal_name?: string | null;
    abn?: string | null;
    entity_type?: string | null;
    company_status?: string | null;
    state?: string | null;
    postcode?: string | null;
    gst_registered?: boolean | null;
  };
  inferred_location?: {
    label: string;
    address_raw?: string | null;
    state?: string | null;
    postcode?: string | null;
    country: string;
    lat: number;
    lon: number;
    radius_km: number;
    confidence: string;
    method: string;
    source: string;
    location_id?: string | null;
  };
  location?: {
    lat: number;
    lon: number;
    radius_km: number;
  } | {
    label: string;
    lat: number;
    lon: number;
    radius_km: number;
    confidence: string;
    method: string;
    source: string;
    state?: string | null;
    postcode?: string | null;
    country?: string;
  };
  data_sources?: string[];
  total_ala_records?: number;
  unique_species_count?: number;
  iucn_assessed_species?: number;
  threatened_species_count?: number;
  species_threat_score?: number;
  score_breakdown?: Record<string, number>;
  threatened_species?: SpatialSpeciesRecord[];
  all_species?: SpatialSpeciesRecord[];
}

export interface SpatialLayerAParams {
  lat: number;
  lon: number;
  radius_km?: number;
  max_species?: number;
}

export interface QueryReportResponse {
  status: string;
  report: Record<string, unknown>;
}

export interface GenerateReportResponse {
  status: string;
  report_id: string;
  report: {
    report_id: string;
    query_id: string;
    title: string;
    format: string;
    status: string;
    generated_at: string;
    metadata_json?: Record<string, unknown>;
  };
}

export interface SendReportEmailResponse {
  status: string;
  report_id?: string;
  report_title?: string;
  delivery: 'smtp' | 'outbox';
  to: string;
  path?: string;
  sent_at?: string;
}

// ─── API surface ─────────────────────────────────────────────────────────────

/**
 * POST /api/search
 * Main consumer search — submit barcode, brand, or company/ABN.
 */
export const search = (body: SearchRequest) =>
  post<SearchResponse>('/api/search', body);

export const resolveCompanyForAnalysis = (form: FormData) =>
  postForm<any>('/api/analyse/company/resolve', form);

export const analyseCompanyWithReports = (form: FormData) =>
  postForm<any>('/api/analyse/company', form);

/**
 * GET /api/abn/verify/:abn
 * Direct ABN verification via ABR.
 */
export const verifyAbn = (abn: string) =>
  get<AbnResult>(`/api/abn/verify/${encodeURIComponent(abn)}`);

/**
 * GET /api/company/search/:name
 * Search company name via ABR.
 */
export const searchCompany = (name: string) =>
  get<AbnResult>(`/api/company/search/${encodeURIComponent(name)}`);

/**
 * GET /api/barcode/:barcode
 * Direct barcode lookup via OpenFoodFacts.
 */
export const lookupBarcode = (barcode: string) =>
  get<Record<string, unknown>>(`/api/barcode/${encodeURIComponent(barcode)}`);

/**
 * GET /api/trademark/search/:brand
 * Search IP Australia trademark registry.
 */
export const searchTrademark = (brand: string) =>
  get<Record<string, unknown>>(`/api/trademark/search/${encodeURIComponent(brand)}`);

/**
 * GET /api/trademark/token-test
 * Test that the IP Australia OAuth token can be obtained.
 */
export const testTrademarkToken = () =>
  get<{ status: string; token_preview?: string }>('/api/trademark/token-test');

/**
 * GET /api/search/query/:query_id
 * Retrieve a stored search_query record.
 */
export const getSearchQuery = (queryId: string) =>
  get<{ query: SearchQueryRecord }>(`/api/search/query/${encodeURIComponent(queryId)}`);

/**
 * GET /api/search/history/:user_id
 * Retrieve search history for a user.
 */
export const getSearchHistory = (userId: string) =>
  get<{ user_id: string; history: SearchQueryRecord[] }>(
    `/api/search/history/${encodeURIComponent(userId)}`
  );

/**
 * POST /api/upload
 * Upload a PDF document (CSR report, product manual).
 */
export const uploadDocument = (file: File) => {
  const form = new FormData();
  form.append('file', file);
  return postForm<UploadResponse>('/api/upload', form);
};

/**
 * GET /api/spatial/layer-a
 * Species occurrence and IUCN threat scoring for a site location.
 */
export const getSpatialLayerA = ({
  lat,
  lon,
  radius_km = 10,
  max_species = 50,
}: SpatialLayerAParams) => {
  const params = new URLSearchParams({
    lat: String(lat),
    lon: String(lon),
    radius_km: String(radius_km),
    max_species: String(max_species),
  });
  return get<SpatialLayerAResponse>(`/api/spatial/layer-a?${params.toString()}`);
};

/**
 * GET /api/spatial/query/:query_id
 * Layer A spatial analysis inferred from the company attached to a search query.
 */
export const getSpatialAnalysisForQuery = (queryId: string, force = false) =>
  get<SpatialLayerAResponse>(
    `/api/spatial/query/${encodeURIComponent(queryId)}${force ? '?force=true' : ''}`
  );

export const getQueryReport = (queryId: string) =>
  get<QueryReportResponse>(`/api/report/query/${encodeURIComponent(queryId)}`);

export const generateReport = (queryId: string, analysisPayload?: unknown) =>
  post<GenerateReportResponse>('/api/report/generate', {
    query_id: queryId,
    analysis_payload: analysisPayload,
  });

export const getReport = (reportId: string) =>
  get<QueryReportResponse>(`/api/report/${encodeURIComponent(reportId)}`);

export const reportHtmlUrl = (reportId: string, print = false) =>
  apiUrl(`/api/report/${encodeURIComponent(reportId)}/html${print ? '?print=1' : ''}`);

export const queryReportHtmlUrl = (queryId: string) =>
  apiUrl(`/api/report/query/${encodeURIComponent(queryId)}/html`);

export const sendPersistedReportEmail = (reportId: string, email: string) =>
  post<SendReportEmailResponse>(`/api/report/${encodeURIComponent(reportId)}/email`, { email });

export const sendReportEmail = (queryId: string, email: string) =>
  post<SendReportEmailResponse>('/api/report/email', { query_id: queryId, email });

/**
 * GET /health
 * Backend liveness check.
 */
export const healthCheck = () =>
  get<{ status: string }>('/health');

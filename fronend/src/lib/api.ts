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

// ─── API surface ─────────────────────────────────────────────────────────────

/**
 * POST /api/search
 * Main consumer search — submit barcode, brand, or company/ABN.
 */
export const search = (body: SearchRequest) =>
  post<SearchResponse>('/api/search', body);

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
 * GET /health
 * Backend liveness check.
 */
export const healthCheck = () =>
  get<{ status: string }>('/health');

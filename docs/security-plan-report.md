# Seeco Security Plan Report

Prepared: 2026-05-05  
Application: Seeco biodiversity and supply-chain risk analysis platform  
Repository assessed: `/Users/alanleemon/Documents/Seeco/seeco`

## 1. Executive Summary

Seeco is a React/Vite frontend and FastAPI/PostgreSQL backend that lets users search products, brands, companies, and ABNs, upload company reports, generate biodiversity risk reports, run spatial species-risk analysis, and receive email verification/report links.

This security plan follows the supplied Security Plan Report Guidelines. It is written as a live project document, focused on risks visible in this repository rather than generic controls.

The main security priorities for Seeco are:

1. Enforce backend authorization for report, search history, spatial, and analysis endpoints instead of relying on frontend email gating only.
2. Add rate limiting and abuse controls to email verification, public search, LLM/news analysis, upload, and spatial-analysis endpoints.
3. Harden uploaded report handling with file-signature validation, malware scanning, safe storage, retention rules, and stronger MIME checks.
4. Disable or protect debug/test endpoints in production.
5. Reduce information disclosure in API errors and deployment/runtime logs.
6. Formalize privacy handling for emails, uploaded reports, generated reports, ABNs, inferred locations, and LLM/news evidence.

## 2. System Overview

### Main Components

| Component | Repo evidence | Security relevance |
|---|---|---|
| Frontend app | `fronend/src/app`, `fronend/src/lib/api.ts` | Stores query/report IDs and verified email flags in `localStorage`; calls backend APIs directly. |
| Backend API | `backend/main.py` | Public FastAPI endpoints for search, email verification, report generation, report retrieval, spatial analysis, and diagnostics. |
| Database | `backend/schema.sql`, `backend/db_writer.py` | Stores users, email verification token hashes, search queries, companies, ABNs, products, inferred locations, news articles, and reports. |
| Upload/report pipeline | `backend/upload_endpoint.py`, `backend/analysis_pipeline.py`, `backend/report_service.py` | Accepts PDFs and report-like files; sends report excerpts/news evidence to LLM providers; persists generated HTML reports. |
| External services | ABR, IP Australia, OpenFoodFacts, news APIs, OpenRouter/NVIDIA, ALA/IUCN | API keys/secrets are held in environment variables; availability and data quality affect system behavior. |
| Deployment | `AZURE_DEPLOYMENT.md`, `startup.sh`, `app.json` | Azure App Service + PostgreSQL deployment; CORS and secrets are configured through app settings. |

### Assets To Protect

| Asset | Confidentiality | Integrity | Availability |
|---|---:|---:|---:|
| User email addresses | High | Medium | Medium |
| Email verification tokens | High | High | Medium |
| Uploaded company reports | High | High | Medium |
| Generated risk reports and metadata | High | High | Medium |
| Search history and query IDs | Medium | Medium | Medium |
| Company/ABN/trademark/product records | Low/Medium | High | High |
| API credentials and DB password | Critical | Critical | High |
| Spatial analysis cache/results | Medium | Medium | Medium |

## 3. Current Security Controls Observed

| Area | Existing control |
|---|---|
| Database queries | Most backend SQL uses psycopg2 parameter binding, reducing SQL injection risk. |
| Database transport | `DB_SSLMODE` defaults to `require`. |
| CORS | Allowed origins are configurable through `CORS_ALLOW_ORIGINS`; production guidance lists exact frontend origins. |
| Email verification | Uses random URL-safe tokens, stores SHA-256 token hashes, and expires links after 30 minutes. |
| Return URL validation | Email verification return paths must start with `/app/` and cannot point to `/app/verify-email`, reducing open redirect risk. |
| File upload size | Upload endpoints enforce `MAX_UPLOAD_MB` / `MAX_REPORT_UPLOAD_MB`. |
| File names | Upload paths strip path components; analysis uploads sanitize filenames. |
| HTML report rendering | Generated report HTML escapes dynamic values before insertion. |
| Secrets | `.gitignore` excludes `.env`, `backend/.env`, publish settings, logs, and outbox files. |
| Frontend static serving | `fronend/server.js` validates resolved asset path stays inside `dist` and sets `X-Content-Type-Options: nosniff`. |

## 4. System Security Awareness

### Authentication And Authorization

Seeco currently uses an email magic-link style gate for frontend pages. The backend verifies tokens, but the frontend stores `seeco_email_verified=true` in `localStorage`, and backend data/report APIs do not currently require an authenticated session, bearer token, or verified user binding.

Policy:

| Policy item | Seeco requirement |
|---|---|
| Password policy | No password login is currently implemented. If passwords are added later, require passphrases of at least 12 characters, deny known breached passwords, hash with Argon2id or bcrypt, and provide secure password reset. |
| Magic-link token management | Keep single-use, random tokens; store hashes only; expire within 30 minutes; invalidate older outstanding tokens after a new request; log verification events without logging raw tokens. |
| Session management | Replace local-only verification state with a signed, HttpOnly, Secure, SameSite cookie or short-lived access token after `/api/auth/confirm-verification`. |
| Authorization | Bind generated reports, search history, watchlists, and analysis jobs to a verified user ID and check ownership on every backend request. |
| Least privilege | Database user should have only required application privileges, not superuser/admin privileges. |

### Threat Prevention

| Threat | Relevant Seeco surface | Required prevention |
|---|---|---|
| Automated abuse | `/api/auth/request-verification`, `/api/search`, `/api/analyse/company`, `/api/spatial/layer-a` | Per-IP and per-email rate limiting; request quotas; CAPTCHA or turnstile on email/search forms if abused. |
| File-based attacks | `/api/upload`, `/api/analyse/company` | File signature validation, malware scan, quarantine, safe temporary storage, deletion after analysis, and strict extension/content rules. |
| ID guessing/IDOR | `/api/report/{report_id}`, `/api/report/query/{query_id}`, `/api/search/history/{user_id}` | Enforce ownership and signed session checks; avoid exposing user IDs in URLs where possible. |
| Secret leakage | Debug endpoints, logs, env vars, CI/CD | Disable debug routes in production; redact API errors; keep secrets in Azure/GitHub secret stores only. |
| Third-party dependency risk | Python/Node packages | Pin versions, run dependency scans, enable Dependabot/Renovate, and review critical advisories before release. |

### Open Ports And Services

Expected production exposure:

| Service | Port | Exposure policy |
|---|---:|---|
| Frontend Azure App Service | 443 | Public. Redirect HTTP to HTTPS. |
| Backend Azure App Service | 443 | Public only for documented API. Restrict admin/diagnostic routes. |
| PostgreSQL | 5432 | Not public. Restrict to backend service/private network/firewall allowlist; require TLS. |
| Local development Vite | 5173 | Local/dev only. |
| Local backend | 8000 or platform `$PORT` | Local/dev or App Service only. |

Unwanted ports and services must be closed. No database management UI, debug server, or local-only diagnostics should be exposed publicly.

## 5. Ethical, Legal, Security, And Privacy Issues

Seeco processes a mix of public business data and user-supplied data. Although ABN/company/trademark data may be public, user emails, uploaded reports, generated analyses, inferred locations, and report-email recipients require privacy controls.

### Data Types And Handling Rules

| Data type | Source | Privacy/security treatment |
|---|---|---|
| Email addresses | Verification and report email forms | Treat as personal information. Store only when necessary. Do not expose search history by user ID without session ownership checks. |
| Uploaded reports | User upload | Treat as confidential. Store temporarily; delete after analysis unless user explicitly saves. Do not reuse one user’s uploaded reports for another user’s analysis. |
| Generated reports | Backend report table | Treat as confidential derived data. Require owner authorization before view/email/download. |
| ABN/company data | ABR/IP Australia/OpenFoodFacts | Public or semi-public, but integrity matters. Store source, timestamp, and confidence. |
| News/LLM evidence | News APIs and LLM provider | Disclose limitations. Keep evidence provenance. Avoid presenting scores as regulatory determinations. |
| Inferred spatial locations | ABN/report/news evidence | May be commercially sensitive. Show confidence and source; require authorization for user-generated reports. |

### Privacy Requirements

1. Publish a privacy notice explaining what data Seeco collects, why it is collected, which third-party APIs/LLM providers receive report/news excerpts, retention periods, and user contact/removal rights.
2. Obtain explicit user consent before sending uploaded report content or excerpts to LLM providers.
3. Retain uploaded reports only for the analysis window unless the user opts in to storage.
4. Provide deletion workflow for user email, search history, generated reports, and uploaded report artifacts.
5. Do not store raw email verification tokens.
6. Avoid including raw secrets, tokens, report content, or personal data in logs.

## 6. Risk Analysis

| ID | Risk description | Likelihood | Impact | Rating | Repo-specific evidence | Mitigation plan |
|---:|---|---|---|---|---|---|
| 1 | Backend authorization bypass / insecure direct object reference | High | High | Critical | Report/search/spatial endpoints retrieve by `query_id`, `report_id`, or `user_id` with no session ownership check. Frontend gate is localStorage based. | Implement signed sessions after email verification; store `user_id` on searches/reports; enforce ownership in all report/history/watchlist endpoints. |
| 2 | Automated abuse of public APIs and email verification | High | High | Critical | No rate limiting observed on `/api/auth/request-verification`, `/api/search`, `/api/analyse/company`, or spatial endpoints. | Add API rate limiting by IP/email/user; throttle expensive LLM/news/spatial calls; add CAPTCHA/turnstile if public abuse appears. |
| 3 | File upload malware or content spoofing | Medium | High | High | Uploads rely on content-type/extension and size. `application/octet-stream` is allowed for PDFs in `/api/upload`; analysis accepts text/HTML/CSV/JSON. | Validate magic bytes; scan with malware service; store outside web root; quarantine; limit total files and cumulative size; strip active HTML; delete temp files reliably. |
| 4 | Debug/test endpoint exposure | Medium | High | High | `/api/debug/trademark-auth`, `/api/trademark/token-test`, `/api/users/test`, direct lookup test routes are public. | Gate with `ENABLE_DEBUG_ENDPOINTS=false` default in production, admin auth, or remove from production build. |
| 5 | Sensitive report data accessible through predictable leaked UUID links | Medium | High | High | `/api/report/{report_id}/html` and `/api/report/query/{query_id}/html` return report HTML without auth. UUIDs are hard to guess but can leak through localStorage, browser history, email, referrers, or logs. | Require authenticated ownership; use short-lived signed share links for email recipients; set `Referrer-Policy: no-referrer` or `strict-origin-when-cross-origin`. |
| 6 | Information disclosure through raw exception messages | Medium | Medium | Medium | Several handlers return `HTTPException(..., detail=str(e))`; pipeline errors may expose internal details. | Return generic client errors; log detailed errors server-side with redaction; add structured error IDs. |
| 7 | CORS misconfiguration | Medium | Medium | Medium | CORS is env-driven; `allow_methods=["*"]`, `allow_headers=["*"]`; if `*` is configured, broader browser access is allowed. | Production CORS must list exact HTTPS origins only. Keep credentials off unless cookie auth is used with explicit origins. |
| 8 | LLM/data exfiltration and prompt-injection risk from uploaded reports/news | Medium | High | High | Uploaded report excerpts and news text can be sent to LLM providers for extraction. | Consent notice; redact sensitive content where possible; prompt-injection guardrails; restrict model outputs to schema; keep provenance; avoid tool execution based on LLM text. |
| 9 | Denial of service through expensive spatial/news/LLM calls | Medium | High | High | Spatial Layer A can query external biodiversity APIs; analysis loops through multiple news providers and LLM calls. | Queue background jobs; cache results; enforce quotas; cap request parameters; add timeout/retry budgets and circuit breakers. |
| 10 | LocalStorage tampering and data exposure | Medium | Medium | Medium | Frontend stores verification flags, query IDs, company IDs, report IDs, and analysis payloads in localStorage. | Treat localStorage as convenience cache only; never as authorization; minimize stored sensitive data; clear on logout; move auth to HttpOnly cookies. |
| 11 | Dependency vulnerabilities | Medium | Medium | Medium | Node and Python dependencies exist; no lock/scanning policy documented for backend. | Pin backend dependencies with hashes or lock file; run `npm audit`, `pip-audit`, and GitHub Dependabot. |
| 12 | Weak email abuse controls | Medium | Medium | Medium | Verification and report email endpoints accept arbitrary email addresses. | Per-email/IP throttles; domain validation policies if needed; bounce monitoring; require verified session before sending reports. |
| 13 | Database over-privilege or network exposure | Low/Medium | High | High | `DB_USER` examples use `postgres`; Azure PostgreSQL is referenced. | Use a dedicated least-privilege app user; private networking/firewall; rotation policy; backups and point-in-time recovery. |
| 14 | Report HTML risks | Low | Medium | Low/Medium | `render_report_html` escapes dynamic content; this is a good control. Future changes could reintroduce XSS. | Maintain escaping tests; avoid raw HTML insertion from LLM/news/report content. |
| 15 | Open ports/services | Low | Medium | Low | Only app services and PostgreSQL are expected. | Keep only 443 public; restrict PostgreSQL; close dev ports; disable FTP/basic publishing where possible after CI/CD setup. |

## 7. Documented Widespread Security Attacks Applicable To Seeco

| Attack | How it applies | Current posture | Required control |
|---|---|---|---|
| Broken access control | Users may access reports/history/spatial results by IDs without backend ownership checks. | High concern. | Backend authorization checks on every data endpoint. |
| Injection | Search inputs flow into SQL and external APIs. SQL uses parameters in reviewed code. | SQL risk reduced; external API query abuse remains. | Continue parameterized SQL; validate lengths/characters; rate-limit. |
| Cross-site scripting | Generated HTML reports include external data and LLM-extracted text. | Values are escaped in current renderer. | Regression tests for escaping; strict CSP headers. |
| Cross-site request forgery | If future cookie auth is added, state-changing POST endpoints need CSRF protection. | Not applicable yet because no cookie auth. | Use SameSite cookies plus CSRF tokens for unsafe methods. |
| File upload attacks | Reports may contain malformed PDFs/HTML or disguised content. | Size/type controls exist, but content validation/scanning is incomplete. | Magic-byte checks, malware scan, sanitization, temp storage. |
| Brute force / credential stuffing | Password login is not implemented. Magic links can still be spammed. | Brute force prohibited by guidelines; token entropy is strong. | Rate-limit verification requests and confirmation attempts. |
| Denial of service | LLM/news/spatial endpoints are computational and network expensive. | Public endpoints can trigger costly work. | Quotas, caching, queues, timeouts. |
| Sensitive data exposure | Reports, uploaded content, emails, tokens, API keys. | Secrets templates are safe; endpoint authorization needs work. | Auth, redaction, TLS, secret rotation, retention policy. |

## 8. Vulnerability Assessment And Pen Test Findings

The guideline prohibits brute-force attacks. This assessment is therefore non-invasive and based on source inspection plus safe test cases that can be executed in a local/staging environment.

### Findings

| Finding | Attack simulated / observed | Affected routes/files | Result | Severity |
|---|---|---|---|---|
| F1: Frontend-only verification gate | Modify `localStorage.seeco_email_verified` or call backend APIs directly. | `fronend/src/app/Root.tsx`, `backend/main.py` report/search/spatial routes | Protected pages are gated in the browser only; backend does not require verified session. | Critical |
| F2: Report access by ID without owner check | Request `/api/report/{report_id}` or `/api/report/{report_id}/html` with a known report ID. | `backend/main.py`, `backend/report_service.py` | Any holder of the ID can retrieve report content. | High |
| F3: Search history by user ID without owner check | Request `/api/search/history/{user_id}` with a known UUID. | `backend/main.py` | Any holder of a user ID can retrieve that user’s search history. | High |
| F4: Debug/token diagnostic endpoints exposed | Call `/api/debug/trademark-auth` or `/api/trademark/token-test`. | `backend/main.py`, `backend/brand_pipeline.py` | Public diagnostics disclose credential configuration state and token preview. | High |
| F5: Email verification endpoint lacks anti-automation | Repeatedly request verification links for the same or different email addresses. | `backend/main.py`, `backend/report_service.py` | No per-email/IP throttling is implemented in code. | High |
| F6: Upload validation can be bypassed by content spoofing | Submit non-PDF content with `application/octet-stream` to `/api/upload`, or active HTML to analysis endpoint. | `backend/upload_endpoint.py`, `backend/analysis_pipeline.py` | Type validation is content-type/extension based, not file-signature/malware based. | High |
| F7: Raw backend error disclosure | Trigger unexpected backend/database errors. | Multiple `HTTPException(detail=str(e))` handlers | Internal errors may leak service/database details. | Medium |
| F8: Expensive unauthenticated analysis calls | Submit repeated `/api/analyse/company` or spatial calls. | `backend/main.py`, `backend/analysis_pipeline.py` | No quota/queue/rate-limit layer is visible. | High |

### Safe Pen Test Commands For Staging

Use these only against local or approved staging systems. Do not perform brute-force testing.

```bash
# Health and public route exposure
curl -i http://127.0.0.1:8000/health
curl -i http://127.0.0.1:8000/api/debug/trademark-auth
curl -i http://127.0.0.1:8000/api/trademark/token-test

# Validation tests
curl -i -X POST http://127.0.0.1:8000/api/search \
  -H 'Content-Type: application/json' \
  -d '{"barcode":"abc","brand":"","company_or_abn":""}'

# Upload type spoof test using a harmless text file in staging
curl -i -X POST http://127.0.0.1:8000/api/upload \
  -F 'file=@harmless.txt;type=application/octet-stream'
```

Expected secure result after mitigations:

| Test | Expected secure behavior |
|---|---|
| Debug routes in production | `404` or `403`. |
| Invalid search input | `400` with generic validation message. |
| Spoofed upload | `415` or `400` after file-signature validation. |
| Report/history access without session | `401`. |
| Report/history access for wrong user | `403`. |
| Excessive email/search/analysis requests | `429`. |

## 9. Impact Assessment

| Vulnerability | Confidentiality impact | Integrity impact | Availability impact | Overall impact |
|---|---|---|---|---|
| Backend authorization bypass | High: report/history data can be exposed by leaked IDs. | Medium: unauthorized report email sending may alter delivery status. | Low | High |
| No rate limiting | Medium: email enumeration/spam. | Medium: automated data pollution. | High: LLM/news/spatial costs and API exhaustion. | High |
| Weak upload validation | High: confidential/malicious files may enter pipeline. | High: spoofed data can poison evidence. | Medium/High: parser/malware DoS. | High |
| Debug route exposure | Medium: environment/config state exposed. | Low | Medium: attackers can probe dependencies. | Medium/High |
| Raw error disclosure | Medium: internal host/db/API details may leak. | Low | Low | Medium |
| LLM prompt/data risks | High: uploaded report excerpts leave system boundary. | Medium: malicious documents may manipulate extraction. | Low/Medium | High |

## 10. Recommendations

| Priority | Recommendation | Implementation owner | Target iteration |
|---|---|---|---|
| P0 | Add backend session authentication after email verification using HttpOnly, Secure, SameSite cookies or signed bearer tokens. | Backend | Next build |
| P0 | Enforce ownership checks for `/api/report/*`, `/api/report/query/*`, `/api/search/history/*`, generated reports, watchlists, and saved analyses. | Backend | Next build |
| P0 | Disable `/api/debug/trademark-auth`, `/api/trademark/token-test`, and `/api/users/test` unless `ENABLE_DEBUG_ENDPOINTS=true` and admin auth is present. | Backend/DevOps | Next build |
| P0 | Add rate limiting to email verification, report email, search, analysis, upload, and spatial endpoints. | Backend/DevOps | Next build |
| P1 | Harden upload validation with magic-byte checks, malware scan, cumulative upload limits, safe temporary directory, and guaranteed deletion. | Backend | Next build |
| P1 | Add privacy consent before report upload/LLM processing, with retention disclosure and delete option. | Frontend/Backend | Next build |
| P1 | Replace raw `str(e)` API responses with generic messages and structured server logs. | Backend | Next build |
| P1 | Add security headers: CSP, `Referrer-Policy`, `Permissions-Policy`, `Strict-Transport-Security`, and `X-Frame-Options`/`frame-ancestors`. | Frontend/Backend/DevOps | Next build |
| P1 | Use least-privilege PostgreSQL app user, private networking/firewall, backup/PITR, and secret rotation schedule. | DevOps | Next build |
| P2 | Add dependency scanning: `npm audit`, `pip-audit`, Dependabot/Renovate, and pinned backend lock file. | DevOps | Iteration +1 |
| P2 | Add audit logging for verification, report access, report email, uploads, and admin/debug access. | Backend | Iteration +1 |
| P2 | Add queue/caching for expensive LLM/news/spatial jobs with per-user quotas and timeout budgets. | Backend | Iteration +1 |
| P2 | Add tests for XSS escaping in generated reports and unsafe uploaded HTML/content handling. | Backend | Iteration +1 |

## 11. Secure Operation Policies

### Environment And Secrets

1. Store production secrets only in Azure App Service settings or GitHub Actions secrets.
2. Rotate `DB_PASSWORD`, `RESEND_API_KEY`, `ABR_GUID`, `IP_AUSTRALIA_CLIENT_SECRET`, and LLM/news API keys at least once per semester or after suspected exposure.
3. Never commit `.env`, publish profiles, API responses containing tokens, backend outbox emails, or uploaded reports.
4. Keep `DB_SSLMODE=require` or stricter.

### Deployment

1. Production `CORS_ALLOW_ORIGINS` must contain exact HTTPS frontend domains only.
2. HTTPS must be enforced for frontend and backend.
3. PostgreSQL must not be publicly reachable except from approved backend network paths.
4. Debug endpoints must be disabled in production.
5. Use separate dev/staging/prod credentials and databases.

### Logging And Monitoring

1. Log security events: verification requested/confirmed, upload accepted/rejected, report generated/viewed/emailed, rate-limit hits, debug endpoint access, auth failures.
2. Redact emails where full value is not needed; never log raw tokens, passwords, or API keys.
3. Alert on spikes in email verification, report email, upload failures, LLM calls, or 5xx errors.

### Incident Response And Root Cause Analysis

If Seeco is attacked or a vulnerability is exploited:

1. Contain: disable affected endpoint or rotate exposed credential.
2. Preserve evidence: capture logs, timestamps, affected users/reports, request IDs, and deployment version.
3. Assess impact: classify affected data and whether confidentiality, integrity, or availability was impacted.
4. Root cause: identify missing control, code defect, misconfiguration, or process failure.
5. Remediate: patch, deploy, rotate secrets, invalidate sessions/tokens, and verify with regression tests.
6. Document: update this security plan, Project Governance Portfolio Security folder, and LeanKit item with incident summary and action status.
7. Notify: follow applicable privacy/studio/mentor notification obligations if personal or confidential data was exposed.

## 12. Security Drill Structure

### 1. Pen Test Findings

Current findings are listed in Section 8. For each iteration, add:

| Date | Tester | Environment | Test | Evidence/screenshots | Result | Follow-up ticket |
|---|---|---|---|---|---|---|
| TBD | TBD | Staging | Auth/IDOR route checks | TBD | TBD | TBD |
| TBD | TBD | Staging | Upload spoofing checks | TBD | TBD | TBD |
| TBD | TBD | Staging | Rate-limit checks | TBD | TBD | TBD |

### 2. Impact Assessment

Use Section 9 as the baseline and update it when a new vulnerability is discovered or fixed.

### 3. Recommendations

Use Section 10 as the prioritized backlog. Mark each recommendation as `Open`, `In progress`, `Implemented`, or `Accepted risk`.

## 13. Live Document Change Log

| Date | Change | Author |
|---|---|---|
| 2026-05-05 | Initial repo-specific security plan created from supplied guidelines and source review. | Codex |

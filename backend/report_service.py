from __future__ import annotations

import html
import os
import re
import smtplib
from datetime import datetime, timezone
from email.message import EmailMessage
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from psycopg2.extras import Json


REPORT_OUTBOX_DIR = Path(__file__).resolve().parent / "outbox"


def valid_email(value: str) -> bool:
    return bool(re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", (value or "").strip()))


def env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def email_delivery_mode() -> str:
    mode = (os.getenv("EMAIL_DELIVERY_MODE") or "auto").strip().lower()
    return mode if mode in {"auto", "smtp", "outbox"} else "auto"


def email_provider() -> str:
    provider = (os.getenv("EMAIL_PROVIDER") or os.getenv("SMTP_PROVIDER") or "").strip().lower()
    return provider if provider in {"resend", "smtp"} else ""


def smtp_settings() -> Dict[str, Any]:
    provider = email_provider()
    resend_api_key = os.getenv("RESEND_API_KEY") or ""
    configured_host = (os.getenv("SMTP_HOST") or "").strip()
    is_resend_host = configured_host.lower() == "smtp.resend.com"
    use_resend_defaults = (
        provider == "resend"
        or is_resend_host
        or bool(resend_api_key and not configured_host)
    )
    use_ssl = env_bool("SMTP_USE_SSL", False)
    use_tls = True if use_resend_defaults and not use_ssl else env_bool("SMTP_USE_TLS", not use_ssl)

    return {
        "provider": "resend" if use_resend_defaults else provider,
        "host": configured_host or ("smtp.resend.com" if use_resend_defaults else ""),
        "port": int(os.getenv("SMTP_PORT", "587")),
        "username": (os.getenv("SMTP_USERNAME") or ("resend" if use_resend_defaults else "")).strip(),
        "password": os.getenv("SMTP_PASSWORD") or resend_api_key,
        "from_email": (
            os.getenv("REPORT_FROM_EMAIL")
            or os.getenv("SMTP_FROM_EMAIL")
            or os.getenv("SMTP_USERNAME")
            or ""
        ).strip(),
        "from_name": (os.getenv("REPORT_FROM_NAME") or "Seeco").strip(),
        "reply_to": (os.getenv("REPORT_REPLY_TO") or "").strip(),
        "use_tls": use_tls,
        "use_ssl": use_ssl,
        "require_auth": env_bool("SMTP_REQUIRE_AUTH", use_resend_defaults),
        "timeout": int(os.getenv("SMTP_TIMEOUT_SECONDS", "30")),
    }


def smtp_is_configured(settings: Dict[str, Any]) -> bool:
    has_endpoint = bool(settings["host"] and settings["from_email"])
    has_auth = bool(settings["username"] and settings["password"])
    return has_endpoint and (not settings["require_auth"] or has_auth)


def smtp_has_partial_config(settings: Dict[str, Any]) -> bool:
    keys = ("host", "username", "password", "from_email")
    configured = [bool(settings[key]) for key in keys]
    return any(configured) and not smtp_is_configured(settings)


def _string(value: Any, fallback: str = "Not available") -> str:
    if value is None:
        return fallback
    text = str(value).strip()
    return text or fallback


def _percent(value: Any) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "Not scored"
    if number <= 1:
        number *= 100
    return f"{round(number)}%"


def _display_datetime(value: Any) -> str:
    if not value:
        return "Not available"
    text = str(value)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return parsed.strftime("%d %b %Y, %H:%M UTC")
    except ValueError:
        return text


def _fetch_all(cur, query: str, params: Iterable[Any]) -> List[Dict[str, Any]]:
    cur.execute(query, tuple(params))
    return [dict(row) for row in cur.fetchall()]


def _serializable(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _serializable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_serializable(item) for item in value]
    if isinstance(value, tuple):
        return [_serializable(item) for item in value]
    if isinstance(value, (datetime,)):
        return value.isoformat()
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def _analysis_records(analysis_payload: Optional[Dict[str, Any]], key: str) -> List[Dict[str, Any]]:
    if not isinstance(analysis_payload, dict):
        return []
    nested = analysis_payload.get("analysis_evidence")
    if isinstance(nested, dict):
        section = nested.get(key)
        if isinstance(section, list):
            return [record for record in section if isinstance(record, dict)]
    section = analysis_payload.get(key)
    if isinstance(section, list):
        return [record for record in section if isinstance(record, dict)]
    if not isinstance(section, dict):
        return []
    records = section.get("evidence")
    if not isinstance(records, list):
        return []
    return [record for record in records if isinstance(record, dict)]


def _analysis_candidates(analysis_payload: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not isinstance(analysis_payload, dict):
        return []
    nested = analysis_payload.get("analysis_evidence")
    if isinstance(nested, dict):
        candidates = nested.get("news_candidates")
        if isinstance(candidates, list):
            return [candidate for candidate in candidates if isinstance(candidate, dict)]
    news = analysis_payload.get("news")
    if not isinstance(news, dict):
        return []
    candidates = news.get("candidates")
    if not isinstance(candidates, list):
        return []
    return [candidate for candidate in candidates if isinstance(candidate, dict)]


def _analysis_layer_a(analysis_payload: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not isinstance(analysis_payload, dict):
        return {}
    layer_a = analysis_payload.get("spatial_analysis") or analysis_payload.get("layer_a")
    if isinstance(layer_a, dict):
        return layer_a
    nested = analysis_payload.get("metadata_json")
    if isinstance(nested, dict):
        return _analysis_layer_a(nested)
    return {}


def build_query_report(
    cur,
    query_id: str,
    analysis_payload: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    cur.execute(
        """
        SELECT
            sq.query_id,
            sq.input_type,
            sq.input_value,
            sq.resolution_status,
            sq.submitted_at,
            sq.resolved_company_id,
            sq.resolved_brand_id,
            sq.resolved_product_id,
            c.legal_name,
            c.abn,
            c.entity_type,
            c.company_status,
            ar.state,
            ar.postcode,
            ar.gst_registered,
            b.brand_name,
            p.product_name,
            p.barcode,
            p.manufacturer_name
        FROM search_query sq
        LEFT JOIN company c ON c.company_id = sq.resolved_company_id
        LEFT JOIN abn_record ar ON ar.abn = c.abn
        LEFT JOIN brand b ON b.brand_id = sq.resolved_brand_id
        LEFT JOIN product p ON p.product_id = sq.resolved_product_id
        WHERE sq.query_id = %s;
        """,
        (query_id,),
    )
    row = cur.fetchone()
    if not row:
        return {}

    base = dict(row)
    company_id = base.get("resolved_company_id")
    locations: List[Dict[str, Any]] = []
    news: List[Dict[str, Any]] = []

    if company_id:
        locations = _fetch_all(
            cur,
            """
            SELECT label, address_raw, state, postcode, country, latitude, longitude,
                   confidence, source_type, extracted_at
            FROM inferred_location
            WHERE company_id = %s
            ORDER BY
                CASE source_type WHEN 'report' THEN 1 WHEN 'news' THEN 2 WHEN 'abn' THEN 3 ELSE 4 END,
                CASE
                    WHEN lower(COALESCE(label, '') || ' ' || COALESCE(address_raw, '')) LIKE '%%pilbara%%' THEN 1
                    WHEN lower(COALESCE(label, '') || ' ' || COALESCE(address_raw, '')) LIKE '%%olympic dam%%' THEN 1
                    WHEN lower(COALESCE(label, '') || ' ' || COALESCE(address_raw, '')) LIKE '%%port hedland%%' THEN 1
                    WHEN lower(COALESCE(label, '') || ' ' || COALESCE(address_raw, '')) LIKE '%%bowen basin%%' THEN 1
                    ELSE 2
                END,
                extracted_at DESC
            LIMIT 10;
            """,
            (company_id,),
        )
        news = _fetch_all(
            cur,
            """
            SELECT headline, source_url, publisher, sentiment, published_at
            FROM news_article
            WHERE company_id = %s
            ORDER BY published_at DESC NULLS LAST, ingested_at DESC
            LIMIT 10;
            """,
            (company_id,),
        )

    generated_at = datetime.now(timezone.utc).isoformat()
    analysis_resolution = (
        analysis_payload.get("resolution")
        if isinstance(analysis_payload, dict) and isinstance(analysis_payload.get("resolution"), dict)
        else {}
    )
    display_name = (
        base.get("legal_name")
        or analysis_resolution.get("legal_name")
        or analysis_resolution.get("normalized_name")
        or base.get("brand_name")
        or base.get("product_name")
        or base.get("input_value")
        or "Seeco entity"
    )

    report_evidence = _analysis_records(analysis_payload, "reports")
    news_evidence = _analysis_records(analysis_payload, "news")
    news_candidates = _analysis_candidates(analysis_payload)
    layer_a = _analysis_layer_a(analysis_payload)

    completeness = 35
    if base.get("resolved_company_id"):
        completeness += 20
    if locations:
        completeness += 15
    if news or news_evidence or news_candidates:
        completeness += 15
    if report_evidence:
        completeness += 10
    if base.get("resolved_brand_id") or base.get("resolved_product_id"):
        completeness += 5

    evidence_count = len(report_evidence) + len(news_evidence) + len(news)
    primary_location = locations[0] if locations else {}
    extracted_locations = [
        location for location in locations
        if location.get("source_type") in ("report", "news")
    ]
    location_label = primary_location.get("label") or "No operating location inferred"
    report_sources = sorted(
        {
            str(item.get("source"))
            for item in report_evidence
            if item.get("source")
        }
    )
    key_findings = [
        f"Primary biodiversity context is {location_label}.",
        f"{len(report_evidence)} uploaded-report evidence signal(s) and {len(news_evidence)} news evidence signal(s) were extracted.",
        f"{len(extracted_locations)} operating or evidence-derived location(s) are available for spatial assessment.",
    ]
    if report_sources:
        key_findings.append(f"Uploaded evidence source reviewed: {', '.join(report_sources[:3])}.")
    if layer_a.get("status") == "success":
        key_findings.append(
            "Layer A biodiversity scoring found "
            f"{layer_a.get('threatened_species_count', 0)} threatened species "
            f"and a species threat score of {float(layer_a.get('species_threat_score') or 0):.1f}/100."
        )
    summary_text = (
        f"{display_name} was resolved from {base.get('input_type')} input. "
        f"Seeco found {evidence_count} persisted or extracted evidence record(s), "
        f"with {location_label} used as the primary spatial context when available."
    )

    return _serializable(
        {
            "query_id": str(base["query_id"]),
            "generated_at": generated_at,
            "title": f"Seeco biodiversity report - {display_name}",
            "executive_summary": summary_text,
            "key_findings": key_findings,
            "summary": {
                "entity_name": display_name,
                "input_type": base.get("input_type"),
                "input_value": base.get("input_value"),
                "resolution_status": base.get("resolution_status"),
                "submitted_at": base.get("submitted_at"),
                "completeness_score": min(completeness, 100),
                "evidence_count": evidence_count,
                "news_candidate_count": len(news_candidates),
                "report_evidence_count": len(report_evidence),
                "primary_location": location_label,
                "evidence_location_count": len(extracted_locations),
            },
            "company": {
                "company_id": str(base["resolved_company_id"])
                if base.get("resolved_company_id")
                else None,
                "legal_name": base.get("legal_name") or analysis_resolution.get("legal_name"),
                "abn": base.get("abn") or analysis_resolution.get("abn"),
                "entity_type": base.get("entity_type"),
                "company_status": base.get("company_status"),
                "state": base.get("state") or analysis_resolution.get("state"),
                "postcode": base.get("postcode") or analysis_resolution.get("postcode"),
                "gst_registered": base.get("gst_registered"),
            },
            "brand": {
                "brand_id": str(base["resolved_brand_id"])
                if base.get("resolved_brand_id")
                else None,
                "brand_name": base.get("brand_name"),
            },
            "product": {
                "product_id": str(base["resolved_product_id"])
                if base.get("resolved_product_id")
                else None,
                "product_name": base.get("product_name"),
                "barcode": base.get("barcode"),
                "manufacturer_name": base.get("manufacturer_name"),
            },
            "locations": locations,
            "persisted_news": news,
            "spatial_analysis": layer_a,
            "analysis_evidence": {
                "news": news_evidence,
                "reports": report_evidence,
                "news_candidates": news_candidates,
            },
            "limitations": [
                "ABN locations are registered addresses and may not represent operating sites.",
                "Uploaded report evidence reflects the files submitted during the latest analysis.",
                "Scores are decision-support signals, not a regulatory determination.",
            ],
        }
    )


def render_report_html(report: Dict[str, Any]) -> str:
    title = html.escape(_string(report.get("title"), "Seeco report"))
    summary = report.get("summary") or {}
    company = report.get("company") or {}
    brand = report.get("brand") or {}
    product = report.get("product") or {}
    locations = report.get("locations") or []
    persisted_news = report.get("persisted_news") or []
    analysis = report.get("analysis_evidence") or {}
    report_records = analysis.get("reports") or []
    news_records = analysis.get("news") or []
    news_candidates = analysis.get("news_candidates") or []
    limitations = report.get("limitations") or []
    key_findings = report.get("key_findings") or []
    primary_location = summary.get("primary_location") or "Not available"
    layer_a = report.get("spatial_analysis") or {}
    threatened_species = layer_a.get("threatened_species") or []

    def card(label: str, value: Any) -> str:
        return (
            "<div class='metric'>"
            f"<span>{html.escape(label)}</span>"
            f"<strong>{html.escape(_string(value))}</strong>"
            "</div>"
        )

    def source_cell(item: Dict[str, Any]) -> str:
        label = html.escape(_string(item.get("source") or item.get("publisher")))
        url = item.get("source_url") or item.get("url")
        if isinstance(url, str) and url.startswith(("http://", "https://")):
            return f"<a href='{html.escape(url, quote=True)}'>{label}</a>"
        return label

    def evidence_rows(records: List[Dict[str, Any]], fallback: str) -> str:
        rows = "".join(
            "<tr>"
            f"<td>{html.escape(_string(item.get('biodiversity_signal') or item.get('headline') or item.get('title')))}</td>"
            f"<td>{html.escape(_string(item.get('evidence_type') or item.get('source_type')))}</td>"
            f"<td>{html.escape(_string(item.get('location')))}</td>"
            f"<td>{source_cell(item)}</td>"
            f"<td>{html.escape(_percent(item.get('confidence') or item.get('llm_confidence')))}</td>"
            "</tr>"
            for item in records
        )
        return rows or f"<tr><td colspan='5'>{html.escape(fallback)}</td></tr>"

    location_rows = "".join(
        "<tr>"
        f"<td>{html.escape(_string(item.get('label')))}</td>"
        f"<td>{html.escape(_string(item.get('state')))} {html.escape(_string(item.get('postcode'), ''))}</td>"
        f"<td>{html.escape(_string(item.get('confidence')))}</td>"
        f"<td>{html.escape(_string(item.get('source_type')))}</td>"
        "</tr>"
        for item in locations
    ) or "<tr><td colspan='4'>No inferred locations recorded.</td></tr>"

    candidate_rows = "".join(
        "<tr>"
        f"<td>{html.escape(_string(item.get('title')))}</td>"
        f"<td>{html.escape(_string(item.get('source')))}</td>"
        f"<td>{html.escape(_string(item.get('published_date')))}</td>"
        "</tr>"
        for item in news_candidates[:10]
    ) or "<tr><td colspan='3'>No news candidates included.</td></tr>"

    limitation_items = "".join(
        f"<li>{html.escape(_string(item))}</li>" for item in limitations
    )
    key_finding_items = "".join(
        f"<li>{html.escape(_string(item))}</li>" for item in key_findings
    )
    threat_rows = "".join(
        "<tr>"
        f"<td>{html.escape(_string(item.get('scientific_name')))}</td>"
        f"<td>{html.escape(_string(item.get('common_name')))}</td>"
        f"<td>{html.escape(_string(item.get('iucn_category')))}</td>"
        f"<td>{html.escape(_string(item.get('record_count')))}</td>"
        "</tr>"
        for item in threatened_species[:10]
        if isinstance(item, dict)
    ) or "<tr><td colspan='4'>No threatened species returned by Layer A.</td></tr>"

    return f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <title>{title}</title>
  <style>
    body {{ font-family: Arial, sans-serif; color: #1c1917; margin: 0; background: #f5f3ee; }}
    main {{ max-width: 960px; margin: 0 auto; padding: 36px 24px; }}
    header {{ border-bottom: 3px solid #047857; padding-bottom: 18px; margin-bottom: 24px; }}
    h1 {{ margin: 0; font-size: 28px; }}
    h2 {{ margin-top: 28px; font-size: 18px; }}
    .muted {{ color: #78716c; font-size: 13px; }}
    .summary {{ background: #ecfdf5; border: 1px solid #a7f3d0; border-radius: 8px; padding: 14px; margin: 16px 0; }}
    .grid {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; }}
    .metric {{ background: white; border: 1px solid #e7e5e4; border-radius: 8px; padding: 12px; }}
    .metric span {{ display: block; color: #78716c; font-size: 11px; text-transform: uppercase; margin-bottom: 6px; }}
    .metric strong {{ font-size: 15px; }}
    table {{ width: 100%; border-collapse: collapse; background: white; border: 1px solid #e7e5e4; }}
    th, td {{ text-align: left; border-bottom: 1px solid #e7e5e4; padding: 10px; font-size: 13px; vertical-align: top; }}
    th {{ background: #ecfdf5; color: #065f46; font-size: 11px; text-transform: uppercase; }}
    a {{ color: #047857; }}
    ul {{ background: white; border: 1px solid #e7e5e4; border-radius: 8px; padding: 14px 18px 14px 32px; }}
    @media print {{ body {{ background: white; }} main {{ padding: 0; }} }}
  </style>
  <script>
    window.addEventListener('load', function () {{
      if (new URLSearchParams(window.location.search).get('print') === '1') {{
        setTimeout(function () {{ window.print(); }}, 300);
      }}
    }});
  </script>
</head>
<body>
  <main>
    <header>
      <div class="muted">Seeco investor biodiversity dossier</div>
      <h1>{title}</h1>
      <div class="muted">Generated {html.escape(_display_datetime(report.get("generated_at")))}</div>
    </header>

    <div class="summary">{html.escape(_string(report.get("executive_summary")))}</div>

    <h2>Key Findings</h2>
    <ul>{key_finding_items}</ul>

    <section class="grid">
      {card("Entity", summary.get("entity_name"))}
      {card("Resolution", summary.get("resolution_status"))}
      {card("Completeness", _percent(summary.get("completeness_score")))}
      {card("ABN", company.get("abn"))}
      {card("Brand", brand.get("brand_name"))}
      {card("Product", product.get("product_name"))}
    </section>

    <h2>Biodiversity Impact Summary</h2>
    <section class="grid">
      {card("Primary spatial context", primary_location)}
      {card("Evidence locations", summary.get("evidence_location_count"))}
      {card("Evidence records", summary.get("evidence_count"))}
    </section>

    <section class="grid">
      {card("Species threat score", f"{float(layer_a.get('species_threat_score') or 0):.1f}/100" if layer_a.get("status") == "success" else "Pending")}
      {card("ALA occurrence records", layer_a.get("total_ala_records") if layer_a.get("status") == "success" else "Pending")}
      {card("Threatened species", layer_a.get("threatened_species_count") if layer_a.get("status") == "success" else "Pending")}
    </section>

    <h2>Layer A Threatened Species</h2>
    <table>
      <thead><tr><th>Scientific name</th><th>Common name</th><th>IUCN category</th><th>ALA records</th></tr></thead>
      <tbody>{threat_rows}</tbody>
    </table>

    <h2>Company Snapshot</h2>
    <section class="grid">
      {card("Legal name", company.get("legal_name"))}
      {card("Entity type", company.get("entity_type"))}
      {card("Registered address", f"{_string(company.get('state'), '')} {_string(company.get('postcode'), '')}".strip())}
    </section>

    <h2>Inferred Spatial Context</h2>
    <table>
      <thead><tr><th>Location</th><th>State/postcode</th><th>Confidence</th><th>Source</th></tr></thead>
      <tbody>{location_rows}</tbody>
    </table>

    <h2>Extracted Report Evidence</h2>
    <table>
      <thead><tr><th>Signal</th><th>Type</th><th>Location</th><th>Source</th><th>Confidence</th></tr></thead>
      <tbody>{evidence_rows(report_records, "No uploaded report evidence included.")}</tbody>
    </table>

    <h2>News Evidence</h2>
    <table>
      <thead><tr><th>Signal</th><th>Type</th><th>Location</th><th>Source</th><th>Confidence</th></tr></thead>
      <tbody>{evidence_rows(news_records or persisted_news, "No persisted or extracted news evidence included.")}</tbody>
    </table>

    <h2>Reviewed News Candidates</h2>
    <table>
      <thead><tr><th>Title</th><th>Source</th><th>Date</th></tr></thead>
      <tbody>{candidate_rows}</tbody>
    </table>

    <h2>Limitations</h2>
    <ul>{limitation_items}</ul>
  </main>
</body>
</html>"""


def create_persisted_report(
    cur,
    query_id: str,
    analysis_payload: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    report = build_query_report(cur, query_id, analysis_payload)
    if not report:
        return {}
    html_content = render_report_html(report)
    cur.execute(
        """
        INSERT INTO report
            (query_id, title, format, status, html_content, metadata_json)
        VALUES (%s, %s, 'html', 'generated', %s, %s)
        RETURNING report_id, query_id, title, format, status, generated_at,
                  sent_at, recipient_email, delivery_method;
        """,
        (query_id, report["title"], html_content, Json(report)),
    )
    saved = dict(cur.fetchone())
    saved["metadata_json"] = report
    return _serializable(saved)


def refresh_persisted_report_content(
    cur,
    report_id: str,
    analysis_payload: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    existing = get_persisted_report(cur, report_id)
    if not existing:
        return {}

    payload = analysis_payload
    if payload is None and isinstance(existing.get("metadata_json"), dict):
        payload = existing["metadata_json"]

    report = build_query_report(cur, existing["query_id"], payload)
    if not report:
        return {}

    html_content = render_report_html(report)
    cur.execute(
        """
        UPDATE report
        SET title = %s,
            html_content = %s,
            metadata_json = %s
        WHERE report_id = %s
        RETURNING report_id, query_id, title, format, status, generated_at,
                  sent_at, recipient_email, delivery_method;
        """,
        (report["title"], html_content, Json(report), report_id),
    )
    saved = dict(cur.fetchone())
    saved["metadata_json"] = report
    return _serializable(saved)


def get_persisted_report(cur, report_id: str) -> Dict[str, Any]:
    cur.execute(
        """
        SELECT report_id, query_id, recipient_email, title, format, status,
               html_content, metadata_json, generated_at, sent_at, delivery_method
        FROM report
        WHERE report_id = %s;
        """,
        (report_id,),
    )
    row = cur.fetchone()
    return _serializable(dict(row)) if row else {}


def deliver_report_email(to_email: str, subject: str, html_body: str) -> Dict[str, Any]:
    if not valid_email(to_email):
        raise ValueError("Please provide a valid email address")

    settings = smtp_settings()
    mode = email_delivery_mode()

    if mode == "smtp" and not smtp_is_configured(settings):
        raise RuntimeError(
            "SMTP delivery is required but email settings are incomplete. "
            "For Resend, set EMAIL_PROVIDER=resend, RESEND_API_KEY, and REPORT_FROM_EMAIL."
        )
    if mode == "auto" and smtp_has_partial_config(settings):
        raise RuntimeError(
            "SMTP is partially configured. Complete the SMTP/Resend settings, "
            "or clear them to use outbox fallback."
        )

    if mode != "outbox" and smtp_is_configured(settings):
        message = EmailMessage()
        message["Subject"] = subject
        message["From"] = f"{settings['from_name']} <{settings['from_email']}>" if settings["from_name"] else settings["from_email"]
        message["To"] = to_email
        if settings["reply_to"]:
            message["Reply-To"] = settings["reply_to"]
        message.set_content("Open this Seeco email in an HTML-capable email client.")
        message.add_alternative(html_body, subtype="html")

        smtp_class = smtplib.SMTP_SSL if settings["use_ssl"] else smtplib.SMTP
        with smtp_class(settings["host"], settings["port"], timeout=settings["timeout"]) as smtp:
            if settings["use_tls"] and not settings["use_ssl"]:
                smtp.starttls()
            if settings["username"]:
                smtp.login(settings["username"], settings["password"])
            smtp.send_message(message)
        return {
            "delivery": "smtp",
            "to": to_email,
            "smtp_host": settings["host"],
            "smtp_provider": settings["provider"] or "smtp",
        }

    if mode == "smtp":
        raise RuntimeError("SMTP delivery failed before outbox fallback could be used")

    REPORT_OUTBOX_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    safe_email = re.sub(r"[^A-Za-z0-9_.-]+", "_", to_email)
    outbox_path = REPORT_OUTBOX_DIR / f"{stamp}_{safe_email}.html"
    outbox_path.write_text(html_body, encoding="utf-8")
    return {"delivery": "outbox", "to": to_email, "path": str(outbox_path)}


def send_persisted_report(cur, report_id: str, to_email: str) -> Dict[str, Any]:
    report = get_persisted_report(cur, report_id)
    if not report:
        return {}
    delivery = deliver_report_email(to_email, report["title"], report["html_content"])
    cur.execute(
        """
        UPDATE report
        SET recipient_email = %s,
            status = 'sent',
            sent_at = NOW(),
            delivery_method = %s
        WHERE report_id = %s
        RETURNING report_id, status, sent_at, recipient_email, delivery_method;
        """,
        (to_email, delivery["delivery"], report_id),
    )
    updated = _serializable(dict(cur.fetchone()))
    return {**delivery, **updated}

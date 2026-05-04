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


def smtp_settings() -> Dict[str, Any]:
    return {
        "host": (os.getenv("SMTP_HOST") or "").strip(),
        "port": int(os.getenv("SMTP_PORT", "587")),
        "username": (os.getenv("SMTP_USERNAME") or "").strip(),
        "password": os.getenv("SMTP_PASSWORD") or "",
        "from_email": (
            os.getenv("REPORT_FROM_EMAIL")
            or os.getenv("SMTP_FROM_EMAIL")
            or os.getenv("SMTP_USERNAME")
            or ""
        ).strip(),
        "from_name": (os.getenv("REPORT_FROM_NAME") or "EcoTrace").strip(),
        "reply_to": (os.getenv("REPORT_REPLY_TO") or "").strip(),
        "use_tls": env_bool("SMTP_USE_TLS", True),
        "use_ssl": env_bool("SMTP_USE_SSL", False),
        "timeout": int(os.getenv("SMTP_TIMEOUT_SECONDS", "30")),
    }


def smtp_is_configured(settings: Dict[str, Any]) -> bool:
    return bool(settings["host"] and settings["from_email"])


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
            ORDER BY extracted_at DESC
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
        or "EcoTrace entity"
    )

    report_evidence = _analysis_records(analysis_payload, "reports")
    news_evidence = _analysis_records(analysis_payload, "news")
    news_candidates = _analysis_candidates(analysis_payload)

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
    summary_text = (
        f"{display_name} is resolved from {base.get('input_type')} input "
        f"with {evidence_count} persisted or extracted evidence record(s) available."
    )

    return _serializable(
        {
            "query_id": str(base["query_id"]),
            "generated_at": generated_at,
            "title": f"EcoTrace biodiversity report - {display_name}",
            "executive_summary": summary_text,
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
    title = html.escape(_string(report.get("title"), "EcoTrace report"))
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

    def card(label: str, value: Any) -> str:
        return (
            "<div class='metric'>"
            f"<span>{html.escape(label)}</span>"
            f"<strong>{html.escape(_string(value))}</strong>"
            "</div>"
        )

    def evidence_rows(records: List[Dict[str, Any]], fallback: str) -> str:
        rows = "".join(
            "<tr>"
            f"<td>{html.escape(_string(item.get('biodiversity_signal') or item.get('headline') or item.get('title')))}</td>"
            f"<td>{html.escape(_string(item.get('evidence_type') or item.get('source_type')))}</td>"
            f"<td>{html.escape(_string(item.get('location')))}</td>"
            f"<td>{html.escape(_string(item.get('source') or item.get('publisher')))}</td>"
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
    ul {{ background: white; border: 1px solid #e7e5e4; border-radius: 8px; padding: 14px 18px 14px 32px; }}
    @media print {{ body {{ background: white; }} main {{ padding: 0; }} }}
  </style>
</head>
<body>
  <main>
    <header>
      <div class="muted">EcoTrace investor biodiversity dossier</div>
      <h1>{title}</h1>
      <div class="muted">Generated {html.escape(_string(report.get("generated_at")))}</div>
    </header>

    <div class="summary">{html.escape(_string(report.get("executive_summary")))}</div>

    <section class="grid">
      {card("Entity", summary.get("entity_name"))}
      {card("Resolution", summary.get("resolution_status"))}
      {card("Completeness", _percent(summary.get("completeness_score")))}
      {card("ABN", company.get("abn"))}
      {card("Brand", brand.get("brand_name"))}
      {card("Product", product.get("product_name"))}
    </section>

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
        raise RuntimeError("SMTP delivery is required but SMTP_HOST and REPORT_FROM_EMAIL are not configured")
    if mode == "auto" and smtp_has_partial_config(settings):
        raise RuntimeError("SMTP is partially configured. Set SMTP_HOST and REPORT_FROM_EMAIL, or clear SMTP settings for outbox fallback")

    if mode != "outbox" and smtp_is_configured(settings):
        message = EmailMessage()
        message["Subject"] = subject
        message["From"] = f"{settings['from_name']} <{settings['from_email']}>" if settings["from_name"] else settings["from_email"]
        message["To"] = to_email
        if settings["reply_to"]:
            message["Reply-To"] = settings["reply_to"]
        message.set_content("Open this EcoTrace email in an HTML-capable email client.")
        message.add_alternative(html_body, subtype="html")

        smtp_class = smtplib.SMTP_SSL if settings["use_ssl"] else smtplib.SMTP
        with smtp_class(settings["host"], settings["port"], timeout=settings["timeout"]) as smtp:
            if settings["use_tls"] and not settings["use_ssl"]:
                smtp.starttls()
            if settings["username"]:
                smtp.login(settings["username"], settings["password"])
            smtp.send_message(message)
        return {"delivery": "smtp", "to": to_email, "smtp_host": settings["host"]}

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

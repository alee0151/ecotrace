from __future__ import annotations

from typing import Any, Iterable


def clamp_score(value: float, minimum: float = 0.0, maximum: float = 100.0) -> float:
    return max(minimum, min(maximum, value))


def confidence_value(record: dict[str, Any]) -> float:
    raw = record.get("confidence")
    if raw is None:
        raw = record.get("llm_confidence")
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return 0.6
    if value > 1:
        value = value / 100
    return clamp_score(value, 0.0, 1.0)


def evidence_records_from_analysis(analysis_payload: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(analysis_payload, dict):
        return []
    records: list[dict[str, Any]] = []
    for section_name in ("news", "reports"):
        section = analysis_payload.get(section_name)
        if isinstance(section, dict):
            section_records = section.get("evidence")
            if isinstance(section_records, list):
                records.extend(item for item in section_records if isinstance(item, dict))
    nested = analysis_payload.get("analysis_evidence")
    if isinstance(nested, dict):
        for section_name in ("news", "reports"):
            section_records = nested.get(section_name)
            if isinstance(section_records, list):
                records.extend(item for item in section_records if isinstance(item, dict))
    return records


def evidence_pressure_score(records: Iterable[dict[str, Any]]) -> tuple[float, dict[str, float]]:
    positive_impacts: list[float] = []
    action_relief = 0.0
    regulatory_count = 0
    risk_count = 0
    action_count = 0

    for record in records:
        evidence_type = str(record.get("evidence_type") or "").lower()
        activity = str(record.get("activity_type") or "").lower()
        signal = str(record.get("biodiversity_signal") or "").lower()
        confidence = 0.5 + confidence_value(record) / 2

        impact = 0.0
        if "regulatory" in evidence_type:
            impact += 26
            regulatory_count += 1
        elif "risk" in evidence_type:
            impact += 24
            risk_count += 1
        elif "unknown" in evidence_type:
            impact += 8

        if "action" in evidence_type:
            action_count += 1
            action_relief += 10 * confidence

        if any(term in activity for term in ("clearing", "deforestation", "mining", "drilling", "dam collapse")):
            impact += 14
        elif any(term in activity for term in ("rehabilitation", "restoration", "conservation", "monitoring", "offset")):
            action_relief += 6 * confidence

        if any(term in signal for term in ("critically endangered", "endangered", "threatened", "koala", "habitat", "deforestation", "clearing", "fish kill", "rehabilitation failures")):
            impact += 10

        if impact > 0:
            positive_impacts.append(impact * confidence)

    positive_impacts.sort(reverse=True)
    positive_pressure = sum(
        impact * (0.72 ** index)
        for index, impact in enumerate(positive_impacts[:8])
    )

    score = 25 + min(65, positive_pressure) - min(18, action_relief)
    score = clamp_score(score, 5, 95)
    return round(score, 2), {
        "risk_records": float(risk_count),
        "regulatory_records": float(regulatory_count),
        "action_records": float(action_count),
        "positive_pressure": round(min(65, positive_pressure), 2),
        "action_relief": round(min(18, action_relief), 2),
    }


def evidence_coverage_score(records: Iterable[dict[str, Any]], candidate_count: int = 0) -> float:
    materialized = list(records)
    sources = {
        str(record.get("source") or record.get("source_url") or "").strip().lower()
        for record in materialized
        if record.get("source") or record.get("source_url")
    }
    report_records = sum(1 for record in materialized if record.get("source_type") == "report")
    score = len(materialized) * 10 + len(sources) * 6 + min(15, candidate_count * 1.5)
    if report_records:
        score += 10
    return round(clamp_score(score, 0, 100), 2)


def combined_biodiversity_score(
    *,
    species_threat_score: float | int | None,
    evidence_records: list[dict[str, Any]] | None = None,
    candidate_count: int = 0,
) -> dict[str, Any]:
    try:
        species_score = float(species_threat_score or 0)
    except (TypeError, ValueError):
        species_score = 0.0
    records = evidence_records or []
    evidence_score, evidence_breakdown = evidence_pressure_score(records)
    coverage_score = evidence_coverage_score(records, candidate_count)

    if records:
        combined = species_score * 0.45 + evidence_score * 0.45 + coverage_score * 0.10
    else:
        combined = species_score

    return {
        "combined_score": round(clamp_score(combined), 2),
        "species_threat_component": round(clamp_score(species_score), 2),
        "evidence_pressure_component": evidence_score if records else 0.0,
        "evidence_coverage_component": coverage_score if records else 0.0,
        "weights": {
            "species_threat": 0.45 if records else 1.0,
            "evidence_pressure": 0.45 if records else 0.0,
            "evidence_coverage": 0.10 if records else 0.0,
        },
        "evidence_record_count": len(records),
        "candidate_count": candidate_count,
        **evidence_breakdown,
    }

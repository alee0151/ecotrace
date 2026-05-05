from backend.combined_biodiversity_score import (
    combined_biodiversity_score,
    evidence_records_from_analysis,
)


def record(evidence_type: str, activity: str, confidence: float = 0.9, signal: str = "habitat impact"):
    return {
        "evidence_type": evidence_type,
        "activity_type": activity,
        "confidence": confidence,
        "biodiversity_signal": signal,
        "source": "Test Source",
        "source_type": "news",
    }


def test_combined_score_uses_species_only_when_no_evidence():
    score = combined_biodiversity_score(species_threat_score=18.65, evidence_records=[])

    assert score["combined_score"] == 18.65
    assert score["weights"]["species_threat"] == 1.0


def test_combined_score_raises_low_species_score_when_evidence_pressure_is_high():
    evidence = [
        record("biodiversity risk", "mining", signal="threatened habitat impact"),
        record("regulatory signal", "rehabilitation", signal="rehabilitation failures"),
        record("biodiversity risk", "clearing", signal="endangered species habitat clearing"),
    ]

    score = combined_biodiversity_score(
        species_threat_score=18.65,
        evidence_records=evidence,
        candidate_count=10,
    )

    assert 45 <= score["combined_score"] < 75
    assert score["species_threat_component"] == 18.65
    assert score["evidence_pressure_component"] > score["species_threat_component"]


def test_biodiversity_actions_reduce_evidence_pressure():
    risky = [record("biodiversity risk", "clearing")]
    mixed = risky + [
        record("biodiversity action", "conservation", signal="conserve and enhance biodiversity"),
        record("biodiversity action", "monitoring", signal="species monitoring program"),
    ]

    risky_score = combined_biodiversity_score(species_threat_score=20, evidence_records=risky)
    mixed_score = combined_biodiversity_score(species_threat_score=20, evidence_records=mixed)

    assert mixed_score["evidence_pressure_component"] < risky_score["evidence_pressure_component"]


def test_extracts_records_from_analysis_payload_shapes():
    analysis = {
        "news": {"evidence": [record("biodiversity risk", "mining")]},
        "reports": {"evidence": [record("regulatory signal", "approval")]},
    }

    assert len(evidence_records_from_analysis(analysis)) == 2

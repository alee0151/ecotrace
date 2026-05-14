from backend_clean.app.providers.biodiversity.layer_a import (
    SpeciesRecord,
    calculate_species_threat_score,
)


def species(category: str, records: int = 10) -> SpeciesRecord:
    return SpeciesRecord(
        scientific_name=f"Species {category} {records}",
        common_name=None,
        taxon_rank="species",
        record_count=records,
        iucn_category=category,
        iucn_category_name=category,
        threat_weight=0.0,
        iucn_url=None,
    )


def test_five_threatened_species_out_of_48_is_not_critical():
    assessed = [species("VU", records=500) for _ in range(5)]
    assessed.extend(species("LC", records=500) for _ in range(43))

    score = calculate_species_threat_score(assessed)

    assert 20 <= score < 35


def test_cr_en_heavy_mix_scores_higher_than_vulnerable_only():
    vulnerable_only = [species("VU") for _ in range(5)] + [species("LC") for _ in range(43)]
    severe_mix = [species("CR") for _ in range(2)]
    severe_mix.extend(species("EN") for _ in range(3))
    severe_mix.extend(species("LC") for _ in range(43))

    assert calculate_species_threat_score(severe_mix) > calculate_species_threat_score(vulnerable_only)


def test_no_threatened_species_scores_zero():
    assessed = [species("LC", records=100) for _ in range(50)]

    assert calculate_species_threat_score(assessed) == 0.0

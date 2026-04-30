import os
import sys
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import mock_open, patch

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = Path(__file__).resolve().parent
for path in (REPO_ROOT, BACKEND_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from ecotrace_pipeline import (
    ArticleMetadata,
    DEFAULT_OPENROUTER_MODEL,
    EcoTracePipeline,
    EvidenceRecord,
    ExtractionInput,
    KeywordLLMExtractor,
    NvidiaNIMLLMExtractor,
    OpenRouterLLMExtractor,
    SimpleArticleTextRetriever,
    UploadedReportTextReader,
    build_location_options,
    combine_confidence,
    create_llm_extractor_from_env,
    evidence_context,
    generate_queries,
    infer_payload_from_text,
    is_australia_linked,
    load_env_file,
    normalize_evidence_type,
    normalize_location,
    normalize_nvidia_model_name,
    parse_json_object,
    quality_gate_record,
)
from run_ecotrace import (
    article_candidate_score,
    article_is_llm_worthy,
    article_source_quality_score,
    build_company_search_queries,
    company_from_search_query,
    company_search_name,
    report_article_metadata,
    relevant_llm_candidates,
    resolve_report_paths,
)


class FakeProvider:
    name = "guardian"

    def search(self, query):
        return [
            ArticleMetadata(
                title="BHP Pilbara habitat rehabilitation under EPBC approval",
                snippet="BHP reports conservation work and species monitoring in the Pilbara.",
                source="Guardian",
                published_date="2026-04-20",
                url="https://example.test/bhp-pilbara",
            )
        ]


class NonAustralianProvider:
    name = "newsapi"

    def search(self, query):
        return [
            ArticleMetadata(
                title="BHP biodiversity offset in Guinea",
                snippet="BHP-linked mining biodiversity action reported in Guinea.",
                source="NewsAPI",
                published_date="2026-04-20",
                url="https://example.test/bhp-guinea",
            )
        ]


class PipelineTests(unittest.TestCase):
    def test_generates_assignment_queries(self):
        self.assertEqual(
            generate_queries("BHP"),
            [
                "BHP biodiversity",
                "BHP conservation",
                "BHP rehabilitation",
                "BHP EPBC",
            ],
        )

    def test_step_7_confidence_runs_without_datasets(self):
        snippet_score = combine_confidence(
            llm_confidence=0.55,
            source_count=1,
            credibility=0.86,
            full_text_used=False,
        )
        stronger_article_score = combine_confidence(
            llm_confidence=0.78,
            source_count=3,
            credibility=0.86,
            full_text_used=True,
        )

        self.assertLess(snippet_score, stronger_article_score)
        self.assertLessEqual(stronger_article_score, 0.90)

    def test_pipeline_outputs_structured_evidence(self):
        pipeline = EcoTracePipeline(
            providers=[FakeProvider()],
            extractor=KeywordLLMExtractor(),
        )

        records = pipeline.run("BHP")

        self.assertEqual(records[0].company, "BHP")
        self.assertEqual(records[0].location, "Pilbara WA")
        self.assertEqual(records[0].evidence_type, "regulatory signal")
        self.assertGreaterEqual(records[0].confidence, 0.49)

    def test_australia_only_pipeline_filters_non_australian_evidence(self):
        pipeline = EcoTracePipeline(
            providers=[NonAustralianProvider()],
            extractor=KeywordLLMExtractor(),
            australia_only=True,
        )

        self.assertEqual(pipeline.run("BHP"), [])

    def test_australia_link_detection(self):
        record = KeywordLLMExtractor().extract(
            item=ExtractionInput(
                company="BHP",
                article=ArticleMetadata(
                    title="BHP Pilbara rehabilitation",
                    snippet="Species monitoring in Western Australia.",
                    source="Guardian",
                    published_date=None,
                    url="https://example.test",
                ),
            )
        )

        self.assertTrue(is_australia_linked(record))

    def test_pipeline_returns_json_ready_output(self):
        pipeline = EcoTracePipeline(
            providers=[FakeProvider()],
            extractor=KeywordLLMExtractor(),
        )

        output = pipeline.run_json("BHP")

        self.assertEqual(output[0]["company"], "BHP")
        self.assertIn("confidence", output[0])
        self.assertNotIn("validated_with", output[0])

    def test_openrouter_extractor_reads_env_configuration(self):
        env_file = mock_open(
            read_data=(
                "OPENROUTER_API_KEY=test-key\n"
                "OPENROUTER_MODEL=nvidia/nemotron-3-super-120b-a12b:free\n"
            )
        )

        with patch.dict("os.environ", {}, clear=True):
            with patch("os.path.exists", return_value=True):
                with patch("builtins.open", env_file):
                    load_env_file(".env")
                extractor = OpenRouterLLMExtractor()

        self.assertEqual(extractor.api_key, "test-key")
        self.assertEqual(extractor.model, DEFAULT_OPENROUTER_MODEL)

    def test_llm_request_retries_transient_gateway_errors(self):
        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return None

            def read(self):
                return b'{"choices":[{"message":{"content":"{}"}}]}'

        error = urllib.error.HTTPError(
            url="https://example.test",
            code=502,
            msg="Bad Gateway",
            hdrs={},
            fp=None,
        )
        extractor = OpenRouterLLMExtractor(
            api_key="test-key",
            max_retries=1,
            retry_delay_seconds=0,
        )

        with patch("urllib.request.urlopen", side_effect=[error, FakeResponse()]):
            data = extractor._send_request_with_retries(
                urllib.request.Request("https://example.test")
            )

        self.assertIn("choices", data)

    def test_create_llm_extractor_selects_nvidia_provider(self):
        with patch.dict(
            "os.environ",
            {
                "LLM_PROVIDER": "nvidia",
                "NVIDIA_API_KEY": "test-nvidia-key",
                "NVIDIA_NIM_MODEL": "nvidia/nemotron-3-super-120b-a12b",
            },
            clear=True,
        ):
            extractor = create_llm_extractor_from_env("missing.env")

        self.assertIsInstance(extractor, NvidiaNIMLLMExtractor)
        self.assertEqual(extractor.api_key, "test-nvidia-key")

    def test_nvidia_model_name_strips_openrouter_free_suffix(self):
        self.assertEqual(
            normalize_nvidia_model_name("nvidia/nemotron-3-super-120b-a12b:free"),
            "nvidia/nemotron-3-super-120b-a12b",
        )

    def test_candidate_score_keeps_company_biodiversity_article_without_visible_location(self):
        article = ArticleMetadata(
            title="Mapping of important biodiversity and ecosystems",
            snippet="BHP describes species monitoring and habitat work.",
            source="BHP",
            published_date=None,
            url="https://www.bhp.com/news/case-studies/example",
        )

        score = article_candidate_score("BHP", article, australia_only=True)

        self.assertGreaterEqual(score, 90)

    def test_source_quality_keeps_relevant_company_environment_article(self):
        article = ArticleMetadata(
            title=(
                "16,000 hectares of forests found flattened on beef farms "
                "linked to Coles"
            ),
            snippet=(
                "The ABC reports Queensland land clearing and deforestation "
                "risk in supermarket beef supply chains."
            ),
            source="Australian Broadcasting Corporation",
            published_date=None,
            url="https://www.abc.net.au/news/coles-beef-linked-to-deforestation",
        )

        self.assertGreaterEqual(article_source_quality_score("Coles", article), 80)
        self.assertTrue(article_is_llm_worthy("Coles", article))

    def test_source_quality_rejects_generic_low_value_article(self):
        article = ArticleMetadata(
            title="News live: PM speaks as supermarket trading hours change",
            snippet="A live blog mentions Coles but does not report biodiversity evidence.",
            source="Webz.io",
            published_date=None,
            url="https://www.hilaryfarrerphysiotherapy.co.uk/live-updates",
        )

        self.assertLess(article_source_quality_score("Coles", article), 60)
        self.assertFalse(article_is_llm_worthy("Coles", article))

    def test_source_quality_rejects_sponsored_content(self):
        article = ArticleMetadata(
            title="Coles Nurture Fund helps sustainable agriculture",
            snippet="Sponsored content about agriculture and sustainability in Australia.",
            source="The Australian",
            published_date=None,
            url="https://www.theaustralian.com.au/business/sponsored-content/example",
        )

        self.assertLess(article_source_quality_score("Coles", article), 60)
        self.assertFalse(article_is_llm_worthy("Coles", article))

    def test_relevant_candidates_apply_source_quality_filter(self):
        strong_article = ArticleMetadata(
            title="Coles beef linked to deforestation in Queensland",
            snippet="ABC reports land clearing and deforestation in the beef supply chain.",
            source="Australian Broadcasting Corporation",
            published_date=None,
            url="https://www.abc.net.au/news/coles-beef-linked-to-deforestation",
        )
        weak_article = ArticleMetadata(
            title="Coles mentioned in live updates on trading hours",
            snippet="A generic update mentions biodiversity in passing.",
            source="Webz.io",
            published_date=None,
            url="https://www.hilaryfarrerphysiotherapy.co.uk/live-updates",
        )

        candidates = relevant_llm_candidates("Coles", [weak_article, strong_article])

        self.assertEqual(candidates, [strong_article])

    def test_smoke_search_queries_cover_targeted_company_topics(self):
        queries = build_company_search_queries("Coles")

        self.assertIn("Coles biodiversity Australia", queries)
        self.assertIn("Coles deforestation beef Australia", queries)
        self.assertIn("Coles sustainability report biodiversity", queries)

    def test_smoke_search_queries_use_mining_topics_for_bhp(self):
        queries = build_company_search_queries("BHP")

        self.assertIn("BHP EPBC biodiversity Australia", queries)
        self.assertIn("BHP rehabilitation mining Australia", queries)
        self.assertIn("BHP species monitoring Australia", queries)
        self.assertNotIn("BHP deforestation beef Australia", queries)

    def test_smoke_search_queries_use_agribusiness_topics_for_elders(self):
        queries = build_company_search_queries("ELDERS LIMITED")

        self.assertIn("Elders agribusiness biodiversity Australia", queries)
        self.assertIn("Elders land management biodiversity Australia", queries)
        self.assertIn("Elders natural capital agriculture Australia", queries)
        self.assertNotIn("Elders EPBC biodiversity Australia", queries)

    def test_company_search_name_normalizes_abn_legal_names(self):
        self.assertEqual(company_search_name("BHP GROUP LIMITED"), "BHP")
        self.assertEqual(company_search_name("COLES GROUP LIMITED"), "Coles")
        self.assertEqual(company_search_name("ALDI Foods Pty Limited"), "ALDI")
        self.assertEqual(company_search_name("ALCOA OF AUSTRALIA LIMITED"), "Alcoa")
        self.assertEqual(company_search_name("ELDERS LIMITED"), "Elders")
        self.assertEqual(company_search_name("Rio Tinto Limited"), "Rio Tinto")

    def test_search_queries_accept_abn_legal_names(self):
        bhp_queries = build_company_search_queries("BHP GROUP LIMITED")
        coles_queries = build_company_search_queries("COLES GROUP LIMITED")
        aldi_queries = build_company_search_queries("ALDI Foods Pty Limited")
        elders_queries = build_company_search_queries("ELDERS LIMITED")

        self.assertIn("BHP EPBC biodiversity Australia", bhp_queries)
        self.assertNotIn("BHP deforestation beef Australia", bhp_queries)
        self.assertIn("Coles deforestation beef Australia", coles_queries)
        self.assertIn("ALDI deforestation beef Australia", aldi_queries)
        self.assertIn("Elders sustainable agriculture biodiversity Australia", elders_queries)

    def test_normalizes_generic_wa_location_to_specific_jarrah_forest(self):
        article = ArticleMetadata(
            title="Alcoa penalty for clearing WA jarrah forests",
            snippet=(
                "The article describes bauxite mining impacts in the "
                "Northern Jarrah Forest."
            ),
            source="Guardian",
            published_date=None,
            url="https://example.test",
        )

        location = normalize_location(
            "Western Australia",
            ExtractionInput(company="Alcoa", article=article),
        )

        self.assertEqual(location, "Northern Jarrah Forest WA")

    def test_normalizes_jarrah_forest_location_variant(self):
        location = normalize_location("Northern Jarrah Forest, Western Australia")

        self.assertEqual(location, "Northern Jarrah Forest WA")

    def test_smoke_query_company_parser_handles_targeted_topics(self):
        self.assertEqual(
            company_from_search_query("Coles deforestation beef Australia"),
            "Coles",
        )
        self.assertEqual(
            company_from_search_query("BHP sustainability report biodiversity"),
            "BHP",
        )

    def test_parse_json_object_from_wrapped_model_output(self):
        parsed = parse_json_object(
            "```json\n{\"location\":\"Pilbara WA\",\"llm_confidence\":0.8}\n```"
        )

        self.assertEqual(parsed["location"], "Pilbara WA")

    def test_normalizes_model_evidence_type_labels(self):
        self.assertEqual(
            normalize_evidence_type("biodiversity_action"),
            "biodiversity action",
        )

    def test_quality_gate_downgrades_empty_biodiversity_signal(self):
        record = EvidenceRecordForTest(
            biodiversity_signal="none",
            evidence_type="regulatory signal",
            llm_confidence=0.8,
        ).to_record()

        quality_gate_record(
            record,
            "BHP mining operations in Australia with regulatory approvals.",
        )

        self.assertEqual(record.biodiversity_signal, "unknown")
        self.assertEqual(record.evidence_type, "unknown")
        self.assertLessEqual(record.llm_confidence, 0.25)

    def test_quality_gate_keeps_clear_biodiversity_evidence(self):
        article = ArticleMetadata(
            title="BHP Pilbara habitat rehabilitation",
            snippet="Species monitoring and habitat rehabilitation in Western Australia.",
            source="Guardian",
            published_date=None,
            url="https://example.test",
        )
        record = EvidenceRecordForTest(
            biodiversity_signal="species monitoring and habitat rehabilitation",
            evidence_type="biodiversity action",
            llm_confidence=0.8,
        ).to_record()

        quality_gate_record(record, evidence_context(article))

        self.assertEqual(record.evidence_type, "biodiversity action")
        self.assertEqual(record.llm_confidence, 0.8)

    def test_quality_gate_infers_deforestation_risk_when_type_is_unknown(self):
        article = ArticleMetadata(
            title="Coles beef linked to deforestation in Queensland",
            snippet="The article reports land clearing and deforestation risk.",
            source="ABC",
            published_date=None,
            url="https://example.test",
        )
        record = EvidenceRecordForTest(
            biodiversity_signal="deforestation risk",
            evidence_type="unknown",
            llm_confidence=0.6,
        ).to_record()

        quality_gate_record(record, evidence_context(article))

        self.assertEqual(record.evidence_type, "biodiversity risk")

    def test_quality_gate_keeps_single_specific_biodiversity_signal(self):
        article = ArticleMetadata(
            title="Coles beef linked to deforestation in Queensland",
            snippet="The article reports deforestation connected to beef sourcing.",
            source="ABC",
            published_date=None,
            url="https://example.test",
        )
        record = EvidenceRecordForTest(
            biodiversity_signal="deforestation",
            evidence_type="unknown",
            llm_confidence=0.6,
        ).to_record()

        quality_gate_record(record, evidence_context(article))

        self.assertEqual(record.evidence_type, "biodiversity risk")
        self.assertEqual(record.llm_confidence, 0.6)

    def test_quality_gate_downgrades_generic_signal_words(self):
        record = EvidenceRecordForTest(
            biodiversity_signal="True",
            evidence_type="regulatory signal",
            llm_confidence=0.95,
        ).to_record()

        quality_gate_record(
            record,
            "BHP mining approvals in Queensland mention biodiversity and habitat.",
        )

        self.assertEqual(record.evidence_type, "regulatory signal")
        self.assertLessEqual(record.llm_confidence, 0.45)

    def test_quality_gate_downgrades_weak_non_regulatory_evidence_type(self):
        record = EvidenceRecordForTest(
            biodiversity_signal="positive",
            evidence_type="biodiversity action",
            llm_confidence=0.95,
        ).to_record()

        quality_gate_record(
            record,
            "BHP describes biodiversity and conservation in Western Australia.",
        )

        self.assertEqual(record.evidence_type, "unknown")
        self.assertLessEqual(record.llm_confidence, 0.45)

    def test_quality_gate_keeps_specific_signal_even_when_short(self):
        record = EvidenceRecordForTest(
            biodiversity_signal="species monitoring",
            evidence_type="biodiversity action",
            llm_confidence=0.95,
        ).to_record()

        quality_gate_record(
            record,
            "BHP uses species monitoring and habitat rehabilitation at Olympic Dam.",
        )

        self.assertEqual(record.evidence_type, "biodiversity action")
        self.assertEqual(record.llm_confidence, 0.95)

    def test_infers_payload_when_model_returns_reasoning_without_json(self):
        article = ArticleMetadata(
            title="BHP enhances Olympic Dam biodiversity",
            snippet=(
                "BHP uses eDNA monitoring for subterranean fauna at Olympic Dam "
                "in South Australia."
            ),
            source="SmokeTest",
            published_date=None,
            url="https://example.test",
        )

        payload = infer_payload_from_text(
            "The location is Olympic Dam, South Australia.",
            ExtractionInput(company="BHP", article=article),
        )

        self.assertEqual(payload["location"], "Olympic Dam, South Australia")
        self.assertEqual(payload["activity_type"], "monitoring")
        self.assertEqual(payload["evidence_type"], "biodiversity action")

    def test_normalizes_reasoning_contaminated_location(self):
        article = ArticleMetadata(
            title="BHP enhances Olympic Dam biodiversity",
            snippet="eDNA monitoring at Olympic Dam.",
            source="SmokeTest",
            published_date=None,
            url="https://example.test",
        )

        location = normalize_location(
            "Olympic Dam, South Australia? Wait, no",
            ExtractionInput(company="BHP", article=article),
        )

        self.assertEqual(location, "Olympic Dam, South Australia")

    def test_normalizes_generic_country_location_to_specific_state_from_text(self):
        article = ArticleMetadata(
            title="Coles beef linked to deforestation in Queensland",
            snippet="The report describes clearing on cattle properties.",
            source="SmokeTest",
            published_date=None,
            url="https://example.test",
        )

        location = normalize_location(
            "Australia",
            ExtractionInput(company="Coles", article=article),
        )

        self.assertEqual(location, "Queensland")

    def test_normalizes_country_only_location_to_none_without_specific_hint(self):
        article = ArticleMetadata(
            title="Coles sustainability report",
            snippet="The report discusses national supply chain goals.",
            source="SmokeTest",
            published_date=None,
            url="https://example.test",
        )

        location = normalize_location(
            "Australia",
            ExtractionInput(company="Coles", article=article),
        )

        self.assertIsNone(location)

    def test_article_retriever_extracts_visible_text(self):
        html = (
            "<html><head><title>ignore</title><script>hidden()</script></head>"
            "<body><h1>BHP Pilbara rehabilitation</h1>"
            "<p>Species monitoring under approval conditions.</p></body></html>"
        ).encode("utf-8")

        class FakeResponse:
            headers = {"Content-Type": "text/html; charset=utf-8"}

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return None

            def read(self):
                return html

        with patch("urllib.request.urlopen", return_value=FakeResponse()):
            text = SimpleArticleTextRetriever().fetch_text("https://example.test")

        self.assertIn("BHP Pilbara rehabilitation", text)
        self.assertIn("Species monitoring", text)
        self.assertNotIn("hidden", text)

    def test_uploaded_report_reader_reads_plain_text(self):
        report_text = (
            "The sustainability report identifies biodiversity risk from land "
            "clearing in Queensland supply chains."
        )

        with patch("builtins.open", mock_open(read_data=report_text)):
            with patch("os.path.exists", return_value=True):
                with patch("os.path.isfile", return_value=True):
                    text = UploadedReportTextReader().read_text("report.txt")

        self.assertIn("biodiversity risk", text)
        self.assertIn("Queensland", text)

    def test_uploaded_report_reader_extracts_html_visible_text(self):
        report_html = (
            "<html><head><script>hidden()</script></head>"
            "<body><h1>Nature risk</h1><p>Biodiversity habitat loss.</p></body></html>"
        )

        with patch("builtins.open", mock_open(read_data=report_html)):
            with patch("os.path.exists", return_value=True):
                with patch("os.path.isfile", return_value=True):
                    text = UploadedReportTextReader().read_text("report.html")

        self.assertIn("Nature risk", text)
        self.assertIn("Biodiversity habitat loss", text)
        self.assertNotIn("hidden", text)

    def test_uploaded_report_reader_selects_biodiversity_passages(self):
        front_matter = " ".join(["financial overview"] * 600)
        biodiversity_section = (
            "Queensland biodiversity risk includes habitat disturbance, "
            "species impact, and rehabilitation monitoring."
        )
        report_text = f"{front_matter} {biodiversity_section}"

        with patch("builtins.open", mock_open(read_data=report_text)):
            with patch("os.path.exists", return_value=True):
                with patch("os.path.isfile", return_value=True):
                    text = UploadedReportTextReader(max_chars=900).read_text("report.txt")

        self.assertIn("Queensland biodiversity risk", text)
        self.assertLess(len(text), len(report_text))

    def test_uploaded_report_reader_prioritizes_risk_passages(self):
        nature_positive = (
            "The company reports nature-positive biodiversity conservation, "
            "restoration, regenerative management and natural capital accounting. "
        ) * 20
        risk_section = (
            "The report identifies risk of direct impacts to ecosystems that "
            "could affect IUCN Red List threatened species."
        )
        report_text = f"{nature_positive} {risk_section}"

        with patch("builtins.open", mock_open(read_data=report_text)):
            with patch("os.path.exists", return_value=True):
                with patch("os.path.isfile", return_value=True):
                    text = UploadedReportTextReader(max_chars=900).read_text("report.txt")

        self.assertIn("risk of direct impacts to ecosystems", text)
        self.assertIn("threatened species", text)

    def test_uploaded_report_reader_can_return_multiple_chunks(self):
        risk_section = (
            "Queensland biodiversity risk includes habitat disturbance and "
            "threatened species impact. "
        ) * 10
        action_section = (
            "South Australia biodiversity conservation includes restoration "
            "and monitoring. "
        ) * 10

        with patch("os.path.exists", return_value=True):
            with patch("os.path.isfile", return_value=True):
                with patch.object(
                    UploadedReportTextReader,
                    "_read_report_pages",
                    return_value=[(1, risk_section), (2, action_section)],
                ):
                    chunks = UploadedReportTextReader(max_chars=900).read_chunks(
                        "report.txt",
                        max_chunks=2,
                    )

        self.assertEqual(len(chunks), 2)
        self.assertTrue(all(len(chunk) <= 900 for chunk in chunks))
        self.assertTrue(any("Queensland biodiversity risk" in chunk for chunk in chunks))
        self.assertTrue(any("South Australia biodiversity" in chunk for chunk in chunks))

    def test_uploaded_report_reader_scans_evidence_with_page_metadata(self):
        report_text = (
            "The report identifies biodiversity risk from unauthorised clearing "
            "of high value vegetation in Queensland."
        )

        with patch("builtins.open", mock_open(read_data=report_text)):
            with patch("os.path.exists", return_value=True):
                with patch("os.path.isfile", return_value=True):
                    excerpts = UploadedReportTextReader(max_chars=500).scan_evidence(
                        "report.txt",
                        max_excerpts=1,
                    )

        self.assertEqual(excerpts[0].page_number, 1)
        self.assertGreater(excerpts[0].score, 0)
        self.assertIn("biodiversity", excerpts[0].matched_terms)
        self.assertIn("unauthorised clearing", excerpts[0].text)

    def test_uploaded_report_reader_excerpt_starts_near_evidence_sentence(self):
        report_text = (
            "Introductory context about company operations. "
            "This sentence is not relevant. "
            "We do not explore, extract resources or operate where there is a "
            "risk of direct impacts to ecosystems that could result in the "
            "extinction of an IUCN Red List Threatened Species in the wild. "
            "Trailing governance context."
        )

        with patch("builtins.open", mock_open(read_data=report_text)):
            with patch("os.path.exists", return_value=True):
                with patch("os.path.isfile", return_value=True):
                    excerpts = UploadedReportTextReader(max_chars=180).scan_evidence(
                        "report.txt",
                        max_excerpts=1,
                    )

        self.assertTrue(excerpts[0].text.startswith("We do not explore"))
        self.assertIn("risk of direct impacts", excerpts[0].text)

    def test_uploaded_report_reader_ignores_generic_risk_without_biodiversity_context(self):
        report_text = "Forward-looking statements involve business risk and uncertainty."

        with patch("builtins.open", mock_open(read_data=report_text)):
            with patch("os.path.exists", return_value=True):
                with patch("os.path.isfile", return_value=True):
                    excerpts = UploadedReportTextReader(max_chars=500).scan_evidence(
                        "report.txt",
                        max_excerpts=1,
                    )

        self.assertEqual(excerpts[0].score, 0)
        self.assertEqual(excerpts[0].matched_terms, [])

    def test_report_article_metadata_marks_uploaded_report_source(self):
        article = report_article_metadata(
            "reports/coles-annual-report.txt",
            "Biodiversity risk in the beef supply chain.",
        )

        self.assertEqual(article.source, "coles-annual-report.txt")
        self.assertEqual(article.source_type, "report")
        self.assertIn("Uploaded sustainability or annual report", article.title)

    def test_resolve_report_paths_uses_explicit_paths_first(self):
        paths = resolve_report_paths(
            ["reports/a.pdf", "reports/a.pdf", "reports/b.txt"],
            reports_dir="missing",
        )

        self.assertEqual(paths, ["reports/a.pdf", "reports/b.txt"])

    def test_resolve_report_paths_discovers_supported_local_reports(self):
        def fake_isdir(path):
            return path == "reports"

        def fake_isfile(path):
            return not path.endswith("nested")

        with patch("os.path.isdir", side_effect=fake_isdir):
            with patch("os.listdir", return_value=["b.pdf", "a.txt", "notes.tmp", "nested"]):
                with patch("os.path.isfile", side_effect=fake_isfile):
                    paths = resolve_report_paths([], reports_dir="reports")

        self.assertEqual(paths, [os.path.join("reports", "a.txt"), os.path.join("reports", "b.pdf")])

    def test_builds_location_options_for_user_choice(self):
        records = [
            EvidenceRecordForTest(
                location="Olympic Dam SA",
                biodiversity_signal="habitat monitoring",
                evidence_type="biodiversity action",
                llm_confidence=0.9,
                confidence=0.82,
            ).to_record(),
            EvidenceRecordForTest(
                location="Pilbara WA",
                biodiversity_signal="species monitoring",
                evidence_type="biodiversity action",
                llm_confidence=0.8,
                confidence=0.70,
            ).to_record(),
        ]

        options = build_location_options(records)

        self.assertEqual(options[0].location, "Olympic Dam SA")
        self.assertEqual(options[0].record_count, 1)
        self.assertEqual(options[0].top_confidence, 0.82)

    def test_location_options_group_multiple_records_by_confidence(self):
        records = [
            EvidenceRecordForTest(
                location="Olympic Dam SA",
                biodiversity_signal="eDNA monitoring of subterranean fauna",
                evidence_type="biodiversity action",
                llm_confidence=0.95,
                confidence=0.88,
            ).to_record(),
            EvidenceRecordForTest(
                location="Pilbara WA",
                biodiversity_signal="habitat rehabilitation",
                evidence_type="biodiversity action",
                llm_confidence=0.85,
                confidence=0.78,
            ).to_record(),
            EvidenceRecordForTest(
                location="Olympic Dam SA",
                biodiversity_signal="species monitoring",
                evidence_type="biodiversity action",
                llm_confidence=0.75,
                confidence=0.69,
            ).to_record(),
        ]

        options = build_location_options(records)

        self.assertEqual(options[0].location, "Olympic Dam SA")
        self.assertEqual(options[0].record_count, 2)
        self.assertEqual(options[0].top_confidence, 0.88)
        self.assertEqual(options[1].location, "Pilbara WA")

    def test_location_options_exclude_country_only_and_unknown_locations(self):
        records = [
            EvidenceRecordForTest(
                location="Australia",
                biodiversity_signal="deforestation risk",
                evidence_type="biodiversity risk",
                llm_confidence=0.7,
                confidence=0.6,
            ).to_record(),
            EvidenceRecordForTest(
                location=None,
                biodiversity_signal="deforestation risk",
                evidence_type="biodiversity risk",
                llm_confidence=0.7,
                confidence=0.6,
            ).to_record(),
            EvidenceRecordForTest(
                location="Mount Garnet, Queensland",
                biodiversity_signal="deforestation risk",
                evidence_type="biodiversity risk",
                llm_confidence=0.7,
                confidence=0.6,
            ).to_record(),
        ]

        options = build_location_options(records)

        self.assertEqual(len(options), 1)
        self.assertEqual(options[0].location, "Mount Garnet, Queensland")


class EvidenceRecordForTest:
    def __init__(
        self,
        biodiversity_signal: str,
        evidence_type: str,
        llm_confidence: float,
        location: str = "Australia",
        confidence: float = 0.0,
    ) -> None:
        self.biodiversity_signal = biodiversity_signal
        self.evidence_type = evidence_type
        self.llm_confidence = llm_confidence
        self.location = location
        self.confidence = confidence

    def to_record(self):
        return EvidenceRecord(
            company="BHP",
            location=self.location,
            activity_type="mining",
            biodiversity_signal=self.biodiversity_signal,
            evidence_type=self.evidence_type,
            source_type="news",
            source="SmokeTest",
            source_url="https://example.test",
            source_date=None,
            llm_confidence=self.llm_confidence,
            confidence=self.confidence,
            notes=None,
        )


if __name__ == "__main__":
    unittest.main()

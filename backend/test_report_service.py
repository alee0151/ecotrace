import os
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

BACKEND_ROOT = Path(__file__).resolve().parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from report_service import (
    create_persisted_report,
    deliver_report_email,
    render_report_html,
    valid_email,
)


class FakeReportCursor:
    def __init__(self):
        self.last_query = ""
        self.inserted = None

    def execute(self, query, params=()):
        self.last_query = " ".join(query.split()).lower()
        self.params = params

    def fetchone(self):
        if "from search_query" in self.last_query:
            return {
                "query_id": "11111111-1111-1111-1111-111111111111",
                "input_type": "company_name",
                "input_value": "BHP",
                "resolution_status": "resolved",
                "submitted_at": datetime(2026, 5, 4, 9, 0, 0),
                "resolved_company_id": "22222222-2222-2222-2222-222222222222",
                "resolved_brand_id": None,
                "resolved_product_id": None,
                "legal_name": "BHP GROUP LIMITED",
                "abn": "49004028077",
                "entity_type": "LTD",
                "company_status": "registered",
                "state": "VIC",
                "postcode": "3000",
                "gst_registered": True,
                "brand_name": None,
                "product_name": None,
                "barcode": None,
                "manufacturer_name": None,
            }
        if "insert into report" in self.last_query:
            return {
                "report_id": "33333333-3333-3333-3333-333333333333",
                "query_id": "11111111-1111-1111-1111-111111111111",
                "title": "EcoTrace biodiversity report - BHP GROUP LIMITED",
                "format": "html",
                "status": "generated",
                "generated_at": datetime(2026, 5, 4, 9, 1, 0),
                "sent_at": None,
                "recipient_email": None,
                "delivery_method": None,
            }
        return None

    def fetchall(self):
        if "from inferred_location" in self.last_query:
            return [
                {
                    "label": "Melbourne CBD",
                    "state": "VIC",
                    "postcode": "3000",
                    "country": "AU",
                    "latitude": -37.8136,
                    "longitude": 144.9631,
                    "confidence": "high",
                    "source_type": "abn",
                    "address_raw": "ABN registered address: VIC 3000",
                    "extracted_at": datetime(2026, 5, 4, 9, 0, 0),
                }
            ]
        return []


class ReportServiceTests(unittest.TestCase):
    def test_valid_email_rejects_invalid_address(self):
        self.assertTrue(valid_email("analyst@example.com"))
        self.assertFalse(valid_email("not-an-email"))

    def test_create_persisted_report_builds_metadata_and_html(self):
        cursor = FakeReportCursor()
        saved = create_persisted_report(
            cursor,
            "11111111-1111-1111-1111-111111111111",
            {
                "reports": {
                    "evidence": [
                        {
                            "biodiversity_signal": "habitat disturbance",
                            "evidence_type": "biodiversity risk",
                            "source": "uploaded-report.pdf",
                            "confidence": 0.82,
                        }
                    ]
                }
            },
        )

        self.assertEqual(saved["report_id"], "33333333-3333-3333-3333-333333333333")
        self.assertEqual(saved["metadata_json"]["summary"]["report_evidence_count"], 1)
        self.assertIn("BHP GROUP LIMITED", saved["metadata_json"]["title"])

    def test_render_report_html_returns_printable_document(self):
        cursor = FakeReportCursor()
        saved = create_persisted_report(cursor, "11111111-1111-1111-1111-111111111111")

        html = render_report_html(saved["metadata_json"])

        self.assertIn("<!doctype html>", html)
        self.assertIn("Company Snapshot", html)
        self.assertIn("Inferred Spatial Context", html)

    def test_email_without_smtp_writes_outbox_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch("report_service.REPORT_OUTBOX_DIR", new=Path(tmp)):
                with patch.dict(os.environ, {"EMAIL_DELIVERY_MODE": "auto", "SMTP_HOST": "", "REPORT_FROM_EMAIL": ""}, clear=False):
                    result = deliver_report_email(
                        "analyst@example.com",
                        "EcoTrace report",
                        "<html><body>Report</body></html>",
                    )

            self.assertEqual(result["delivery"], "outbox")
            self.assertTrue(os.path.exists(result["path"]))

    def test_forced_smtp_requires_configuration(self):
        with patch.dict(os.environ, {"EMAIL_DELIVERY_MODE": "smtp", "SMTP_HOST": "", "REPORT_FROM_EMAIL": ""}, clear=False):
            with self.assertRaises(RuntimeError):
                deliver_report_email(
                    "analyst@example.com",
                    "EcoTrace verification",
                    "<html><body>Verify</body></html>",
                )

    def test_smtp_delivery_uses_configured_server(self):
        class FakeSMTP:
            sent = False
            logged_in = False
            tls_started = False

            def __init__(self, host, port, timeout):
                self.host = host
                self.port = port
                self.timeout = timeout

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def starttls(self):
                FakeSMTP.tls_started = True

            def login(self, username, password):
                FakeSMTP.logged_in = username == "user" and password == "pass"

            def send_message(self, message):
                FakeSMTP.sent = message["To"] == "analyst@example.com"

        env = {
            "EMAIL_DELIVERY_MODE": "smtp",
            "SMTP_HOST": "smtp.example.com",
            "SMTP_PORT": "587",
            "SMTP_USERNAME": "user",
            "SMTP_PASSWORD": "pass",
            "SMTP_USE_TLS": "true",
            "SMTP_USE_SSL": "false",
            "REPORT_FROM_EMAIL": "noreply@example.com",
        }
        with patch.dict(os.environ, env, clear=False):
            with patch("report_service.smtplib.SMTP", new=FakeSMTP):
                result = deliver_report_email(
                    "analyst@example.com",
                    "EcoTrace verification",
                    "<html><body>Verify</body></html>",
                )

        self.assertEqual(result["delivery"], "smtp")
        self.assertTrue(FakeSMTP.tls_started)
        self.assertTrue(FakeSMTP.logged_in)
        self.assertTrue(FakeSMTP.sent)


if __name__ == "__main__":
    unittest.main()

import json
from pathlib import Path

from app.services.filings_fetcher_jp import FilingsFetcherJP


class FakeEdinetClient:
    def __init__(self, xbrl_path):
        self.xbrl_path = Path(xbrl_path)
        self.last_call = None

    def list_documents(self, code, form_codes=None, limit=10, use_security_code=False):
        self.last_call = {
            "code": code,
            "use_security_code": use_security_code,
        }
        return [{"docID": "DUMMY"}]

    def download_document(self, doc_id):
        return self.xbrl_path  # not used in stub

    def extract_primary_xbrl(self, zip_path):
        return self.xbrl_path


def test_fetch_recent_filings_reads_mapping(tmp_path):
    fixture = Path("tests/fixtures/sample_jp.xbrl")
    mapping_path = tmp_path / "mapping.json"
    mapping_path.write_text(json.dumps([
        {"code": "7203", "edinet_code": "E05653"}
    ]))

    fetcher = FilingsFetcherJP(
        FakeEdinetClient(fixture),
        cache=None,
        mapping_file=str(mapping_path),
    )

    metrics = fetcher.fetch_recent_filings("7203", years=1)
    assert "revenue" in metrics
    assert metrics["revenue"][-1]["value"] == 1000000.0


def test_fetch_recent_filings_uses_security_code_when_numeric(tmp_path):
    fixture = Path("tests/fixtures/sample_jp.xbrl")
    mapping_path = tmp_path / "mapping.json"
    mapping_path.write_text("[]")

    client = FakeEdinetClient(fixture)
    fetcher = FilingsFetcherJP(
        client,
        cache=None,
        mapping_file=str(mapping_path),
    )

    fetcher.fetch_recent_filings("6857", years=1)
    assert client.last_call["use_security_code"] is True

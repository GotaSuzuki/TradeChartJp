import pathlib

from app.parsers.xbrl_parser import XbrlParser


def test_parse_file_extracts_japanese_metrics(tmp_path):
    fixture = pathlib.Path("tests/fixtures/sample_jp.xbrl")
    parser = XbrlParser()

    metrics = parser.parse_file(str(fixture))

    assert "revenue" in metrics
    series = metrics["revenue"]
    years = [entry["year"] for entry in series]
    assert years == [2022, 2023]
    values = [entry["value"] for entry in series]
    assert values == [900000.0, 1000000.0]

    operating = metrics["operating_income"]
    assert operating[-1]["value"] == 200000.0

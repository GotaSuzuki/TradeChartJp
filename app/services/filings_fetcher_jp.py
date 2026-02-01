"""EDINET から財務データを取得して正規化する。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from app.cache import DataCache

from ..clients.edinet_client import EdinetClient
from ..parsers.xbrl_parser import XbrlParser


class FilingsFetcherJP:
    def __init__(
        self,
        client: EdinetClient,
        *,
        cache: Optional[DataCache] = None,
        cache_ttl_hours: int = 12,
        mapping_file: str = "data/mappings/code_mapping.json",
    ) -> None:
        self.client = client
        self.cache = cache
        self.cache_ttl_hours = cache_ttl_hours
        self.mapping = _load_mapping(mapping_file)
        self.parser = XbrlParser()

    def fetch_recent_filings(
        self,
        code: str,
        *,
        years: int,
        form_codes: Optional[Iterable[str]] = None,
    ) -> Dict[str, List[dict]]:
        if years <= 0:
            return {}

        mapping = self.mapping.get(code)
        edinet_code = mapping.get("edinet_code") if mapping else code
        cache_key = f"edinet:{edinet_code}:{years}"
        if self.cache:
            cached = self.cache.get(cache_key)
            if cached:
                return cached

        use_security_code = False
        lookup_code = edinet_code
        if mapping and mapping.get("edinet_code"):
            lookup_code = mapping["edinet_code"]
        else:
            lookup_code = code
            if str(code).isdigit():
                use_security_code = True

        rows = self.client.list_documents(
            lookup_code,
            form_codes=form_codes or ("120", "130"),
            limit=years,
            use_security_code=use_security_code,
        )
        metrics: Dict[str, List[dict]] = {}
        for row in rows:
            doc_id = row.get("docID")
            if not doc_id:
                continue
            zip_path = self.client.download_document(doc_id)
            xbrl_path = self.client.extract_primary_xbrl(zip_path)
            if not xbrl_path:
                continue
            parsed = self.parser.parse_file(str(xbrl_path))
            metrics = _merge_metric_dict(metrics, parsed)

        if self.cache:
            self.cache.set(cache_key, metrics, self.cache_ttl_hours)
        return metrics


def _merge_metric_dict(
    base: Dict[str, List[dict]],
    new_metrics: Dict[str, List[dict]],
) -> Dict[str, List[dict]]:
    for metric, series in new_metrics.items():
        existing = base.setdefault(metric, [])
        combined = {item["year"]: item for item in existing if item.get("year") is not None}
        for item in series:
            year = item.get("year")
            if year is None:
                continue
            combined[year] = item
        base[metric] = sorted(combined.values(), key=lambda x: x.get("year"))
    return base


def _load_mapping(path: str) -> Dict[str, Dict[str, Any]]:
    mapping_path = Path(path)
    if not mapping_path.exists():
        return {}
    try:
        data = json.loads(mapping_path.read_text())
    except (OSError, json.JSONDecodeError):
        return {}
    result = {}
    for entry in data:
        code = str(entry.get("code"))
        if not code:
            continue
        result[code] = entry
    return result

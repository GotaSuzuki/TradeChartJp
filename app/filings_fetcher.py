"""SEC 10-Kの取得と正規化を担うモジュール。"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from .cache import DataCache
from .edgar_client import EdgarClient


class FilingsFetcher:
    """Fetches recent 10-K submissions and attaches company facts."""

    def __init__(
        self,
        client: EdgarClient,
        *,
        cache: Optional[DataCache] = None,
        cache_ttl_hours: int = 12,
    ) -> None:
        self.client = client
        self.cache = cache
        self.cache_ttl_hours = cache_ttl_hours

    def fetch_recent_filings(self, ticker: str, *, years: int) -> List[Dict[str, Any]]:
        if years <= 0:
            return []

        submissions = self._cached_fetch(
            f"submissions:{ticker.lower()}",
            lambda: self.client.get_filings(ticker, form_type="10-K"),
        )
        company_facts = self._cached_fetch(
            f"company_facts:{ticker.lower()}",
            lambda: self.client.get_company_facts(ticker),
        )

        recent = (submissions.get("filings", {}) or {}).get("recent", {})
        if not recent:
            return []

        records = self._normalize_recent_filings(recent)
        unique_years = []
        seen_years = set()
        for record in records:
            fiscal_year = record.get("fiscal_year")
            if fiscal_year is None:
                continue
            if fiscal_year in seen_years:
                continue
            seen_years.add(fiscal_year)
            unique_years.append(record)
            if len(unique_years) >= years:
                break

        # ソートして最新を最後に（時間軸を揃える）
        unique_years.sort(key=lambda item: item.get("fiscal_year", 0))

        if unique_years:
            self.client.download_filings(ticker, limit=len(unique_years))

        enriched = []
        for record in unique_years:
            enriched.append({
                "meta": record,
                "facts": company_facts,
            })

        return enriched

    # ------------------------------------------------------------------
    def _cached_fetch(self, key: str, loader: Callable[[], Dict[str, Any]]) -> Dict[str, Any]:
        if self.cache:
            cached = self.cache.get(key)
            if cached is not None:
                return cached

        data = loader()
        if self.cache:
            self.cache.set(key, data, self.cache_ttl_hours)
        return data

    def _normalize_recent_filings(self, filings: Dict[str, List[Any]]) -> List[Dict[str, Any]]:
        forms = filings.get("form", [])
        filed_dates = filings.get("filed") or filings.get("filingDate", [])
        report_dates = filings.get("reportDate", [])
        accession_numbers = filings.get("accessionNumber", [])

        fiscal_years = filings.get("fy") or []
        total = len(forms)
        records = []
        for idx in range(total):
            fiscal_year = _safe_int_from_list(fiscal_years, idx)

            record = {
                "form": forms[idx] if idx < len(forms) else None,
                "filed": filed_dates[idx] if idx < len(filed_dates) else None,
                "report_date": report_dates[idx] if idx < len(report_dates) else None,
                "accession_number": accession_numbers[idx] if idx < len(accession_numbers) else None,
            }

            if fiscal_year is not None:
                record["fiscal_year"] = fiscal_year
            else:
                derived = _derive_year_from_dates(record)
                record["fiscal_year"] = derived

            records.append(record)

        # 提出日が新しいものから順にする
        records.sort(key=lambda item: item.get("filed") or "", reverse=True)
        return records


def _safe_int_from_list(values: List[Any], index: int) -> Optional[int]:
    if not values or index >= len(values):
        return None
    try:
        return int(values[index])
    except (ValueError, TypeError):
        return None


def _derive_year_from_dates(record: Dict[str, Any]) -> Optional[int]:
    for key in ("report_date", "filed"):
        raw = record.get(key)
        if not raw:
            continue
        try:
            return datetime.fromisoformat(str(raw)).year
        except ValueError:
            try:
                return int(str(raw)[:4])
            except ValueError:
                continue
    return None

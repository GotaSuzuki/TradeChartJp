"""SEC EDGAR APIクライアント (sec-edgar-downloader連携)。"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

import requests
from sec_edgar_downloader import Downloader


class EdgarClient:
    COMPANY_FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts"
    SUBMISSIONS_URL = "https://data.sec.gov/submissions"

    def __init__(
        self,
        *,
        company_name: str,
        email_address: str,
        download_dir: str = "data/raw",
        session: Optional[requests.Session] = None,
    ) -> None:
        if not company_name or not email_address:
            raise ValueError("company_name と email_address は必須です")

        download_path = Path(download_dir)
        download_path.mkdir(parents=True, exist_ok=True)

        self.downloader = Downloader(company_name, email_address, download_path)
        self.user_agent = self.downloader.user_agent
        self._session = session or requests.Session()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def get_company_facts(self, ticker_or_cik: str) -> Dict[str, Any]:
        cik = self._lookup_cik(ticker_or_cik)
        url = f"{self.COMPANY_FACTS_URL}/CIK{cik}.json"
        return self._get_json(url)

    def get_filings(self, ticker_or_cik: str, form_type: str = "10-K") -> Dict[str, Any]:
        cik = self._lookup_cik(ticker_or_cik)
        url = f"{self.SUBMISSIONS_URL}/CIK{cik}.json"
        data = self._get_json(url)

        if not form_type:
            return data

        filings = data.get("filings", {}).get("recent") or {}
        forms = [form.upper() for form in filings.get("form", [])]
        mask = [form == form_type.upper() for form in forms]

        if not mask or not any(mask):
            return data

        filtered_recent: Dict[str, Any] = {}
        for key, values in filings.items():
            filtered_recent[key] = [value for value, keep in zip(values, mask) if keep]

        new_data = dict(data)
        new_filings = dict(new_data.get("filings", {}))
        new_filings["recent"] = filtered_recent
        new_data["filings"] = new_filings
        return new_data

    def download_filings(self, ticker_or_cik: str, *, limit: int, include_details: bool = True) -> int:
        """Download filings locally via sec-edgar-downloader."""

        return self.downloader.get(
            "10-K",
            ticker_or_cik,
            limit=limit,
            download_details=include_details,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _headers(self) -> Dict[str, str]:
        return {
            "User-Agent": self.user_agent,
            "Accept-Encoding": "gzip, deflate",
        }

    def _get_json(self, url: str) -> Dict[str, Any]:
        response = self._session.get(url, headers=self._headers(), timeout=30)
        response.raise_for_status()
        return response.json()

    def _lookup_cik(self, ticker_or_cik: str) -> str:
        identifier = ticker_or_cik.strip()
        if not identifier:
            raise ValueError("ticker/CIK を指定してください")

        if identifier.isdigit():
            return f"{int(identifier):010d}"

        mapping = self.downloader.ticker_to_cik_mapping
        try:
            return mapping[identifier.upper()]
        except KeyError as exc:
            raise ValueError(f"Unknown ticker: {ticker_or_cik}") from exc

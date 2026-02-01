"""EDINET API クライアント。"""

from __future__ import annotations

import json
import zipfile
from datetime import date as date_cls, timedelta
from pathlib import Path
from typing import Dict, Iterable, List, Optional

import requests


class EdinetClient:
    BASE_URL = "https://disclosure.edinet-fsa.go.jp/api/v2"

    def __init__(
        self,
        *,
        user_agent: str,
        download_dir: str,
        session: Optional[requests.Session] = None,
    ) -> None:
        self.user_agent = user_agent
        self.download_dir = Path(download_dir)
        self.download_dir.mkdir(parents=True, exist_ok=True)
        self.session = session or requests.Session()
        self._daily_cache: Dict[str, List[Dict[str, str]]] = {}

    # ------------------------------------------------------------------
    def list_documents(
        self,
        code: str,
        *,
        form_codes: Optional[Iterable[str]] = None,
        limit: int = 10,
        use_security_code: bool = False,
    ) -> List[Dict[str, str]]:
        results: List[Dict[str, str]] = []
        seen_doc_ids = set()
        allowed_forms = {code.upper() for code in form_codes} if form_codes else None
        target_code = self._normalize_code(code, use_security_code)

        current_date = date_cls.today()
        max_days = max(limit * 400, 400)
        while len(results) < limit and max_days > 0:
            date_str = current_date.strftime("%Y-%m-%d")
            daily_rows = self._fetch_documents_by_date(date_str)
            for row in daily_rows:
                if allowed_forms and row.get("docTypeCode") not in allowed_forms:
                    continue
                candidate = row.get("secCode") if use_security_code else row.get("edinetCode")
                if not candidate:
                    continue
                normalized = self._normalize_code(str(candidate), use_security_code)
                if normalized != target_code:
                    continue
                doc_id = row.get("docID")
                if not doc_id or doc_id in seen_doc_ids:
                    continue
                results.append(row)
                seen_doc_ids.add(doc_id)
                if len(results) >= limit:
                    break
            current_date -= timedelta(days=1)
            max_days -= 1

        results.sort(key=lambda row: row.get("submitDateTime", ""), reverse=True)
        return results[:limit]

    def download_document(self, doc_id: str) -> Path:
        """docID の ZIP を保存し、そのパスを返す。"""

        url = f"{self.BASE_URL}/documents/{doc_id}"
        params = {"type": 1}  # ZIP (type=1)
        response = self._request("GET", url, params=params)
        path = self.download_dir / f"{doc_id}.zip"
        path.write_bytes(response.content)
        return path

    def extract_primary_xbrl(self, zip_path: Path) -> Optional[Path]:
        """ZIP からメインとなる XBRL ファイルを展開して返す。"""

        if not zip_path.exists():
            return None

        output_dir = zip_path.with_suffix("")
        output_dir.mkdir(parents=True, exist_ok=True)
        target_path: Optional[Path] = None
        with zipfile.ZipFile(zip_path) as archive:
            for member in archive.namelist():
                lower = member.lower()
                if not lower.endswith(".xbrl"):
                    continue
                dest = output_dir / Path(member).name
                with archive.open(member) as src:
                    dest.write_bytes(src.read())
                if target_path is None:
                    target_path = dest
        return target_path

    def download_json_metadata(self, doc_id: str) -> Dict[str, str]:
        url = f"{self.BASE_URL}/documents/{doc_id}"
        params = {"type": 2}  # metadata JSON
        response = self._request("GET", url, params=params)
        return json.loads(response.content.decode("utf-8"))

    # ------------------------------------------------------------------
    def _fetch_documents_by_date(self, date_str: str) -> List[Dict[str, str]]:
        if date_str in self._daily_cache:
            return self._daily_cache[date_str]

        url = f"{self.BASE_URL}/documents.json"
        params = {"date": date_str, "type": 2}
        try:
            response = self._request("GET", url, params=params)
        except requests.HTTPError as exc:
            if exc.response is not None and exc.response.status_code == 404:
                self._daily_cache[date_str] = []
                return []
            raise
        payload = response.json()
        rows = payload.get("results", [])
        self._daily_cache[date_str] = rows
        return rows

    @staticmethod
    def _normalize_code(code: str, is_security_code: bool) -> str:
        if is_security_code:
            return str(code).lstrip("0")
        return str(code).upper()

    def _request(self, method: str, url: str, **kwargs):
        headers = kwargs.pop("headers", {})
        headers.setdefault("User-Agent", self.user_agent)
        headers.setdefault("Accept", "application/json")
        response = self.session.request(
            method,
            url,
            headers=headers,
            timeout=30,
            **kwargs,
        )
        response.raise_for_status()
        return response

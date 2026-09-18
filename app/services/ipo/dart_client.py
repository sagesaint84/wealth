from __future__ import annotations

import io
import json
import logging
import os
import re
import zipfile
from typing import Any
from urllib.parse import urlencode

import httpx

logger = logging.getLogger(__name__)

DART_BASE_URL = "https://opendart.fss.or.kr/api"


class DartClientError(RuntimeError):
    """Base exception for DART client errors."""


class DartAuthError(DartClientError):
    """Raised on configuration or authentication failure (e.g. 010, 011, 012)."""


class DartRateLimitError(DartClientError):
    """Raised when request rate limit is exceeded (e.g. 020)."""


class DartNoData(DartClientError):
    """Raised when no data is found for request (e.g. 013, 014)."""


class DartRequestError(DartClientError):
    """Raised on request contract or parameter error (e.g. 100)."""


class DartSourceError(DartClientError):
    """Raised on DART system inspection, maintenance, or internal error (e.g. 800, 900)."""


def extract_document_text_from_zip(zip_bytes: bytes) -> str:
    """Extract document text from OpenDART document ZIP binary.

    Selection strategy:
    1. Inspect all files in the ZIP archive.
    2. Exclude 0-byte entries and non-document files.
    3. Filter for .xml, .html, .htm extensions.
    4. Deterministically select and sort meaningful content candidates.
    5. Decode using UTF-8 with fallback to CP949 / EUC-KR.
    """
    if not zip_bytes:
        raise DartClientError("ZIP archive bytes are empty")

    try:
        zf = zipfile.ZipFile(io.BytesIO(zip_bytes))
    except Exception as exc:
        raise DartClientError(f"Corrupt or invalid ZIP archive: {exc}") from exc

    infolist = [info for info in zf.infolist() if not info.is_dir() and info.file_size > 0]
    if not infolist:
        raise DartClientError("ZIP archive contains no readable document files")

    valid_exts = {".xml", ".html", ".htm"}
    candidates = [info for info in infolist if any(info.filename.lower().endswith(ext) for ext in valid_exts)]
    if not candidates:
        candidates = infolist

    # Sort candidates deterministically: XML/HTML first, larger files first, then filename
    def sort_key(info: zipfile.ZipInfo):
        fname = info.filename.lower()
        is_xml = fname.endswith(".xml")
        is_html = fname.endswith(".html") or fname.endswith(".htm")
        ext_score = 0 if is_xml else (1 if is_html else 2)
        return (ext_score, -info.file_size, info.filename)

    candidates.sort(key=sort_key)

    extracted_texts: list[str] = []
    for info in candidates:
        try:
            raw = zf.read(info)
        except Exception as exc:
            raise DartClientError(f"Failed to read entry {info.filename} from ZIP: {exc}") from exc

        decoded = None
        for enc in ("utf-8", "cp949", "euc-kr"):
            try:
                decoded = raw.decode(enc)
                break
            except UnicodeDecodeError:
                continue

        if decoded is None:
            raise DartClientError(f"Failed to decode entry {info.filename} with utf-8 or cp949/euc-kr")

        extracted_texts.append(decoded)

    if not extracted_texts:
        raise DartClientError("Failed to extract readable text from ZIP archive")

    # Combine candidates deterministically so multi-document filings are fully available to parser
    return "\n\n<!-- NEXT_DOCUMENT_SECTION -->\n\n".join(extracted_texts)


ALLOWED_REPORT_TITLES = (
    "증권신고서(지분증권)",
    "[기재정정]증권신고서(지분증권)",
    "[발행조건확정]증권신고서(지분증권)",
    "[정정]증권신고서(지분증권)",
    "투자설명서(지분증권)",
    "투자설명서",
)

EXCLUDED_REPORT_KEYWORDS = (
    "증권발행실적보고서",
    "채무증권",
    "파생결합증권",
    "사채",
)


def select_point_in_time_filing(
    filings: list[dict[str, Any]],
    score_as_of: str,
) -> dict[str, Any] | None:
    """Select latest valid filing strictly on or before score_as_of date.

    Excludes:
    - Reports after score_as_of date (prevents future data leakage)
    - 증권발행실적보고서 (post-subscription issuance result report)
    - Non-equity filings (debt, derivatives, etc.)
    - Non-registration statement / prospectus reports
    """
    if not filings or not score_as_of:
        return None

    as_of_clean = str(score_as_of)[:10].replace("-", "")
    if not re.match(r"^\d{8}$", as_of_clean):
        return None

    valid_candidates: list[dict[str, Any]] = []
    for f in filings:
        if not isinstance(f, dict):
            continue
        report_nm = str(f.get("report_nm", "")).strip()
        rcept_dt = str(f.get("rcept_dt", "")).strip().replace("-", "")

        # Must have valid 8-digit date format
        if not re.match(r"^\d{8}$", rcept_dt):
            continue

        # Future data leakage check
        if rcept_dt > as_of_clean:
            continue

        # Exclude non-equity or post-issuance reports
        if any(keyword in report_nm for keyword in EXCLUDED_REPORT_KEYWORDS):
            continue

        # Must explicitly be equity registration or prospectus
        is_equity = (
            "지분증권" in report_nm
            or any(allowed in report_nm for allowed in ALLOWED_REPORT_TITLES)
            or ("증권신고서" in report_nm and "채무" not in report_nm and "사채" not in report_nm)
        )
        if is_equity:
            valid_candidates.append(f)

    if not valid_candidates:
        return None

    # Sort by rcept_dt ascending, then rcept_no ascending; latest is at the end
    valid_candidates.sort(key=lambda x: (str(x.get("rcept_dt", "")), str(x.get("rcept_no", ""))))
    return valid_candidates[-1]


class DartClient:
    """Client for OpenDART API."""

    def __init__(
        self,
        api_key: str | None = None,
        timeout_seconds: float = 15.0,
        user_agent: str = "Wealth/1.3.0 (OpenDART Client)",
    ):
        self.api_key = (api_key or os.environ.get("DART_API_KEY", "")).strip()
        self.timeout_seconds = timeout_seconds
        self.user_agent = user_agent

    def is_configured(self) -> bool:
        return bool(self.api_key)

    def _safe_log_url(self, endpoint: str, params: dict[str, Any]) -> str:
        safe_params = {k: ("***" if k == "crtfc_key" else v) for k, v in params.items()}
        return f"{endpoint}?{urlencode(safe_params)}"

    def _check_status_code(self, status: str, message: str, endpoint: str) -> None:
        if status == "000":
            return
        if status in ("010", "011", "012", "101", "901"):
            raise DartAuthError(f"DART authentication error [{status}]: {message}")
        if status == "013":
            raise DartNoData(f"DART no data found [{status}]: {message}")
        if status == "014":
            raise DartNoData(f"DART no file found [{status}]: {message}")
        if status == "020":
            raise DartRateLimitError(f"DART rate limit exceeded [{status}]: {message}")
        if status in ("021", "100"):
            raise DartRequestError(f"DART request contract error [{status}]: {message}")
        if status in ("800", "900"):
            raise DartSourceError(f"DART system error [{status}]: {message}")
        raise DartClientError(f"DART error [{status}]: {message}")

    def _request_json(self, endpoint: str, params: dict[str, Any]) -> dict[str, Any]:
        if not self.is_configured():
            raise DartAuthError("DART_API_KEY environment variable is not configured.")

        full_params = dict(params)
        full_params["crtfc_key"] = self.api_key
        headers = {"User-Agent": self.user_agent}

        try:
            with httpx.Client(timeout=self.timeout_seconds) as client:
                resp = client.get(f"{DART_BASE_URL}/{endpoint}", params=full_params, headers=headers)
                resp.raise_for_status()
                data = resp.json()
        except httpx.TimeoutException as exc:
            raise DartClientError(f"DART request timed out on {endpoint}") from exc
        except httpx.HTTPStatusError as exc:
            status_code = exc.response.status_code
            if status_code >= 500:
                raise DartSourceError(f"DART server HTTP {status_code} error on {endpoint}") from exc
            raise DartClientError(f"DART HTTP {status_code} error on {endpoint}") from exc
        except httpx.RequestError as exc:
            raise DartClientError(f"DART network request error on {endpoint}: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise DartClientError(f"DART returned non-JSON response on {endpoint}") from exc

        status = str(data.get("status", "")).strip()
        message = str(data.get("message", "")).strip()
        self._check_status_code(status, message, endpoint)
        return data

    def get_filing_list(
        self,
        corp_code: str,
        bgn_de: str,
        end_de: str,
        *,
        pblntf_ty: str = "C",
        pblntf_detail_ty: str = "C001",
        last_reprt_at: str = "N",
        page_no: int = 1,
        page_count: int = 100,
    ) -> dict[str, Any]:
        """Retrieve filing list (list.json) for equity registration statements."""
        params = {
            "corp_code": corp_code,
            "bgn_de": bgn_de.replace("-", ""),
            "end_de": end_de.replace("-", ""),
            "pblntf_ty": pblntf_ty,
            "pblntf_detail_ty": pblntf_detail_ty,
            "last_reprt_at": last_reprt_at,
            "page_no": page_no,
            "page_count": page_count,
        }
        try:
            res = self._request_json("list.json", params)
            return res
        except DartNoData as e:
            if "[013]" in str(e):
                return {
                    "status": "013",
                    "message": "조회된 데이터가 없습니다.",
                    "page_no": page_no,
                    "page_count": page_count,
                    "total_count": 0,
                    "total_page": 0,
                    "list": [],
                }
            raise

    def get_equity_registration_statements(
        self,
        corp_code: str,
        bgn_de: str,
        end_de: str,
    ) -> dict[str, Any]:
        """Retrieve structured equity registration statements (estkRs.json)."""
        params = {
            "corp_code": corp_code,
            "bgn_de": bgn_de.replace("-", ""),
            "end_de": end_de.replace("-", ""),
        }
        try:
            res = self._request_json("estkRs.json", params)
            return res
        except DartNoData as e:
            if "[013]" in str(e):
                return {
                    "status": "013",
                    "message": "조회된 데이터가 없습니다.",
                    "list": [],
                }
            raise

    def get_equity_registration_statement(self, rcept_no: str) -> dict[str, Any]:
        """Deprecated API. OpenDART estkRs.json requires corp_code, bgn_de, end_de."""
        raise DartRequestError(
            f"Deprecated API: get_equity_registration_statement(rcept_no='{rcept_no}'). "
            "Use get_equity_registration_statements(corp_code, bgn_de, end_de) instead."
        )

    def download_document_zip(self, rcept_no: str) -> bytes:
        """Download raw filing document archive (document.xml returns raw ZIP binary)."""
        if not self.is_configured():
            raise DartAuthError("DART_API_KEY environment variable is not configured.")

        params = {
            "crtfc_key": self.api_key,
            "rcept_no": rcept_no,
        }
        headers = {"User-Agent": self.user_agent}

        try:
            with httpx.Client(timeout=self.timeout_seconds) as client:
                resp = client.get(f"{DART_BASE_URL}/document.xml", params=params, headers=headers)
                resp.raise_for_status()
                content = resp.content

            # Check if DART returned an error XML instead of binary ZIP
            stripped_head = content.lstrip(b"\xef\xbb\xbf \t\r\n")
            if stripped_head.startswith(b"<?xml") or stripped_head.startswith(b"<result>"):
                try:
                    text = content.decode("utf-8", errors="replace")
                    status_match = re.search(r"<status>(\d+)</status>", text)
                    msg_match = re.search(r"<message>(.*?)</message>", text)
                    if status_match:
                        status = status_match.group(1)
                        msg = msg_match.group(1) if msg_match else ""
                        self._check_status_code(status, msg, "document.xml")
                except DartClientError:
                    raise
                except Exception:
                    pass

            if not content.startswith(b"PK"):
                raise DartClientError(f"Invalid ZIP binary received for rcept_no={rcept_no}")

            return content
        except httpx.TimeoutException as exc:
            raise DartClientError(f"DART download timed out for rcept_no={rcept_no}") from exc
        except httpx.HTTPStatusError as exc:
            status_code = exc.response.status_code
            if status_code >= 500:
                raise DartSourceError(f"DART server HTTP {status_code} error on document.xml") from exc
            raise DartClientError(f"DART HTTP {status_code} error on document.xml") from exc
        except httpx.RequestError as exc:
            raise DartClientError(f"DART download error on document.xml: {exc}") from exc

    def download_document_xml(self, rcept_no: str) -> bytes:
        """Deprecated compatibility alias for download_document_zip."""
        return self.download_document_zip(rcept_no)

    def get_financial_statements(
        self,
        corp_code: str,
        bsns_year: str,
        reprt_code: str,
        fs_div: str,
    ) -> dict[str, Any]:
        """Retrieve financial statements (fnlttSinglAcntAll.json).

        fs_div must be either 'CFS' (consolidated) or 'OFS' (separate).
        """
        if fs_div not in ("CFS", "OFS"):
            raise ValueError(f"fs_div must be 'CFS' or 'OFS', got '{fs_div}'")

        params = {
            "corp_code": corp_code,
            "bsns_year": bsns_year,
            "reprt_code": reprt_code,
            "fs_div": fs_div,
        }
        try:
            return self._request_json("fnlttSinglAcntAll.json", params)
        except DartNoData:
            return {
                "status": "013",
                "message": "조회된 데이터가 없습니다.",
                "list": [],
            }

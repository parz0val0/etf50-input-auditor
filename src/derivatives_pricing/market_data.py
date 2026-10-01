"""Read-only adapter for the audited local 2024 ETF-option daily CSV."""

from __future__ import annotations

import csv
from .contract_terms import static_terms_eligible
import hashlib
import json
from functools import lru_cache
from math import isfinite
from pathlib import Path

DATA_PATH = Path(__file__).resolve().parents[2] / "data/private/etf50_2024/normalized_2024.csv"
REVIEWED_SHA256 = "6210fe8f2d1f8326a3229980b0c68e9ce621f2e3063db3b391a4fbed7904a90c"
_FLOATS = ("strike", "close", "settle", "spot", "volume", "open_interest",
           "contract_unit", "T_act365", "vendor_iv_pct", "source_row")
_BOOLS = ("official_strike_mismatch", "spot_conflict", "invalid_terms", "low_volume")


def _float(value):
    if value in (None, ""):
        return None
    try:
        result = float(value)
        return result if isfinite(result) else None
    except ValueError:
        return None


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024*1024), b""):
            digest.update(block)
    return digest.hexdigest()


def source_summary() -> dict:
    """Identify the reviewed normalized version and its original source manifest."""
    folder = DATA_PATH.parent
    status_path, summary_path = folder / "run_status.json", folder / "summary.json"
    if not all(path.is_file() for path in (DATA_PATH, status_path, summary_path)):
        return {"status": "unavailable", "audit_status": "missing",
                "normalized_file": DATA_PATH.name}
    try:
        status = json.loads(status_path.read_text(encoding="utf-8"))
        audit = json.loads(summary_path.read_text(encoding="utf-8"))
        audit_hash, data_hash = _sha256(summary_path), _sha256(DATA_PATH)
        valid = (status.get("status") == "complete"
                 and status.get("summary_sha256") == audit_hash
                 and data_hash == REVIEWED_SHA256)
        return {"status": "ok" if valid else "unavailable",
                "audit_status": status.get("status", "missing"),
                "version_validation": "matched_reviewed_version" if valid else "failed",
                "normalized_file": DATA_PATH.name, "normalized_sha256": data_hash,
                "audit_summary_sha256": audit_hash,
                "source_manifest": [{key: item.get(key) for key in ("name", "sha256", "rows")}
                                    for item in audit.get("source_manifest", [])],
                "independent_price_crosscheck": "not_completed"}
    except (OSError, ValueError, TypeError, AttributeError):
        return {"status": "unavailable", "audit_status": "unreadable",
                "normalized_file": DATA_PATH.name}


def _audit_valid() -> bool:
    return source_summary()["status"] == "ok"


@lru_cache(maxsize=1)
def _load_rows() -> tuple[dict, ...]:
    if not _audit_valid():
        return ()
    rows = []
    with DATA_PATH.open(encoding="utf-8-sig", newline="") as source:
        for raw in csv.DictReader(source):
            item = {key: raw.get(key) for key in (
                "date", "code", "trading_code", "cp", "expiry", "adjustment_flag",
                "unit_status", "unit_source", "input_status", "iv_status_close",
                "source_file")}
            item.update({key: _float(raw.get(key)) for key in _FLOATS})
            item.update({key: raw.get(key) == "True" for key in _BOOLS})
            rows.append(item)
    return tuple(rows)


def summary(*, include_dates: bool = True) -> dict:
    provenance = source_summary()
    if provenance["status"] != "ok":
        return {"status": "unavailable", "source": str(DATA_PATH), "rows": 0,
                "reason": "missing_or_unverified_audit", "source_summary": provenance}
    rows = _load_rows()
    if not rows:
        return {"status": "unavailable", "source": str(DATA_PATH), "rows": 0}
    days = sorted({row["date"] for row in rows})
    result = {
        "status": "ok", "source": "user_supplied_audited_2024_daily_csv",
        "rows": len(rows), "dates": len(days), "first_date": days[0], "last_date": days[-1],
        "verified_historical_iv_rows": 0,
        "price_independent_crosscheck": "not_completed",
        "historical_rate_and_dividend_inputs": "not_verified",
        "source_summary": provenance,
    }
    if include_dates:
        result["available_dates"] = days
    return result


def snapshot(date: str, *, expiry: str | None = None, cp: str | None = None,
             min_volume: float = 0, limit: int = 500) -> dict:
    if not isinstance(date, str) or len(date) != 10:
        raise ValueError("date must be YYYY-MM-DD")
    if cp is not None and cp not in ("C", "P"):
        raise ValueError("cp must be C or P")
    if limit < 1 or limit > 2000:
        raise ValueError("limit must be between 1 and 2000")
    if not isfinite(min_volume) or min_volume < 0:
        raise ValueError("min_volume must be nonnegative and finite")
    provenance = source_summary()
    if provenance["status"] != "ok":
        return {"status": "unavailable", "rows": [], "total": 0,
                "reason": "missing_or_unverified_audit", "source_summary": provenance}
    all_rows = _load_rows()
    if not all_rows:
        return {"status": "unavailable", "rows": [], "total": 0}
    matched = [row for row in all_rows if row["date"] == date
               and (expiry is None or row["expiry"] == expiry)
               and (cp is None or row["cp"] == cp)
               and (row["volume"] or 0) >= min_volume]
    matched.sort(key=lambda row: (row["expiry"], row["cp"], row["strike"] or 0, row["code"]))
    return {"status": "ok", "date": date, "total": len(matched), "rows": matched[:limit],
            "truncated": len(matched) > limit,
            "source": "user_supplied_audited_2024_daily_csv", "source_summary": provenance}


def scenario_eligible(row: dict) -> tuple[bool, str]:
    """Restrict static-strike BS/Heston scenarios to unaffected standard terms."""
    eligible, reason = static_terms_eligible(row)
    if not eligible:
        return False, reason
    if row["official_strike_mismatch"] or row["invalid_terms"] or row["spot_conflict"]:
        return False, "unverified_terms_or_spot"
    if row["volume"] is None or row["volume"] < 10:
        return False, "low_volume"
    if any(row[field] is None or row[field] <= 0 for field in ("close", "spot", "strike", "T_act365")):
        return False, "invalid_price_or_tenor"
    return True, "eligible"

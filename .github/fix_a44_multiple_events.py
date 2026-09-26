from pathlib import Path

path = Path("app/services/etf_kind_distributions.py")
text = path.read_text(encoding="utf-8")

old = '''def _find_item(bucket: dict[str, Any] | None, code: str) -> dict[str, Any] | None:
    if not isinstance(bucket, dict) or not isinstance(bucket.get("items"), list):
        return None
    return next(
        (
            item
            for item in bucket["items"]
            if isinstance(item, dict) and _stock_code(item.get("code")) == code
        ),
        None,
    )


def _remove_item'''
new = '''def _find_item(bucket: dict[str, Any] | None, code: str) -> dict[str, Any] | None:
    if not isinstance(bucket, dict) or not isinstance(bucket.get("items"), list):
        return None
    return next(
        (
            item
            for item in bucket["items"]
            if isinstance(item, dict) and _stock_code(item.get("code")) == code
        ),
        None,
    )


def _find_replaceable_item(
    bucket: dict[str, Any] | None, code: str
) -> dict[str, Any] | None:
    """Find only a legacy/heuristic item, never a KIND event added earlier."""
    if not isinstance(bucket, dict) or not isinstance(bucket.get("items"), list):
        return None
    return next(
        (
            item
            for item in bucket["items"]
            if isinstance(item, dict)
            and _stock_code(item.get("code")) == code
            and item.get("forecast_source") != "kind_etf_distribution"
        ),
        None,
    )


def _remove_item'''
if old not in text:
    raise SystemExit("find-item insertion target missing")
text = text.replace(old, new, 1)
text = text.replace(
    "        existing = _find_item(record_bucket, code)\n",
    "        existing = _find_replaceable_item(record_bucket, code)\n",
    1,
)
text = text.replace(
    "            existing = _find_item(payment_bucket, code)\n",
    "            existing = _find_replaceable_item(payment_bucket, code)\n",
    1,
)
path.write_text(text, encoding="utf-8")

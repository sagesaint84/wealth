"""User-scoped visualization metadata; no balances, snapshots or calculations."""
from copy import deepcopy
import re

from app.services import portfolio
from app.services.financial_json import financial_rmw

GROUPS = ("calendar_event_colors", "asset_category_colors", "stock_category_colors")
CALENDAR_KEYS = {"ipo_subscription", "ipo_listing", "profit", "loss", "dividend", "income", "expense"}
KEY = re.compile(r"[a-z][a-z0-9_]*|(?:id|name):[A-Za-z0-9_.!~*'()%:-]+")
HEX = re.compile(r"#[0-9a-fA-F]{6}")


def empty():
    return {group: {} for group in GROUPS}


def validate_key(group, key):
    if group not in GROUPS or not isinstance(key, str) or len(key) > 512 or not KEY.fullmatch(key) or key in {"constructor", "prototype"}:
        raise ValueError("색상 분류 키가 유효하지 않습니다.")
    if group == "calendar_event_colors" and key not in CALENDAR_KEYS:
        raise ValueError("캘린더 이벤트 종류가 유효하지 않습니다.")


def normalize(value):
    if not isinstance(value, str) or not HEX.fullmatch(value.strip()):
        raise ValueError("색상은 #RRGGBB 형식으로 입력하세요.")
    return value.strip().upper()


def validated(doc):
    if not isinstance(doc, dict) or set(doc) - set(GROUPS):
        raise ValueError("색상 설정 형식이 유효하지 않습니다.")
    result = empty()
    for group, values in doc.items():
        if not isinstance(values, dict):
            raise ValueError("색상 설정 형식이 유효하지 않습니다.")
        for key, color in values.items():
            validate_key(group, key)
            result[group][key] = normalize(color)
    return result


def read_colors(username):
    data = portfolio.read_financial_json(portfolio._get_portfolio_file(username), default=portfolio.EMPTY_PORTFOLIO)
    return validated(data.get("settings", {}).get("visualization_colors", {}))


@financial_rmw("portfolio.json")
def patch_color(username, payload):
    if not isinstance(payload, dict) or set(payload) != {"group", "key", "color"}:
        raise ValueError("색상 설정 입력값을 확인하세요.")
    group, key = payload["group"], payload["key"]
    validate_key(group, key)
    color = None if payload["color"] is None else normalize(payload["color"])
    path = portfolio._get_portfolio_file(username)
    data = deepcopy(portfolio.read_financial_json(path, default=portfolio.EMPTY_PORTFOLIO))
    colors = validated(data.get("settings", {}).get("visualization_colors", {}))
    before = deepcopy(colors)
    if color is None:
        colors[group].pop(key, None)
    else:
        colors[group][key] = color
    if colors != before:
        data.setdefault("settings", {})["visualization_colors"] = colors
        portfolio.write_financial_json(path, data)
    return colors

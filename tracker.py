"""롯데마트 도와센터의 공개 매장별 상품 조회를 이용하는 읽기 전용 추적기."""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

BASE = "https://company.lottemart.com"
STORE_PATH = "/mobiledowa/inc/asp/search_market_list.asp"
SEARCH_PATH = "/mobiledowa/product/search_product.asp"
PAGE_PATH = "/mobiledowa/inc/asp/search_product_list.asp"
SOURCE_URL = BASE + "/mobiledowa/"
EMPTY_MARKERS = ("검색 결과가 없습니다", "검색결과가 없습니다", "검색된 상품이 없습니다", "검색된 상품이 없", "조회된 상품이 없")


class LookupError(RuntimeError):
    """공식 사이트 조회에 실패했거나 응답 형식을 신뢰할 수 없음."""


def decode_response(response):
    for encoding in ("utf-8", "cp949", "euc-kr"):
        try:
            return response.content.decode(encoding)
        except UnicodeDecodeError:
            continue
    return response.content.decode("utf-8", errors="replace")


def session():
    client = requests.Session()
    retries = Retry(
        total=1,
        backoff_factor=1.0,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset(("GET", "POST")),
    )
    client.mount("https://", HTTPAdapter(max_retries=retries))
    client.headers.update({
        "User-Agent": "DDC-LotteMart-Tracker/0.1 (read-only; six-hour polling)",
        "Accept-Language": "ko-KR,ko;q=0.9",
        "Referer": SOURCE_URL,
    })
    return client


def request_html(client, method, path, *, params=None, data=None, timeout=12):
    try:
        response = client.request(
            method, BASE + path, params=params, data=data, timeout=timeout
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        raise LookupError(f"{path}: {type(exc).__name__}: {exc}") from exc
    text = decode_response(response)
    if not text.strip():
        raise LookupError(f"{path}: 빈 응답")
    return text


def normalize(text):
    return re.sub(r"\s+", "", str(text)).lower()


def parse_stores(html):
    soup = BeautifulSoup(html, "html.parser")
    stores = {}
    for option in soup.select("option[value]"):
        code = option.get("value", "").strip()
        name = option.get_text(" ", strip=True)
        if code and name and name != "매장선택":
            stores[name] = code
    return stores


def find_store(stores, desired):
    if desired in stores:
        return stores[desired]
    matches = [(name, code) for name, code in stores.items()
               if normalize(name) == normalize(desired)]
    if len(matches) == 1:
        return matches[0][1]
    raise LookupError(f"'{desired}' 매장 코드 확인 실패. 확인된 매장: {', '.join(stores)[:250]}")


def number_from_price(raw):
    if not raw:
        return None
    match = re.search(r"(\d[\d,]*)\s*원", raw)
    if not match:
        match = re.search(r"^\s*([\d,]+)\s*$", raw)
    return int(match.group(1).replace(",", "")) if match else None


def stock_status(raw):
    if not raw:
        return "unknown"
    value = normalize(raw)
    if "품절" in value or "재고없음" in value or "재고0" in value or "0개" == value:
        return "out_of_stock"
    match = re.search(r"(\d+)\s*(?:개|병|ea|박스|box)", value, re.IGNORECASE)
    if match:
        return "in_stock" if int(match.group(1)) > 0 else "out_of_stock"
    if value.isdecimal():
        return "in_stock" if int(value) > 0 else "out_of_stock"
    return "unknown"


def volume(name, spec):
    text = f"{spec} {name}"
    match = re.search(r"(\d[\d,]*(?:\.\d+)?)\s*(ml|cl|l|ℓ)(?![a-z])", text, re.IGNORECASE)
    if not match:
        return None
    value, unit = float(match.group(1).replace(",", "")), match.group(2).lower()
    ml = value * (1000 if unit in ("l", "ℓ") else 10 if unit == "cl" else 1)
    return f"{int(ml)}mL" if ml.is_integer() else f"{ml:g}mL"


def product_from_popup(popup):
    title = popup.select_one(".layer-head")
    if not title:
        return None
    name = title.get_text(" ", strip=True)
    if not name:
        return None
    fields = {}
    for th in popup.select("th"):
        td = th.find_next_sibling("td")
        if td is None:
            continue
        label = re.sub(r"[^가-힣a-zA-Z]", "", th.get_text(" ", strip=True)).lower()
        if label:
            fields[label] = td.get_text(" ", strip=True)
    raw_price = fields.get("가격") or fields.get("판매가") or ""
    raw_stock = fields.get("재고") or fields.get("재고수량") or ""
    spec = fields.get("규격") or fields.get("용량") or ""
    price = number_from_price(raw_price)
    regular = number_from_price(fields.get("정상가") or fields.get("정가") or "")
    discount = "unknown"
    rate = None
    stated_rate = re.fullmatch(r"(\d+(?:\.\d+)?)\s*%", fields.get("할인율", ""))
    if stated_rate and float(stated_rate.group(1)) <= 100:
        rate = float(stated_rate.group(1))
        discount = "discounted" if rate > 0 else "not_discounted"
    elif price is not None and regular is not None and regular > 0:
        rate = round(100 * max(0, regular - price) / regular, 2)
        discount = "discounted" if price < regular else "not_discounted"
    return {
        "name": name,
        "spec": spec or None,
        "volume": volume(name, spec),
        "price_krw": price,
        "price_raw": raw_price or None,
        "regular_price_krw": regular,
        "discount_status": discount,
        "discount_rate_pct": rate,
        "stock_raw": raw_stock or None,
        "stock_status": stock_status(raw_stock),
    }


def parse_products(html):
    soup = BeautifulSoup(html, "html.parser")
    products = []
    for popup in soup.select(".layer_popup"):
        value = product_from_popup(popup)
        if value:
            products.append(value)
    seen = set()
    unique = []
    for product in products:
        key = (normalize(product["name"]), product["spec"], product["price_krw"])
        if key not in seen:
            unique.append(product)
            seen.add(key)
    return unique


def total_pages(html):
    found = re.search(r"\btotalPage\s*=\s*['\"]?(\d+)", html)
    return int(found.group(1)) if found else 1


def declared_empty(html):
    soup = BeautifulSoup(html, "html.parser")
    count = soup.select_one(".result-prod .total-num")
    if count and re.fullmatch(r"검색결과[:：]?0건", normalize(count.get_text())):
        return True
    normalized = normalize(soup.get_text(" "))
    return any(re.sub(r"\s+", "", marker) in normalized for marker in EMPTY_MARKERS)


def search(client, area, store_code, query, max_pages=3):
    form = {"p_area": area, "p_market": store_code, "p_schWord": query}
    first = request_html(client, "POST", SEARCH_PATH, data=form)
    products = parse_products(first)
    pages = min(max_pages, max(1, total_pages(first)))
    if not products and not declared_empty(first):
        # 초기 응답에 결과가 없을 때 도와센터가 사용하는 페이지 조각 경로로 재확인.
        first = request_html(client, "GET", PAGE_PATH, params={
            "p_market": store_code, "p_schWord": query, "page": 1
        })
        products = parse_products(first)
    if not products:
        if declared_empty(first):
            return []
        raise LookupError(f"'{query}': 상품 HTML을 해석할 수 없어 재고를 확정하지 않음")
    for page in range(2, pages + 1):
        html = request_html(client, "GET", PAGE_PATH, params={
            "p_market": store_code, "p_schWord": query, "page": page
        })
        products.extend(parse_products(html))
    deduped = {}
    for product in products:
        deduped[(normalize(product["name"]), product["spec"], product["price_krw"])] = product
    return list(deduped.values())


def make_result(config, queries, client=None):
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    store = config["store"]
    result = {
        "checked_at": now,
        "source": SOURCE_URL,
        "status": "error",
        "store": {"area": store["area"], "name": store["name"], "code": None},
        "queries": queries,
        "products": [],
        "targets": [],
        "error": None,
    }
    try:
        client = client or session()
        stores_html = request_html(client, "GET", STORE_PATH, params={
            "p_area": store["area"], "p_type": 1
        })
        stores = parse_stores(stores_html)
        if not stores:
            raise LookupError("매장 목록에서 유효한 코드를 찾지 못함")
        code = find_store(stores, store["name"])
        result["store"]["code"] = code
        products = []
        for query in queries:
            matches = search(client, store["area"], code, query)
            if not matches:
                for target in config.get("targets", []):
                    registered = target.get("search_name")
                    names = [target["name"], *target.get("aliases", [])]
                    if registered and registered != query and any(
                        normalize(query) == normalize(name) for name in names
                    ):
                        candidates = search(client, store["area"], code, registered)
                        matches = [p for p in candidates if normalize(p["name"]) == normalize(registered)]
                        break
            products.extend(matches)
        found = {}
        for product in products:
            key = (normalize(product["name"]), product["spec"], product["price_krw"])
            found[key] = product
        result["products"] = list(found.values())
        result["status"] = "ok"
        for target in config.get("targets", []):
            label = target["name"]
            aliases = target.get("aliases") or [label]
            matches = [p for p in result["products"] if any(
                normalize(alias) in normalize(p["name"]) for alias in aliases
            )]
            result["targets"].append({
                "name": label,
                "status": "found" if matches else "not_found_in_search",
                "products": matches,
            })
    except (LookupError, KeyError, ValueError) as exc:
        result["error"] = str(exc)
        # 조회 실패를 품절이나 할인 종료로 기록하지 않음.
        result["products"] = []
        result["targets"] = []
    return result


def save(path, payload):
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def main(argv=None):
    parser = argparse.ArgumentParser(description="롯데마트 상품/재고/가격 조회")
    parser.add_argument("--config", default="watchlist.json")
    parser.add_argument("--query", action="append", help="검색어. 반복 지정 가능")
    parser.add_argument("--status", default="data/status.json")
    parser.add_argument("--latest", default="data/latest.json")
    args = parser.parse_args(argv)
    config = json.loads(Path(args.config).read_text(encoding="utf-8"))
    queries = args.query if args.query else config["queries"]
    result = make_result(config, queries)
    save(args.status, result)
    if result["status"] == "ok":
        save(args.latest, result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "ok" else 1


if __name__ == "__main__":
    sys.exit(main())

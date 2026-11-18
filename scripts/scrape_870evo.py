"""Collect Samsung 870 EVO Danawa price-comparison totals by capacity."""

import re
from time import sleep

import requests

from common import capacity_sort_key, merge_and_save
from danawa import fetch_search, listing_prices, product_cards

SITE = "다나와"
TARGET_KEYWORD = "870 EVO"
CATE_CODE = "112760"
REQUEST_DELAY = 2
MAX_PAGES = 3
VALID_CAPACITIES = {"250GB", "500GB", "1TB", "2TB", "4TB", "8TB"}
SOURCE_TYPES = {"정품", "병행수입"}
MODEL = re.compile(
    r"삼성전자\s+870\s*EVO(?:\s+(정품|병행수입))?"
    r"(?:\s*\(?\d+\s*(?:GB|TB)\)?)?",
    re.I,
)


def parse_page(html):
    for card, title in product_cards(html):
        model = MODEL.fullmatch(title)
        if not model:
            continue
        for pcode, capacity, price, _ in listing_prices(card, title):
            if capacity in VALID_CAPACITIES:
                yield {
                    "site": SITE,
                    "source_type": model.group(1) or "정품",
                    "capacity": capacity,
                    "price_krw": price,
                    "pcode": pcode,
                    "url": f"https://prod.danawa.com/info/?pcode={pcode}&cate={CATE_CODE}",
                }


def collect():
    best = {}
    expected = {
        (source, capacity)
        for source in SOURCE_TYPES
        for capacity in VALID_CAPACITIES - {"8TB"}
    }
    previous_html = None
    for page in range(1, MAX_PAGES + 1):
        if page > 1:
            sleep(REQUEST_DELAY)
        try:
            html = fetch_search(TARGET_KEYWORD, page)
        except requests.RequestException as error:
            if not best:
                raise
            print(f"[다나와 SSD] 검색 {page}페이지 조회 실패: {error}")
            break
        if html == previous_html:
            break
        previous_html = html
        for item in parse_page(html):
            key = item["source_type"], item["capacity"]
            if key not in best or item["price_krw"] < best[key]["price_krw"]:
                best[key] = item
        if expected <= best.keys():
            break
    for source, capacity in sorted(expected - best.keys()):
        print(f"[다나와 SSD] 가격 미확인: {source} {capacity}")
    return list(best.values())


def main():
    variants = collect()
    if not variants:
        raise SystemExit("[다나와 SSD] 유효한 가격 0건. 응답 구조 또는 접근 상태를 확인하세요.")
    variants.sort(key=lambda item: (item["source_type"], capacity_sort_key(item["capacity"])))
    _, history = merge_and_save("ssd", SITE, variants)
    print(f"[다나와 SSD] {len(variants)}건 저장. 누적 {len(history['entries'])}일.")


if __name__ == "__main__":
    main()

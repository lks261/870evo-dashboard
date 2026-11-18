"""Collect Samsung DDR4 ECC RDIMM and EDIMM Danawa prices."""

import re
from time import sleep

import requests

from common import merge_and_save
from danawa import fetch_html, fetch_search, listing_prices, product_cards

SITE = "다나와"
CATEGORY_URL = "https://prod.danawa.com/list/"
CATEGORY_PARAMS = {"cate": "11335273"}
REQUEST_DELAY = 1.5
CLOCK_MHZ = {
    "17000": "2133",
    "19200": "2400",
    "21300": "2666",
    "23400": "2933",
    "25600": "3200",
}
DIMM_CLOCKS = {
    "RDIMM": ["17000", "19200", "21300", "25600"],
    "EDIMM": ["19200", "21300", "23400", "25600"],
}
VALID_CAPACITIES_BY_DIMM = {
    "RDIMM": {"8GB", "16GB", "32GB", "64GB"},
    "EDIMM": {"8GB", "16GB", "32GB"},
}
MODEL = re.compile(
    r"삼성전자\s+DDR4\s*[- ]\s*(?P<speed>\d{4,5})(?:\s*MHz)?"
    r"\s*(?:CL\d+\s+)?ECC\s*[/ ]\s*(?P<kind>Unbuffered|[ERU]DIMM|REG(?:istered)?)"
    r"(?:\s*\(?\d+\s*GB\)?)?",
    re.I,
)


def build_query(dimm_type, clock):
    kind = "REG" if dimm_type == "RDIMM" else "Unbuffered"
    return f"삼성전자 DDR4-{CLOCK_MHZ[clock]} ECC/{kind}"


def parse_catalog(html):
    for card, title in product_cards(html):
        # Exclusion is based on the product name, so general advisory text cannot drop the card.
        model = MODEL.fullmatch(title)
        if not model:
            continue
        kind = model["kind"].upper()
        dimm_type = "RDIMM" if kind.startswith("R") else "EDIMM"
        clock = next(
            (clock for clock, mhz in CLOCK_MHZ.items() if model["speed"] in (clock, mhz)),
            None,
        )
        if clock not in DIMM_CLOCKS[dimm_type]:
            continue
        for pcode, capacity, price, text in listing_prices(card, title):
            if capacity in VALID_CAPACITIES_BY_DIMM[dimm_type]:
                yield {
                    "site": SITE,
                    "category": "RAM",
                    "dimm_type": dimm_type,
                    "clock": clock,
                    "capacity": capacity,
                    "price_krw": price,
                    "pcode": pcode,
                    "matched_text": text[:120],
                    "url": f"https://prod.danawa.com/info/?pcode={pcode}",
                }


def collect():
    expected = {
        (dimm, clock, capacity)
        for dimm, clocks in DIMM_CLOCKS.items()
        for clock in clocks
        for capacity in VALID_CAPACITIES_BY_DIMM[dimm]
    }
    best = {}
    for index, (dimm, clock) in enumerate(
        (dimm, clock) for dimm, clocks in DIMM_CLOCKS.items() for clock in clocks
    ):
        if index:
            sleep(REQUEST_DELAY)
        try:
            html = fetch_search(build_query(dimm, clock))
        except requests.RequestException as error:
            print(f"[다나와 RAM] {dimm} PC4-{clock} 검색 실패: {error}")
            continue
        for item in parse_catalog(html):
            key = item["dimm_type"], item["clock"], item["capacity"]
            if key[:2] != (dimm, clock):
                continue
            if key not in best or item["price_krw"] < best[key]["price_krw"]:
                best[key] = item

    missing = expected - best.keys()
    if missing:
        sleep(REQUEST_DELAY)
        try:
            html = fetch_html(CATEGORY_URL, CATEGORY_PARAMS)
        except requests.RequestException as error:
            print(f"[다나와 RAM] 서버용 RAM 목록 조회 실패: {error}")
        else:
            for item in parse_catalog(html):
                key = item["dimm_type"], item["clock"], item["capacity"]
                if key not in missing:
                    continue
                if key not in best or item["price_krw"] < best[key]["price_krw"]:
                    best[key] = item

    for dimm, clock, capacity in sorted(expected - best.keys()):
        print(f"[다나와 RAM] 가격 미확인: {dimm} PC4-{clock} {capacity}")
    return list(best.values())

def sanity_check(items: list[dict]):
    """가격 역전(용량/클럭 순서가 말이 안 되는 경우)을 감지해서 경고만 남긴다."""
    warnings = []
    clock_order = {"17000": 0, "19200": 1, "21300": 2, "23400": 3, "25600": 4}
    cap_order = {"8GB": 0, "16GB": 1, "32GB": 2, "64GB": 3}

    by_dimm_cap, by_dimm_clock = {}, {}
    for it in items:
        by_dimm_cap.setdefault((it["dimm_type"], it["capacity"]), []).append(it)
        by_dimm_clock.setdefault((it["dimm_type"], it["clock"]), []).append(it)

    for (dimm, cap), group in by_dimm_cap.items():
        gs = sorted(group, key=lambda x: clock_order.get(x["clock"], 99))
        for a, b in zip(gs, gs[1:]):
            if b["price_krw"] < a["price_krw"]:
                warnings.append(f"{dimm} {cap}: PC4-{a['clock']}({a['price_krw']:,}) > PC4-{b['clock']}({b['price_krw']:,}) — 클럭 높은데 더 쌈")

    for (dimm, clock), group in by_dimm_clock.items():
        gs = sorted(group, key=lambda x: cap_order.get(x["capacity"], 99))
        for a, b in zip(gs, gs[1:]):
            if b["price_krw"] < a["price_krw"]:
                warnings.append(f"{dimm} PC4-{clock}: {a['capacity']}({a['price_krw']:,}) > {b['capacity']}({b['price_krw']:,}) — 용량 큰데 더 쌈")

    if warnings:
        print(f"\n⚠️  가격 역전 감지 ({len(warnings)}건):")
        for w in warnings:
            print(f"   - {w}")
    else:
        print("\n✅ 가격 역전 없음")



def main():
    items = collect()
    if not items:
        raise SystemExit("[다나와 RAM] 유효한 가격 0건. 검색 및 카테고리 응답을 확인하세요.")
    sanity_check(items)
    _, history = merge_and_save("ram", SITE, items)
    print(f"[다나와 RAM] {len(items)}건 저장. 누적 {len(history['entries'])}일.")


if __name__ == "__main__":
    main()

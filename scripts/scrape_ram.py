"""
다나와 - 삼성전자 서버용 DDR4 RAM(RDIMM/EDIMM) 용량×클럭별 가격 수집 (v2)
================================================================

v1(개별 조합 28회 검색) 문제점:
    "8GB" / "16GB"를 한 상품명 안에 같이 적어놓은 중고 번들 리스팅이 여러
    용량 검색에 동시에 걸려서, 서로 다른 용량인데 가격이 거의 똑같이 나오는
    등 신뢰도가 낮았다. "[해외]" 표기 상품도 마찬가지로 시세와 동떨어진
    가격이 잡히는 경우가 확인됨. (실제 캡처로 확인된 문제 2건)

v2 변경: SSD(870 EVO) 스크래퍼와 동일한 "가격비교 그룹" 방식으로 전환.
    다나와에 "삼성전자 DDR4-2133 ECC/REG"처럼 클럭+타입만으로 검색하면,
    그 규격의 8GB/16GB/32GB/64GB 옵션이 리뷰 수·평점·순위와 함께 한
    그룹으로 묶여 나오는 신뢰도 높은 리스팅을 찾을 수 있다. 그 그룹 하나에서
    용량별 가격을 전부 뽑아오므로, 클럭+타입 조합(7개)당 검색 1번이면 된다
    (28번 -> 7번). 중고/해외 상품은 명시적으로 제외한다.

수집 대상 (요청하신 스펙 그대로):
    RDIMM(Registered): 클럭 17000 / 19200 / 21300 / 25600
    UDIMM(Unbuffered, 표기는 EDIMM): 클럭 19200 / 21300 / 25600 (17000 없음)
    각 클럭마다 용량: 8GB / 16GB / 32GB / 64GB
"""

import re
import sys
import os
import time

import requests
from bs4 import BeautifulSoup

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import merge_and_save

SITE = "다나와"
SEARCH_URL = "https://search.danawa.com/dsearch.php"
REQUEST_DELAY = 1.5

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ko-KR,ko;q=0.9",
}

CLOCK_MHZ = {
    "17000": "2133",
    "19200": "2400",
    "21300": "2666",
    "25600": "3200",
}
DIMM_CLOCKS = {
    "RDIMM": ["17000", "19200", "21300", "25600"],
    "EDIMM": ["19200", "21300", "25600"],
}
VALID_CAPACITIES = {"8GB", "16GB", "32GB", "64GB"}
EXCLUDE_KEYWORDS = ["중고", "해외", "리퍼", "벌크"]  # 신뢰도 낮은 리스팅 제외

CAPACITY_PATTERN = re.compile(r"(\d+)\s*GB", re.IGNORECASE)
PRICE_PATTERN = re.compile(r"([\d,]+)\s*원")


def has_excluded_keyword(text: str) -> bool:
    return any(kw in text for kw in EXCLUDE_KEYWORDS)


def build_query(dimm_type: str, clock: str) -> str:
    mhz = CLOCK_MHZ[clock]
    reg_kw = "REG" if dimm_type == "RDIMM" else "UDIMM"  # 검색어는 업계 표준 용어(UDIMM) 사용
    return f"삼성전자 DDR4-{mhz} ECC {reg_kw}"


def fetch_search(query: str, page: int = 1) -> str:
    params = {"k1": query, "module": "goods", "act": "dispMain", "tab": "goods", "page": page}
    for attempt in range(3):
        try:
            resp = requests.get(SEARCH_URL, params=params, headers=HEADERS, timeout=20)
            resp.raise_for_status()
            resp.encoding = "utf-8"
            return resp.text
        except requests.exceptions.RequestException as e:
            print(f"    검색 실패 (시도 {attempt+1}/3): {e}")
            time.sleep(3 * (attempt + 1))
    return ""


def find_target_blocks(soup: BeautifulSoup, dimm_type: str):
    """'가격비교 그룹'으로 보이는 li 블록들을 찾는다 (SSD 스크래퍼와 동일한 방식)."""
    candidates = soup.select("li.prod_item, li[id^='productItem']")
    if not candidates:
        candidates = soup.find_all("li")

    matched = []
    for block in candidates:
        text = block.get_text(" ", strip=True)
        if "삼성" not in text:
            continue
        if has_excluded_keyword(text):
            continue
        if "DDR4" not in text.upper():
            continue
        if dimm_type == "RDIMM":
            if "REG" not in text.upper():
                continue
        else:  # EDIMM
            if "REG" in text.upper():
                continue  # RDIMM과 혼동 방지
            if "UDIMM" not in text.upper() and "UNBUFFERED" not in text.upper():
                continue
        matched.append(block)
    return matched


def parse_capacity_variants(block, dimm_type: str, clock: str) -> list[dict]:
    """SSD 스크래퍼의 parse_capacity_variants와 동일한 방식.
    한 '가격비교 그룹' 블록 안의 용량별 옵션(pcode 링크)들을 파싱한다."""
    results = []
    variant_links = block.select("a[href*='pcode=']")
    seen_pcodes = set()

    for a in variant_links:
        href = a.get("href", "")
        pcode_match = re.search(r"pcode=(\d+)", href)
        if not pcode_match:
            continue
        pcode = pcode_match.group(1)
        if pcode in seen_pcodes:
            continue

        container = a.find_parent("li") or a.parent
        text = container.get_text(" ", strip=True)

        if has_excluded_keyword(text):
            continue

        cap_match = CAPACITY_PATTERN.search(text)
        price_match = PRICE_PATTERN.search(text)
        if not (cap_match and price_match):
            continue

        capacity = f"{cap_match.group(1)}GB"
        if capacity not in VALID_CAPACITIES:
            continue

        price = int(price_match.group(1).replace(",", ""))

        results.append({
            "site": SITE,
            "category": "RAM",
            "dimm_type": dimm_type,
            "clock": clock,
            "capacity": capacity,
            "price_krw": price,
            "pcode": pcode,
            "matched_text": text[:120],
            "url": f"https://prod.danawa.com/info/?pcode={pcode}",
        })
        seen_pcodes.add(pcode)

    return results


def collect_combo(dimm_type: str, clock: str) -> list[dict]:
    query = build_query(dimm_type, clock)
    html = fetch_search(query)
    if not html:
        return []

    soup = BeautifulSoup(html, "html.parser")
    blocks = find_target_blocks(soup, dimm_type)

    # 용량 옵션이 2개 이상 묶인 "가격비교 그룹"만 채택 (단품 리스팅은 노이즈)
    best_group = None
    for block in blocks:
        variants = parse_capacity_variants(block, dimm_type, clock)
        if len(variants) < 2:
            continue
        if best_group is None or len(variants) > len(best_group):
            best_group = variants

    return best_group or []


def sanity_check(items: list[dict]):
    """가격 역전(용량/클럭 순서가 말이 안 되는 경우)을 감지해서 경고만 남긴다."""
    warnings = []
    clock_order = {"17000": 0, "19200": 1, "21300": 2, "25600": 3}
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
    print("[다나와] 삼성전자 서버용 DDR4 RAM 가격비교 그룹 수집 시작 (v2)")

    combos = [(dimm, clock) for dimm, clocks in DIMM_CLOCKS.items() for clock in clocks]
    items = []

    for i, (dimm_type, clock) in enumerate(combos, 1):
        print(f"  ({i}/{len(combos)}) {dimm_type} PC4-{clock} 검색 중...")
        variants = collect_combo(dimm_type, clock)
        if variants:
            items.extend(variants)
            for v in variants:
                print(f"    -> {v['capacity']} {v['price_krw']:,}원 | {v['matched_text'][:60]}")
        else:
            print("    -> 가격비교 그룹을 못 찾음 (스킵)")
        time.sleep(REQUEST_DELAY)

    if not items:
        print("경고: 수집된 항목이 없습니다. 이번 회차는 저장하지 않고 종료합니다.")
        return

    print(f"\n총 {len(items)}개 항목 수집 완료 ({len(combos)}개 조합 중)")
    sanity_check(items)
    latest, history = merge_and_save("ram", SITE, items)
    print(f"저장 완료 (dataset=ram, site={SITE}). 히스토리 누적 {len(history['entries'])}일치")


if __name__ == "__main__":
    main()

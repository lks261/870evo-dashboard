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
    "23400": "2933",
    "25600": "3200",
}
DIMM_CLOCKS = {
    "RDIMM": ["17000", "19200", "21300", "25600"],
    "EDIMM": ["19200", "21300", "23400", "25600"],
}
# DIMM 타입별로 수집할 용량 범위가 다름 (EDIMM은 64GB 제외, 8/16/32GB만)
VALID_CAPACITIES_BY_DIMM = {
    "RDIMM": {"8GB", "16GB", "32GB", "64GB"},
    "EDIMM": {"8GB", "16GB", "32GB"},
}
EXCLUDE_KEYWORDS = ["중고", "해외", "리퍼", "벌크"]  # 신뢰도 낮은 리스팅 제외

CAPACITY_PATTERN = re.compile(r"(\d+)\s*GB", re.IGNORECASE)
# "15,469원/1GB" 같은 단가 표기는 총액이 아니므로 절대 총액으로 잡히면 안 됨.
# 부정형 전방탐색(negative lookahead)으로 "/1GB"가 바로 뒤에 붙지 않는 "숫자원"만 총액으로 인정.
TOTAL_PRICE_PATTERN = re.compile(r"([\d,]+)\s*원(?!\s*/\s*1GB)")
UNIT_PRICE_PATTERN = re.compile(r"([\d,]+)\s*원\s*/\s*1GB")


def has_excluded_keyword(text: str) -> bool:
    return any(kw in text for kw in EXCLUDE_KEYWORDS)


def build_query(dimm_type: str, clock: str) -> str:
    mhz = CLOCK_MHZ[clock]
    # 다나와 실제 상품명은 "UDIMM"이 아니라 "ECC/Unbuffered"로 표기됨 (REG는 실제 표기와 일치)
    reg_kw = "REG" if dimm_type == "RDIMM" else "Unbuffered"
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


def find_unique_scope(a):
    """이 pcode 링크 하나만 포함하는 가장 좁은 범위를 찾는다.
    다나와가 여러 용량 옵션을 하나의 li 안에 같이 묶어서 렌더링하는 경우가 있는데,
    그럴 때 find_parent('li') 텍스트를 그대로 쓰면 다른 옵션의 용량/가격이 섞여서
    엉뚱한 pcode에 엉뚱한 용량이 붙는 문제가 생긴다 (실제로 EDIMM 32GB가 8GB 상품
    링크로 잘못 연결된 사례로 확인됨). 그래서 "pcode 링크가 정확히 1개만 있는"
    가장 좁은 컨테이너를 찾아서 그 범위의 텍스트만 신뢰한다. 끝까지 못 찾으면
    이 옵션은 신뢰할 수 없다고 보고 건너뛴다(포기)."""
    candidates = [a, a.parent]
    li_parent = a.find_parent("li")
    if li_parent:
        candidates.append(li_parent)
        if li_parent.parent:
            candidates.append(li_parent.parent)

    for scope in candidates:
        if scope is None:
            continue
        pcode_links = scope.select("a[href*='pcode=']")
        if len(pcode_links) == 1:
            return scope
    return None  # 끝까지 모호하면 포기


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

        scope = find_unique_scope(a)
        if scope is None:
            continue  # 이 옵션 하나만 딱 집을 수 있는 범위를 못 찾음 -> 신뢰 못 함, 건너뜀
        text = scope.get_text(" ", strip=True)

        if has_excluded_keyword(text):
            continue

        cap_match = CAPACITY_PATTERN.search(text)
        if not cap_match:
            continue

        capacity_gb = int(cap_match.group(1))
        capacity = f"{capacity_gb}GB"
        if capacity not in VALID_CAPACITIES_BY_DIMM[dimm_type]:
            continue

        # 총액("543,000원")이 범위 안에 있으면 그걸 쓰고, 없으면(단가만 보이는 좁은
        # 범위일 때) 단가("15,469원/1GB") x 용량으로 총액을 역산한다.
        total_match = TOTAL_PRICE_PATTERN.search(text)
        if total_match:
            price = int(total_match.group(1).replace(",", ""))
        else:
            unit_match = UNIT_PRICE_PATTERN.search(text)
            if not unit_match:
                continue
            unit_price = int(unit_match.group(1).replace(",", ""))
            price = unit_price * capacity_gb  # 단가 x 용량 = 총액 추정

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

    # 같은 상품이 '이미지 카드'/'VS상품비교 팝업' 등 여러 블록에 중복 노출되는데,
    # 블록마다 보이는 용량 옵션이 서로 다를 수 있다(한쪽엔 8GB가 없고 다른쪽엔 있는 식).
    # 그래서 블록 하나만 고르지 않고, 용량 옵션이 2개 이상인 블록들을 전부 모아서
    # "용량별 최저가"로 병합한다 — 이러면 누락도 줄고, 같은 용량이 중복으로
    # 잡혀도(같은 상품이 여러 블록에 찍혀서) 자동으로 한 줄로 합쳐진다.
    best_by_capacity = {}
    for block in blocks:
        raw_link_count = len(block.select("a[href*='pcode=']"))
        if raw_link_count < 2:
            continue  # 옵션 1개짜리 단품 리스팅은 노이즈로 보고 제외 (원본 링크 개수 기준)
        variants = parse_capacity_variants(block, dimm_type, clock)
        for v in variants:
            cap = v["capacity"]
            if cap not in best_by_capacity or v["price_krw"] < best_by_capacity[cap]["price_krw"]:
                best_by_capacity[cap] = v

    return list(best_by_capacity.values())


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

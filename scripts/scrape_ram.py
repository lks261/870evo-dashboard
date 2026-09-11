"""
다나와 - 삼성전자 서버용 DDR4 RAM(RDIMM/EDIMM) 용량×클럭별 가격 수집
================================================================

SSD(870 EVO)와 다른 점: SSD는 한 상품에 용량별 옵션이 "가격비교 그룹"으로
깔끔하게 묶여서 나오는데, 서버용 RAM은 용량마다 사실상 별개 상품이라 그런
묶음이 없다. 그래서 "용량 + 클럭 + DIMM타입" 조합별로 각각 검색해서 그 중
최저가를 채택하는 방식으로 만들었다.

수집 대상 (요청하신 스펙 그대로):
    RDIMM(Registered): 클럭 17000 / 19200 / 21300 / 25600
    UDIMM(Unbuffered, 표기는 EDIMM): 클럭 19200 / 21300 / 25600  (17000 없음)
    각 클럭마다 용량:   8GB / 16GB / 32GB / 64GB
    → 총 (4+3) x 4 = 28개 조합

클럭 표기 대응:
    17000 = PC4-17000 = 2133MHz
    19200 = PC4-19200 = 2400MHz
    21300 = PC4-21300 = 2666MHz
    25600 = PC4-25600 = 3200MHz
    (다나와 상품명에 이 중 어떤 표기가 섞여 있어도 인식하도록 정규식을 넉넉하게 잡음)

주의:
    - RAM은 판매자마다 상품명 표기가 SSD보다 훨씬 제각각이라, 오검출 가능성이
      SSD 스크래퍼보다 높다. 처음 며칠은 대시보드에서 값이 튀거나 비어있는
      조합이 없는지 한 번씩 확인해보는 게 좋다.
    - 조합이 28개라 다나와에 짧은 시간 안에 여러 번 요청하게 된다. 요청 간
      REQUEST_DELAY 만큼 텀을 둬서 과도한 부하를 주지 않도록 함.
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
REQUEST_DELAY = 1.2

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ko-KR,ko;q=0.9",
}

# PC4-XXXXX(클럭코드) <-> MHz 대응. 상품명에 둘 중 뭐가 적혀있든 인식하기 위함.
CLOCK_MHZ = {
    "17000": "2133",
    "19200": "2400",
    "21300": "2666",
    "25600": "3200",
}

# (dimm_type, 허용 클럭 목록)
DIMM_CLOCKS = {
    "RDIMM": ["17000", "19200", "21300", "25600"],
    "EDIMM": ["19200", "21300", "25600"],
}
CAPACITIES = ["8GB", "16GB", "32GB", "64GB"]

CAPACITY_PATTERN = re.compile(r"(\d+)\s*GB", re.IGNORECASE)
PRICE_PATTERN = re.compile(r"([\d,]+)\s*원")


def build_query(dimm_type: str, clock: str, capacity: str) -> str:
    reg_kw = "REG" if dimm_type == "RDIMM" else "UDIMM"  # 검색어 자체는 업계 표준 용어(UDIMM)로 보냄
    return f"삼성전자 서버용 DDR4 {capacity} PC4-{clock} {reg_kw} ECC"


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


def find_candidate_blocks(soup: BeautifulSoup):
    candidates = soup.select("li.prod_item, li[id^='productItem']")
    if not candidates:
        candidates = soup.find_all("li")
    return candidates


def block_matches(text: str, dimm_type: str, clock: str, capacity: str) -> bool:
    if "삼성" not in text:
        return False
    if "DDR4" not in text.upper().replace(" ", ""):
        # 상품명에 'DDR4'가 아예 없으면 대상 아님 (DDR5 등 오검출 방지)
        if "DDR4" not in text:
            return False

    cap_num = capacity.replace("GB", "")
    # "8GB"가 문장 어디서든 독립된 숫자로 나와야 함 (80GB 같은 오탐 방지 위해 경계 체크)
    if not re.search(rf"(?<!\d){cap_num}\s*GB", text, re.IGNORECASE):
        return False

    mhz = CLOCK_MHZ[clock]
    has_clock = (clock in text) or (mhz in text)
    if not has_clock:
        return False

    if dimm_type == "RDIMM":
        if not ("REG" in text.upper() or "RDIMM" in text.upper()):
            return False
    else:  # EDIMM (Unbuffered) — 상품명 텍스트 판별은 여전히 UDIMM/Unbuffered 키워드로
        if "REG" in text.upper() or "RDIMM" in text.upper():
            return False  # RDIMM으로 오검출되는 것 방지
        if not ("UDIMM" in text.upper() or "UNBUFFERED" in text.upper() or "ECC" in text.upper()):
            return False

    return True


def extract_price(text: str):
    """텍스트에서 상품 가격을 뽑는다.
    주의: 다나와 표기는 보통 '상품가 12,220원 배송비 3,000원' 순서라서,
    가장 먼저 나오는 원화 숫자가 상품가다. min()을 쓰면 배송비(보통 더 작은 값)를
    상품가로 착각하는 버그가 생기므로, 반드시 '첫 매치'를 쓴다."""
    matches = PRICE_PATTERN.findall(text)
    for raw in matches:
        price = int(raw.replace(",", ""))
        if price >= 1000:  # 너무 작은 값(할인율 표시 등 잡음) 제외
            return price
    return None


def collect_one(dimm_type: str, clock: str, capacity: str):
    query = build_query(dimm_type, clock, capacity)
    html = fetch_search(query)
    if not html:
        return None

    soup = BeautifulSoup(html, "html.parser")
    blocks = find_candidate_blocks(soup)

    best_price = None
    best_pcode = None
    best_text = None
    for block in blocks:
        text = block.get_text(" ", strip=True)
        if not block_matches(text, dimm_type, clock, capacity):
            continue
        price = extract_price(text)
        if price is None:
            continue
        if best_price is None or price < best_price:
            best_price = price
            best_text = text[:120]  # 디버깅용으로 앞부분만 저장 (전체는 너무 길어서)
            a = block.select_one("a[href*='pcode=']")
            pcode_match = re.search(r"pcode=(\d+)", a.get("href", "")) if a else None
            best_pcode = pcode_match.group(1) if pcode_match else None

    if best_price is None:
        return None

    return {
        "site": SITE,
        "category": "RAM",
        "dimm_type": dimm_type,
        "clock": clock,
        "capacity": capacity,
        "price_krw": best_price,
        "pcode": best_pcode,
        "matched_text": best_text,  # 실제로 뭘 매칭했는지 나중에 검증할 때 씀
        "url": (
            f"https://prod.danawa.com/info/?pcode={best_pcode}"
            if best_pcode else f"https://search.danawa.com/dsearch.php?k1={query}"
        ),
    }


def sanity_check(items: list[dict]):
    """수집된 가격들 사이에 말이 안 되는 역전이 있는지 확인해서 로그에 경고를 남긴다.
    (자동으로 지우거나 고치지는 않음 — 사람이 한 번 눈으로 확인하라는 용도)"""
    warnings = []
    clock_order = {"17000": 0, "19200": 1, "21300": 2, "25600": 3}
    cap_order = {"8GB": 0, "16GB": 1, "32GB": 2, "64GB": 3}

    by_dimm_cap = {}
    by_dimm_clock = {}
    for it in items:
        by_dimm_cap.setdefault((it["dimm_type"], it["capacity"]), []).append(it)
        by_dimm_clock.setdefault((it["dimm_type"], it["clock"]), []).append(it)

    # 같은 용량 내에서: 클럭이 높은데 더 싸면 이상함
    for (dimm, cap), group in by_dimm_cap.items():
        group_sorted = sorted(group, key=lambda x: clock_order.get(x["clock"], 99))
        for a, b in zip(group_sorted, group_sorted[1:]):
            if b["price_krw"] < a["price_krw"]:
                warnings.append(
                    f"{dimm} {cap}: PC4-{a['clock']}({a['price_krw']:,}원) > "
                    f"PC4-{b['clock']}({b['price_krw']:,}원) — 클럭 높은데 더 쌈"
                )

    # 같은 클럭 내에서: 용량이 큰데 더 싸면 이상함
    for (dimm, clock), group in by_dimm_clock.items():
        group_sorted = sorted(group, key=lambda x: cap_order.get(x["capacity"], 99))
        for a, b in zip(group_sorted, group_sorted[1:]):
            if b["price_krw"] < a["price_krw"]:
                warnings.append(
                    f"{dimm} PC4-{clock}: {a['capacity']}({a['price_krw']:,}원) > "
                    f"{b['capacity']}({b['price_krw']:,}원) — 용량 큰데 더 쌈"
                )

    if warnings:
        print(f"\n⚠️  가격 역전 감지 ({len(warnings)}건) — 매칭이 잘못됐을 가능성이 있으니 확인 필요:")
        for w in warnings:
            print(f"   - {w}")
    else:
        print("\n✅ 가격 역전 없음 (용량/클럭 순서 정상)")


def main():
    print("[다나와] 삼성전자 서버용 DDR4 RAM 용량×클럭별 가격 수집 시작")

    items = []
    combos = [
        (dimm_type, clock, capacity)
        for dimm_type, clocks in DIMM_CLOCKS.items()
        for clock in clocks
        for capacity in CAPACITIES
    ]

    for i, (dimm_type, clock, capacity) in enumerate(combos, 1):
        label = f"{dimm_type} {clock} {capacity}"
        print(f"  ({i}/{len(combos)}) {label} 검색 중...")
        item = collect_one(dimm_type, clock, capacity)
        if item:
            items.append(item)
            print(f"    -> {item['price_krw']:,}원 | {item.get('matched_text', '')}")
        else:
            print(f"    -> 못 찾음 (스킵)")
        time.sleep(REQUEST_DELAY)

    if not items:
        print("경고: 수집된 항목이 없습니다. 이번 회차는 저장하지 않고 종료합니다.")
        return

    print(f"\n총 {len(items)}/{len(combos)}개 조합 수집 완료")
    sanity_check(items)
    latest, history = merge_and_save("ram", SITE, items)
    print(f"저장 완료 (dataset=ram, site={SITE}). 히스토리 누적 {len(history['entries'])}일치")


if __name__ == "__main__":
    main()

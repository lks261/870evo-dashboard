"""
다나와 - 삼성 870 EVO 용량별 단가 수집 스크립트 (GitHub Actions용)
================================================================

- "정품"과 "병행수입"만 수집한다 (중고 / 벌크 / 해외구매는 제외)
- 결과는 site="다나와" 태그를 붙여서 data/latest.json, data/history.json에
  다른 사이트(예: 컴퓨존) 결과와 함께 병합 저장된다 (scripts/common.py 참고)
"""

import re
import time
import sys
import os

import requests
from bs4 import BeautifulSoup

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import merge_and_save, capacity_sort_key, CAPACITY_ORDER

SITE = "다나와"
TARGET_KEYWORD = "870 EVO"
SEARCH_URL = "https://search.danawa.com/dsearch.php"
CATE_CODE = "112760"
REQUEST_DELAY = 2
MAX_PAGES = 3

# 이 값에 없는 유형(중고/벌크/해외구매 등)은 전부 제외
ALLOWED_SOURCE_TYPES = {"정품", "병행수입"}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ko-KR,ko;q=0.9",
}

CAPACITY_PATTERN = re.compile(r"(\d+(?:\.\d+)?)\s*(TB|GB)", re.IGNORECASE)
VALID_CAPACITIES = set(CAPACITY_ORDER.keys())
UNIT_PRICE_PATTERN = re.compile(r"([\d,]+)\s*원\s*/\s*1GB")
PRICE_PATTERN = re.compile(r"([\d,]+)\s*원")


def fetch_page(page: int = 1) -> str:
    params = {
        "k1": TARGET_KEYWORD,
        "module": "goods",
        "act": "dispMain",
        "tab": "goods",
        "page": page,
    }
    resp = requests.get(SEARCH_URL, params=params, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    return resp.text


def find_target_blocks(soup: BeautifulSoup):
    candidates = soup.select("li.prod_item, li[id^='productItem']")
    if not candidates:
        candidates = soup.find_all(
            lambda tag: tag.name == "li" and TARGET_KEYWORD in tag.get_text()
        )
    matched = []
    for block in candidates:
        text = block.get_text(" ", strip=True)
        if TARGET_KEYWORD in text and "삼성" in text:
            matched.append(block)
    return matched


def detect_source_type(block) -> str:
    """상품명 텍스트를 보고 정품/병행수입/중고/벌크/해외구매 등을 구분한다."""
    name_tag = block.select_one("a.prod_name, .prod_name a")
    name_text = name_tag.get_text(" ", strip=True) if name_tag else block.get_text(" ", strip=True)

    if "병행수입" in name_text:
        return "병행수입"
    if "중고" in name_text:
        return "중고"
    if "벌크" in name_text:
        return "벌크"
    if "해외구매" in name_text or "해외배송" in name_text or "직구" in name_text:
        return "해외구매"
    return "정품"


def parse_capacity_variants(block, source_type: str) -> list[dict]:
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

        cap_match = CAPACITY_PATTERN.search(text)
        price_match = PRICE_PATTERN.search(text)

        if not (cap_match and price_match):
            continue

        capacity = f"{cap_match.group(1)}{cap_match.group(2).upper()}"
        if capacity not in VALID_CAPACITIES:
            continue

        price = int(price_match.group(1).replace(",", ""))

        results.append(
            {
                "site": SITE,
                "source_type": source_type,
                "capacity": capacity,
                "price_krw": price,
                "pcode": pcode,
                "url": f"https://prod.danawa.com/info/?pcode={pcode}&cate={CATE_CODE}",
            }
        )
        seen_pcodes.add(pcode)
    return results


def collect() -> list[dict]:
    all_variants = []
    seen_pcodes = set()

    for page in range(1, MAX_PAGES + 1):
        html = fetch_page(page)
        soup = BeautifulSoup(html, "html.parser")
        blocks = find_target_blocks(soup)

        for block in blocks:
            source_type = detect_source_type(block)
            variants = parse_capacity_variants(block, source_type)

            if len(variants) < 2:
                continue  # 단품 리스팅(노이즈) 제외

            for v in variants:
                if v["source_type"] not in ALLOWED_SOURCE_TYPES:
                    continue
                if v["pcode"] in seen_pcodes:
                    continue
                seen_pcodes.add(v["pcode"])
                all_variants.append(v)

        if all_variants:
            break
        time.sleep(REQUEST_DELAY)

    return all_variants


def main():
    print(f"[다나와] 삼성 870 EVO 용량별 단가 수집 시작 (정품/병행수입만)")

    variants = collect()

    if not variants:
        print("경고: 상품을 찾지 못했습니다. 이번 회차는 저장하지 않고 종료합니다.")
        return

    variants.sort(key=lambda v: (v["source_type"], capacity_sort_key(v["capacity"])))

    print("\n수집 결과:")
    for v in variants:
        print(f"  [{v['source_type']:>4}] {v['capacity']:>6} | {v['price_krw']:>10,}원")

    latest, history = merge_and_save("ssd", SITE, variants)
    print(f"\n저장 완료 (site={SITE}). 히스토리 누적 {len(history['entries'])}일치")


if __name__ == "__main__":
    main()


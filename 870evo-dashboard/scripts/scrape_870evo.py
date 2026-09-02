"""
다나와 - 삼성 870 EVO 용량별 단가 수집 스크립트 (GitHub Actions용)
================================================================

로컬 버전과 다른 점:
    - "정품(리테일)"과 "병행수입"만 수집한다 (중고 / 벌크 / 해외구매는 제외)
    - 결과를 CSV가 아니라 JSON으로 저장한다 (대시보드 페이지가 바로 fetch해서 씀)
    - data/latest.json   : 가장 최근 실행 결과 스냅샷 (대시보드가 이걸 보여줌)
    - data/history.json  : 날짜별로 계속 누적되는 전체 히스토리 (그래프용)

동작 순서는 로컬 버전과 동일:
    1. 다나와 통합검색 페이지(search.danawa.com)에서 "870 evo" 키워드로 검색
    2. "가격비교" 섹션에서 상품 블록을 찾고, 정품/병행수입만 남긴다
    3. 용량별(250GB~8TB) 가격과 단가(원/GB)를 추출
    4. data/latest.json, data/history.json 갱신

주의:
    - 다나와 페이지 구조가 바뀌면 셀렉터를 다시 맞춰야 함 (find_target_blocks, detect_source_type)
    - GitHub Actions에서 하루 1회 실행되는 것을 전제로 작성됨. 그 이상 자주 돌리지 말 것
"""

import re
import json
import time
import os
from datetime import datetime, timezone, timedelta

import requests
from bs4 import BeautifulSoup

# ------------------------------------------------------------------
# 설정
# ------------------------------------------------------------------
TARGET_KEYWORD = "870 EVO"
SEARCH_URL = "https://search.danawa.com/dsearch.php"
CATE_CODE = "112760"
REQUEST_DELAY = 2
MAX_PAGES = 3

# 이 값에 없는 유형(중고/벌크/해외구매 등)은 전부 제외
ALLOWED_SOURCE_TYPES = {"정품(리테일)", "병행수입"}

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_DIR = os.path.dirname(SCRIPT_DIR)
DATA_DIR = os.path.join(REPO_DIR, "data")
LATEST_PATH = os.path.join(DATA_DIR, "latest.json")
HISTORY_PATH = os.path.join(DATA_DIR, "history.json")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ko-KR,ko;q=0.9",
}

CAPACITY_PATTERN = re.compile(r"(\d+(?:\.\d+)?)\s*(TB|GB)", re.IGNORECASE)
VALID_CAPACITIES = {
    "120GB", "128GB", "240GB", "250GB", "256GB", "480GB", "500GB", "512GB",
    "1TB", "2TB", "4TB", "8TB", "16TB",
}
UNIT_PRICE_PATTERN = re.compile(r"([\d,]+)\s*원\s*/\s*1GB")
PRICE_PATTERN = re.compile(r"([\d,]+)\s*원")

KST = timezone(timedelta(hours=9))


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
    return "정품(리테일)"


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
        unit_price_match = UNIT_PRICE_PATTERN.search(text)

        if not (cap_match and price_match):
            continue

        capacity = f"{cap_match.group(1)}{cap_match.group(2).upper()}"
        if capacity not in VALID_CAPACITIES:
            continue

        price = int(price_match.group(1).replace(",", ""))
        unit_price = (
            int(unit_price_match.group(1).replace(",", ""))
            if unit_price_match
            else None
        )

        results.append(
            {
                "source_type": source_type,
                "capacity": capacity,
                "price_krw": price,
                "price_per_gb_krw": unit_price,
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
                    continue  # 중고/벌크/해외구매 등 제외 — 정품/병행수입만
                if v["pcode"] in seen_pcodes:
                    continue
                seen_pcodes.add(v["pcode"])
                all_variants.append(v)

        if all_variants:
            break
        time.sleep(REQUEST_DELAY)

    return all_variants


def capacity_sort_key(capacity: str) -> float:
    match = CAPACITY_PATTERN.search(capacity)
    if not match:
        return 0
    value = float(match.group(1))
    unit = match.group(2).upper()
    return value * 1024 if unit == "TB" else value


def load_json(path, default):
    if not os.path.exists(path):
        return default
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def main():
    now_kst = datetime.now(KST)
    today = now_kst.strftime("%Y-%m-%d")
    print(f"[{now_kst.isoformat()}] 삼성 870 EVO 용량별 단가 수집 시작 (정품/병행수입만)")

    variants = collect()

    if not variants:
        print("경고: 상품을 찾지 못했습니다. 이번 회차는 저장하지 않고 종료합니다.")
        return

    variants.sort(key=lambda v: (v["source_type"], capacity_sort_key(v["capacity"])))

    print("\n수집 결과:")
    for v in variants:
        unit = f"{v['price_per_gb_krw']}원/GB" if v["price_per_gb_krw"] else "-"
        print(f"  [{v['source_type']:>8}] {v['capacity']:>6} | {v['price_krw']:>10,}원 | {unit}")

    # 1) 최신 스냅샷 저장 (대시보드가 화면에 바로 보여줄 데이터)
    latest = {
        "updated_at": now_kst.isoformat(),
        "updated_at_display": now_kst.strftime("%Y-%m-%d %H:%M"),
        "items": variants,
    }
    save_json(LATEST_PATH, latest)

    # 2) 히스토리에 오늘자 데이터 누적 (이미 오늘 데이터가 있으면 덮어씀 → 하루 여러 번 실행돼도 안전)
    history = load_json(HISTORY_PATH, {"entries": []})
    history["entries"] = [e for e in history["entries"] if e.get("date") != today]
    history["entries"].append({"date": today, "items": variants})
    history["entries"].sort(key=lambda e: e["date"])
    save_json(HISTORY_PATH, history)

    print(f"\n저장 완료: {LATEST_PATH}")
    print(f"저장 완료: {HISTORY_PATH} (누적 {len(history['entries'])}일치)")


if __name__ == "__main__":
    main()

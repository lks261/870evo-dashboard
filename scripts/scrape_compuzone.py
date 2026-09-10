"""
컴퓨존 - [삼성전자] 공식인증 870 EVO SATA 용량별 가격 수집 스크립트
================================================================

컴퓨존은 검색결과 목록 자체가 자바스크립트로 그려져서(초기 HTML엔 상품이 안 담김),
검색페이지를 그대로 크롤링하기 어렵다. 대신 이 특정 상품의 "상세페이지" 하단에는
같은 라인업의 용량별 옵션(250GB~8TB)이 가격과 함께 리스트로 그대로 노출되므로,
상세페이지 하나만 가져오면 6개 용량을 한 번에 얻을 수 있다.

※ 병행수입/중고 등은 이 상품 옵션 목록에 아예 섞이지 않으므로 별도 필터링이 필요 없다.
   (사용자가 원한 것도 "공식인증 870 EVO SATA" 이 라인업 하나만이라 이 방식이 딱 맞음)

주의 — 이 스크립트는 상품번호(ProductNo)를 하드코딩해서 쓴다:
    컴퓨존은 검색 결과에 여러 판매자/등록유형 상품이 섞여 나오고 구조가 자바스크립트
    기반이라, 매번 검색해서 "이게 그 상품이 맞다"를 안정적으로 자동 판별하기가
    다나와보다 어렵다. 대신 이 라인업의 대표 상품(1TB, ProductNo=755257) 상세페이지에
    전체 옵션이 노출되는 걸 확인했으므로, 그 페이지 하나만 가져와 옵션 목록을 파싱한다.
    나중에 컴퓨존이 이 상품을 단종하거나 URL 구조를 바꾸면 REP_PRODUCT_NO를 다시
    확인해서 갱신해야 한다.
"""

import re
import sys
import os
import time

import requests
from bs4 import BeautifulSoup

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import merge_and_save, capacity_sort_key, CAPACITY_ORDER

SITE = "컴퓨존"
SOURCE_TYPE = "정품"  # 컴퓨존은 이 라인업(공식인증 정품)만 수집 대상

REP_PRODUCT_NO = 755257  # [1TB] 공식인증 870 EVO SATA

# 데스크톱이 막힐 경우를 대비해 모바일 서브도메인도 순서대로 시도한다
CANDIDATE_URLS = [
    f"https://www.compuzone.co.kr/product/product_detail.htm?ProductNo={REP_PRODUCT_NO}",
    f"https://m.compuzone.co.kr/product/product_detail.htm?ProductNo={REP_PRODUCT_NO}",
]
PRODUCT_DETAIL_URL = CANDIDATE_URLS[0]  # 대시보드 링크 표기용 기본값

REQUIRED_TITLE_KEYWORDS = ["870 EVO", "공식인증"]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ko-KR,ko;q=0.9",
}

VALID_CAPACITIES = set(CAPACITY_ORDER.keys())
OPTION_PATTERN = re.compile(r"\[\s*(\d+(?:\.\d+)?\s*(?:GB|TB))\s*\]\s*([\d,]+)\s*원")


def fetch_product_page() -> str:
    """데스크톱 URL을 먼저 시도하고, 실패하면 모바일 URL로 넘어간다.
    (컴퓨존이 GitHub Actions 같은 해외 데이터센터 IP를 막아두면 접속 자체가
    타임아웃되는데, 모바일 서브도메인은 정책이 다를 수 있어 우회를 시도함)"""
    last_error = None
    for url in CANDIDATE_URLS:
        for attempt in range(3):  # 네트워크 흔들림 대비 재시도 (점진적으로 대기시간 늘림)
            try:
                resp = requests.get(url, headers=HEADERS, timeout=20)
                resp.raise_for_status()
                resp.encoding = "euc-kr"
                print(f"접속 성공: {url}")
                return resp.text
            except requests.exceptions.RequestException as e:
                last_error = e
                wait = 3 * (attempt + 1)
                print(f"접속 실패 ({url}, 시도 {attempt+1}/3): {e} → {wait}초 대기 후 재시도")
                time.sleep(wait)
    raise RuntimeError(
        f"모든 URL에서 접속 실패. 컴퓨존이 이 서버(GitHub Actions)의 IP를 "
        f"차단하고 있을 가능성이 높습니다. 마지막 에러: {last_error}"
    )


def parse_options(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    title = soup.title.get_text(strip=True) if soup.title else ""

    if not all(kw in title for kw in REQUIRED_TITLE_KEYWORDS):
        print(f"경고: 페이지 제목이 예상과 다릅니다 ('{title}'). "
              f"REP_PRODUCT_NO가 더 이상 유효하지 않을 수 있습니다.")

    text = soup.get_text(" ", strip=True)
    matches = OPTION_PATTERN.findall(text)

    results = []
    seen_caps = set()
    for cap_raw, price_raw in matches:
        capacity = cap_raw.replace(" ", "").upper()
        if capacity not in VALID_CAPACITIES:
            continue
        if capacity in seen_caps:
            continue  # 페이지 내 같은 옵션이 중복 노출되는 경우 첫 값만 사용
        seen_caps.add(capacity)
        price = int(price_raw.replace(",", ""))
        results.append({
            "site": SITE,
            "source_type": SOURCE_TYPE,
            "capacity": capacity,
            "price_krw": price,
            "url": PRODUCT_DETAIL_URL,
        })
    return results


def main():
    print(f"[컴퓨존] 공식인증 870 EVO SATA 용량별 가격 수집 시작")

    html = fetch_product_page()
    items = parse_options(html)

    if not items:
        print("경고: 옵션 목록을 찾지 못했습니다. 페이지 구조가 바뀌었을 수 있습니다. "
              "이번 회차는 저장하지 않고 종료합니다.")
        return

    items.sort(key=lambda v: capacity_sort_key(v["capacity"]))

    print("\n수집 결과:")
    for v in items:
        print(f"  {v['capacity']:>6} | {v['price_krw']:>10,}원")

    latest, history = merge_and_save("ssd", SITE, items)
    print(f"\n저장 완료 (site={SITE}). 히스토리 누적 {len(history['entries'])}일치")


if __name__ == "__main__":
    main()

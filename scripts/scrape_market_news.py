"""
Fusion Worldwide "The Greensheet" 월간 시장 리포트에서
메모리(DRAM/RDIMM) / 스토리지(SSD·NAND) / 주요 이슈 섹션만 추출하는 스크래퍼
================================================================

동작:
    1. 리소스 목록 페이지(/ko/resources)에서 "Greensheet" 최신 글 링크를 찾는다.
       (URL이 "the-greensheet-2026년-9월"처럼 매달 바뀌어서, 날짜로 계산해
        접속하지 않고 목록에서 매번 최신 링크를 찾는 방식을 쓴다)
    2. 그 리포트 페이지에서 "주요 주제", "메모리", "스토리지" 섹션의 불릿만 뽑는다.
    3. 각 불릿은 원문 그대로 두지 않고 앞부분(핵심 문장)만 짧게 잘라서 저장한다.
       (원문 전체를 그대로 복제하지 않기 위함. 전체 맥락이 필요하면 원문 링크로
        연결되는 "출처 보기" 버튼을 대시보드에 같이 노출한다)

주기: 월간 리포트이므로 하루 1회가 아니라 월 1회(매달 초) 실행하면 충분하다.

주의:
    - 이 사이트는 실제 접속 테스트를 못 해봤다(샌드박스 네트워크 제약).
      최초 실행 시 구조가 안 맞으면 Actions 로그의 경고 메시지를 보고
      find_section_bullets()의 탐색 방식을 조정해야 할 수 있다.
"""

import re
import sys
import os
from datetime import datetime, timezone, timedelta

import requests
from bs4 import BeautifulSoup

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import load_json, save_json, dataset_paths

DATASET = "market_news"
RESOURCES_URL = "https://info.fusionww.com/ko/resources"
KST = timezone(timedelta(hours=9))

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ko-KR,ko;q=0.9",
}

# 이 섹션들만 뽑는다 (요청하신 "메모리/SSD 낸드플래시 + 주요 이슈")
SECTION_HEADINGS = {
    "key_topics": ["주요 주제"],
    "memory": ["메모리"],
    "storage": ["스토리지"],
}

MAX_BULLET_LEN = 90  # 원문을 그대로 옮기지 않기 위해 핵심 문장만 짧게 자름


def fetch(url: str) -> str:
    resp = requests.get(url, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    resp.encoding = resp.apparent_encoding or "utf-8"
    return resp.text


def to_absolute(href: str) -> str:
    if href.startswith("/"):
        return "https://info.fusionww.com" + href
    return href


def is_tag_or_category_link(href: str) -> bool:
    """'/tag/the-greensheet' 같은 분류 페이지는 개별 리포트가 아니므로 제외."""
    return "/tag/" in href.lower() or "/category/" in href.lower()


def looks_like_individual_report(href: str) -> bool:
    """개별 리포트 링크는 보통 'the-greensheet-2026년-9월'처럼 날짜(숫자)가 슬러그에
    붙어 있다. 태그 페이지('the-greensheet'만 있고 뒤에 아무것도 안 붙음)와
    구분하기 위한 조건."""
    if is_tag_or_category_link(href):
        return False
    if "greensheet" not in href.lower():
        return False
    return bool(re.search(r"greensheet.+\d", href, re.IGNORECASE))


def find_report_links(html: str) -> list[tuple[str, str]]:
    soup = BeautifulSoup(html, "html.parser")
    results = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if looks_like_individual_report(href):
            text = a.get_text(" ", strip=True) or href
            results.append((text, to_absolute(href)))
    return results


def find_latest_report_url() -> tuple[str, str] | None:
    """1단계: 리소스 목록 페이지에서 'Greensheet' 관련 링크를 찾는다
       (개별 리포트일 수도, 전용 태그/분류 목록 페이지일 수도 있음).
    2단계: 찾은 게 태그/분류 페이지면, 그 안에 들어가서 실제 개별 리포트
       링크를 다시 찾는다. (실제로 이렇게 중첩된 구조였던 게 확인됨:
       메인 목록 -> "THE GREENSHEET" 태그 페이지 -> 개별 월간 리포트들)
    """
    html = fetch(RESOURCES_URL)

    # 메인 목록에 이미 개별 리포트 링크가 바로 있는 경우
    direct_hits = find_report_links(html)
    if direct_hits:
        return direct_hits[0]

    # 없으면 Greensheet 관련 링크(태그 페이지 포함 전부)를 모아서 따라 들어가본다
    soup = BeautifulSoup(html, "html.parser")
    related_links = []
    for a in soup.find_all("a", href=True):
        text = a.get_text(" ", strip=True)
        href = a["href"]
        if "greensheet" in text.lower() or "greensheet" in href.lower():
            related_links.append(to_absolute(href))

    for link in related_links:
        try:
            sub_html = fetch(link)
        except requests.exceptions.RequestException:
            continue
        hits = find_report_links(sub_html)
        if hits:
            return hits[0]

    return None


def find_section_bullets(soup: BeautifulSoup, heading_keywords: list[str]) -> list[str]:
    """제목 텍스트(strong/b 태그)가 heading_keywords로 시작하는 지점을 찾아서,
    그 뒤에 나오는 <ul><li> 불릿들을 가져온다."""
    heading_tag = None
    for tag in soup.find_all(["strong", "b"]):
        text = tag.get_text(strip=True)
        if any(text.startswith(kw) for kw in heading_keywords):
            heading_tag = tag
            break

    if heading_tag is None:
        return []

    # 제목이 속한 블록(p/div/h*)을 찾고, 그 뒤에 나오는 첫 <ul>을 찾는다
    container = heading_tag.find_parent(["p", "div", "h1", "h2", "h3", "h4", "li"]) or heading_tag
    next_ul = container.find_next("ul")
    if next_ul is None:
        return []

    bullets = []
    for li in next_ul.find_all("li", recursive=False):
        text = li.get_text(" ", strip=True)
        if text:
            bullets.append(text)
    return bullets


def shorten(text: str, max_len: int = MAX_BULLET_LEN) -> str:
    """원문을 그대로 옮기지 않도록, 핵심 문장(첫 문장 또는 앞부분)만 짧게 자른다."""
    # 첫 문장(마침표 기준)만 취하고, 그래도 길면 글자 수로 자름
    first_sentence = re.split(r"(?<=[.!?])\s", text.strip())[0]
    candidate = first_sentence if first_sentence else text
    if len(candidate) > max_len:
        candidate = candidate[:max_len].rstrip() + "…"
    return candidate


def collect():
    found = find_latest_report_url()
    if not found:
        print("경고: 리소스 목록에서 Greensheet 링크를 찾지 못했습니다.")
        return None

    title, url = found
    print(f"최신 리포트: {title}\n{url}")

    html = fetch(url)
    soup = BeautifulSoup(html, "html.parser")

    sections = {}
    for key, keywords in SECTION_HEADINGS.items():
        bullets = find_section_bullets(soup, keywords)
        if not bullets:
            print(f"  경고: '{keywords[0]}' 섹션을 못 찾았습니다.")
        sections[key] = [shorten(b) for b in bullets]
        for b in sections[key]:
            print(f"  [{key}] {b}")

    if not any(sections.values()):
        print("경고: 어떤 섹션도 못 찾았습니다. 페이지 구조가 바뀌었을 수 있습니다.")
        return None

    return {"title": title, "url": url, "sections": sections}


def main():
    print("[Fusion Worldwide] The Greensheet 시장동향 수집 시작")
    result = collect()
    if not result:
        print("이번 회차는 저장하지 않고 종료합니다.")
        return

    now_kst = datetime.now(KST)
    latest_path, history_path = dataset_paths(DATASET)

    latest = {
        "updated_at": now_kst.isoformat(),
        "updated_at_display": now_kst.strftime("%Y-%m-%d %H:%M"),
        "report_title": result["title"],
        "report_url": result["url"],
        "sections": result["sections"],
    }
    save_json(latest_path, latest)

    # 과거 발행분도 참고할 수 있게 월별로 누적 (같은 리포트면 덮어씀)
    history = load_json(history_path, {"entries": []})
    history["entries"] = [e for e in history["entries"] if e.get("report_url") != result["url"]]
    history["entries"].append({
        "collected_at": now_kst.strftime("%Y-%m-%d"),
        "report_title": result["title"],
        "report_url": result["url"],
        "sections": result["sections"],
    })
    history["entries"].sort(key=lambda e: e["collected_at"])
    save_json(history_path, history)

    print(f"\n저장 완료 (dataset={DATASET}). 히스토리 누적 {len(history['entries'])}건")


if __name__ == "__main__":
    main()

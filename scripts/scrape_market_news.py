"""
Fusion Worldwide "The Greensheet" 월간 시장 리포트에서
메모리(DRAM/RDIMM) / 스토리지(SSD·NAND) / 주요 이슈 섹션만 추출하는 스크래퍼
================================================================

동작:
    1. 리소스 목록 페이지(/ko/resources)에서 "Greensheet" 최신 글 링크를 찾는다.
       (URL이 "the-greensheet-2026년-9월"처럼 매달 바뀌어서, 날짜로 계산해
        접속하지 않고 목록에서 매번 최신 링크를 찾는 방식을 쓴다)
    2. 리포트의 "주요 주제", "메모리", "스토리지" 섹션에서 문단과 목록을 읽는다.
    3. 섹션별로 핵심 문장을 최대 3개 저장한다. 원문 링크도 함께 저장한다.

주기: 월간 리포트이므로 하루 1회가 아니라 월 1회(매달 초) 실행하면 충분하다.

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

HEADING_TAGS = ("h1", "h2", "h3", "h4", "h5", "h6")
SECTION_BOUNDARIES = (
    *(name for names in SECTION_HEADINGS.values() for name in names),
    "시장 변동성 지수", "제품 업데이트", "네트워킹", "수동부품 및 원자재",
    "집적 회로", "CPU", "GPU", "조달 우선순위", "리소스로 돌아가기",
)
SHARE_LABELS = {"linkedin", "twitter", "email", "e-mail", "facebook", "공유"}
SECTION_TERMS = {
    "memory": re.compile(r"(?<![A-Z0-9])(?:DDR\d*|LPDDR\d*[A-Z]?|DRAM|RDIMM|HBM\d*)(?![A-Z0-9])", re.I),
    "storage": re.compile(r"(?<![A-Z0-9])(?:SSD|NAND)(?![A-Z0-9])|낸드", re.I),
}
MAX_ITEMS = 3
PREFERRED_SENTENCE_LENGTH = 120


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


def heading_matches(text: str, keywords) -> bool:
    return any(re.match(rf"^{re.escape(kw)}\s*(?:$|[:：(（])", text) for kw in keywords)


def find_section_items(soup: BeautifulSoup, heading_keywords: list[str]) -> list[str]:
    """Collect sibling paragraphs and list items until the next section."""
    heading = next((
        tag for tag in soup.find_all(("p", *HEADING_TAGS))
        if not tag.find_parent(["table", "li", "nav", "footer"])
        and heading_matches(tag.get_text(" ", strip=True), heading_keywords)
    ), None)
    if heading is None:
        return []

    items = []
    for block in heading.find_next_siblings():
        if block.name in (*HEADING_TAGS, "table", "nav", "footer"):
            break
        if block.name not in ("p", "ul", "ol"):
            continue
        paragraphs = [block] if block.name == "p" else block.find_all("li", recursive=False)
        for paragraph in paragraphs:
            text = re.sub(r"\s+", " ", paragraph.get_text(" ", strip=True))
            if heading_matches(text, SECTION_BOUNDARIES):
                return items
            if text and text.casefold() not in SHARE_LABELS and not all(
                node.find_parent("a") for node in paragraph.find_all(string=True) if node.strip()
            ):
                items.append(text)
    return items


def summarize(text: str, terms: re.Pattern | None) -> str:
    """Keep complete sentences. Prefer short sentences with relevant figures."""
    text = re.sub(r"\s+([:：,.!?])", r"\1", text)
    label, separator, body = text.partition(":")
    has_label = bool(separator and len(label) <= 48 and body.strip())
    sentences = re.split(r"(?<=[.!?])\s+(?=[가-힣A-Z0-9])", body.strip() if has_label else text)
    prefix = f"{label}: " if has_label else ""
    candidates = [s for s in sentences if len(s) <= PREFERRED_SENTENCE_LENGTH]
    if terms:
        relevant = [s for s in candidates if terms.search(s)]
        if relevant:
            candidates = relevant
    if candidates:
        sentence = max(candidates, key=lambda s: bool(re.search(r"\d\s*(?:%|주|개월|GB|TB)", s, re.I)))
        return prefix + sentence if len(prefix + sentence) <= PREFERRED_SENTENCE_LENGTH else sentence
    if has_label:
        return label
    return sentences[0]


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
        terms = SECTION_TERMS.get(key)
        bullets = find_section_items(soup, keywords)
        if terms:
            bullets = [bullet for bullet in bullets if terms.search(bullet)]
        if not bullets:
            print(f"  경고: '{keywords[0]}' 섹션을 못 찾았습니다.")
        summaries = dict.fromkeys(summarize(b, terms) for b in bullets)
        sections[key] = list(summaries)[:MAX_ITEMS]
        for b in sections[key]:
            print(f"  [{key}] {b}")

    if not all(sections.values()):
        print("경고: 일부 섹션에 유효한 본문이 없어 기존 데이터를 유지합니다.")
        return None

    return {"title": title, "url": url, "sections": sections}


def main():
    print("[Fusion Worldwide] The Greensheet 시장동향 수집 시작")
    result = collect()
    if not result:
        print("이번 회차는 저장하지 않고 종료합니다.")
        raise SystemExit(1)

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

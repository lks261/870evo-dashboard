"""Shared parsing for Danawa price-comparison listings."""

import re
from urllib.parse import parse_qs, urljoin, urlsplit

import requests
from bs4 import BeautifulSoup

SEARCH_URL = "https://search.danawa.com/"
PRODUCT_URL = "https://prod.danawa.com/"
HEADERS = {"Accept-Language": "ko-KR,ko;q=0.9"}
REQUEST_DELAY = 10
CARD_SELECTOR = "li.prod_item, [id^='productItem'], li.product-item, li.product_item"
TITLE_SELECTOR = "a.prod_name, .prod_name a, a.product_name, .product_name a, a.product-name"
SEARCH_TITLE_SELECTOR = "#DnwSearchContents li > div > div > p > a[href*='pcode=']"
PRICE_SELECTOR = ".price_sect, .price_box, .lowest_price"
UNIT_PRICE = re.compile(r"(?<!\d)[\d,]+\s*원\s*/\s*1\s*GB\b", re.I)
TOTAL_PRICE = re.compile(r"(?<![\d,])([\d,]+)\s*원")
SHIPPING_PRICE = re.compile(r"배송비\s*[:+]?\s*[\d,]+\s*원")
CAPACITY = re.compile(r"(?<![\w.])(\d+(?:\.\d+)?)\s*(GB|TB)\b(?!\s*[x×+])", re.I)


def fetch_html(url, params):
    response = requests.get(url, params=params, headers=HEADERS, timeout=20)
    print(f"[다나와 HTTP] {response.status_code} {response.url} ({len(response.content):,} bytes)")
    response.raise_for_status()
    return response.content


def fetch_search(query, page=1):
    params = {"query": query}
    if page > 1:
        params["page"] = page
    return fetch_html(SEARCH_URL, params)


def text_of(tag):
    return tag.get_text(" ", strip=True)


def pcode_of(link):
    url = urlsplit(urljoin(PRODUCT_URL, link.get("href", "")))
    if url.hostname != "prod.danawa.com" or url.path.rstrip("/") != "/info":
        return None
    code = parse_qs(url.query).get("pcode", [""])[0]
    return code if code.isascii() and code.isdigit() else None


def product_cards(html):
    soup = BeautifulSoup(html, "html.parser")
    title_links = [(card, card.select_one(TITLE_SELECTOR)) for card in soup.select(CARD_SELECTOR)]
    # Find the title link first, then walk to its card without a complex :has() selector.
    title_links.extend((link.find_parent("li"), link) for link in soup.select(SEARCH_TITLE_SELECTOR))
    matched = {}
    for card, title_link in title_links:
        if card is not None and title_link is not None and pcode_of(title_link):
            title = " ".join(title_link.get_text().split())
            if title:
                matched.setdefault(id(card), (card, title))
    if not matched:
        page_title = text_of(soup.title)[:100] if soup.title else "(제목 없음)"
        print(f"[다나와 HTML] 상품명·상품코드가 있는 카드 0개, 페이지 제목 {page_title!r}")
    return list(matched.values())


def capacities(text):
    return {
        number + unit.upper()
        for number, unit in CAPACITY.findall(UNIT_PRICE.sub("", text))
    }


def total_price(text):
    text = SHIPPING_PRICE.sub("", UNIT_PRICE.sub("", text))
    matches = TOTAL_PRICE.findall(text)
    if len(matches) != 1:
        return None
    return int(matches[0].replace(",", "")) or None


def listing_prices(card, title):
    """Yield a product code, an unambiguous capacity and an exact listed price."""
    title_capacities = capacities(title)
    links = [(link, pcode_of(link)) for link in card.select("a[href*='pcode=']")]
    linked_codes = {code for _, code in links if code}
    seen = set()
    for link, code in links:
        if not code or code in seen:
            continue
        link_text = text_of(link)
        link_price = total_price(link_text)
        for scope in (link, *link.parents):
            if scope is card:
                # A group description can contain capacities for unrelated specs.
                if linked_codes == {code} and len(title_capacities) == 1 and link_price:
                    seen.add(code)
                    yield code, next(iter(title_capacities)), link_price, link_text
                break
            scope_codes = {pcode_of(other) for other in scope.select("a[href*='pcode=']")}
            scope_codes.discard(None)
            if scope_codes - {code}:
                break
            scope_text = text_of(scope)
            # Capacity labels frequently sit beside both the unit-price and total-price links.
            option_capacities = capacities(scope_text)
            if not option_capacities and link_price and linked_codes == {code}:
                option_capacities = title_capacities
            if len(option_capacities) != 1:
                continue
            price_node = scope.select_one(PRICE_SELECTOR)
            price = link_price or (total_price(text_of(price_node)) if price_node else None)
            price = price or total_price(scope_text)
            if price:
                seen.add(code)
                yield code, next(iter(option_capacities)), price, scope_text
                break

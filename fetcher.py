import logging
import re
import urllib.error
import urllib.request
from html.parser import HTMLParser
from typing import Optional

logger = logging.getLogger("price_monitor.fetcher")


class _SelectorPriceExtractor(HTMLParser):
    """Извлекает текстовые фрагменты из элементов, подходящих под простой селектор (.class, #id или tag)."""

    def __init__(self, selector: Optional[str]) -> None:
        super().__init__()
        self.kind: Optional[str] = None
        self.target: Optional[str] = None
        self._capture_depth: int = 0
        self.matched_chunks: list[str] = []
        self.all_chunks: list[str] = []

        if selector:
            sel = selector.strip()
            if sel.startswith(".") and len(sel) > 1:
                self.kind = "class"
                self.target = sel[1:]
            elif sel.startswith("#") and len(sel) > 1:
                self.kind = "id"
                self.target = sel[1:]
            elif sel:
                self.kind = "tag"
                self.target = sel.lower()

    def _matches_attrs(self, tag: str, attrs: dict[str, Optional[str]]) -> bool:
        if not self.kind or not self.target:
            return False
        if self.kind == "tag":
            return tag.lower() == self.target
        if self.kind == "id":
            return attrs.get("id") == self.target
        if self.kind == "class":
            classes = (attrs.get("class") or "").split()
            return self.target in classes
        return False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, Optional[str]]]) -> None:
        attr_map = dict(attrs)
        if self._capture_depth > 0:
            self._capture_depth += 1
        elif self._matches_attrs(tag, attr_map):
            self._capture_depth = 1
            for attr_name in ("content", "data-price", "value"):
                if attr_map.get(attr_name):
                    self.matched_chunks.append(str(attr_map[attr_name]))

    def handle_endtag(self, tag: str) -> None:
        if self._capture_depth > 0:
            self._capture_depth -= 1

    def handle_data(self, data: str) -> None:
        cleaned = data.strip()
        if not cleaned:
            return
        self.all_chunks.append(cleaned)
        if self._capture_depth > 0:
            self.matched_chunks.append(cleaned)


def parse_price_value(raw_text: str) -> Optional[float]:
    if not raw_text:
        return None
    match = re.search(r"(\d[\d\s.,]*\d|\d)", raw_text)
    if not match:
        return None
    token = match.group(1).replace(" ", "")
    if "," in token and "." in token:
        if token.find(",") < token.find("."):
            token = token.replace(",", "")
        else:
            token = token.replace(".", "").replace(",", ".")
    elif "," in token:
        parts = token.split(",")
        if len(parts[-1]) <= 2:
            token = "".join(parts[:-1]) + "." + parts[-1]
        else:
            token = "".join(parts)
    try:
        val = float(token)
        return val if val > 0 else None
    except ValueError:
        return None


def fetch_price_from_url(
    url: str,
    timeout: int = 10,
    selector: Optional[str] = None,
) -> Optional[float]:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "en-US,en;q=0.9,pl;q=0.8,ru;q=0.7",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        html = resp.read().decode("utf-8", errors="ignore")

    parser = _SelectorPriceExtractor(selector=selector)
    parser.feed(html)

    for chunk in parser.matched_chunks:
        price = parse_price_value(chunk)
        if price is not None:
            return price

    meta_patterns = [
        r'<meta[^>]+(?:property|name)=["\'](?:product:price:amount|price)["\'][^>]+content=["\']([^"\']+)["\']',
        r'itemprop=["\']price["\'][^>]+content=["\']([^"\']+)["\']',
        r'data-price=["\']([^"\']+)["\']',
    ]
    for pattern in meta_patterns:
        match = re.search(pattern, html, flags=re.IGNORECASE)
        if match:
            price = parse_price_value(match.group(1))
            if price is not None:
                return price

    for chunk in parser.all_chunks:
        if any(sym in chunk for sym in ("$", "€", "£", "zł", "PLN", "USD", "EUR", "UAH", "₴")):
            price = parse_price_value(chunk)
            if price is not None:
                return price

    return None


def get_item_price(
    url: str,
    timeout: int = 10,
    fallback_price: Optional[float] = None,
    selector: Optional[str] = None,
) -> tuple[Optional[float], str]:
    try:
        price = fetch_price_from_url(url, timeout=timeout, selector=selector)
        if price is not None:
            return price, "LIVE_SCRAPE"
        logger.warning("Цена не найдена на странице %s (selector=%s)", url, selector)
    except (urllib.error.URLError, TimeoutError, ValueError, OSError) as exc:
        logger.warning("Ошибка запроса к %s: %s", url, exc)

    if fallback_price is not None and fallback_price > 0:
        return float(fallback_price), "FALLBACK_CONFIG"

    return None, "FAILED"
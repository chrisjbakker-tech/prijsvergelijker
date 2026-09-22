import json
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from urllib.parse import urlparse
import httpx
from bs4 import BeautifulSoup

USER_AGENT = "Mozilla/5.0 (compatible; Prijsmonitor/1.0; +https://github.com/)"


class ScrapeError(Exception):
    pass


@dataclass
class ScrapeResult:
    title: str
    price_cents: int
    currency: str


def _cents(value) -> int | None:
    if value is None:
        return None
    text = str(value).strip().replace("€", "").replace("EUR", "").replace(" ", "")
    if not text:
        return None
    if "," in text and "." in text:
        if text.rfind(",") > text.rfind("."):
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
    elif "," in text:
        text = text.replace(".", "").replace(",", ".")
    try:
        amount = Decimal(text)
        if amount <= 0:
            return None
        return int((amount * 100).quantize(Decimal("1")))
    except InvalidOperation:
        return None


def _walk_json(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk_json(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_json(child)


def parse_product_html(html: str, fallback_title: str = "Product") -> ScrapeResult:
    soup = BeautifulSoup(html, "html.parser")
    title = (soup.title.get_text(" ", strip=True) if soup.title else fallback_title)
    candidates: list[tuple[int, str, str]] = []

    for script in soup.select('script[type="application/ld+json"]'):
        try:
            data = json.loads(script.string or script.get_text())
        except (json.JSONDecodeError, TypeError):
            continue
        for item in _walk_json(data):
            item_type = item.get("@type")
            types = item_type if isinstance(item_type, list) else [item_type]
            if "Product" in types and item.get("name"):
                title = str(item["name"])
            if "Offer" in types or "AggregateOffer" in types or any(k in item for k in ("price", "lowPrice")):
                raw = item.get("price", item.get("lowPrice"))
                cents = _cents(raw)
                if cents:
                    candidates.append((cents, str(item.get("priceCurrency", "EUR")), title))

    meta_pairs = [
        ('meta[property="product:price:amount"]', 'meta[property="product:price:currency"]'),
        ('meta[property="og:price:amount"]', 'meta[property="og:price:currency"]'),
        ('meta[itemprop="price"]', 'meta[itemprop="priceCurrency"]'),
    ]
    for price_selector, currency_selector in meta_pairs:
        node = soup.select_one(price_selector)
        if node:
            cents = _cents(node.get("content"))
            currency_node = soup.select_one(currency_selector)
            currency = currency_node.get("content", "EUR") if currency_node else "EUR"
            if cents:
                candidates.append((cents, currency, title))

    if not candidates:
        text = soup.get_text(" ", strip=True)
        match = re.search(r"(?:€|EUR)\s*([0-9]{1,5}(?:[.,][0-9]{2})?)", text, re.I)
        if match:
            cents = _cents(match.group(1))
            if cents:
                candidates.append((cents, "EUR", title))

    if not candidates:
        raise ScrapeError("Geen prijs gevonden op de productpagina")
    price_cents, currency, found_title = candidates[0]
    return ScrapeResult(found_title[:300], price_cents, currency[:3].upper())


def scrape_url(url: str) -> ScrapeResult:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ScrapeError("Ongeldige URL")
    try:
        with httpx.Client(follow_redirects=True, timeout=25, headers={"User-Agent": USER_AGENT, "Accept-Language": "nl-NL,nl;q=0.9"}) as client:
            response = client.get(url)
            response.raise_for_status()
    except httpx.HTTPError as exc:
        raise ScrapeError(f"Pagina kon niet worden opgehaald: {exc}") from exc
    return parse_product_html(response.text, parsed.netloc)

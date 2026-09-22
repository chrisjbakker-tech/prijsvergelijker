from app.scraper import parse_product_html


def test_parses_json_ld_offer():
    html = '''<html><head><title>Winkel</title><script type="application/ld+json">{"@type":"Product","name":"Hardloopschoen","offers":{"@type":"Offer","price":"139,95","priceCurrency":"EUR"}}</script></head></html>'''
    result = parse_product_html(html)
    assert result.title == "Hardloopschoen"
    assert result.price_cents == 13995
    assert result.currency == "EUR"


def test_parses_meta_price():
    html = '''<html><head><title>Luiers</title><meta property="product:price:amount" content="24.99"><meta property="product:price:currency" content="EUR"></head></html>'''
    result = parse_product_html(html)
    assert result.price_cents == 2499

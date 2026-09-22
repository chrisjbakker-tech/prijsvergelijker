from datetime import datetime, timezone
from sqlalchemy import select
from .db import SessionLocal
from .mailer import MailError, send_price_alert
from .models import PriceHistory, Product, Settings
from .scraper import ScrapeError, scrape_url


def check_product(product_id: int) -> dict:
    with SessionLocal() as db:
        product = db.get(Product, product_id)
        if not product:
            return {"ok": False, "error": "Product niet gevonden"}
        settings = db.get(Settings, 1)
        try:
            result = scrape_url(product.url)
            product.previous_cents = product.current_cents
            product.current_cents = result.price_cents
            product.currency = result.currency
            product.last_checked_at = datetime.now(timezone.utc)
            product.last_error = None
            if product.name == "Nieuw product" or not product.name.strip():
                product.name = result.title
            db.add(PriceHistory(product_id=product.id, price_cents=result.price_cents))

            is_below = product.target_cents is not None and result.price_cents < product.target_cents
            if not is_below:
                product.below_threshold = False
            elif not product.below_threshold:
                recipient = product.recipient_email or (settings.default_email if settings else None)
                if recipient:
                    try:
                        send_price_alert(recipient, product.name, result.price_cents, product.target_cents, product.url)
                        product.below_threshold = True
                    except MailError as exc:
                        product.last_error = str(exc)
                else:
                    product.last_error = "Geen centraal of productspecifiek e-mailadres ingesteld"
            db.commit()
            return {"ok": True, "price_cents": result.price_cents, "error": product.last_error}
        except ScrapeError as exc:
            product.last_checked_at = datetime.now(timezone.utc)
            product.last_error = str(exc)
            db.commit()
            return {"ok": False, "error": str(exc)}


def check_all_products() -> list[dict]:
    with SessionLocal() as db:
        ids = list(db.scalars(select(Product.id).where(Product.active.is_(True))))
    return [dict(product_id=product_id, **check_product(product_id)) for product_id in ids]

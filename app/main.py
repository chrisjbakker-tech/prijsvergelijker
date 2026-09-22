import base64
import os
import re
import secrets
from contextlib import asynccontextmanager
from decimal import Decimal, InvalidOperation
from urllib.parse import urlparse
from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from .db import Base, SessionLocal, engine
from .models import Product, PriceHistory, Settings
from .monitor import check_all_products, check_product

INITIAL_PRODUCTS = [
    ("Kruidvat Junior maat 5 luiers Jumbopack", "https://www.kruidvat.nl/kruidvat-junior-maat-5-luiers-jumbopack/p/2210790", None),
    ("HEMA dames T-shirt Clara rib katoen donkerblauw", "https://www.hema.nl/dames/dameskleding/shirts-tops/dames-t-shirt-clara-rib-katoen-donkerblauw-36307750DARKBLUE.html", None),
    ("ASICS Gel-Nimbus 28 heren", "https://www.passasports.nl/asics-gel-nimbus-28-heren-1011c127-405?size=5652&discipline=7407", 14000),
]

scheduler = BackgroundScheduler(timezone=os.getenv("TZ", "Europe/Amsterdam"))
templates = Jinja2Templates(directory="app/templates")


def euros_to_cents(value: str | None):
    if not value or not value.strip():
        return None
    try:
        return int((Decimal(value.strip().replace(",", ".")) * 100).quantize(Decimal("1")))
    except InvalidOperation as exc:
        raise ValueError("Ongeldige prijs") from exc


def valid_email(value: str | None):
    return not value or bool(re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", value))


def valid_url(value: str):
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        if not db.get(Settings, 1):
            db.add(Settings(id=1, default_email=os.getenv("INITIAL_DEFAULT_EMAIL", "chris.j.bakker@gmail.com")))
            db.commit()
        load_initial = os.getenv("LOAD_INITIAL_PRODUCTS", "true").lower() in {"1", "true", "yes"}
        if load_initial and not db.scalar(select(Product.id).limit(1)):
            for name, url, target_cents in INITIAL_PRODUCTS:
                db.add(Product(name=name, url=url, target_cents=target_cents))
            db.commit()
    if os.getenv("ENABLE_SCHEDULER", "true").lower() in {"1", "true", "yes"}:
        hour = int(os.getenv("CHECK_HOUR", "8"))
        scheduler.add_job(check_all_products, "cron", hour=hour, minute=0, id="daily-check", replace_existing=True)
        scheduler.start()
    yield
    if scheduler.running:
        scheduler.shutdown(wait=False)


app = FastAPI(title="Prijsmonitor", lifespan=lifespan)
app.mount("/static", StaticFiles(directory="app/static"), name="static")


@app.middleware("http")
async def basic_auth(request: Request, call_next):
    username = os.getenv("APP_USERNAME")
    password = os.getenv("APP_PASSWORD")
    if not username or not password or request.url.path in {"/health", "/api/check-all"}:
        return await call_next(request)
    auth = request.headers.get("Authorization", "")
    try:
        scheme, encoded = auth.split(" ", 1)
        supplied_user, supplied_password = base64.b64decode(encoded).decode().split(":", 1)
    except Exception:
        scheme, supplied_user, supplied_password = "", "", ""
    valid = (
        scheme.lower() == "basic"
        and secrets.compare_digest(supplied_user, username)
        and secrets.compare_digest(supplied_password, password)
    )
    if not valid:
        return Response(status_code=401, headers={"WWW-Authenticate": "Basic"}, content="Inloggen vereist")
    return await call_next(request)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    with SessionLocal() as db:
        products = list(db.scalars(select(Product).order_by(Product.created_at.desc())))
        settings = db.get(Settings, 1)
        return templates.TemplateResponse("index.html", {"request": request, "products": products, "settings": settings})


@app.post("/products")
def add_product(url: str = Form(...), name: str = Form(""), target_price: str = Form(""), recipient_email: str = Form("")):
    url, name, recipient_email = url.strip(), name.strip(), recipient_email.strip()
    if not valid_url(url):
        raise HTTPException(400, "Voer een geldige http(s)-URL in")
    if not valid_email(recipient_email):
        raise HTTPException(400, "Ongeldig e-mailadres")
    try:
        cents = euros_to_cents(target_price)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    with SessionLocal() as db:
        if db.scalar(select(Product).where(Product.url == url)):
            raise HTTPException(409, "Deze URL wordt al gevolgd")
        product = Product(name=name or "Nieuw product", url=url, target_cents=cents, recipient_email=recipient_email or None)
        db.add(product)
        db.commit()
        db.refresh(product)
        product_id = product.id
    check_product(product_id)
    return RedirectResponse(f"/products/{product_id}", status_code=303)


@app.get("/products/{product_id}", response_class=HTMLResponse)
def product_detail(product_id: int, request: Request):
    with SessionLocal() as db:
        product = db.get(Product, product_id)
        if not product:
            raise HTTPException(404)
        history = list(db.scalars(select(PriceHistory).where(PriceHistory.product_id == product_id).order_by(PriceHistory.checked_at.desc()).limit(100)))
        settings = db.get(Settings, 1)
        return templates.TemplateResponse("product.html", {"request": request, "product": product, "history": history, "settings": settings})


@app.post("/products/{product_id}")
def update_product(product_id: int, name: str = Form(...), target_price: str = Form(""), recipient_email: str = Form(""), active: str | None = Form(None)):
    recipient_email = recipient_email.strip()
    if not valid_email(recipient_email):
        raise HTTPException(400, "Ongeldig e-mailadres")
    try:
        cents = euros_to_cents(target_price)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    with SessionLocal() as db:
        product = db.get(Product, product_id)
        if not product:
            raise HTTPException(404)
        if product.target_cents != cents:
            product.below_threshold = False
        product.name = name.strip() or product.name
        product.target_cents = cents
        product.recipient_email = recipient_email or None
        product.active = active == "on"
        db.commit()
    return RedirectResponse(f"/products/{product_id}", status_code=303)


@app.post("/products/{product_id}/check")
def run_product_check(product_id: int):
    check_product(product_id)
    return RedirectResponse(f"/products/{product_id}", status_code=303)


@app.post("/products/{product_id}/delete")
def delete_product(product_id: int):
    with SessionLocal() as db:
        product = db.get(Product, product_id)
        if product:
            db.delete(product)
            db.commit()
    return RedirectResponse("/", status_code=303)


@app.post("/settings")
def save_settings(default_email: str = Form("")):
    default_email = default_email.strip()
    if not valid_email(default_email):
        raise HTTPException(400, "Ongeldig e-mailadres")
    with SessionLocal() as db:
        settings = db.get(Settings, 1) or Settings(id=1)
        settings.default_email = default_email or None
        db.add(settings)
        db.commit()
    return RedirectResponse("/", status_code=303)


@app.post("/api/check-all")
def api_check_all(request: Request):
    secret = os.getenv("CRON_SECRET")
    supplied = request.headers.get("Authorization", "").removeprefix("Bearer ")
    if secret and supplied != secret:
        raise HTTPException(401, "Ongeldige sleutel")
    return {"results": check_all_products()}

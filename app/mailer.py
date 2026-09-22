import os
import smtplib
from email.message import EmailMessage


class MailError(Exception):
    pass


def send_price_alert(to_email: str, product_name: str, price_cents: int, target_cents: int, url: str):
    host = os.getenv("SMTP_HOST")
    sender = os.getenv("SMTP_FROM") or os.getenv("SMTP_USERNAME")
    if not host or not sender:
        raise MailError("SMTP_HOST en SMTP_FROM (of SMTP_USERNAME) zijn niet ingesteld")
    port = int(os.getenv("SMTP_PORT", "587"))
    username = os.getenv("SMTP_USERNAME")
    password = os.getenv("SMTP_PASSWORD")
    use_tls = os.getenv("SMTP_USE_TLS", "true").lower() in {"1", "true", "yes"}

    price = f"€ {price_cents / 100:.2f}".replace(".", ",")
    target = f"€ {target_cents / 100:.2f}".replace(".", ",")
    msg = EmailMessage()
    msg["Subject"] = f"Prijsalarm: {product_name} kost nu {price}"
    msg["From"] = sender
    msg["To"] = to_email
    msg.set_content(
        f"Goed nieuws!\n\n{product_name} kost nu {price}. "
        f"Dat is lager dan jouw ingestelde prijs van {target}.\n\nBekijk het product:\n{url}\n"
    )
    try:
        with smtplib.SMTP(host, port, timeout=30) as smtp:
            if use_tls:
                smtp.starttls()
            if username:
                smtp.login(username, password or "")
            smtp.send_message(msg)
    except Exception as exc:
        raise MailError(f"E-mail verzenden mislukt: {exc}") from exc

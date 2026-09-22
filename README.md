# Prijsmonitor

Een online prijsmonitor voor losse product-URL’s. De app controleert iedere dag dezelfde aanbieder, bewaart de prijshistorie en stuurt één e-mail zodra de prijs onder de ingestelde grens komt. Zodra de prijs weer boven de grens is geweest, kan bij een volgende daling opnieuw een melding worden gestuurd.

## Inbegrepen startgegevens

Bij de eerste start van een lege database worden de drie aangeleverde product-URL’s toegevoegd. Het centrale e-mailadres is `chris.j.bakker@gmail.com`. Voor de ASICS Gel-Nimbus 28 staat de meldingsgrens op **€ 140,00**. Zet `LOAD_INITIAL_PRODUCTS=false` om zonder startgegevens te beginnen.

## Functies

- Meerdere product-URL’s beheren
- Dagelijkse controle, standaard om 08:00 uur (`Europe/Amsterdam`)
- Handmatige knop **Nu controleren**
- Centrale e-mailontvanger met een optionele afwijking per product
- Prijshistorie per product
- E-mail slechts eenmaal per neerwaartse drempeloverschrijding
- Loginbeveiliging via `APP_USERNAME` en `APP_PASSWORD`
- SQLite voor lokaal gebruik; PostgreSQL voor online gebruik
- Docker-, Docker Compose- en Render-configuratie

## Lokaal starten

1. Kopieer `.env.example` naar `.env` en vul sterke wachtwoorden en SMTP-instellingen in.
2. Start met `docker compose up --build -d`.
3. Open http://localhost:8000.

## Online via GitHub en Render

GitHub bewaart de broncode; Render draait de applicatie doorlopend.

1. Maak een nieuwe privé-repository op GitHub en upload alle bestanden uit deze map.
2. Open Render, kies **New > Blueprint** en koppel de repository. Render leest `render.yaml` en maakt de webservice en PostgreSQL-database.
3. Vul bij de geheime omgevingsvariabelen minimaal `APP_USERNAME`, `APP_PASSWORD`, `SMTP_HOST`, `SMTP_USERNAME`, `SMTP_PASSWORD` en `SMTP_FROM` in.
4. Na de deployment open je de Render-URL en log je in.

Controleer vooraf de actuele kosten en slaapvoorwaarden van de gekozen hosting. Een slapende service kan de interne dagelijkse taak missen. Gebruik dan een externe cronjob die dagelijks een POST uitvoert naar `/api/check-all` met header `Authorization: Bearer <CRON_SECRET>`.

## SMTP

Elke SMTP-provider werkt. Voor Gmail gebruik je `smtp.gmail.com`, poort `587`, TLS, je Gmail-adres als gebruikersnaam/afzender en een Google app-wachtwoord. Zet nooit een wachtwoord in GitHub; gebruik uitsluitend geheime omgevingsvariabelen van je host.

## Beperking

Webwinkels kunnen hun HTML wijzigen of geautomatiseerde verzoeken blokkeren. De scraper probeert JSON-LD, productmeta-tags en een zichtbare europrijs. Een mislukte controle verschijnt bij het product en overschrijft nooit de laatst geldige prijs.

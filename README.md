Ein Service zum Erstellen von JSON-Dateien aus VHS-Kursen.

## Lokale Ausführung

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python vhs_scraper.py --output kurse.json
```

## Automatisierung mit GitHub Actions

Dieses Repository enthält den Workflow [`VHS Lahnstein Scraper`](.github/workflows/vhs-scraper.yml),
der täglich um 05:00 UTC sowie manuell per *workflow_dispatch* ausgeführt werden kann. Der Workflow

1. checkt das Repository aus,
2. richtet Python 3.11 ein,
3. installiert die in `requirements.txt` definierten Abhängigkeiten,
4. führt den Scraper mit der Standardkonfiguration aus und
5. lädt die erzeugte `kurse.json` als Build-Artefakt hoch.

Die erzeugte Datei kann anschließend aus den Workflow-Ergebnissen heruntergeladen werden.

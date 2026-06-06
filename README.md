# spend.it

A small **Progressive Web App** for tracking personal spending.
Records save to a local **SQLite** database. Runs as a single **Docker** container.

- Add expenses by **amount** + **category**, with optional note.
- Enter past expenses **retroactively** with the date picker.
- See **daily / monthly / yearly** totals and a per-category breakdown,
  visualized with charts.
- **Installable** PWA with offline app shell — open in a browser, "Install app",
  and your data stays on your machine.

## Stack

- **Backend:** FastAPI · SQLAlchemy 2 · SQLite
- **Frontend:** Vanilla JS · Chart.js · Service Worker + Web App Manifest
- **Container:** Python 3.12-slim, runs as non-root, persists DB to a volume

## Project layout

```
spend.it/
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── app/
    ├── main.py          # FastAPI app + routes + static mount
    ├── database.py      # engine / session / Base
    ├── models.py        # Expense ORM model
    ├── schemas.py       # Pydantic request/response models
    ├── repository.py    # data access (single responsibility)
    └── static/
        ├── index.html
        ├── app.js
        ├── styles.css
        ├── manifest.webmanifest
        ├── sw.js
        └── icons/icon.svg
```

The architecture follows a thin-route + repository pattern:

- **Routes** (`main.py`) only validate input and shape responses.
- **Repository** (`repository.py`) owns all DB access — queries, aggregations.
- **Schemas** (`schemas.py`) decouple wire format from ORM models.

This keeps things SOLID without dragging in a DI framework or extra layers
(YAGNI). Aggregations are computed in SQL for simplicity and speed (DRY: one
formula per period in one map).

## Run with Docker

```bash
docker compose up -d --build
```

Then open http://localhost:8000.

The SQLite file lives in the named volume `spendit-data` (mounted at `/data`
inside the container), so your records survive container rebuilds.

To stop:

```bash
docker compose down
```

To wipe data:

```bash
docker compose down -v
```

## Run locally (no Docker)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Open http://127.0.0.1:8000. The SQLite file is created at `data/spendit.db`.

## API

| Method | Path                          | Description                            |
| ------ | ----------------------------- | -------------------------------------- |
| POST   | `/api/expenses`               | Create an expense (date optional)      |
| GET    | `/api/expenses`               | List expenses (filters: `start`, `end`, `limit`) |
| DELETE | `/api/expenses/{id}`          | Delete an expense                      |
| GET    | `/api/reports/summary`        | Totals by category + by period (`period=daily\|monthly\|yearly`) |
| GET    | `/api/health`                 | Health check                           |

Interactive docs: http://localhost:8000/docs

## Install as a PWA

1. Open the site in Chrome / Edge / Safari.
2. Use the browser's **Install app** option (address bar or share menu).
3. Launch from your home screen / app launcher — the shell works offline; data
   syncs whenever the backend is reachable.

## Notes

- This is a single-user, local-first app. There is no auth — don't expose it
  to the public internet without putting it behind a reverse proxy + auth.
- Currency is rendered as a plain decimal so it works for any locale; change
  the `Intl.NumberFormat` options in `app/static/app.js` if you want a symbol.

# Handoff — spend.it

A guide for future LLM agents (and humans) to ramp up on this codebase in one read.

## 1. What this app is

`spend.it` is a single-user, local-first **personal spending tracker**. It runs as one
FastAPI service that also serves a vanilla-JS Progressive Web App from the same
origin. Records save to a local SQLite file. The intended deployment is a single
Docker container on a personal machine or a small VPS, optionally behind a
reverse proxy. There is no auth, no multi-tenant model, no external API.

Key non-obvious traits, all derived from code:

- **Local-first / single-user.** No login, no sessions. The README explicitly
  warns against exposing it on the public internet without a proxy + auth
  ([README.md#L98-L101](README.md#L98-L101)).
- **PWA with split caching strategy.** Service worker is **cache-first** for
  the app shell and **network-only** for `/api/*` so user data is never cached
  ([app/static/sw.js#L29-L50](app/static/sw.js#L29-L50)).
- **Frontend is dependency-free vanilla JS** (one IIFE in
  [app/static/app.js](app/static/app.js)). Chart.js is the only runtime JS dep
  and is loaded from a CDN tag in [app/static/index.html#L12](app/static/index.html#L12).
- **Single source of truth for the deployment port.** `APP_PORT` in `.env`
  drives the container listener, the host mapping, and the healthcheck — no
  literal `8000` outside defaults ([.env.example](.env.example),
  [docker-compose.yml](docker-compose.yml), [Dockerfile](Dockerfile)).
- **Hand-rolled additive SQLite migrations** via `ALTER TABLE` in
  [app/database.py#L37-L57](app/database.py#L37-L57). No Alembic.
- **Image attachments are downscaled in the browser** to a small JPEG data URL
  before being POSTed, so payloads stay <100 KB
  ([app/static/app.js#L67-L92](app/static/app.js#L67-L92)).
- **Receipt-styled "Recent entries" UI** uses CSS masks for scalloped torn
  edges; not just decorative styling
  ([app/static/styles.css#L233-L277](app/static/styles.css#L233-L277)).

## 2. Architecture

### Tech stack

| Layer | Technology | Version | Source |
| ----- | ---------- | ------- | ------ |
| Language | Python | 3.12 (slim) | [Dockerfile#L2](Dockerfile#L2) |
| Web framework | FastAPI | `0.118.0` | [requirements.txt#L1](requirements.txt#L1) |
| ASGI server | uvicorn (`[standard]`) | `0.32.1` | [requirements.txt#L2](requirements.txt#L2) |
| ORM | SQLAlchemy 2 | `2.0.36` | [requirements.txt#L3](requirements.txt#L3) |
| Validation | Pydantic v2 | `2.10.4` | [requirements.txt#L4](requirements.txt#L4) |
| Datastore | SQLite (file `data/spendit.db`) | stdlib | [app/database.py#L12-L20](app/database.py#L12-L20) |
| Frontend | Vanilla JS (no bundler) + Chart.js `4.4.4` (CDN) | — | [app/static/index.html#L12](app/static/index.html#L12) |
| Tests | pytest, httpx (TestClient backend) | `8.3.3`, `0.27.2` | [requirements-dev.txt](requirements-dev.txt) |
| Container | python:3.12-slim, non-root user `spendit` | — | [Dockerfile](Dockerfile) |

Python is pinned to **3.12** (uses `str | None` and `Mapped[...]` patterns).
SQLAlchemy 2.0 declarative style (`DeclarativeBase`, `Mapped`, `mapped_column`)
is used throughout — older SQLAlchemy 1.x patterns from training data will not
match this codebase.

### Layout

```
spend.it/
├── Dockerfile                 # python:3.12-slim image; APP_PORT-aware uvicorn launch
├── docker-compose.yml         # Single-service deployment; APP_PORT/HOST_BIND interpolation
├── .env.example               # Template for APP_PORT / HOST_BIND
├── pytest.ini                 # testpaths = tests; --strict-markers
├── requirements.txt           # Runtime deps (4 packages, all pinned)
├── requirements-dev.txt       # Test deps only
├── README.md                  # Human-facing docs + API table
├── app/
│   ├── __init__.py            # Package marker
│   ├── main.py                # FastAPI app, routes, lifespan, static mount
│   ├── database.py            # Engine, SessionLocal, Base, init_db, additive migrations
│   ├── models.py              # Expense ORM model (single table)
│   ├── schemas.py             # Pydantic v2 request/response models + photo validator
│   ├── repository.py          # All SQL queries / aggregations live here
│   └── static/                # PWA assets, served as-is
│       ├── index.html         # SPA shell
│       ├── app.js             # IIFE: form, charts, receipt list, photo resize
│       ├── styles.css         # All CSS; receipt block uses CSS mask scallops
│       ├── manifest.webmanifest
│       ├── sw.js              # Service worker; cache name `spendit-shell-v1`
│       └── icons/icon.svg
└── tests/
    ├── __init__.py
    ├── conftest.py            # Sets SPENDIT_DB_PATH to a tmp file BEFORE app import
    ├── test_api.py            # HTTP-level integration via TestClient
    ├── test_repository.py     # Direct repository / DB unit tests
    └── test_static.py         # Asserts shell/manifest/SW are served correctly
```

There is no generated code, no build step, and no node_modules. The Docker
build copies `app/` and `requirements.txt` only ([Dockerfile#L13-L16](Dockerfile#L13-L16)).

### State / data flow

The single source of truth is one SQLite table, `expenses`, defined in
[app/models.py#L13-L24](app/models.py#L13-L24):

| Column      | Type                  | Notes |
| ----------- | --------------------- | ----- |
| `id`        | INTEGER PK autoinc    | |
| `amount`    | FLOAT not null        | Validated `> 0` at the schema layer |
| `category`  | VARCHAR(64) not null  | Indexed; trimmed on create |
| `note`      | VARCHAR(255) nullable | Trimmed; `""` becomes `NULL` |
| `photo`     | TEXT nullable         | base64 `data:image/*` URL; ~1 MB cap in schema |
| `spent_at`  | DATE not null         | Indexed; defaults to `date.today()` server-side |
| `created_at`| DATETIME not null     | Defaults to `datetime.utcnow` |

Request lifecycle (typical create):

1. Browser POSTs JSON to `/api/expenses` ([app/static/app.js#L154-L181](app/static/app.js#L154-L181)).
2. FastAPI dispatches to `create_expense` in [app/main.py#L34-L43](app/main.py#L34-L43).
3. `ExpenseCreate` (Pydantic) validates and coerces — including the `photo`
   field's `data:image/*` prefix check
   ([app/schemas.py#L9-L31](app/schemas.py#L9-L31)).
4. Route hands the validated DTO to `repository.create_expense`
   ([app/repository.py#L37-L48](app/repository.py#L37-L48)) which is the **only** place
   that writes the table.
5. `ExpenseRead.model_validate(...)` shapes the response from the ORM row.

Aggregations are computed in SQL via `func.strftime(...)` keyed by a small
period-format map ([app/repository.py#L13-L17](app/repository.py#L13-L17)). The summary
endpoint scopes the **category breakdown and headline total** to the current
period (`current_period_range`) while the **bar trend** spans the full
dataset — a deliberate split documented inline at
[app/main.py#L65-L86](app/main.py#L65-L86) and asserted in
[tests/test_api.py#L120-L155](tests/test_api.py#L120-L155).

Derived UI values (active bucket label, formatted month, drill-in totals) are
computed in `renderFromState()` in
[app/static/app.js#L431-L470](app/static/app.js#L431-L470). The module-scoped
`state` object ([app/static/app.js#L26-L33](app/static/app.js#L26-L33)) is the
single client-side store.

### Key patterns in use

- **Repository pattern.** All persistence lives in
  [app/repository.py](app/repository.py). Routes never import models or run
  queries directly. To add a query, add a function here.
- **Schema/DTO separation.** [app/schemas.py](app/schemas.py) decouples wire
  format from ORM models; routes return `ExpenseRead.model_validate(orm_row)`
  rather than the ORM object.
- **Dependency injection via FastAPI `Depends`.** The session is yielded by
  `get_session` ([app/database.py#L26-L33](app/database.py#L26-L33)) and injected into
  every route ([app/main.py#L40](app/main.py#L40)). Tests substitute the engine by
  setting `SPENDIT_DB_PATH` *before* import
  ([tests/conftest.py#L18-L20](tests/conftest.py#L18-L20)).
- **Lifespan-based init.** `init_db()` runs once at startup via the FastAPI
  lifespan context ([app/main.py#L21-L24](app/main.py#L21-L24)).

### Cross-cutting concerns

- **Persistence / migrations.** SQLite file lives at `$SPENDIT_DB_PATH`
  (default `data/spendit.db`). New columns are added via a hand-rolled
  idempotent helper, `_apply_lightweight_migrations`
  ([app/database.py#L37-L57](app/database.py#L37-L57)). There is **no Alembic**. For
  any schema change beyond an additive nullable column, follow the same
  pattern: bump the model, add an idempotent ALTER, and add a test.
- **Config.** Two environment variables only:
  - `SPENDIT_DB_PATH` — DB file location ([app/database.py#L12](app/database.py#L12)).
  - `APP_PORT` — uvicorn listener; also drives compose mapping
    ([Dockerfile#L9](Dockerfile#L9), [docker-compose.yml#L19-L24](docker-compose.yml#L19-L24)).
- **No auth.** The README and this document both warn about it.
- **Logging.** Uvicorn defaults; compose pins JSON-file rotation at 10 MB × 3
  ([docker-compose.yml#L36-L40](docker-compose.yml#L36-L40)).
- **Offline / PWA.** Service worker registers from the client
  ([app/static/app.js#L498-L505](app/static/app.js#L498-L505)). The cache
  name is `spendit-shell-v1` ([app/static/sw.js#L2](app/static/sw.js#L2)) and
  must be bumped any time files in the `SHELL` array change, otherwise old
  clients keep serving stale assets.
- **Healthcheck.** `/api/health` returns `{"status":"ok"}`
  ([app/main.py#L91-L93](app/main.py#L91-L93)) and is wired into both the Docker
  `HEALTHCHECK` and the compose-level healthcheck.

### Concurrency / runtime model

- ASGI / asyncio event loop, but every route is `def` (sync) and uses
  SQLAlchemy synchronously. FastAPI offloads sync handlers to a threadpool;
  `check_same_thread=False` is set on the SQLite connection
  ([app/database.py#L17-L19](app/database.py#L17-L19)) so this is safe.
- `autoflush=False, autocommit=False` in `SessionLocal`
  ([app/database.py#L20](app/database.py#L20)); commits are explicit in
  `repository.py`.

### Reusable conventions

- **Currency / number formatting.** Always go through
  `Intl.NumberFormat` set up at
  [app/static/app.js#L36-L41](app/static/app.js#L36-L41); call `fmt(n)`. Do
  not hand-format money elsewhere.
- **Period labels.** Computed once via `periodLabels()`
  ([app/static/app.js#L185-L210](app/static/app.js#L185-L210)) so chart titles
  always reflect the actual current month/year. Don't add a second copy.
- **API response shape.** Always validated through Pydantic models in
  [app/schemas.py](app/schemas.py); never return raw dicts from routes.

## 3. Functional decisions and unique attributes

| Theme | Decision | Where |
| ----- | -------- | ----- |
| Privacy | No third-party network calls from the server. The only outbound asset is the Chart.js CDN, loaded by the browser. | [app/static/index.html#L12](app/static/index.html#L12) |
| Domain model | One flat table `expenses`. No categories table; category is a free-text string trimmed on save. The category `<datalist>` is hint-only. | [app/models.py#L18](app/models.py#L18), [app/static/index.html#L34-L43](app/static/index.html#L34-L43) |
| Reporting scope | "Headline total" and "By category" are scoped to the current period; the bar trend is unscoped. Tests assert both behaviors. | [app/main.py#L70-L86](app/main.py#L70-L86), [tests/test_api.py#L120-L165](tests/test_api.py#L120-L165) |
| Photos | Resized client-side to ≤480 px JPEG quality `0.72`; stored as a `data:image/*` URL. Server-side cap is `_MAX_PHOTO_LEN = 1_500_000`. | [app/static/app.js#L67-L92](app/static/app.js#L67-L92), [app/schemas.py#L7-L9](app/schemas.py#L7-L9) |
| Migrations | Additive ALTERs only; `_apply_lightweight_migrations` runs from `init_db`. | [app/database.py#L37-L57](app/database.py#L37-L57) |
| Deployment port | One knob (`APP_PORT`). Don't introduce per-side host/container vars. | [.env.example](.env.example), [docker-compose.yml#L19-L24](docker-compose.yml#L19-L24) |
| Error shape | FastAPI defaults: 422 for validation errors, 404 for missing rows. Routes raise `HTTPException` directly ([app/main.py#L58-L60](app/main.py#L58-L60)). |
| UX | "Recent entries" uses a paper-receipt aesthetic with CSS masks; tweaks must keep `-webkit-mask` and `mask` declarations in sync ([app/static/styles.css#L249-L266](app/static/styles.css#L249-L266)). |

### Pitfalls to watch

- **Service-worker cache name must be bumped on shell changes.** Edit any
  asset in the `SHELL` array of [app/static/sw.js#L3-L10](app/static/sw.js#L3-L10) →
  bump `CACHE` from `spendit-shell-v1` → `v2` etc. Tests do not enforce this.
- **`SPENDIT_DB_PATH` must be set before `app.*` import.** This is what
  [tests/conftest.py#L18-L23](tests/conftest.py#L18-L23) is doing; if you add a new
  test module that imports `app.*` at module top, ensure `conftest` runs
  first (it does, because `tests/__init__.py` exists).
- **`app.fastapi.testclient` requires `httpx`.** Already in
  [requirements-dev.txt](requirements-dev.txt); don't drop it.
- **SQLite `func.strftime` is dialect-specific.** If you ever consider
  swapping to Postgres you'll need to revisit
  [app/repository.py#L13-L17](app/repository.py#L13-L17).
- **Photo data URLs inflate row size.** Always resize on the client; never
  accept full-resolution images.
- **Mask-based torn edges** require both `-webkit-mask` and `mask` lines in
  CSS to render on Safari and Chromium. Keep them in lockstep.
- **No Alembic.** Renaming or dropping a column requires a manual SQLite
  table-rebuild dance — don't pretend the lightweight helper covers that.
- **Compose port literals.** Don't reintroduce a hard-coded `8000:8000` line;
  use `${APP_PORT:-8000}` on both sides.

## 4. How to add functionality (engineering playbook)

### The change loop

1. **Read** the relevant route in [app/main.py](app/main.py), follow it into
   [app/repository.py](app/repository.py), and check the schema in
   [app/schemas.py](app/schemas.py).
2. **Run the existing tests** (`python -m pytest -q`) to confirm a green
   baseline.
3. **Write the failing test first** in the matching `tests/test_*.py` file.
4. **Implement** the smallest change that turns the test green, preserving
   layering rules below.
5. **Re-run all tests**.
6. **Update docs** only when behavior or contracts change (this file +
   [README.md](README.md), in the same commit).
7. **If a schema or static-asset change**, bump the appropriate version
   (additive migration in [app/database.py](app/database.py) or `CACHE` in
   [app/static/sw.js](app/static/sw.js)).

### Layering rules

```
app.main  -->  app.repository  -->  app.models  -->  app.database
            \                    /
             ->  app.schemas  <-
```

- Routes (`app/main.py`) may depend on `repository`, `schemas`, `database`
  (only for `get_session`). They must **not** import `models` directly or
  build queries inline.
- `repository.py` may depend on `models`, `schemas`, and SQLAlchemy. It is
  the only module that calls `session.execute / commit / scalar`.
- `schemas.py` depends on `pydantic` only; it never imports SQLAlchemy.
- `models.py` depends on `database.Base` only; no business logic.
- The frontend (`app/static/*.js`) talks to the API via `fetch`; it never
  reads or writes anything else.

### DRY rules — canonical single-source-of-truth locations

| Concern | Canonical location |
| ------- | ------------------ |
| Domain types / column definitions | [app/models.py](app/models.py) |
| API request/response shapes | [app/schemas.py](app/schemas.py) |
| All SQL | [app/repository.py](app/repository.py) |
| Period bucket formats (`%Y`, `%Y-%m`, `%Y-%m-%d`) | [app/repository.py#L13-L17](app/repository.py#L13-L17) |
| Client-side state | `state` in [app/static/app.js#L26-L33](app/static/app.js#L26-L33) |
| Currency formatting | `fmt()` in [app/static/app.js#L36-L41](app/static/app.js#L36-L41) |
| Period labels (UI strings) | `periodLabels()` in [app/static/app.js#L185-L210](app/static/app.js#L185-L210) |
| Deployment port | `APP_PORT` in [.env.example](.env.example) |
| DB path | `$SPENDIT_DB_PATH` ([app/database.py#L12](app/database.py#L12)) |
| Service-worker shell list | `SHELL` array in [app/static/sw.js#L3-L10](app/static/sw.js#L3-L10) |

Do not duplicate any of the above. Reuse the existing module/function instead
of inlining a literal.

### Extension points

- **New report period** (e.g. weekly): add a key to `_PERIOD_FORMATS`
  ([app/repository.py#L13-L17](app/repository.py#L13-L17)), extend
  `current_period_range` ([app/repository.py#L20-L34](app/repository.py#L20-L34)),
  add the literal to `Literal[...]` in [app/main.py#L66](app/main.py#L66), and add a
  toggle chip in [app/static/index.html#L67-L70](app/static/index.html#L67-L70) +
  matching label in `periodLabels()`.
- **New API endpoint**: add a route in [app/main.py](app/main.py); push all DB
  work into a new function in [app/repository.py](app/repository.py); add
  request/response schemas to [app/schemas.py](app/schemas.py).
- **New nullable column**: add a `mapped_column(...)` in
  [app/models.py](app/models.py), an additive `ALTER TABLE` branch in
  `_apply_lightweight_migrations` ([app/database.py#L46-L57](app/database.py#L46-L57)),
  and (if user-facing) fields on `ExpenseCreate` / `ExpenseRead`.
- **New static asset**: add it under [app/static/](app/static), include it in
  the `SHELL` array of [app/static/sw.js](app/static/sw.js) if it's part of the
  offline shell, and **bump `CACHE`**.

### Avoiding over-engineering

- No new runtime dependencies without a concrete justification tied to a
  feature in flight. The runtime stack is intentionally four packages.
- No DI framework, no service layer, no Alembic, no node bundler.
- No drive-by refactors on files you didn't otherwise need to touch.
- No comments or docstrings on unchanged code.
- Validate at boundaries (Pydantic schemas at the HTTP layer); don't sprinkle
  defensive checks in repository or model code.

### Tests — what to add, where

| Kind of change | File | Style | Framework / fixtures |
| -------------- | ---- | ----- | -------------------- |
| New repository function or aggregation | [tests/test_repository.py](tests/test_repository.py) | Unit, direct call | `db_session` fixture |
| New route, status code, or response shape | [tests/test_api.py](tests/test_api.py) | Integration via `TestClient` | `client` fixture |
| New static file or PWA shell change | [tests/test_static.py](tests/test_static.py) | Asserts `GET` + content-type/body | `client` fixture |

Conventions:

- Use `_make(db_session, ...)` style helpers already in
  [tests/test_repository.py#L11-L15](tests/test_repository.py#L11-L15).
- Use `_seed(client, [...])` for HTTP integration setup
  ([tests/test_api.py#L57-L60](tests/test_api.py#L57-L60)).
- Schema is dropped/recreated **before each test** by the autouse
  `_fresh_schema` fixture ([tests/conftest.py#L26-L33](tests/conftest.py#L26-L33)) —
  do not write tests that assume cross-test state.
- Use `pytest.mark.parametrize` for table-driven cases (already common).

### Documentation

In the same commit as a behavior or contract change, update:

- This file (`AGENTS.md`) — only if architecture, conventions, or pitfalls
  change.
- [README.md](README.md) — if user-facing behavior, deploy steps, or the API
  table changes.

Do **not** create new markdown files. There is no `CHANGELOG.md`,
`ARCHITECTURE.md`, or `ADRs/` directory and adding one is over-engineering for
a project this size.

### Applicable checklists

- **Security:** never log photo payloads, request bodies, or DB rows. Don't
  add unauthenticated write endpoints. Don't accept non-`data:image/*` photo
  URLs (already enforced in [app/schemas.py#L24-L31](app/schemas.py#L24-L31)).
- **Database migrations:** additive only via the lightweight helper. For
  destructive changes, plan a one-shot rebuild script and document it.
- **PWA cache:** bump `CACHE` whenever any file in `SHELL` changes.

### Pre-merge checklist

- [ ] `python -m pytest -q` is green (52+ tests).
- [ ] `python -m flake8 app tests` is clean (config in [.flake8](.flake8),
      `max-line-length = 100`).
- [ ] New routes have at least one happy-path and one validation-error test.
- [ ] New repository functions have a unit test with the `db_session` fixture.
- [ ] If models changed: model + migration branch + test all in the same commit.
- [ ] If `SHELL` files changed: `CACHE` bumped in [app/static/sw.js](app/static/sw.js).
- [ ] If port handling changed: `APP_PORT` flow still works
      (`APP_PORT=9000 docker compose config` shows `target: 9000` *and*
      `published: "9000"`).
- [ ] No new runtime dependency without justification.
- [ ] [README.md](README.md) and this file updated if behavior or contracts
      changed.
- [ ] No new markdown files.

## Quick orientation checklist for a new agent

Read in this order, then run the baseline:

1. [README.md](README.md) — product framing and run instructions.
2. [app/main.py](app/main.py) — routes + lifespan; the whole HTTP surface in <100 lines.
3. [app/repository.py](app/repository.py) — every query and aggregation.
4. [app/schemas.py](app/schemas.py) and [app/models.py](app/models.py) — wire format vs. storage.
5. [app/database.py](app/database.py) — engine, session, additive migrations.
6. [app/static/app.js](app/static/app.js) — client state, charts, photo resize, receipt list.
7. [tests/conftest.py](tests/conftest.py) plus one of [tests/test_api.py](tests/test_api.py) / [tests/test_repository.py](tests/test_repository.py).

Confirm the baseline:

```bash
python -m pip install -r requirements.txt -r requirements-dev.txt
python -m pytest -q
python -m flake8 app tests
docker compose config           # validates compose without starting anything
```

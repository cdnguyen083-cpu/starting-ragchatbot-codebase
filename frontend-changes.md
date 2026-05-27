# Frontend Changes

This file aggregates the changes recorded by several `/implement_feature` tasks.
Each top-level section below documents one feature.

---

# Frontend Changes — Theme Toggle Button

Added a light/dark theme toggle to the Course Materials Assistant UI.

## Summary

A circular, icon-based toggle button now sits in the top-right corner of the
app. It switches between the existing dark theme and a new light theme, animates
smoothly between the two, persists the user's choice, and is fully keyboard
accessible.

## Files changed

### `frontend/index.html`
- Added a no-flash inline script in `<head>` that reads the saved theme from
  `localStorage` and sets `data-theme="light"` on `<html>` **before first paint**,
  so a returning light-mode user never sees a dark flash.
- Added the toggle button markup just inside `.container`:
  - A `<button id="themeToggle" class="theme-toggle">` positioned top-right.
  - Contains two inline SVGs — a **sun** icon and a **moon** icon — that
    cross-fade based on the active theme.
  - Accessibility: `type="button"`, `aria-label` (updated dynamically),
    `aria-pressed` state, and a `title` tooltip. SVGs are `aria-hidden="true"`.
- Bumped cache-busting query strings: `style.css?v=11 → v=12`,
  `script.js?v=9 → v=10`.

### `frontend/style.css`
- **Light theme variables:** Renamed the default `:root` block to "dark theme
  (default)" and added a `:root[data-theme="light"]` block overriding all color
  variables (background, surface, text, borders, shadow, focus ring, welcome
  colors) with light-mode values.
- **New `--code-bg` variable:** Replaced the two hard-coded
  `rgba(0,0,0,0.2)` code/`pre` backgrounds with `var(--code-bg)` so inline code
  and code blocks remain readable in light mode.
- **Smooth theme transition:** Added a shared
  `transition: background-color/color/border-color 0.3s ease` to all the
  color-bearing surfaces (body, sidebar, chat areas, inputs, messages, chips,
  buttons) so switching themes animates instead of snapping.
- **Toggle button styles:** Circular 44×44 button using the theme variables
  (`--surface`, `--border-color`, `--shadow`), with hover (lift + accent
  border), active, and `:focus-visible` (accent focus ring) states.
- **Animated icons:** Sun/moon SVGs are absolutely stacked and transition
  opacity + rotation/scale. Dark theme shows the moon; light theme
  (`:root[data-theme="light"]`) shows the sun — each icon rotates and scales as
  it fades in/out.
- **Reduced motion:** A `@media (prefers-reduced-motion: reduce)` block disables
  these transitions for users who request it.

### `frontend/script.js`
- Added `themeToggle` to the cached DOM element list.
- `initTheme()` runs on `DOMContentLoaded`, reading `localStorage` and applying
  the saved theme (defaults to dark).
- `applyTheme(theme)` toggles the `data-theme` attribute on `<html>` and keeps
  the button's `aria-pressed` and `aria-label` in sync with the current state.
- `toggleTheme()` flips the theme, persists the choice to `localStorage`, and
  re-applies it. Wired to the button's `click` event in `setupEventListeners()`.
- All `localStorage` access is wrapped in `try/catch` to stay functional where
  storage is unavailable.

## Design notes

- **Fits the existing aesthetic:** reuses the same CSS variables, border-radius,
  focus-ring, and hover-lift patterns already used by the send/new-chat buttons.
- **Icon-based:** sun (light) / moon (dark) line icons matching the existing
  stroke-based SVG style of the send button.
- **Smooth animation:** icons cross-fade with rotation/scale; the whole UI
  transitions its colors over 0.3s.
- **Accessible & keyboard navigable:** it's a native `<button>`, so it's in the
  tab order and Enter/Space activate it. Screen readers get a descriptive,
  state-aware `aria-label` plus `aria-pressed`; focus is clearly visible.

---

# Front-End Changes: Code Quality Tooling

This change adds essential code quality tooling to the front-end development
workflow: an automatic code formatter, consistent formatting applied across the
whole front-end, and developer scripts for running quality checks.

## Note on the formatter choice (black → Prettier)

The request asked to "set up **black** for automatic code formatting." `black`
is a **Python-only** formatter and cannot format HTML, CSS, or JavaScript. Since
this work is scoped to **front-end features only**, black does not apply here.

The front-end equivalent of black — an opinionated, near-zero-config
auto-formatter — is **[Prettier](https://prettier.io/)**, so Prettier is what
was set up. It formats the front-end's `.html`, `.css`, and `.js` files.

## What was added

### 1. Formatter: Prettier

- **`package.json`** (new, repo root) — declares `prettier` as a dev dependency
  and defines the quality scripts (see below). `private: true` since this is not
  a published package.
- **`.prettierrc.json`** (new) — the formatting rules, applied consistently to
  every front-end file:
  - `printWidth: 100`
  - `tabWidth: 2`, `useTabs: false`
  - `semi: true`
  - `singleQuote: true` (matches the existing JS style)
  - `trailingComma: "es5"`
  - `bracketSpacing: true`
  - `arrowParens: "always"`
  - `endOfLine: "lf"`
- **`.prettierignore`** (new) — excludes everything out of scope: `node_modules/`,
  the Python `backend/`, data/build artifacts (`chroma_db/`, `docs/`), and `*.md`.

### 2. Consistent formatting applied to the codebase

Prettier was run with `--write` over the whole front-end. All three files were
reformatted to a single consistent style (4-space → 2-space indentation,
normalized quotes/semicolons, wrapped long lines, trailing commas):

- `frontend/index.html`
- `frontend/script.js`
- `frontend/style.css`

These are **formatting-only** changes — verified with `git diff -w` (whitespace
ignored), the only remaining diffs are Prettier idioms such as arrow-parameter
parentheses (`s =>` → `(s) =>`), trailing commas, and line wrapping. No
application logic was changed.

### 3. Developer scripts for quality checks

npm scripts (in `package.json`):

| Command | What it does |
| --- | --- |
| `npm run format` | Auto-format all front-end files in place |
| `npm run format:check` | Verify formatting without writing; non-zero exit if any file is off (CI / pre-commit friendly) |
| `npm run quality` | Umbrella quality gate — currently runs `format:check` |

Convenience shell scripts (in `scripts/`, matching the existing `run.sh`
Git-Bash-on-Windows convention):

- **`scripts/format.sh`** — runs `npm run format`.
- **`scripts/check-quality.sh`** — runs `npm run format:check`; exits non-zero on
  any unformatted file.

### 4. Supporting config

- **`.gitignore`** — added `node_modules/`.
- **`.gitattributes`** (new) — pins `eol=lf` for `frontend/*.{js,css,html}` so
  Prettier's `endOfLine: "lf"` check stays consistent across platforms and avoids
  CRLF churn on Windows.

## How to use

```bash
# one-time install of the tooling
npm install

# auto-format the front-end
npm run format        # or: bash scripts/format.sh

# verify formatting (use in CI / before committing)
npm run quality       # or: bash scripts/check-quality.sh
```

## Files changed/added

| File | Status |
| --- | --- |
| `package.json` | added |
| `.prettierrc.json` | added |
| `.prettierignore` | added |
| `.gitattributes` | added |
| `scripts/format.sh` | added |
| `scripts/check-quality.sh` | added |
| `.gitignore` | modified (ignore `node_modules/`) |
| `frontend/index.html` | reformatted |
| `frontend/script.js` | reformatted |
| `frontend/style.css` | reformatted |

---

# Testing Framework Enhancements

> Note on scope: the `/implement_feature` command template carries a generic
> "front-end features only" line, but the actual task was **backend
> test-infrastructure** work. This file documents what was built, per the
> command's instruction to record changes in `frontend-changes.md`. No
> production application code (frontend or backend) was modified — only the
> test suite and its configuration.

## Goal

The existing test suite covered individual backend components (`AIGenerator`,
`CourseSearchTool`, `RAGSystem`) but had no coverage of the FastAPI HTTP layer.
This change adds API endpoint tests plus the shared fixtures and pytest
configuration to support them.

## What changed

### 1. `pyproject.toml` — pytest configuration

Expanded `[tool.pytest.ini_options]` for cleaner, stricter test runs:

- `addopts = ["-ra", "--strict-markers", "--tb=short", "--color=yes"]`
  - `-ra` prints a summary of every non-passing test at the end.
  - `--strict-markers` turns a mistyped marker into an error instead of a
    silent warning.
  - `--tb=short` keeps tracebacks readable.
- Registered an `api` marker for the HTTP-layer tests.
- Added `httpx>=0.27` to the `dev` dependency group — `fastapi.testclient.TestClient`
  (Starlette) requires it.

`testpaths` and `pythonpath` were left unchanged.

### 2. `backend/tests/conftest.py` — shared fixtures

Kept the existing `sys.path` setup (so `from vector_store import ...` resolves)
and added reusable fixtures:

- **Sample data**: `sample_sources`, `sample_answer`, `sample_query_response`,
  `sample_course_stats`.
- **`mock_rag_system`**: a `MagicMock` standing in for `RAGSystem` with sensible
  defaults (`query`, `session_manager.create_session`, `get_course_analytics`).
- **`test_app`**: a FastAPI app that **mirrors `backend/app.py`'s routes inline**
  against the mocked RAG system.
- **`client`**: a `TestClient` bound to `test_app`.

**Why build the app inline instead of importing `backend/app.py`:** the
production module mounts the `../frontend` static directory *at import time*
(`StaticFiles` raises if the directory is missing) and constructs a real
`RAGSystem` (loading an embedding model and opening ChromaDB). Both are
unavailable/undesirable under test. The fixture rebuilds the same routes
(`/api/query`, `/api/courses`, `/api/session/clear`) with identical Pydantic
schemas, and mounts a **throwaway `tmp_path` frontend dir** at `/` so the root
route is exercisable without the real frontend.

### 3. `backend/tests/test_api_endpoints.py` — new endpoint tests

18 tests grouped by endpoint, all tagged `@pytest.mark.api`:

- **`POST /api/query`**: new-session creation, session reuse, source shape,
  missing/empty-body validation (422), RAG failure → 500, empty-string query.
- **`GET /api/courses`**: stats payload, single analytics call, empty catalog,
  failure → 500.
- **`POST /api/session/clear`**: success, missing id (422), failure → 500.
- **`GET /`**: serves the (test) frontend HTML; unknown path → 404.
- **Cross-cutting**: non-JSON body rejected (422), `GET`-only route returns 405
  on `POST`.

## Running the tests

```bash
# API tests only (fast — no embedding/ChromaDB imports):
uv run pytest backend/tests/test_api_endpoints.py

# Select by marker:
uv run pytest -m api

# Full suite:
uv run pytest
```

## Results

- API endpoint tests: **18 passed** (~1.4s in isolation).
- Full suite: **40 passed** (22 pre-existing + 18 new).

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

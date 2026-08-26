# Quality gates — SonarQube parity per language

`quality/quality.py` reproduces SonarQube's default **Sonar way** quality gate
locally (or in pre-merge CI), so failures surface before Sonar blocks a merge.
Run from the target repo root: `python3 quality/quality.py <lang>`.

Variants: `node`, `typescript`, `deno`, `bun`, `rust`, `go`, `python`.

## What SonarQube actually gates on ("Sonar way", verified 2026-08)

Four conditions, all scoped to **new code**; PR analysis evaluates new code
only:

1. No new issues (equivalently: Reliability/Security/Maintainability ratings = A)
2. Security hotspots reviewed = 100% (transitional: hotspots are being
   reclassified as regular security issues in 2026.x)
3. Coverage on new code ≥ **80.0%**
4. Duplicated lines on new code ≤ **3.0%**

Fudge factor: coverage/duplication conditions are skipped until there are
≥ 20 new lines. Source:
[Introduction to quality gates](https://docs.sonarsource.com/sonarqube-server/latest/quality-standards-administration/managing-quality-gates/introduction-to-quality-gates).

Two things our scripts cannot reproduce locally (documented, accepted):

- **New-code scoping** — local tools measure the whole project. Stricter
  early, equal once the codebase is clean.
- **S3776 cognitive complexity** is the same rule id in every language with
  default threshold 15, settable only in a server-side quality profile. Our
  per-language local stand-ins target the same 15.

## Gate → tool mapping

| Sonar way gate | Threshold | node / typescript | deno | bun |
|---|---|---|---|---|
| Bugs / code smells | zero issues | eslint (flat config) | `deno lint` | eslint |
| Cognitive complexity (S3776) | ≤ 15 / function | `sonarjs/cognitive-complexity` | eslint+sonarjs if configured, else SKIP (gap 1) | `sonarjs/cognitive-complexity` |
| Duplicated lines | ≤ 3% (block ≥ 100 tokens / 10 lines) | jscpd (all languages — see duplication notes) | jscpd | jscpd |
| Formatting | clean | `prettier --check` | `deno fmt --check` | `prettier --check` |
| Security | no high/critical | `npm audit --audit-level=high` | `osv-scanner` on `deno.lock` (gap 2) | `bun audit` |
| Coverage | ≥ 80% lines | vitest `--coverage.thresholds.lines` or `c8 --check-coverage` | `deno test --coverage` + lcov | `bun test --coverage` (lcov) |

| Sonar way gate | rust | go | python |
|---|---|---|---|
| Bugs / code smells | `cargo clippy --all-targets -- -D warnings` | golangci-lint (staticcheck, revive, …) | `ruff check` (E, F, W, I, S) |
| Cognitive complexity | `clippy::cognitive_complexity`, `clippy.toml` threshold 15 (Sonar's native rust:S3776 also exists, default 15) | gocognit `min-complexity: 15` (matches go:S3776; Go has no cyclomatic rule) | ruff C901 cyclomatic proxy (gap 3) |
| Duplicated lines | jscpd | jscpd | jscpd |
| Formatting | `cargo fmt --check` | `gofmt -l` | `ruff format --check` |
| Security | `cargo audit` | gosec + `govulncheck` | ruff S rules + `pip-audit` |
| Coverage | `cargo llvm-cov --fail-under-lines 80` | `go test -coverprofile` + `go tool cover` total | `coverage report --fail-under=80` / pytest-cov |

## Duplication parity notes (verified against tooling, 2026-08)

- SonarQube's CPD counts a duplicated block only at **≥ 100 identical tokens
  over ≥ 10 lines** (non-Java languages; overridable via
  `sonar.cpd.<lang>.minimumTokens/minimumLines`; Python's language key is
  `py`). Duplication is a **metric**, not a rule — it raises no issues.
- jscpd's own defaults (50 tokens / 5 lines) are stricter than Sonar, so the
  engine passes `--min-tokens 100 --min-lines 10` (`QUALITY_DUP_MIN_TOKENS` /
  `QUALITY_DUP_MIN_LINES` to override).
- **jscpd v5** (current npm release, a Rust rewrite) is not usable for this:
  it silently skips extensions it doesn't auto-detect (e.g. `.go` → false
  PASS), dropped `--gitignore`, and its `--min-tokens` filters whole files
  instead of clone blocks. The engine therefore pins the ephemeral runner to
  `jscpd@3` and passes the min flags only to jscpd ≤ 4. Each variant declares
  explicit `DUP_FORMATS` so files are never silently skipped.
- Tokenizers differ between jscpd and Sonar CPD; token-count parity is
  approximate at block boundaries.

## Known gaps vs SonarQube

1. **Deno cognitive complexity**: `deno lint` has no such rule. The variant
   runs eslint + eslint-plugin-sonarjs only when the repo already has an
   eslint config; otherwise the gate SKIPs with the message to add it.
2. **Deno dependency audit**: no `deno audit` exists; the variant uses
   `osv-scanner` against `deno.lock` when installed, else SKIPs.
3. **Python cognitive complexity**: SonarQube has native `python:S3776`
   (default 15), but no maintained *local* cognitive-complexity linter
   exists; ruff's C901 (mccabe cyclomatic, max 15) is the documented proxy.
   Cyclomatic ≠ cognitive — nesting-heavy code can pass locally and fail in
   Sonar.
4. **Taint/injection SAST** (SQLi, XSS, SSRF, path traversal: S3649, S5131,
   S5144, S2083, S2076, …) requires SonarQube Server Developer Edition+ or
   SonarQube Cloud — free Community Build only has pattern-based security
   rules. Our local security gates (gosec, ruff S, audits) cover the
   free-tier gap; they cannot reproduce taint analysis.
5. **Deno/Bun are not officially supported SonarQube languages** — projects
   are analyzed as plain TS/JS; `deno.json`/import maps/`jsr:`/`npm:`
   specifiers are unresolved, degrading type-aware rules. (Bun touchpoints:
   SonarJS 13.4 recognizes `bun:test`; Enterprise Advanced Security reads
   `bun.lock`.)

## Feeding local reports into SonarQube (optional)

The same tools can emit reports SonarQube imports, so local and server results
agree:

| Tool | Format | SonarQube key |
|---|---|---|
| ESLint | `eslint . -f json` | `sonar.eslint.reportPaths` |
| Clippy | `cargo clippy --message-format=json` (or let the scanner run clippy itself) | `sonar.rust.clippyReport.reportPaths` |
| Rust coverage | `cargo llvm-cov --lcov` | `sonar.rust.lcov.reportPaths` |
| golangci-lint | checkstyle XML (`--output.checkstyle.path`) | `sonar.go.golangci-lint.reportPaths` |
| go vet | stderr text | `sonar.go.govet.reportPaths` |
| govulncheck | SARIF (`-format sarif`) | `sonar.sarifReportPaths` |
| Go coverage | native `cover.out` (no conversion needed) | `sonar.go.coverage.reportPaths` |
| Ruff | `ruff check --output-format=json` | `sonar.python.ruff.reportPaths` |
| Bandit | JSON | `sonar.python.bandit.reportPaths` |
| Python coverage | Cobertura XML (`coverage xml`, set `relative_files = True`) | `sonar.python.coverage.reportPaths` |
| JS/TS coverage | LCOV only | `sonar.javascript.lcov.reportPaths` |

External imported issues are deduplicated against native rules but are **not
manageable in quality profiles**. Rust note: native Rust support shipped in
SonarQube Cloud (2025-04) and Server 2025.3; the scanner runs clippy itself
by default (`sonar.rust.clippy.enabled=false` to disable) — don't both
auto-run and import, or issues double.

## Where these scripts sit among prevention products

Full "don't let Sonar block the merge" stack, cheapest first:

1. **IDE**: SonarLint in connected mode (VS Code / JetBrains) — same rules,
   pre-commit feedback.
2. **Local/pre-push**: these scripts (`python3 quality/quality.py <lang>`),
   optionally wired into `pre-commit`, `husky`, or `lefthook`.
3. **CI**: `examples/quality.yml` (this repo) runs the same gates on PRs.
4. **Sonar-side merge block**: PR analysis (Developer Edition+ / Cloud) with
   PR decoration + GitHub branch protection requiring the
   `SonarQube Code Analysis` check; or `SonarSource/sonarqube-scan-action`
   (v8.x) + `sonarqube-quality-gate-action` (set `pollingTimeoutSec`, default
   300s); scanner-side `-Dsonar.qualitygate.wait=true` is documented for
   blocking deployments, not PRs. Use `actions/checkout` with
   `fetch-depth: 0` — new-code attribution needs full git history.

Note: `rules.sonarsource.com` was decommissioned in Feb 2026 — rule
documentation now only ships inside SonarQube/SonarLint; don't deep-link it.

## Config templates

Each variant directory ships the template a target repo can copy:

- `quality/node/eslint.config.mjs`, `quality/bun/eslint.config.mjs`,
  `quality/typescript/eslint.config.mjs` — eslint 9 flat config with
  `@eslint/js` + `eslint-plugin-sonarjs` (`cognitive-complexity: ["error", 15]`,
  the same default as S3776) + `typescript-eslint` scoped to TS files.
- `quality/rust/clippy.toml` — `cognitive-complexity-threshold = 15`
  (auto-copied to the repo root by the rust variant when absent).
- `quality/go/.golangci.yml` — golangci-lint v2 config with gosec, gocognit
  (15), revive, staticcheck. The cognitive-complexity and security gates run
  with generated single-linter configs so the thresholds hold even when a repo
  config omits gocognit/gosec.
- `quality/python/ruff.toml` — `select = ["E","F","W","I","S","C901"]`,
  mccabe max-complexity 15 (used when the repo has no ruff config).

## Knobs

| Variable | Default | Meaning |
|---|---|---|
| `QUALITY_COVERAGE_MIN` | `80` | minimum line coverage % |
| `QUALITY_DUP_MAX` | `3` | max duplicated lines % |
| `QUALITY_DUP_MIN_TOKENS` | `100` | min tokens per duplicated block (Sonar CPD parity) |
| `QUALITY_DUP_MIN_LINES` | `10` | min lines per duplicated block (Sonar CPD parity) |
| `QUALITY_COGNITIVE_MAX` | `15` | max cognitive complexity per function |
| `QUALITY_SKIP` | empty | comma-separated gates to skip, e.g. `coverage,security` |
| `QUALITY_AUTO_TOOLS` | `0` | `1` allows ephemeral tool runners (`npx`, `uvx`) |

Missing **required** tools FAIL with their install command; missing
**optional** tools SKIP with a hint. Nothing is installed into the target repo.

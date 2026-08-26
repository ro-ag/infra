# Quality gates — a local, SonarQube-free quality stack

`quality/quality.py` catches locally (or in pre-merge CI) the same classes of
issues SonarQube's default **Sonar way** gate blocks merges on — **without
running or talking to SonarQube**. Everything runs on open-source
alternatives; the goal is to find the issues *before* any Sonar scan ever
happens. Run from the target repo root: `python3 quality/quality.py <lang>`.

Variants: `node`, `typescript`, `deno`, `bun`, `rust`, `go`, `python`.

## What we reproduce ("Sonar way" defaults, verified 2026-08)

SonarQube's built-in gate has four conditions, all scoped to *new code*:
no new issues, hotspots reviewed 100%, coverage ≥ 80.0%, duplicated lines
≤ 3.0% (coverage/duplication skipped under 20 new lines). Cognitive
complexity is rule S3776, default 15, in every language.

Our stack runs the equivalents **whole-project** (stricter early, equal once
the codebase is clean — local tools can't diff new code):

| Gate | Threshold | Alternative tool |
|---|---|---|
| `lint` — bugs / code smells | zero issues | per-language linter (below) |
| `cognitive-complexity` | ≤ 15 / function | per-language (below) |
| `format` | clean | per-language formatter |
| `security` — vulnerable dependencies | no high/critical | per-language audit (below) |
| `coverage` | ≥ 80% lines | per-language coverage (below) |
| `duplication` | ≤ 3%, block ≥ 100 tokens / 10 lines | jscpd@3 (all languages) |
| `sast` — injection/secrets patterns | zero findings | Semgrep CE `p/security-audit` (all languages, optional) |

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
4. **Deep taint SAST parity**: SonarQube's injection rules (SQLi, XSS, SSRF,
   path traversal) are Developer Edition+ anyway. Our stand-in is the `sast`
   gate (Semgrep CE `p/security-audit`, taint-capable, all seven languages) —
   same issue class, different engine, no Sonar involved.
5. **Deno/Bun are not officially supported SonarQube languages** — projects
   are analyzed as plain TS/JS; `deno.json`/import maps/`jsr:`/`npm:`
   specifiers are unresolved, degrading type-aware rules. (Bun touchpoints:
   SonarJS 13.4 recognizes `bun:test`; Enterprise Advanced Security reads
   `bun.lock`.)

## Why these alternatives (mapping to what Sonar would have done)

| SonarQube component | Our alternative |
|---|---|
| SonarJS / SonarPython / SonarGo / sonar-rust rule engines | eslint+sonarjs, ruff, golangci-lint, clippy, deno lint |
| S3776 cognitive complexity (default 15) | sonarjs/cognitive-complexity (same engine Sonar publishes), clippy `cognitive_complexity`, gocognit, ruff C901 proxy |
| CPD duplication metric (3% gate, 100-token/10-line blocks) | jscpd@3 with Sonar-matched block minimums |
| Taint SAST (paid tiers) | Semgrep CE (`p/security-audit`) |
| Dependency vulnerability scanning | npm/bun audit, osv-scanner, cargo audit, govulncheck, pip-audit |
| Coverage gate 80% | c8/vitest, deno coverage, bun test, llvm-cov, go cover, coverage.py |
| Quality gate as merge blocker | `examples/quality.yml` CI job (branch protection on that check) |

## Hooking it up (no SonarQube anywhere)

1. **Local/pre-push**: `python3 quality/quality.py <lang>` — wire into
   `pre-commit`, `husky`, or `lefthook` as a pre-push hook.
2. **CI merge block**: `examples/quality.yml` (this repo) runs the gates on
   PRs; make that check required in GitHub branch protection and merges are
   blocked on exactly these gates.
3. **Optional hosted dashboards** (if trends/reporting are ever wanted, still
   no SonarQube): Semgrep Cloud (free tier) for SAST history, Codecov/Coveralls
   for coverage trends, Qlty (the CodeClimate successor) for smells/dup trends.
   The gates above stay the source of truth; these are dashboards, not blockers.

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

Gate names: `lint`, `cognitive-complexity`, `format`, `security`, `coverage`,
`duplication`, `sast`.

Missing **required** tools FAIL with their install command; missing
**optional** tools SKIP with a hint. Nothing is installed into the target repo.

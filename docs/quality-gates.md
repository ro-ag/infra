# Quality gates — SonarQube parity per language

`quality/quality.py` reproduces SonarQube's default **Sonar way** quality gate
locally (or in pre-merge CI), so failures surface before Sonar blocks a merge.
Run from the target repo root: `python3 quality/quality.py <lang>`.

Variants: `node`, `typescript`, `deno`, `bun`, `rust`, `go`, `python`.

## Gate → tool mapping

| Sonar way gate | Threshold | node / typescript | deno | bun |
|---|---|---|---|---|
| Bugs / code smells (reliability, maintainability A) | zero issues | eslint (flat config) | `deno lint` | eslint |
| Cognitive complexity | ≤ 15 / function | `sonarjs/cognitive-complexity` | eslint+sonarjs if configured, else SKIP (gap 1) | `sonarjs/cognitive-complexity` |
| Duplicated lines | ≤ 3% | jscpd (all languages) | jscpd | jscpd |
| Formatting | clean | `prettier --check` | `deno fmt --check` | `prettier --check` |
| Security (vulnerabilities A) | no high/critical | `npm audit --audit-level=high` | `osv-scanner` on `deno.lock` (gap 2) | `bun audit` |
| Coverage | ≥ 80% lines | vitest `--coverage.thresholds.lines` or `c8 --check-coverage` | `deno test --coverage` + lcov | `bun test --coverage` (lcov) |

| Sonar way gate | rust | go | python |
|---|---|---|---|
| Bugs / code smells | `cargo clippy --all-targets -- -D warnings` | golangci-lint (staticcheck, revive, …) | `ruff check` (E, F, W, I, S) |
| Cognitive complexity | `clippy::cognitive_complexity`, `clippy.toml` threshold 15 | gocognit `min-complexity: 15` | ruff C901 cyclomatic proxy (gap 3) |
| Duplicated lines | jscpd | jscpd | jscpd |
| Formatting | `cargo fmt --check` | `gofmt -l` | `ruff format --check` |
| Security | `cargo audit` | gosec + `govulncheck` | ruff S rules + `pip-audit` |
| Coverage | `cargo llvm-cov --fail-under-lines 80` | `go test -coverprofile` + `go tool cover` total | `coverage report --fail-under=80` / pytest-cov |

## Known gaps vs SonarQube

1. **Deno cognitive complexity**: `deno lint` has no such rule. The variant
   runs eslint + eslint-plugin-sonarjs only when the repo already has an
   eslint config; otherwise the gate SKIPs with the message to add it.
2. **Deno dependency audit**: no `deno audit` exists; the variant uses
   `osv-scanner` against `deno.lock` when installed, else SKIPs.
3. **Python cognitive complexity**: no maintained cognitive-complexity linter
   exists; ruff's C901 (mccabe cyclomatic complexity, max 15) is used as the
   documented proxy.
4. **New code vs whole project**: Sonar's default gate measures coverage and
   duplication on *new code*; these scripts measure the whole project. That is
   stricter early on and equal once the codebase is clean.
5. **Security hotspots** ("reviewed" rating) have no local equivalent — they
   remain a Sonar-side review step.

## Config templates

Each variant directory ships the template a target repo can copy:

- `quality/node/eslint.config.mjs`, `quality/bun/eslint.config.mjs`,
  `quality/typescript/eslint.config.mjs` — eslint 9 flat config with
  `@eslint/js` + `eslint-plugin-sonarjs` (`cognitive-complexity: ["error", 15]`)
  + `typescript-eslint` scoped to TS files.
- `quality/rust/clippy.toml` — `cognitive-complexity-threshold = 15`
  (auto-copied to the repo root by the rust variant when absent).
- `quality/go/.golangci.yml` — golangci-lint v2 config with gosec, gocognit
  (15), revive, staticcheck. The cognitive-complexity and security gates run
  with generated single-linter configs so the thresholds hold even when a repo
  config omits gocognit/gosec.
- `quality/python/ruff.toml` — `select = ["E","F","W","I","S","C901"]`,
  mccabe max-complexity 15 (used when the repo has no ruff config).

## Notes

- **jscpd v5** (the current npm release, a Rust rewrite) respects `.gitignore`
  by default and dropped the `--gitignore` flag; the engine probes `--help`
  and passes `--gitignore` only to older versions.
- Missing **required** tools FAIL with their install command; missing
  **optional** tools SKIP with a hint. `QUALITY_AUTO_TOOLS=1` allows ephemeral
  runners (`npx`, `uvx`) instead. Nothing is installed into the target repo.
- Knobs: `QUALITY_COVERAGE_MIN`, `QUALITY_DUP_MAX`, `QUALITY_COGNITIVE_MAX`,
  `QUALITY_SKIP` (comma-separated gate names), `QUALITY_AUTO_TOOLS`.

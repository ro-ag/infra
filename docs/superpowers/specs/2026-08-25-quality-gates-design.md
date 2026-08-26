# Quality gates design — SonarQube-parity local checks per language

Date: 2026-08-25
Status: approved-by-design (auto permission mode; interactive gates skipped)

## Problem

SonarQube blocks merges on its default "Sonar way" quality gate. Teams need to
catch the same failures locally (or in pre-merge CI) *before* Sonar runs, with
per-language specialized tooling, across the language mix now in use:
Deno, Bun, Node.js, TypeScript, Rust, Go, Python.

## Gates reproduced (Sonar way defaults)

| SonarQube gate | Threshold |
|---|---|
| Coverage on new code | ≥ 80% |
| Duplicated lines | ≤ 3% |
| Cognitive complexity per function | ≤ 15 |
| Code smells / bugs / vulnerabilities (maintainability, reliability, security rating) | A (zero open issues at severity) |
| Security vulnerabilities in dependencies | none (high/critical) |
| Formatting (user-added requirement; not a Sonar default) | formatter check passes |

## Architecture

New top-level `quality/` directory in `infra` (this repo is the fleet
copy-source; nothing here runs against infra itself):

```
quality/
  README.md              # how to vendor + run in a target repo
  lib/common.sh          # shared bash helpers: tool check, gate report, thresholds
  jscpd.json             # shared duplication config, threshold 3%
  node/quality.sh        # Node.js + TypeScript (one script; TS via @typescript-eslint)
  node/eslint.config.mjs # eslint flat config template incl. eslint-plugin-sonarjs
  deno/quality.sh
  bun/quality.sh
  rust/quality.sh
  rust/clippy.toml       # cognitive-complexity-threshold = 15
  go/quality.sh
  go/.golangci.yml       # gocognit 15, gosec, staticcheck, revive, gofmt
  python/quality.sh
  python/ruff.toml       # incl. S (bandit) + C901 complexity rules
docs/quality-gates.md    # SonarQube gate → tool mapping per language, known gaps
examples/quality.yml     # caller CI workflow showing per-language jobs
```

Each `quality.sh`:

- Runs from a **target repo root** (the repo being checked), not from infra.
- `set -euo pipefail`; each gate prints PASS/FAIL/SKIP; exit 1 if any gate FAILs.
- Missing optional tools → SKIP with install hint; missing required tool → FAIL
  with install hint. No silent passes.
- Env knobs: `QUALITY_COVERAGE_MIN` (default 80), `QUALITY_DUP_MAX` (default 3),
  `QUALITY_COGNITIVE_MAX` (default 15), `QUALITY_SKIP` (comma list of gates).

## Per-language tool mapping

| Gate | Node/TS | Deno | Bun | Rust | Go | Python |
|---|---|---|---|---|---|---|
| Smells/lint | eslint + sonarjs | deno lint | eslint + sonarjs | clippy -D warnings | golangci-lint | ruff check |
| Cognitive ≤15 | sonarjs/cognitive-complexity | eslint sonarjs (optional; deno lint lacks it) | sonarjs | clippy cognitive_complexity (clippy.toml) | gocognit | ruff C901 (mccabe proxy — see gaps) |
| Duplication ≤3% | jscpd (all languages, shared config) |
| Format | prettier --check | deno fmt --check | prettier --check | rustfmt --check | gofmt -l | ruff format --check |
| Security | npm audit --audit-level=high | osv-scanner (optional; deno has no audit) | bun audit | cargo audit | gosec (via golangci) + govulncheck | ruff S rules + pip-audit |
| Coverage ≥80% | c8 --check-coverage (node:test) or vitest/jest passthrough | deno test --coverage + deno coverage | bun test --coverage | cargo llvm-cov --fail-under-lines | go test -coverprofile + awk total | coverage/pytest --cov-fail-under |

## Known gaps (documented, not hidden)

- Deno lint has no cognitive-complexity rule → script runs eslint+sonarjs if an
  eslint config is present, else SKIP with a note.
- Python has no maintained cognitive-complexity linter → ruff C901 (cyclomatic)
  at threshold 15 as documented proxy.
- Coverage on *new code* vs whole project: local tools measure whole-project
  coverage; docs note the difference from Sonar's new-code metric.

## Error handling

- Scripts never install anything into the target repo; they fail with the exact
  install command.
- Tool bootstrap via ephemeral runners where possible (npx, uvx) is opt-in via
  `QUALITY_AUTO_TOOLS=1`, default off.

## Testing

Throwaway fixture projects (one per language, minimal code with a test) under a
temp dir; run each script expecting: all gates PASS on clean fixture, FAIL on a
deliberately broken fixture (format violation / low coverage).

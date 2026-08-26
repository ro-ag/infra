# quality/ — local quality gates (SonarQube-free alternative stack)

A Python primary script (`quality.py`) with per-language variant directories
that catch the same issue classes SonarQube's default "Sonar way" gate blocks
merges on — using only open-source alternative tools, **no SonarQube
anywhere**. Run it locally or in pre-merge CI. Stdlib-only Python 3.9+;
each variant directory holds that language's config templates.

| Gate | Threshold | Tool |
|---|---|---|
| Coverage | ≥ 80% lines | per-language (vitest/c8, deno, bun, llvm-cov, go cover, coverage.py) |
| Duplicated lines | ≤ 3%, block ≥ 100 tokens/10 lines | jscpd@3 |
| Cognitive complexity per function | ≤ 15 | sonarjs / clippy / gocognit / ruff C901 |
| Lint / code smells | zero issues | eslint, deno lint, clippy, golangci-lint, ruff |
| Formatting | formatter check passes | prettier, deno fmt, rustfmt, gofmt, ruff format |
| Security (dependencies) | no high/critical findings | npm/bun audit, osv-scanner, cargo audit, govulncheck, pip-audit |
| SAST (injection/secrets patterns) | zero findings | Semgrep CE `p/security-audit` (optional, all languages) |

## Usage

Vendor the whole `quality/` directory into a target repo (this repo is the
fleet copy-source), then run from the target repo root:

```bash
python3 quality/quality.py node        # Node.js
python3 quality/quality.py typescript  # TypeScript (node gates + tsconfig check)
python3 quality/quality.py deno
python3 quality/quality.py bun
python3 quality/quality.py rust
python3 quality/quality.py go
python3 quality/quality.py python
```

Every gate prints `PASS` / `FAIL` / `SKIP`; the script exits 1 if any gate
fails. A missing **required** tool fails with its install command; a missing
**optional** tool skips the gate with an install hint.

Layout: `quality.py` (engine: reporting, thresholds, jscpd duplication,
semgrep SAST, lcov parsing), `jscommon.py` (shared eslint/prettier helpers
for the JS runtimes), and `<lang>/variant.py` per language next to its config
templates (`eslint.config.mjs`, `clippy.toml`, `.golangci.yml`, `ruff.toml`).

## Knobs (environment variables)

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

See `docs/quality-gates.md` for the full SonarQube gate → alternative-tool
mapping per language and the known gaps.

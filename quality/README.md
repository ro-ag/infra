# quality/ — SonarQube-parity local quality gates

A Python primary script (`quality.py`) with per-language variant directories
that reproduce SonarQube's default "Sonar way" quality gate **before** Sonar
blocks a merge. Run it locally or in pre-merge CI. Stdlib-only Python 3.9+;
each variant directory holds that language's config templates.

| Gate | Threshold |
|---|---|
| Coverage | ≥ 80% lines |
| Duplicated lines | ≤ 3% |
| Cognitive complexity per function | ≤ 15 |
| Lint / code smells | zero issues |
| Formatting | formatter check passes |
| Security | no high/critical findings |

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

Layout: `quality.py` (engine: reporting, thresholds, jscpd, lcov parsing),
`jscommon.py` (shared eslint/prettier helpers for the JS runtimes), and
`<lang>/variant.py` per language next to its config templates
(`eslint.config.mjs`, `clippy.toml`, `.golangci.yml`, `ruff.toml`).

## Knobs (environment variables)

| Variable | Default | Meaning |
|---|---|---|
| `QUALITY_COVERAGE_MIN` | `80` | minimum line coverage % |
| `QUALITY_DUP_MAX` | `3` | max duplicated lines % |
| `QUALITY_COGNITIVE_MAX` | `15` | max cognitive complexity per function |
| `QUALITY_SKIP` | empty | comma-separated gates to skip, e.g. `coverage,security` |
| `QUALITY_AUTO_TOOLS` | `0` | `1` allows ephemeral tool runners (`npx`, `uvx`) |

Gate names: `lint`, `cognitive-complexity`, `format`, `security`, `coverage`,
`duplication`.

See `docs/quality-gates.md` for the full SonarQube gate → tool mapping per
language and the known gaps.

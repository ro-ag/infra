# Quality Gates (SonarQube-parity) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add per-language quality-gate scripts (Deno, Bun, Node.js+TypeScript, Rust, Go, Python) to `infra/quality/` that reproduce SonarQube "Sonar way" defaults locally so failures surface before Sonar blocks a merge.

**Architecture:** One self-contained directory per ecosystem under `quality/<lang>/` — each holds its own standalone `quality.sh` (helpers inlined, no shared library) plus config templates, so a single directory can be vendored on its own. Each script runs from a *target* repo root and exits 1 if any gate FAILs.

> Revision: user directive — no shared `lib/common.sh`; duplicate the ~40 lines of helpers in each script so every directory stands alone. Task 1 shipped only `quality/README.md` and the helper snippet below, which Tasks 2–7 inline verbatim.

**Tech Stack:** bash, eslint + eslint-plugin-sonarjs + prettier, deno lint/fmt/coverage, clippy + rustfmt + cargo-audit + cargo-llvm-cov, golangci-lint + gofmt, ruff + coverage.py/pip-audit, jscpd (duplication, all languages).

## Global Constraints

- Spec: `docs/superpowers/specs/2026-08-25-quality-gates-design.md` (same repo).
- Threshold defaults: coverage ≥ 80%, duplication ≤ 3%, cognitive complexity ≤ 15.
- Env knobs in every script: `QUALITY_COVERAGE_MIN` (80), `QUALITY_DUP_MAX` (3), `QUALITY_COGNITIVE_MAX` (15), `QUALITY_SKIP` (comma-separated gate names), `QUALITY_AUTO_TOOLS` (default 0; 1 allows ephemeral runners like npx/uvx).
- Every script: `#!/usr/bin/env bash`, `set -euo pipefail`, resolves its own dir to locate `lib/common.sh` and its config templates, then `cd` stays at the caller's cwd (the target repo root).
- Gate results are reported as `PASS` / `FAIL` / `SKIP` via common.sh; missing required tool = FAIL with exact install command; missing optional tool = SKIP with install hint. Never install into the target repo.
- Repo working agreements: no commits to `main` (branch first), no AI attribution in commits, no new active workflows in this repo's `.github/` (examples/ callers are fine).
- Coverage measured whole-project locally; `docs/quality-gates.md` must note the difference vs Sonar's new-code metric.

---

### Task 1: Shared library + jscpd config

**Files:**
- Create: `quality/lib/common.sh`
- Create: `quality/jscpd.json`
- Create: `quality/README.md`
- Test: fixture exercise via a smoke script call (Step 3)

**Interfaces:**
- Produces (consumed by Tasks 2–7):
  - `qg_need_tool <cmd> <install-hint> [required|optional]` — returns 0 present, 1 missing-required, 2 missing-optional; prints hint on missing.
  - `qg_pass <gate>` / `qg_fail <gate> <msg>` / `qg_skip <gate> <reason>` — record + print gate result.
  - `qg_gate_skipped <gate>` — returns 0 if `<gate>` is in `$QUALITY_SKIP`.
  - `qg_finish` — prints summary; `exit 1` if any FAIL recorded.
  - `qg_jscpd <path...>` — runs duplication gate on paths with `quality/jscpd.json`, threshold `$QUALITY_DUP_MAX`; records PASS/FAIL/SKIP for gate `duplication`.
  - Env defaults set on sourcing: `QUALITY_COVERAGE_MIN=80`, `QUALITY_DUP_MAX=3`, `QUALITY_COGNITIVE_MAX=15`, `QUALITY_SKIP=""`, `QUALITY_AUTO_TOOLS=0`.

- [ ] **Step 1: Write `quality/lib/common.sh`**

```bash
#!/usr/bin/env bash
# Shared helpers for quality gate scripts. Source, do not execute.
QUALITY_COVERAGE_MIN="${QUALITY_COVERAGE_MIN:-80}"
QUALITY_DUP_MAX="${QUALITY_DUP_MAX:-3}"
QUALITY_COGNITIVE_MAX="${QUALITY_COGNITIVE_MAX:-15}"
QUALITY_SKIP="${QUALITY_SKIP:-}"
QUALITY_AUTO_TOOLS="${QUALITY_AUTO_TOOLS:-0}"

_QG_FAILED=0

_qg_report() { # <status> <gate> <detail>
  printf '%-4s  %-22s %s\n' "$1" "$2" "$3"
}

qg_pass() { _qg_report PASS "$1" "${2:-}"; }
qg_fail() { _qg_report FAIL "$1" "${2:-}"; _QG_FAILED=1; }
qg_skip() { _qg_report SKIP "$1" "${2:-}"; }

qg_gate_skipped() { # <gate> -> 0 if listed in QUALITY_SKIP
  case ",${QUALITY_SKIP}," in *,"$1",*) return 0 ;; esac
  return 1
}

qg_need_tool() { # <cmd> <install-hint> [required|optional] -> 0|1|2
  local cmd="$1" hint="$2" level="${3:-required}"
  if command -v "$cmd" >/dev/null 2>&1; then return 0; fi
  if [ "$level" = optional ]; then
    printf 'missing optional tool: %s (install: %s)\n' "$cmd" "$hint" >&2
    return 2
  fi
  printf 'missing required tool: %s (install: %s)\n' "$cmd" "$hint" >&2
  return 1
}

qg_finish() { # exit 1 if any gate failed
  if [ "$_QG_FAILED" -ne 0 ]; then
    echo "quality gates: FAILED" >&2
    exit 1
  fi
  echo "quality gates: OK"
}

qg_jscpd() { # <path...> — duplication gate via jscpd
  local gate=duplication
  if qg_gate_skipped "$gate"; then qg_skip "$gate" "QUALITY_SKIP"; return 0; fi
  local script_dir config
  script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
  config="$script_dir/jscpd.json"
  local runner=()
  if command -v jscpd >/dev/null 2>&1; then runner=(jscpd)
  elif [ "$QUALITY_AUTO_TOOLS" = "1" ] && command -v npx >/dev/null 2>&1; then runner=(npx --yes jscpd)
  else qg_skip "$gate" "install jscpd (npm i -g jscpd) or set QUALITY_AUTO_TOOLS=1"; return 0; fi
  if "${runner[@]}" --config "$config" --threshold "$QUALITY_DUP_MAX" "$@" >/dev/null 2>&1; then
    qg_pass "$gate"
  else
    qg_fail "$gate" "duplicated lines above ${QUALITY_DUP_MAX}% (run jscpd locally for the report)"
  fi
}
```

- [ ] **Step 2: Write `quality/jscpd.json` and `quality/README.md`**

`quality/jscpd.json`:
```json
{
  "threshold": 3,
  "reporters": ["console"],
  "ignore": [
    "**/node_modules/**", "**/target/**", "**/dist/**", "**/build/**",
    "**/.git/**", "**/coverage/**", "**/vendor/**", "**/__pycache__/**",
    "**/.venv/**", "**/Cargo.lock", "**/package-lock.json", "**/bun.lock*",
    "**/go.sum", "**/uv.lock"
  ],
  "absolute": true
}
```

`quality/README.md`: short usage doc — copy `quality/` into a repo (or call from infra checkout), run `quality/<lang>/quality.sh` from the repo root, env knobs table, gate list.

- [ ] **Step 3: Smoke-test the library**

```bash
cd infra && bash -c 'source quality/lib/common.sh; qg_need_tool bash "n/a" && qg_pass smoke; qg_need_tool definitely-not-a-tool "brew install x" optional; echo "rc=$?"'
```
Expected: `rc=2` printed path taken, `PASS smoke` line, no exit error.

- [ ] **Step 4: Commit**

```bash
git add quality/lib/common.sh quality/jscpd.json quality/README.md
git commit -m "feat(quality): shared gate library and duplication config"
```

---

### Task 2: Node.js + TypeScript script

**Files:**
- Create: `quality/node/quality.sh`
- Create: `quality/node/eslint.config.mjs` (template to copy into target repos)
- Test: fixture `/tmp/quality-fixtures/node`

**Interfaces:**
- Consumes: all of Task 1's common.sh API.
- Produces: `quality/node/quality.sh` — gates: `lint`, `cognitive-complexity`, `format`, `security`, `coverage`, `duplication`.

- [ ] **Step 1: Write the eslint flat-config template**

`quality/node/eslint.config.mjs` — eslint 9 flat config; plugins: `@typescript-eslint` (only applied to `**/*.ts`/`*.tsx`), `eslint-plugin-sonarjs`; key rule: `sonarjs/cognitive-complexity: ["error", 15]`; `prettier` handled separately (not via eslint). The script copies this into the target repo only if no eslint config exists and the target opts in via `--init-config`; default run expects the target's own config and FAILs `lint` if none (message: copy `quality/node/eslint.config.mjs`).

- [ ] **Step 2: Write `quality/node/quality.sh`**

Gate sequence (each guarded by `qg_gate_skipped`):
1. `lint` + `cognitive-complexity`: run `npx eslint .` (or the repo's package runner — detect `package.json` and use `npm exec eslint -- .`); both gates share the eslint run: PASS both if eslint exits 0 and config contains `sonarjs/cognitive-complexity`, else FAIL lint with output; if eslint config lacks the sonarjs rule, PASS lint but FAIL cognitive-complexity with message to enable it.
2. `format`: `npx prettier --check .` → PASS/FAIL.
3. `security`: detect lockfile (`package-lock.json`/`pnpm-lock.yaml`/`yarn.lock`) → `npm audit --audit-level=high` (pnpm/yarn equivalents); no lockfile → SKIP.
4. `coverage`: if `package.json` has a test script, run coverage via `npx c8 --check-coverage --lines "$QUALITY_COVERAGE_MIN" --reporter=text npm test` for `node --test` projects; if `vitest` in devDependencies use `npx vitest run --coverage --coverage.thresholds.lines=$QUALITY_COVERAGE_MIN`; if neither → SKIP with hint. FAIL under threshold.
5. `duplication`: `qg_jscpd src test .` (paths that exist).
End: `qg_finish`.

- [ ] **Step 3: Fixture test — clean project passes**

```bash
mkdir -p /tmp/quality-fixtures/node/src && cd /tmp/quality-fixtures/node
npm init -y && npm i -D eslint eslint-plugin-sonarjs prettier c8
cp $INFRA/quality/node/eslint.config.mjs .
cat > src/add.js <<'EOF'
export function add(a, b) { return a + b; }
EOF
cat > src/add.test.js <<'EOF'
import { test } from 'node:test';
import assert from 'node:assert';
import { add } from './add.js';
test('add', () => assert.equal(add(1, 2), 3));
EOF
node -e 'const p=require("./package.json");p.type="module";p.scripts.test="node --test src/";require("fs").writeFileSync("package.json",JSON.stringify(p,null,2))'
bash $INFRA/quality/node/quality.sh
```
($INFRA = absolute infra repo path.) Expected: all gates PASS or SKIP, exit 0.

- [ ] **Step 4: Fixture test — broken project fails**

Unformat a file (`printf 'export const x=1\n' > src/bad.js`) and add an untested function; re-run script. Expected: `format` and `coverage` FAIL, exit 1.

- [ ] **Step 5: Commit** `feat(quality): node.js + typescript gate script`

---

### Task 3: Deno script

**Files:**
- Create: `quality/deno/quality.sh`
- Test: fixture `/tmp/quality-fixtures/deno`

**Interfaces:**
- Consumes: Task 1 common.sh API.
- Produces: `quality/deno/quality.sh` — gates: `lint`, `cognitive-complexity`, `format`, `security`, `coverage`, `duplication`.

- [ ] **Step 1: Write the script**

Gates:
1. `lint`: `qg_need_tool deno` (required) → `deno lint`.
2. `cognitive-complexity`: if an eslint config exists in target → `npx eslint .` with sonarjs as in Task 2; else SKIP with message "deno lint has no cognitive-complexity rule; add eslint + eslint-plugin-sonarjs or accept the gap".
3. `format`: `deno fmt --check`.
4. `security`: if `osv-scanner` present → `osv-scanner --lockfile=deno.lock`; else SKIP with hint (documented gap: no deno audit).
5. `coverage`: `deno test --coverage=cov_profile` then `deno coverage cov_profile --lcov --output=cov.lcov`; parse line-rate with awk; FAIL if < `$QUALITY_COVERAGE_MIN`; cleanup cov dirs. If no test files → SKIP.
6. `duplication`: `qg_jscpd` on existing source paths.
End: `qg_finish`.

- [ ] **Step 2: Fixture — clean passes, broken fails**

```bash
mkdir -p /tmp/quality-fixtures/deno && cd /tmp/quality-fixtures/deno
cat > add.ts <<'EOF'
export function add(a: number, b: number): number { return a + b; }
EOF
cat > add_test.ts <<'EOF'
import { assertEquals } from "jsr:@std/assert";
import { add } from "./add.ts";
Deno.test("add", () => assertEquals(add(1, 2), 3));
EOF
bash $INFRA/quality/deno/quality.sh
```
Expected: lint/format PASS (run `deno fmt` first), coverage PASS, cognitive SKIP, exit 0. Then break formatting and confirm FAIL + exit 1.

- [ ] **Step 3: Commit** `feat(quality): deno gate script`

---

### Task 4: Bun script

**Files:**
- Create: `quality/bun/quality.sh`
- Test: fixture `/tmp/quality-fixtures/bun`

**Interfaces:**
- Consumes: Task 1 common.sh API, same eslint template as Task 2 (`quality/node/eslint.config.mjs`).
- Produces: `quality/bun/quality.sh` — gates: `lint`, `cognitive-complexity`, `format`, `security`, `coverage`, `duplication`.

- [ ] **Step 1: Write the script**

Gates: same as Node (Task 2) with bun substitutions:
1. `lint`/`cognitive-complexity`: `npx eslint .` with the sonarjs template (same rules as Task 2).
2. `format`: `npx prettier --check .`
3. `security`: `bun audit` if supported (`bun audit --help` probe; PASS on exit 0, FAIL on high/critical findings); else SKIP with hint.
4. `coverage`: `bun test --coverage --coverage-reporter=lcov` → parse `coverage/lcov.info` line-rate with awk; FAIL under threshold; SKIP if no tests.
5. `duplication`: `qg_jscpd`.
End: `qg_finish`.

- [ ] **Step 2: Fixture — clean passes, broken fails** (mirror Task 2 fixture with `bun init`-style `add.ts` + `add.test.ts` using `bun:test`).

- [ ] **Step 3: Commit** `feat(quality): bun gate script`

---

### Task 5: Rust script

**Files:**
- Create: `quality/rust/quality.sh`
- Create: `quality/rust/clippy.toml`
- Test: fixture `/tmp/quality-fixtures/rust`

**Interfaces:**
- Consumes: Task 1 common.sh API.
- Produces: `quality/rust/quality.sh` — gates: `lint`, `cognitive-complexity`, `format`, `security`, `coverage`, `duplication`.

- [ ] **Step 1: Write `quality/rust/clippy.toml`**

```toml
cognitive-complexity-threshold = 15
```

- [ ] **Step 2: Write the script**

Gates:
1. `lint`: `cargo clippy --all-targets -- -D warnings` (workspace-aware).
2. `cognitive-complexity`: requires `clippy::cognitive_complexity` enabled — script runs `cargo clippy --all-targets -- -D warnings -W clippy::cognitive_complexity` with `CLIPPY_CONF_DIR`/copied `clippy.toml` (copy template into target root if absent, note in output if it created it); FAIL on any cognitive_complexity lint hit.
3. `format`: `cargo fmt --check`.
4. `security`: `cargo audit` if installed, else `cargo install cargo-audit` hint → SKIP (or auto via QUALITY_AUTO_TOOLS).
5. `coverage`: `cargo llvm-cov --fail-under-lines "$QUALITY_COVERAGE_MIN"` (clean profile); missing tool → SKIP with `cargo install cargo-llvm-cov` hint.
6. `duplication`: `qg_jscpd src`.
End: `qg_finish`.

- [ ] **Step 3: Fixture — clean passes, broken fails**

```bash
cargo new /tmp/quality-fixtures/rust --name qfix && cd /tmp/quality-fixtures/rust
# add a #[test] in src/main.rs, run script; expect PASS/SKIP, exit 0
# then break fmt (cargo fmt then mangle) and drop the test → expect FAIL exit 1
```

- [ ] **Step 4: Commit** `feat(quality): rust gate script`

---

### Task 6: Go script

**Files:**
- Create: `quality/go/quality.sh`
- Create: `quality/go/.golangci.yml`
- Test: fixture `/tmp/quality-fixtures/go`

**Interfaces:**
- Consumes: Task 1 common.sh API.
- Produces: `quality/go/quality.sh` — gates: `lint`, `cognitive-complexity`, `format`, `security`, `coverage`, `duplication`.

- [ ] **Step 1: Write `quality/go/.golangci.yml`** (golangci-lint v2 config format)

```yaml
version: "2"
linters:
  enable:
    - gosec
    - gocognit
    - revive
    - staticcheck
  settings:
    gocognit:
      min-complexity: 15
```

- [ ] **Step 2: Write the script**

Gates:
1. `lint` + `cognitive-complexity` + `security` (gosec part): `golangci-lint run --config <template-or-repo-config>`; missing tool → FAIL with `go install github.com/golangci/golangci-lint/v2/cmd/golangci-lint@latest` hint. Prefer repo's own `.golangci.yml` if present; check it enables `gocognit`, else WARN within gate message.
2. `format`: `test -z "$(gofmt -l .)"` else FAIL listing files.
3. `coverage`: `go test ./... -coverprofile=cover.out`; `go tool cover -func=cover.out` total line ≥ threshold else FAIL; no test files → SKIP; remove cover.out after.
4. `security` (vulns): `govulncheck ./...` if installed else SKIP with hint (fold into the `security` gate alongside gosec).
5. `duplication`: `qg_jscpd` on `.` (jscpd ignores vendor via config).
End: `qg_finish`.

- [ ] **Step 3: Fixture — clean passes, broken fails**

```bash
mkdir -p /tmp/quality-fixtures/go && cd /tmp/quality-fixtures/go
go mod init qfix && cat > add.go / add_test.go (trivial), gofmt clean
bash $INFRA/quality/go/quality.sh   # expect PASS/SKIP exit 0
# mangle gofmt + remove test → FAIL exit 1
```

- [ ] **Step 4: Commit** `feat(quality): go gate script`

---

### Task 7: Python script

**Files:**
- Create: `quality/python/quality.sh`
- Create: `quality/python/ruff.toml`
- Test: fixture `/tmp/quality-fixtures/python`

**Interfaces:**
- Consumes: Task 1 common.sh API.
- Produces: `quality/python/quality.sh` — gates: `lint`, `cognitive-complexity`, `format`, `security`, `coverage`, `duplication`.

- [ ] **Step 1: Write `quality/python/ruff.toml`**

```toml
target-version = "py311"
[lint]
select = ["E", "F", "W", "I", "S", "C901"]
[lint.mccabe]
max-complexity = 15
```

- [ ] **Step 2: Write the script**

Gates:
1. `lint` + `cognitive-complexity` + `security` (S rules part): `ruff check --config <repo ruff.toml/pyproject or template>`; tool resolution: `ruff` → `uvx ruff` (if QUALITY_AUTO_TOOLS=1 or uvx present) → FAIL/SKIP with `uv tool install ruff` hint. Complexity via C901 is a documented cyclomatic proxy (script prints note).
2. `format`: `ruff format --check .`
3. `security` (deps): `pip-audit` if present else SKIP with `uv tool install pip-audit` hint.
4. `coverage`: if pytest present → `coverage run -m pytest` + `coverage report --fail-under="$QUALITY_COVERAGE_MIN"`; or `pytest --cov --cov-fail-under` if pytest-cov; no tests → SKIP.
5. `duplication`: `qg_jscpd` on source dirs.
End: `qg_finish`.

- [ ] **Step 3: Fixture — clean passes, broken fails** (trivial package + pytest test; run script; then break format + coverage → FAIL exit 1).

- [ ] **Step 4: Commit** `feat(quality): python gate script`

---

### Task 8: Docs, example workflow, README

**Files:**
- Create: `docs/quality-gates.md`
- Create: `examples/quality.yml`
- Modify: `README.md` (add quality/ bullet)
- Modify: `AGENTS.md`? No — AGENTS.md is ptrack-managed; leave it.

- [ ] **Step 1: Write `docs/quality-gates.md`** — table mapping each Sonar way gate → tool per language; known gaps (deno cognitive complexity, python cyclomatic proxy, whole-project vs new-code coverage); vendoring instructions.

- [ ] **Step 2: Write `examples/quality.yml`** — caller workflow template: matrix job per detected language running the vendored `quality/<lang>/quality.sh`, Linux-only, `paths` filter, concurrency cancellation (per repo CI-cost rules).

- [ ] **Step 3: Update `README.md`** — one bullet for `quality/` + `docs/quality-gates.md`.

- [ ] **Step 4: Commit** `docs(quality): gate mapping guide and example caller workflow`

---

### Task 9: End-to-end verification sweep

**Files:** none new (verification only).

- [ ] **Step 1:** `bash -n` syntax-check every `quality/**/*.sh`; `shellcheck` if available.
- [ ] **Step 2:** Re-run all six clean fixtures and all six broken fixtures; record the gate matrix outcome.
- [ ] **Step 3:** Verify jscpd gate fires: duplicate a 10-line block 4× in one fixture, expect `duplication` FAIL.
- [ ] **Step 4:** Commit any fixes; open PR per repo working agreements (branch first, squash merge, no AI attribution).

---

## Self-review notes

- Spec coverage: all 7 language targets map to Tasks 2–7 (Node+TS share Task 2 per spec); gates table fully covered; gaps documented in Tasks 3/7/8.
- Type consistency: common.sh API names (`qg_pass/qg_fail/qg_skip/qg_finish/qg_need_tool/qg_gate_skipped/qg_jscpd`) used identically across tasks; gate names (`lint cognitive-complexity format security coverage duplication`) consistent.
- Placeholders: fixture code abbreviated where trivial (Steps marked with actual commands); implementers must write real fixture files, not stubs that skip gates.

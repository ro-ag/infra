# Rust CI/CD guide — ro-ag fleet standard

How every Rust repo's GitHub Actions should be structured. Optimized for
runner-minute cost (**Linux 1x, Windows 2x, macOS 10x**) and wall-clock time.
Reusable workflow implementations live in `../.github/workflows/`; per-repo
audit in `./audit-2026-08.md`.

**This repo is private — it is the copy source, not a runtime dependency.**
Private repos in the fleet may call the reusable workflows directly
(`uses: ro-ag/infra/.github/workflows/rust-ci.yml@main`, after the one-time
access grant in §8.2). **Public repos must vendor**: copy the reusable
workflow files into the consumer's own `.github/workflows/` and call them
via local paths (`uses: ./.github/workflows/rust-ci.yml`). GitHub does not
allow public repositories to call reusable workflows in a private repo.
`ro-ag/pitch` is the working example of the vendored layout.

## 1. Triggers: one CI workflow, no post-merge duplicates

```yaml
on:
  push:
    branches: [main]
    paths-ignore: ['**/*.md', 'docs/**']
  pull_request:
    paths-ignore: ['**/*.md', 'docs/**']
  workflow_dispatch:

concurrency:
  group: ${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: ${{ github.event_name == 'pull_request' }}
```

- One workflow handles PR **and** main. Never a separate `main-merged.yml`
  that re-runs the PR suite (metro-2 anti-pattern).
- `cancel-in-progress` on PRs; keep release/nightly runs uncancellable.
- Path filters on CI only — never on release or nightly workflows.

## 2. Caching: the non-negotiables

- **`Swatinem/rust-cache@v2` in every job that runs cargo.** It caches
  `target/` + registry, keyed on `Cargo.lock`. Caching only
  `~/.cargo/registry` (native-score, parser) leaves the expensive part —
  compiling the dep graph — uncached.
- **Share cache keys between CI and release — byte-identical.** Use exactly
  the same `shared-key` expression (e.g. `rust-${{ runner.os }}`) in both
  workflows so the tag build starts warm from the main-branch run. Default
  rust-cache keys include the job id, so CI and release jobs do **not**
  share unless you set `shared-key`. Beware drift between contexts:
  `rust-${{ matrix.runner }}` in the release vs `rust-${{ runner.os }}`
  in CI evaluate to *different keys* (`rust-ubuntu-24.04` ≠ `rust-Linux`)
  and silently never share — this exact bug shipped once in this repo's
  own `rust-bin-release.yml`. One cache family per OS across CI, extended
  checks, and release; separate keys only for genuinely different
  instrumentation (e.g. coverage).
- **Never delete `$CARGO_HOME` or the sysroot in a release job** (brano). If
  disk is tight, do targeted cleanup of *build outputs you already
  packaged*, not the toolchain/registry — or accept a restore-only cache.
- C/C++ deps (verovio-rs): add `ccache`/`sccache` keyed per OS, including in
  the publish job.
- Tools installed with `cargo install` (cargo-audit, cargo-deny): cache
  `~/.cargo/bin` keyed on the tool version, or use the project's install
  action (`taiki-e/install-action`, `rustsec/audit-check`).
- apt/system deps: prefer a prebuilt container image if the list is long;
  otherwise accept the 1–2 min — caching apt is rarely worth the complexity.

## 3. Job staging: cheap Linux gate first

```yaml
jobs:
  lint:          # fmt + clippy, ubuntu only
  test:          # needs: lint — portable tests, ubuntu only
  test-windows:  # needs: [lint, test]
  test-macos:    # needs: [lint, test], gated (see §4)
```

- Lint and portable tests run on `ubuntu-latest` **nowhere else**.
- Expensive runners never start until the Linux gate passes (`needs:`).
- **Don't triple-compile**: `cargo clippy --workspace --all-targets`
  already type-checks everything. A separate `cargo check --all-targets` in
  the same job is pure waste; `cargo test` right after clippy is the only
  second compile you need.

## 4. OS gating policy

| Runner | When |
|---|---|
| Linux | every PR + main |
| Windows | PRs + main (never every feature-branch push) |
| macOS | main, nightly, releases, or PRs labeled `run-macos` |

```yaml
test-macos:
  if: >-
    github.ref == 'refs/heads/main' ||
    github.event_name == 'schedule' ||
    startsWith(github.ref, 'refs/tags/') ||
    contains(github.event.pull_request.labels.*.name, 'run-macos')
```

The label only fires a run if `pull_request` declares the trigger —
`types: [opened, synchronize, reopened, labeled]` — otherwise adding
`run-macos` to a PR starts nothing. And guard the job on the specific
label: without the `contains(...)` check every label change re-runs the
whole pipeline (pam).

Carve-out: on **public** repos (free minutes) the extended matrix's macOS
legs may run ungated on every PR — `examples/extended.yml` does this and
documents it in its header. On private repos the table above is the rule;
ungated macOS on PRs burns 10x minutes.

Sanitizers, Miri, fuzz, coverage: nightly `schedule` + `workflow_dispatch`,
not per-PR.

## 5. Toolchain: pin once, in the repo

Every repo gets a `rust-toolchain.toml`:

```toml
[toolchain]
channel = "1.97.0"
components = ["clippy", "rustfmt"]
profile = "minimal"
```

Workflows pass that channel to `dtolnay/rust-toolchain@master` explicitly —
the action does **not** read `rust-toolchain.toml` itself; extract the pin so
the file stays the single source:

```yaml
- name: Toolchain channel
  id: tc
  run: |
    ch=$(sed -n 's/^channel *= *"\(.*\)"/\1/p' rust-toolchain.toml 2>/dev/null || true)
    echo "channel=${ch:-stable}" >> "$GITHUB_OUTPUT"
- uses: dtolnay/rust-toolchain@master
  with:
    toolchain: ${{ steps.tc.outputs.channel }}
```

Never pin a version in YAML that can drift from the repo's pin (brano), and
never float on the runner image's stable (hexy, metro-2, parser).

## 6. The merge → release pipeline (the big one)

Goal: **a release re-validates metadata and republishes — it does not redo
CI.** Three patterns, pick per repo type.

### Pattern A — library crates (crates.io): trust the CI gate

Tag → validate → publish → GitHub release. Validation checks, it does not
re-test:

1. tag == `Cargo.toml` version,
2. tag commit is on `origin/main`,
3. the CI run for that exact commit succeeded:

```bash
sha=$(git rev-list -n 1 "$GITHUB_REF") # peel annotated tags to the commit
run_id=$(gh run list --workflow ci.yml --branch main --commit "$sha" \
  --status success --limit 1 --json databaseId --jq '.[0].databaseId')
[ -n "$run_id" ] || { echo "::error::no green CI run on $sha"; exit 1; }
```

If CI is green, publishing needs no test re-run. `cargo publish` always
repackages (unavoidable), so keep the publish job warm: rust-cache with the
same `shared-key` as CI + ccache if there are C/C++ deps. Poll the sparse
index instead of `sleep 30` between dependent crates:

```bash
until curl -sf "https://index.crates.io/${crate:0:2}/${crate:2:2}/$crate" \
  | grep -q "\"vers\":\"$version\""; do sleep 5; done
```

### Pattern B — apps with platform packages (Tauri, DMG, installers): reuse CI artifacts

For plain CLI binaries, `.github/workflows/rust-bin-release.yml` already implements
pattern C with native per-target builds and fail-closed macOS
signing/notarization (see `templates/pitch/` for a working consumer). The
artifact-reuse pattern below is for heavy app builds (Tauri, DMGs) where a
rebuild costs an hour:

Build packages **once**, on the main-branch CI run, and upload them as
artifacts. The release workflow downloads the artifacts from that run and
publishes them — no rebuild, no re-sign, no re-notarize:

```yaml
# in the release workflow
- name: Download packages from the main CI run
  run: |
    run_id=$(gh run list --branch main --workflow ci.yml \
      --commit "$GITHUB_SHA" --status success --limit 1 --json databaseId --jq '.[0].databaseId')
    gh run download "$run_id" --name packages
```

Caveat: signing/notarization secrets must then be available to the main CI
run. If you don't want that, the fallback is pattern C.

### Pattern C — minimum bar: warm rebuild

If artifacts can't be reused, at least make the tag build incremental:
identical `shared-key` rust-cache in CI and release, same toolchain, same
profile flags. A warm release build of a warm dep tree is minutes, not an
hour.

### What every release workflow still does itself

- Validate tag ↔ version ↔ changelog.
- Extract release notes from `CHANGELOG.md`.
- `gh release create` (prerelease when the version has a `-` suffix).
- `concurrency` per tag with `cancel-in-progress: false`.

## 7. Checklist for every repo

- [ ] One CI workflow: PR + `main` + dispatch, path filters, concurrency cancel
- [ ] `rust-toolchain.toml` pinned; workflows read it (no YAML version pins)
- [ ] `Swatinem/rust-cache@v2` in every cargo job, `shared-key` shared with release
- [ ] Lint + portable tests Linux-only; Windows/macOS `needs:` the Linux gate
- [ ] macOS gated to main/nightly/release/labeled-PRs; sanitizers/fuzz nightly
- [ ] No `check`+`clippy`+`build` triple compile in one job
- [ ] Release: metadata validation + CI-status check; tests not re-run
- [ ] Caller of a reusable release workflow declares `permissions: contents: write`
      **and `actions: read`** (for the CI-status gate) itself — a reusable call
      cannot elevate above the caller's token, and repos default to read-only
      tokens (release `startup_failure` / HTTP 403 otherwise)
- [ ] Release: artifacts reused (B) or warm cache (C) — never a cold full rebuild
- [ ] `cargo install` tools cached or installed via install actions
- [ ] `actionlint` clean on every workflow file (run it locally before pushing
      workflow changes — it catches most of §8)

## 8. Pitfalls — every one cost a real failed run (pitch v0.1.0 rollout)

Paid for in CI minutes while dogfooding this standard on `ro-ag/pitch`.
Check these first when a workflow misbehaves:

1. **Reusable workflows must live in `.github/workflows/`.** Any other path
   (`workflows/`, `ci/`) makes every caller run die instantly with
   "workflow file issue", on *every* push regardless of triggers.
2. **Cross-repo reusable calls from private repos need an access grant** on
   the called repo: Settings → Actions → Access → "accessible from
   repositories owned by the user", or
   `gh api -X PUT repos/OWNER/REPO/actions/permissions/access -f access_level=user`.
3. **`dtolnay/rust-toolchain` does not read `rust-toolchain.toml`.** An empty
   `toolchain` input fails at the parse step. Extract the channel from the
   file and pass it explicitly (§5).
4. **A reusable call cannot elevate permissions.** Repos default to a
   read-only `GITHUB_TOKEN`; the caller job must declare
   `permissions: contents: write` **and** `actions: read` (for the CI-status
   gate's `gh run list`, which 403s without it). Symptom: `startup_failure`.
5. **YAML: quote values containing `: `**. `name: Contract: exact set` and
   `signing-identity: Developer ID Application: Name (TEAM)` are parse
   errors. Run `actionlint` — it catches these and undefined matrix keys
   (`matrix.name` is not implicit).
6. **Windows steps default to pwsh.** Bash syntax fails with a ParserError —
   set `shell: bash` explicitly. It is per-step, not per-job: in a matrix
   that includes Windows, one step missing it fails even when every sibling
   step has it. And Git Bash has no `zip`; use `7z a -tzip`
   (preinstalled on Windows runners).
7. **macOS keychain cleanup must run even on failure, before the run
   ends.** It deletes the ephemeral keychain holding the `ci-notarize`
   notarytool profile; running it before notarization fails with
   `No Keychain password item found for profile: ci-notarize` (exit 69).
   Keep `if: always()` — it needn't be the literal last step;
   `upload-artifact` follows it in `rust-bin-release.yml`.
8. **`gh release create --verify-tag` needs a checkout.** The release job
   that only downloads artifacts fails with "not a git repository" without
   `actions/checkout`.
9. **A "skip CI for the release commit" guard conflicts with a CI-status
   release gate.** If the release validates that CI is green on the exact
   tag commit, skipping CI on `chore(release)` pushes makes every release
   fail validation. Pick one: either the gate trusts CI (no skip guard) or
   the release re-tests (guard allowed). We chose trust + no guard — the
   duplicate run on one commit per release is cheap insurance.
10. **`dtolnay/rust-toolchain` ignores `components` in
    `rust-toolchain.toml` too.** The repo file listing `clippy, rustfmt`
    does nothing for the action; the coverage job needs
    `components: llvm-tools-preview` passed explicitly or `cargo llvm-cov`
    has no `llvm-profdata` to work with.
11. **Annotated tags break `$GITHUB_SHA`-based checks.** For an annotated
    tag, `$GITHUB_SHA` is the *tag object*, not the commit — the ancestry
    check and the CI-status lookup both come up empty. Peel it once:
    `sha=$(git rev-list -n 1 "$GITHUB_REF")` works for annotated and
    lightweight tags alike. Both release workflows do this.

## 9. Measured results (pitch, 2026-08-24)

Zero-dependency CLI, but the structure is what scales:

| Run | What ran | Wall-clock |
|---|---|---|
| CI gate (PR/main) | fmt+clippy → test on Linux, Windows, macOS (gated) | ~1m20s |
| Extended matrix (public, free) | 16 jobs: 7-leg OS×toolchain, coverage, docs, pedantic, 5-target release dry-run, actionlint | ~2m |
| **Release v0.1.1** | validate → 5 native builds → codesign + **notarize** → checksums → GitHub release | **80s** |

Per-leg release times: validate 10s, linux 19–21s, windows 48–54s,
macOS incl. signing + notarization 45s, publish 7s.

Why it's fast:

- the release **re-runs nothing** — validate checks the green CI run on the
  tag commit instead of re-testing (pattern A);
- one cache family per OS (`shared-key: rust-${{ runner.os }}`) shared by
  CI, extended, and release — the tag build is fully incremental;
- no redundant compiles within jobs (clippy subsumes `check`);
- native runners only — no cross-compile setup, no QEMU.

Contrast with the audit baseline: `pam`'s release rebuilds + re-notarizes
everything CI already built (double full pipeline), and `parser`/`native-score`
recompile their entire dep trees on every run (registry-only caching).

## 10. Action pinning policy

- **Third-party actions pin to a full commit SHA with the tag in a trailing
  comment** — `dtolnay/rust-toolchain@<sha> # master 2026-08-05`. A tag is
  a movable pointer; a SHA is not. This is the supply-chain boundary.
- **`actions/*` stay at major tags** (checkout, upload/download-artifact) —
  first-party, same trust domain as the runner itself.
- **`.github/dependabot.yml` keeps the pins moving**: weekly
  `github-actions` bumps (plus the template's cargo deps) so pinned SHAs
  don't fossilize. Snippets in this guide show tags for readability; the
  workflow files carry the SHAs.
- **Enforcement option:** org Settings → Actions → require pinning actions
  to a full-length commit SHA — makes it policy instead of habit.

## 11. crates.io: prefer Trusted Publishing over CARGO_REGISTRY_TOKEN

A long-lived `CARGO_REGISTRY_TOKEN` secret is the liability it looks like.
crates.io Trusted Publishing exchanges a GitHub OIDC token for a
short-lived publish token via `rust-lang/crates-io-auth-action`
(`permissions: id-token: write` on the publish job) — nothing long-lived to
rotate or leak.

It requires per-crate configuration on the crates.io side (each crate names
the repo and workflow it trusts), so `CARGO_REGISTRY_TOKEN` remains the
bootstrap path for a crate's first publish. `rust-release.yml` still takes
the token; switch to OIDC once the crate exists on crates.io.

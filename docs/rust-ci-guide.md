# Rust CI/CD guide — ro-ag fleet standard

How every Rust repo's GitHub Actions should be structured. Optimized for
runner-minute cost (**Linux 1x, Windows 2x, macOS 10x**) and wall-clock time.
Reusable workflow implementations live in `../workflows/`; per-repo audit in
`./audit-2026-08.md`.

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
- **Share cache keys between CI and release.** Use the same `shared-key`
  (e.g. `rust-${{ runner.os }}`) in both workflows so the tag build starts
  warm from the main-branch run. Default rust-cache keys include the job
  id, so CI and release jobs do **not** share unless you set `shared-key`.
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

If you use the `labeled` trigger for this, guard the job on the specific
label — otherwise every label change re-runs the whole pipeline (pam).

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

Workflows then use `dtolnay/rust-toolchain@master` **with no version
input** — it reads the file. Never pin a version in YAML that can drift
from the repo's pin (brano), and never float on the runner image's stable
(hexy, metro-2, parser).

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
gh api "repos/$GITHUB_REPOSITORY/commits/$GITHUB_SHA/check-runs" \
  --jq '[.check_runs[] | select(.name == "ci") | .conclusion] | all(. == "success")'
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

For plain CLI binaries, `workflows/rust-bin-release.yml` already implements
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
- [ ] Release: artifacts reused (B) or warm cache (C) — never a cold full rebuild
- [ ] `cargo install` tools cached or installed via install actions

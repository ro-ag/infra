# infra

Shared infrastructure for the `ro-ag` Rust fleet: CI/CD standards and
reusable GitHub Actions workflows.

- `docs/rust-ci-guide.md` — the fleet standard: triggers, caching, OS
  gating, the merge → release pipeline that doesn't redo CI, and a
  pitfalls section bought with real failed runs.
- `docs/audit-2026-08.md` — per-repo audit findings and quick wins.
- `.github/workflows/rust-ci.yml` — reusable CI (`workflow_call`): Linux
  lint+test gate, optional Windows/macOS legs, `rust-cache` throughout.
- `.github/workflows/rust-release.yml` — reusable library release: tag/CI
  validation → crates.io publish → GitHub release, no re-tested CI.
- `.github/workflows/rust-bin-release.yml` — reusable binary release: 5
  native builds (linux amd64/arm64, windows amd64/arm64, macOS arm64) → macOS
  codesign + notarize (fail-closed, via the apple-developer-signing
  bundle) → checksummed GitHub release.
- `.github/workflows/rust-nightly.yml` — reusable nightly hygiene:
  `cargo audit` + MSRV check.
- `templates/pitch/` — a complete reference app (`pitch`, a
  note/frequency/MIDI CLI) with fleet-standard CI + release callers; copy
  it to bootstrap a new repo. Dogfooded end-to-end as
  [ro-ag/pitch](https://github.com/ro-ag/pitch) — see its signed v0.1.0
  release.
- `examples/` — caller workflows to copy into each repo: `ci.yml`,
  `release.yml`, `bin-release.yml` (binary-release caller), `nightly.yml`,
  `extended.yml` (optional maximal matrix for public/free-tier repos), and
  `quality.yml` (pre-Sonar quality gates).
- `quality/` — SonarQube "Sonar way"-parity quality gates, run locally or in
  CI before Sonar blocks a merge: `python3 quality/quality.py <lang>` for
  node, typescript, deno, bun, rust, go, python (coverage ≥ 80%, duplication
  ≤ 3%, cognitive complexity ≤ 15, lint, format, security). See
  `docs/quality-gates.md` for the gate → tool mapping and known gaps.

This repo is **private**: it is the copy source for the fleet, not a
runtime dependency. Private repos may call the reusable workflows directly
(`uses: ro-ag/infra/.github/workflows/rust-ci.yml@<sha> # main`, after a
one-time access grant — the SHA pin is required once `sha_pinning_required`
is on, see `docs/rust-ci-guide.md` §10). Public repos must vendor the
workflow files into their own `.github/workflows/` and call them via local
`./` paths — `ro-ag/pitch`
(public, the fleet experiment) is the working example.

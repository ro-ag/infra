# infra

Shared infrastructure for the `ro-ag` Rust fleet: CI/CD standards and
reusable GitHub Actions workflows.

- `docs/rust-ci-guide.md` — the fleet standard: triggers, caching, OS
  gating, and the merge → release pipeline that doesn't redo CI.
- `docs/audit-2026-08.md` — per-repo audit findings and quick wins.
- `workflows/rust-ci.yml` — reusable CI (`workflow_call`): Linux lint+test
  gate, optional Windows/macOS legs, `rust-cache` throughout.
- `workflows/rust-release.yml` — reusable library release: tag/CI
  validation → crates.io publish → GitHub release, no re-tested CI.
- `workflows/rust-bin-release.yml` — reusable binary release: 4 native
  builds (linux amd64/arm64, windows amd64, macOS arm64) → macOS codesign +
  notarize (fail-closed, via the apple-developer-signing bundle) →
  checksummed GitHub release.
- `templates/pitch/` — a complete reference app (`pitch`, a
  note/frequency/MIDI CLI) with fleet-standard CI + release callers; copy
  it to bootstrap a new repo.
- `examples/` — caller workflows to copy into each repo.

Repos call the reusable workflows with
`uses: ro-ag/infra/workflows/rust-ci.yml@main`.

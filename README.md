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
- `examples/` — caller workflows to copy into each repo.

Repos call the reusable workflows with
`uses: ro-ag/infra/workflows/rust-ci.yml@main`.

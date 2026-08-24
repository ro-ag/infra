# pitch

Convert between musical notes, frequencies, and MIDI note numbers.
Zero dependencies, single static binary, equal temperament with a
configurable A4 reference.

```console
$ pitch A4
A4 -> 440.00 Hz (MIDI 69)

$ pitch 445
445.00 Hz -> A4 (MIDI 69), +19.6 cents

$ pitch --a4 432 C4
C4 -> 256.87 Hz (MIDI 60)
```

Notes accept sharps and flats (`C#4`, `Bb3`, `F-1`); frequencies give the
nearest note plus the cents offset.

## Install

Download the archive for your platform from
[Releases](../../releases) (Linux amd64/arm64, Windows amd64/arm64, macOS arm64 —
signed and notarized), unpack, put `pitch` on your `PATH`.

## Build

```sh
cargo build --release
cargo test
```

## Release process

CI and release are thin callers of the shared pipelines in
[ro-ag/infra](../..):

- `.github/workflows/ci.yml` → `ro-ag/infra/.github/workflows/rust-ci.yml`
  (Linux gate, Windows on PRs+main, macOS gated to main/manual/`run-macos`)
- `.github/workflows/release.yml` → `ro-ag/infra/.github/workflows/rust-bin-release.yml`
  (tag `v*` → validate → 4 native builds → macOS codesign + notarize →
  checksummed GitHub release)

To cut a release: bump `version` in `Cargo.toml`, add a `## [X.Y.Z]` section
to `CHANGELOG.md`, land it on `main` as `chore(release): vX.Y.Z`, wait for
green CI, then `git tag vX.Y.Z && git push origin vX.Y.Z`.

## Use this as a template

Copy this directory to a new repo, then:

1. rename the crate (`Cargo.toml`, `bin:` in `release.yml`),
2. run `apple-developer-signing/setup-github-secrets.sh owner/repo`,
3. push — CI is already fleet-standard.

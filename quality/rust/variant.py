"""Rust variant — clippy (+cognitive_complexity via clippy.toml), rustfmt,
cargo audit, cargo llvm-cov coverage, jscpd duplication."""

from __future__ import annotations

RUSTUP_HINT = "https://rustup.rs (rustup install stable)"


def _need_cargo(qg, gate: str) -> bool:
    if qg.need_tool("cargo", RUSTUP_HINT):
        return True
    qg.fail(gate, "missing required tool: cargo (install: https://rustup.rs)")
    return False


def _lint(qg) -> None:
    if not _need_cargo(qg, "lint"):
        return
    qg.run(["cargo", "clippy", "--all-targets", "--", "-D", "warnings"], gate="lint",
           fail_msg="clippy warnings (install clippy if missing: rustup component add clippy)")


def _cognitive(qg) -> None:
    gate = "cognitive-complexity"
    if not _need_cargo(qg, gate):
        return
    target_conf = qg.root / "clippy.toml"
    note = "using existing clippy.toml"
    if not target_conf.is_file():
        template = qg.variant_dir / "clippy.toml"
        if not template.is_file():
            qg.fail(gate, "no clippy.toml in repo root and quality/rust/clippy.toml template not found")
            return
        text = template.read_text().replace(
            "cognitive-complexity-threshold = 15",
            f"cognitive-complexity-threshold = {qg.cognitive_max}")
        target_conf.write_text(text)
        note = f"copied clippy.toml (cognitive-complexity-threshold = {qg.cognitive_max}) to repo root"
    if qg.run(["cargo", "clippy", "--all-targets", "--", "-W", "clippy::cognitive_complexity"]) == 0:
        qg.ok(gate, note)
    else:
        qg.fail(gate, "cognitive complexity above clippy.toml threshold")


def _format(qg) -> None:
    if not _need_cargo(qg, "format"):
        return
    qg.run(["cargo", "fmt", "--check"], gate="format",
           fail_msg="rustfmt violations (fix: cargo fmt; install: rustup component add rustfmt)")


def _security(qg) -> None:
    if not qg.need_tool("cargo-audit", "cargo install cargo-audit", required=False):
        qg.skip("security", "cargo install cargo-audit")
        return
    if not (qg.root / "Cargo.lock").is_file():
        qg.skip("security", "no Cargo.lock")
        return
    qg.run(["cargo", "audit"], gate="security",
           fail_msg="known vulnerabilities in dependencies (cargo audit)")


def _coverage(qg) -> None:
    if not qg.need_tool("cargo-llvm-cov", "cargo install cargo-llvm-cov", required=False):
        qg.skip("coverage", "cargo install cargo-llvm-cov")
        return
    qg.run(["cargo", "llvm-cov", "--all-targets", "--fail-under-lines", str(qg.coverage_min)],
           gate="coverage", fail_msg=f"line coverage below {qg.coverage_min}%")


def gates(qg) -> list[tuple[str, object]]:
    return [
        ("lint", lambda: _lint(qg)),
        ("cognitive-complexity", lambda: _cognitive(qg)),
        ("format", lambda: _format(qg)),
        ("security", lambda: _security(qg)),
        ("coverage", lambda: _coverage(qg)),
        ("duplication", None),
    ]

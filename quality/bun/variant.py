"""Bun variant — eslint (+sonarjs cognitive complexity), prettier, bun audit,
bun test coverage, jscpd duplication."""

from __future__ import annotations

import shutil
import subprocess

import jscommon

BUN_HINT = "curl -fsSL https://bun.sh/install | bash"


def _security(qg) -> None:
    if not qg.need_tool("bun", BUN_HINT):
        qg.fail("security", f"missing required tool: bun (install: {BUN_HINT})")
        return
    probe = subprocess.run(["bun", "audit", "--help"], capture_output=True, text=True)
    if probe.returncode != 0:
        qg.skip("security", f"this bun version has no 'bun audit' — upgrade bun ({BUN_HINT})")
        return
    if not any((qg.root / f).is_file() for f in ("bun.lock", "bun.lockb", "package-lock.json")):
        qg.skip("security", "no lockfile (bun.lock/bun.lockb)")
        return
    qg.run(["bun", "audit", "--audit-level", "high"], gate="security",
           fail_msg="high/critical vulnerabilities in dependencies (bun audit)")


def _coverage(qg) -> None:
    if not qg.need_tool("bun", BUN_HINT):
        qg.fail("coverage", f"missing required tool: bun (install: {BUN_HINT})")
        return
    if not qg.find("*.test.ts", "*.test.tsx", "*.test.js", "*.test.jsx"):
        qg.skip("coverage", "no test files (*.test.ts/*.test.js)")
        return
    help_out = subprocess.run(["bun", "test", "--help"], capture_output=True, text=True).stdout
    if "--coverage-reporter" not in help_out:
        qg.skip("coverage", "this bun version lacks 'bun test --coverage-reporter=lcov' — upgrade bun")
        return
    cov_dir = qg.root / ".quality-coverage"
    shutil.rmtree(cov_dir, ignore_errors=True)
    try:
        rc = qg.run(["bun", "test", "--coverage", "--coverage-reporter=lcov",
                     f"--coverage-dir={cov_dir.name}"])
        lcov = cov_dir / "lcov.info"
        if rc != 0 or not lcov.is_file():
            qg.fail("coverage", "bun test --coverage failed (run 'bun test --coverage' to see errors)")
            return
        rate = qg.lcov_line_rate(lcov)
        if rate < qg.coverage_min:
            qg.fail("coverage", f"line coverage {rate}% < {qg.coverage_min}%")
        else:
            qg.ok("coverage", f"line coverage {rate}% >= {qg.coverage_min}%")
    finally:
        shutil.rmtree(cov_dir, ignore_errors=True)


def gates(qg) -> list[tuple[str, object]]:
    return [
        *jscommon.eslint_gates(qg, "quality/bun/eslint.config.mjs"),
        jscommon.prettier_gate(qg),
        ("security", lambda: _security(qg)),
        ("coverage", lambda: _coverage(qg)),
        ("duplication", None),
    ]

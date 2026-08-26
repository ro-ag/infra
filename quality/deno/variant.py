"""Deno variant — deno lint, deno fmt, osv-scanner security, deno coverage,
jscpd duplication.

Known gaps (documented in docs/quality-gates.md):
- deno lint has no cognitive-complexity rule → eslint+sonarjs only when the
  target repo already carries an eslint config, else SKIP.
- deno has no audit command → osv-scanner against deno.lock, else SKIP.
"""

from __future__ import annotations

import shutil

import jscommon

# jscpd v5 needs explicit formats; it silently skips extensions it doesn't auto-detect.
DUP_FORMATS = "typescript,tsx,javascript,jsx"

DENO_HINT = "curl -fsSL https://deno.land/install.sh | sh"


def _lint(qg) -> None:
    if not qg.need_tool("deno", DENO_HINT):
        qg.fail("lint", f"install deno: {DENO_HINT}")
        return
    qg.run(["deno", "lint"], gate="lint", fail_msg="deno lint found issues")


def _cognitive(qg) -> None:
    gate = "cognitive-complexity"
    if jscommon.find_eslint_config(qg) is None:
        qg.skip(gate, "deno lint has no cognitive-complexity rule; "
                      "add eslint + eslint-plugin-sonarjs or accept the gap")
        return
    eslint = jscommon.local_bin(qg, "eslint")
    if eslint is None:
        qg.skip(gate, "eslint config present but eslint not installed "
                      "(npm i -D eslint eslint-plugin-sonarjs) or set QUALITY_AUTO_TOOLS=1")
        return
    qg.run(eslint + ["."], gate=gate,
           fail_msg=f"eslint (sonarjs) found issues (threshold {qg.cognitive_max})")


def _format(qg) -> None:
    if not qg.need_tool("deno", DENO_HINT):
        qg.fail("format", f"install deno: {DENO_HINT}")
        return
    qg.run(["deno", "fmt", "--check"], gate="format",
           fail_msg="deno fmt --check found unformatted files")


def _security(qg) -> None:
    if not (qg.root / "deno.lock").is_file():
        qg.skip("security", "no deno.lock (nothing to audit)")
        return
    if not qg.need_tool("osv-scanner", "https://google.github.io/osv-scanner/installation/", required=False):
        qg.skip("security", "install osv-scanner; deno has no audit command")
        return
    qg.run(["osv-scanner", "--lockfile=deno.lock"], gate="security",
           fail_msg="osv-scanner found vulnerabilities in deno.lock")


def _coverage(qg) -> None:
    if not qg.have("deno"):
        qg.fail("coverage", f"install deno: {DENO_HINT}")
        return
    if not qg.find("*_test.ts"):
        qg.skip("coverage", "no *_test.ts files")
        return
    profile, lcov = qg.root / "cov_profile", qg.root / "cov.lcov"
    shutil.rmtree(profile, ignore_errors=True)
    lcov.unlink(missing_ok=True)
    try:
        if qg.run(["deno", "test", f"--coverage={profile.name}"]) != 0:
            qg.fail("coverage", "deno test failed")
            return
        # deno coverage exits 1 and writes nothing when no source files were
        # covered at all — treat that as 0% rather than a script error.
        rc = qg.run(["deno", "coverage", profile.name, "--lcov", f"--output={lcov.name}"])
        rate = qg.lcov_line_rate(lcov) if rc == 0 and lcov.is_file() else 0
        if rate < qg.coverage_min:
            qg.fail("coverage", f"line coverage {rate}% < {qg.coverage_min}%")
        else:
            qg.ok("coverage", f"line coverage {rate}% >= {qg.coverage_min}%")
    finally:
        shutil.rmtree(profile, ignore_errors=True)
        lcov.unlink(missing_ok=True)


def gates(qg) -> list[tuple[str, object]]:
    return [
        ("lint", lambda: _lint(qg)),
        ("cognitive-complexity", lambda: _cognitive(qg)),
        ("format", lambda: _format(qg)),
        ("security", lambda: _security(qg)),
        ("coverage", lambda: _coverage(qg)),
        ("duplication", None),
    ]

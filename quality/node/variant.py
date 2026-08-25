"""Node.js variant — eslint (+sonarjs cognitive complexity), prettier,
npm audit, c8/vitest coverage, jscpd duplication."""

from __future__ import annotations

import jscommon


def _security(qg) -> None:
    if not (qg.root / "package-lock.json").is_file() and not (qg.root / "npm-shrinkwrap.json").is_file():
        qg.skip("security", "no npm lockfile — nothing to audit")
        return
    if not qg.need_tool("npm", "install Node.js (bundles npm)"):
        qg.fail("security", "missing required tool: npm")
        return
    qg.run(["npm", "audit", "--audit-level=high"], gate="security",
           fail_msg="npm audit found high/critical vulnerabilities")


def _coverage(qg) -> None:
    pkg = qg.package_json()
    if not pkg:
        qg.skip("coverage", "no package.json")
        return
    if (pkg.get("devDependencies") or {}).get("vitest"):
        vitest = jscommon.local_bin(qg, "vitest")
        if vitest is None:
            qg.fail("coverage", "missing required tool: vitest "
                                "(install: npm install --save-dev vitest @vitest/coverage-v8)")
            return
        qg.run(vitest + ["run", "--coverage", f"--coverage.thresholds.lines={qg.coverage_min}"],
               gate="coverage", fail_msg=f"line coverage below {qg.coverage_min}%")
        return
    if (pkg.get("scripts") or {}).get("test"):
        c8 = jscommon.local_bin(qg, "c8")
        if c8 is None:
            qg.fail("coverage", "missing required tool: c8 (install: npm install --save-dev c8)")
            return
        qg.run(c8 + ["--check-coverage", "--lines", str(qg.coverage_min), "--reporter=text",
                     "npm", "test"],
               gate="coverage", fail_msg=f"line coverage below {qg.coverage_min}%")
        return
    qg.skip("coverage", "no test script in package.json")


def gates(qg) -> list[tuple[str, object]]:
    return [
        *jscommon.eslint_gates(qg, "quality/node/eslint.config.mjs"),
        jscommon.prettier_gate(qg),
        ("security", lambda: _security(qg)),
        ("coverage", lambda: _coverage(qg)),
        ("duplication", None),  # engine handles it
    ]

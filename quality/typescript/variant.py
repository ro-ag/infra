"""TypeScript variant — toolchain chosen by project shape:

- Deno-style project (deno.json/deno.jsonc present): delegate to the deno
  variant (deno lint / fmt / test --coverage).
- Node-style project (tsconfig.json / .ts files): `tsc --noEmit` + eslint
  (+sonarjs cognitive complexity) + prettier + npm audit + vitest/c8.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import jscommon

# jscpd v5 needs explicit formats; it silently skips extensions it doesn't auto-detect.
DUP_FORMATS = "typescript,tsx"


def _load(name: str):
    path = Path(__file__).resolve().parent.parent / name / "variant.py"
    spec = importlib.util.spec_from_file_location(f"qg_variant_{name}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _lint(qg, eslint_lint) -> None:
    """tsc --noEmit first (when a tsconfig exists), then eslint."""
    if (qg.root / "tsconfig.json").is_file():
        tsc = jscommon.local_bin(qg, "tsc")
        if tsc is None:
            qg.fail("lint", "missing required tool: typescript "
                            "(install: npm install --save-dev typescript)")
            return
        proc = subprocess.run(tsc + ["--noEmit"], cwd=qg.root, capture_output=True, text=True)
        if proc.returncode != 0:
            qg.fail("lint", "tsc --noEmit type errors")
            out = (proc.stdout + proc.stderr).strip()
            if out:
                print("\n".join(out.splitlines()[-20:]), file=sys.stderr)
            return
    eslint_lint()


def gates(qg) -> list[tuple[str, object]]:
    if (qg.root / "deno.json").is_file() or (qg.root / "deno.jsonc").is_file():
        return _load("deno").gates(qg)

    if not (qg.root / "tsconfig.json").is_file() and not qg.find("*.ts", "*.tsx"):
        def no_ts() -> None:
            qg.fail("lint", "no deno.json, tsconfig.json, or .ts files — "
                            "use the node variant for plain JS")

        rest = ("cognitive-complexity", "format", "security", "coverage")
        return [("lint", no_ts),
                *[(name, (lambda n=name: qg.skip(n, "not a TypeScript project"))) for name in rest],
                ("duplication", None)]

    js_gates = jscommon.eslint_gates(qg, "quality/typescript/eslint.config.mjs")
    eslint_lint, cognitive = js_gates[0][1], js_gates[1][1]
    node_rest = _load("node").gates(qg)[2:]  # format, security, coverage, duplication
    return [
        ("lint", lambda: _lint(qg, eslint_lint)),
        ("cognitive-complexity", cognitive),
        *node_rest,
    ]

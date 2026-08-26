"""Python variant (uv-first) — ruff (lint + C901 complexity + bandit S
security rules), ruff format, pip-audit, coverage.py/pytest-cov, jscpd
duplication.

Toolchain: uv. Tools resolve from PATH first, then via `uvx` (uv's ephemeral
runner — caches outside the repo, installs nothing into it). Tests prefer the
project's own `.venv`.

Note: Python has no maintained cognitive-complexity linter; ruff C901
(mccabe cyclomatic complexity) at threshold 15 is the documented proxy.
"""

from __future__ import annotations

import shutil
import subprocess
import sys

# jscpd v5 needs explicit formats; it silently skips extensions it doesn't auto-detect.
DUP_FORMATS = "python"

RUFF_HINT = "uv tool install ruff"


def _resolve_ruff(qg) -> list[str] | None:
    if qg.have("ruff"):
        return ["ruff"]
    if qg.have("uvx"):
        return ["uvx", "ruff"]
    return None


def _venv_bin(qg, name: str) -> list[str] | None:
    """An executable from the target repo's own .venv, if present."""
    candidate = qg.root / ".venv" / "bin" / name
    return [str(candidate)] if candidate.is_file() else None


def _target_config(qg) -> str | None:
    for name in ("ruff.toml", ".ruff.toml"):
        if (qg.root / name).is_file():
            return name
    pyproject = qg.root / "pyproject.toml"
    if pyproject.is_file() and "\n[tool.ruff" in "\n" + pyproject.read_text():
        return "pyproject.toml"
    return None


def _config_args(qg, config: str | None) -> list[str]:
    """Use the vendored template unless the target repo has its own ruff config."""
    if config is not None:
        return []
    args = ["--config", str(qg.variant_dir / "ruff.toml")]
    if qg.cognitive_max != 15:
        args += ["--config", f"lint.mccabe.max-complexity={qg.cognitive_max}"]
    return args


def _lint(qg, ruff, config) -> None:
    detail = "" if config else f" (using {qg.variant_dir / 'ruff.toml'} — no repo ruff config found)"
    qg.run(ruff + ["check", *_config_args(qg, config), "."], gate="lint",
           fail_msg=f"fix ruff findings{detail}")


def _cognitive(qg, ruff, config) -> None:
    gate = "cognitive-complexity"
    if config and "C901" not in (qg.root / config).read_text():
        qg.fail(gate, f'{config} does not enable C901 (add "C901" to lint.select '
                      "and [lint.mccabe] max-complexity = 15)")
        return
    print(f"note: ruff C901 (cyclomatic complexity, max {qg.cognitive_max}) "
          "proxies SonarQube cognitive complexity", file=sys.stderr)
    qg.run(ruff + ["check", *_config_args(qg, config), "--select", "C901", "."], gate=gate,
           fail_msg=f"complexity over {qg.cognitive_max}")


def _format(qg, ruff, config) -> None:
    qg.run(ruff + ["format", "--check", "."], gate="format",
           fail_msg=f"run: {' '.join(ruff)} format .")


def _security(qg) -> None:
    pip_audit = ["pip-audit"] if qg.have("pip-audit") else None
    if pip_audit is None and qg.have("uvx"):
        pip_audit = ["uvx", "pip-audit"]
    if pip_audit is None:
        qg.skip("security", "pip-audit missing (install: uv tool install pip-audit); "
                            "bandit S rules run via ruff in the lint gate")
        return
    cmd = pip_audit + (["-r", "requirements.txt"]
                       if (qg.root / "requirements.txt").is_file() else [])
    qg.run(cmd, gate="security", fail_msg="fix vulnerable dependencies (pip-audit)")


def _pytest_cmd(qg) -> list[str] | None:
    venv = _venv_bin(qg, "pytest")
    if venv:
        return venv
    if qg.have("pytest"):
        return ["pytest"]
    if qg.have("python3"):
        probe = subprocess.run(["python3", "-m", "pytest", "--version"], capture_output=True)
        if probe.returncode == 0:
            return ["python3", "-m", "pytest"]
    return None


def _coverage_cmd(qg) -> list[str] | None:
    venv = _venv_bin(qg, "coverage")
    if venv:
        return venv
    if qg.have("coverage"):
        return ["coverage"]
    if qg.have("python3"):
        probe = subprocess.run(["python3", "-m", "coverage", "--version"], capture_output=True)
        if probe.returncode == 0:
            return ["python3", "-m", "coverage"]
    return None


def _coverage(qg) -> None:
    if not qg.find("test_*.py", "*_test.py"):
        qg.skip("coverage", "no test files found")
        return
    pytest = _pytest_cmd(qg)
    if pytest is None:
        qg.fail("coverage", "tests found but pytest missing (install: uv pip install pytest)")
        return
    coverage = _coverage_cmd(qg)
    if coverage is not None:
        try:
            if qg.run(coverage + ["run", "-m", "pytest"]) != 0:
                qg.fail("coverage", "pytest run failed")
                return
            qg.run(coverage + ["report", f"--fail-under={qg.coverage_min}"], gate="coverage",
                   fail_msg=f"line coverage below {qg.coverage_min}%")
        finally:
            (qg.root / ".coverage").unlink(missing_ok=True)
        return
    # Fall back to pytest-cov if installed.
    help_out = subprocess.run(pytest + ["--help"], capture_output=True, text=True).stdout
    if "--cov" in help_out:
        qg.run(pytest + ["--cov", f"--cov-fail-under={qg.coverage_min}"], gate="coverage",
               fail_msg=f"line coverage below {qg.coverage_min}%")
        return
    qg.skip("coverage", "coverage/pytest-cov missing (install: uv pip install coverage pytest-cov)")


def gates(qg) -> list[tuple[str, object]]:
    ruff = _resolve_ruff(qg)
    config = _target_config(qg)
    if ruff is None:
        def missing(name):
            return lambda: qg.fail(name, f"missing required tool: ruff (install: {RUFF_HINT})")

        return [("lint", missing("lint")),
                ("cognitive-complexity", missing("cognitive-complexity")),
                ("format", missing("format")),
                ("security", lambda: _security(qg)),
                ("coverage", lambda: _coverage(qg)),
                ("duplication", None)]
    return [
        ("lint", lambda: _lint(qg, ruff, config)),
        ("cognitive-complexity", lambda: _cognitive(qg, ruff, config)),
        ("format", lambda: _format(qg, ruff, config)),
        ("security", lambda: _security(qg)),
        ("coverage", lambda: _coverage(qg)),
        ("duplication", None),
    ]

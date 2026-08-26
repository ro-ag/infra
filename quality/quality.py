#!/usr/bin/env python3
"""quality.py — SonarQube "Sonar way"-parity quality gates, primary script.

Run from the TARGET repo root (the repo being checked):

    python3 quality/quality.py <lang>

Languages (variants): node, typescript, deno, bun, rust, go, python.
Each variant lives in quality/<lang>/variant.py next to that language's
config templates (eslint.config.mjs, clippy.toml, .golangci.yml, ruff.toml).

Gates (Sonar way defaults): lint (code smells/bugs), cognitive-complexity
(<= 15 per function), format, security, coverage (>= 80% lines),
duplication (<= 3%). Every gate reports PASS / FAIL / SKIP; the script
exits 1 if any gate FAILs. Nothing is ever installed into the target repo.

Environment knobs:
    QUALITY_COVERAGE_MIN   minimum line coverage %        (default 80)
    QUALITY_DUP_MAX        max duplicated lines %         (default 3)
    QUALITY_COGNITIVE_MAX  max cognitive complexity       (default 15)
    QUALITY_SKIP           comma-separated gates to skip (e.g. "coverage,security")
    QUALITY_AUTO_TOOLS     1 allows ephemeral runners (npx, uvx) (default 0)

Stdlib only; requires Python 3.9+.
"""

from __future__ import annotations

import argparse
import fnmatch
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

JSCPD_IGNORE = ",".join([
    "**/node_modules/**", "**/target/**", "**/dist/**", "**/build/**",
    "**/coverage/**", "**/cov_profile/**", "**/vendor/**",
    "**/__pycache__/**", "**/.venv/**",
    "**/package-lock.json", "**/npm-shrinkwrap.json", "**/yarn.lock",
    "**/pnpm-lock.yaml", "**/bun.lock", "**/bun.lockb", "**/deno.lock",
    "**/Cargo.lock", "**/go.sum", "**/uv.lock", "**/poetry.lock",
    "**/Pipfile.lock", "**/Gemfile.lock", "**/composer.lock", "**/cover.out",
])

PRUNE_DIRS = {".git", "node_modules", "target", "vendor", "__pycache__", ".venv", "dist", "build"}

ESLINT_CONFIG_NAMES = [
    "eslint.config.mjs", "eslint.config.js", "eslint.config.cjs", "eslint.config.ts",
    ".eslintrc", ".eslintrc.js", ".eslintrc.cjs", ".eslintrc.json",
    ".eslintrc.yml", ".eslintrc.yaml",
]


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, "") or default)
    except ValueError:
        return default


class QG:
    """Gate engine passed to every variant. Variants report through this."""

    def __init__(self, lang: str, variant_dir: Path, root: Path):
        self.lang = lang
        self.variant_dir = variant_dir  # quality/<lang>/ — config templates live here
        self.root = root                # target repo root (cwd)
        self.coverage_min = _env_int("QUALITY_COVERAGE_MIN", 80)
        self.dup_max = _env_int("QUALITY_DUP_MAX", 3)
        self.cognitive_max = _env_int("QUALITY_COGNITIVE_MAX", 15)
        # SonarQube CPD counts a duplicated block only at >= 100 identical
        # tokens over >= 10 lines (non-Java languages); jscpd's own defaults
        # (50 tokens / 5 lines) are stricter than Sonar, so align them.
        self.dup_min_tokens = _env_int("QUALITY_DUP_MIN_TOKENS", 100)
        self.dup_min_lines = _env_int("QUALITY_DUP_MIN_LINES", 10)
        self.dup_formats: str | None = None  # set from the variant's DUP_FORMATS
        self.skip_gates = {g.strip() for g in os.environ.get("QUALITY_SKIP", "").split(",") if g.strip()}
        self.auto_tools = os.environ.get("QUALITY_AUTO_TOOLS", "0") == "1"
        self.failed = False

    # --- reporting -----------------------------------------------------------

    def _report(self, status: str, gate: str, detail: str = "") -> None:
        print(f"{status:<4}  {gate:<22} {detail}")

    def ok(self, gate: str, detail: str = "") -> None:
        self._report("PASS", gate, detail)

    def fail(self, gate: str, detail: str = "") -> None:
        self._report("FAIL", gate, detail)
        self.failed = True

    def skip(self, gate: str, reason: str = "") -> None:
        self._report("SKIP", gate, reason)

    # --- subprocess helpers --------------------------------------------------

    def run(self, cmd: list[str], gate: str | None = None, fail_msg: str = "") -> int:
        """Run cmd in the target root. With gate: PASS on exit 0, else FAIL + output tail."""
        proc = subprocess.run(cmd, cwd=self.root, capture_output=True, text=True)
        out = (proc.stdout + proc.stderr).strip()
        if gate is None:
            return proc.returncode
        if proc.returncode == 0:
            self.ok(gate)
        else:
            self.fail(gate, fail_msg)
            if out:
                print("\n".join(out.splitlines()[-20:]), file=sys.stderr)
        return proc.returncode

    def have(self, tool: str) -> bool:
        return shutil.which(tool) is not None

    def need_tool(self, tool: str, hint: str, required: bool = True) -> bool:
        if self.have(tool):
            return True
        level = "required" if required else "optional"
        print(f"missing {level} tool: {tool} (install: {hint})", file=sys.stderr)
        return False

    def find(self, *patterns: str) -> list[Path]:
        """Files under the target root matching any glob, PRUNE_DIRS excluded."""
        hits: list[Path] = []
        for dirpath, dirnames, filenames in os.walk(self.root):
            dirnames[:] = [d for d in dirnames if d not in PRUNE_DIRS]
            for name in filenames:
                if any(fnmatch.fnmatch(name, p) for p in patterns):
                    hits.append(Path(dirpath) / name)
        return hits

    def package_json(self) -> dict:
        pkg = self.root / "package.json"
        if not pkg.is_file():
            return {}
        try:
            return json.loads(pkg.read_text())
        except (json.JSONDecodeError, OSError):
            return {}

    # --- shared gates --------------------------------------------------------

    def lcov_line_rate(self, lcov: Path) -> int:
        """Line-coverage percent from an lcov file (DA:<line>,<hits>)."""
        total = hit = 0
        for line in lcov.read_text().splitlines():
            if line.startswith("DA:"):
                total += 1
                try:
                    if int(line[3:].split(",")[1]) > 0:
                        hit += 1
                except (IndexError, ValueError):
                    pass
        return round(hit * 100 / total) if total else 0

    def gate_duplication(self) -> None:
        """The duplication gate — identical for every language.

        jscpd version quirks (verified 2026-08):
        - v5 ("cpd", Rust rewrite) respects .gitignore by default, dropped
          --gitignore, does not auto-detect every extension (e.g. .go files
          are silently skipped → false PASS), and its --min-tokens filters
          whole files instead of clone blocks. So the npx fallback pins
          jscpd@3, and the min-tokens/min-lines flags (Sonar CPD parity:
          a duplicated block needs >= 100 tokens over >= 10 lines) are only
          passed to jscpd <= 4.
        """
        gate = "duplication"
        if self.have("jscpd"):
            runner = ["jscpd"]
        elif self.auto_tools and self.have("npx"):
            runner = ["npx", "--yes", "jscpd@3"]
        else:
            self.skip(gate, "install jscpd (npm i -g jscpd@3) or set QUALITY_AUTO_TOOLS=1")
            return
        version_out = subprocess.run(runner + ["--version"], capture_output=True, text=True)
        m = re.search(r"\d+", version_out.stdout + version_out.stderr)
        major = int(m.group(0)) if m else 3
        cmd = runner + [".", "--threshold", str(self.dup_max),
                        "--ignore", JSCPD_IGNORE, "--reporters", "console"]
        if major < 5:
            cmd += ["--min-tokens", str(self.dup_min_tokens),
                    "--min-lines", str(self.dup_min_lines),
                    "--gitignore"]
        else:
            print("note: jscpd v5 detected — cannot enforce the 100-token/10-line "
                  "block minimum; gate may be stricter than SonarQube CPD", file=sys.stderr)
        # Explicit formats: some jscpd builds silently skip extensions they
        # do not auto-detect, yielding a false PASS.
        if self.dup_formats:
            cmd += ["--format", self.dup_formats]
        self.run(cmd, gate=gate, fail_msg=f"duplicated lines above {self.dup_max}%")

    def gate_sast(self) -> None:
        """Cross-language SAST gate via Semgrep CE — the open-source stand-in
        for SonarQube's injection/taint rules (which are paywalled anyway).
        Optional: SKIP when semgrep is not installed."""
        gate = "sast"
        if not self.have("semgrep"):
            self.skip(gate, "install semgrep (uv tool install semgrep) for the SAST gate")
            return
        # p/security-audit: security-focused ruleset for all supported
        # languages (incl. taint mode). Fetched from the Semgrep registry —
        # needs network on first run (cached afterwards).
        self.run(["semgrep", "scan", "--config", "p/security-audit", "--error",
                  "--quiet", "--exclude", "node_modules", "--exclude", "vendor",
                  "--exclude", "target", "--exclude", ".venv"],
                 gate=gate, fail_msg="semgrep security findings (p/security-audit)")

    # --- driver --------------------------------------------------------------

    def run_gates(self, gates: list[tuple[str, object]]) -> int:
        print(f"quality gates ({self.lang}): coverage>={self.coverage_min}% "
              f"dup<={self.dup_max}% cognitive<={self.cognitive_max}")
        gates = [(name, self.gate_duplication if name == "duplication" else fn)
                 for name, fn in gates]
        gates.append(("sast", self.gate_sast))
        for name, fn in gates:
            if name in self.skip_gates:
                self.skip(name, "QUALITY_SKIP")
                continue
            fn()  # type: ignore[operator]
        if self.failed:
            print("quality gates: FAILED", file=sys.stderr)
            return 1
        print("quality gates: OK")
        return 0


def load_variant(lang: str, quality_dir: Path) -> object:
    variant = quality_dir / lang / "variant.py"
    if not variant.is_file():
        available = sorted(p.name for p in quality_dir.iterdir()
                           if p.is_dir() and (p / "variant.py").is_file())
        sys.exit(f"unknown language '{lang}'. Available: {', '.join(available)}")
    # Let variants import sibling helpers (jscommon) and other variants.
    sys.path.insert(0, str(quality_dir))
    spec = importlib.util.spec_from_file_location(f"qg_variant_{lang}", variant)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("lang", help="node | typescript | deno | bun | rust | go | python")
    args = parser.parse_args()

    quality_dir = Path(__file__).resolve().parent
    module = load_variant(args.lang, quality_dir)
    qg = QG(args.lang, quality_dir / args.lang, Path.cwd())
    qg.dup_formats = getattr(module, "DUP_FORMATS", None)
    return qg.run_gates(module.gates(qg))


if __name__ == "__main__":
    sys.exit(main())

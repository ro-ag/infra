"""Shared helpers for the JS-runtime variants (node, typescript, deno, bun).

Loaded by variant.py files; the engine (quality.py) puts this directory on
sys.path before loading a variant.
"""

from __future__ import annotations

ESLINT_CONFIG_NAMES = [
    "eslint.config.mjs", "eslint.config.js", "eslint.config.cjs", "eslint.config.ts",
    ".eslintrc", ".eslintrc.js", ".eslintrc.cjs", ".eslintrc.json",
    ".eslintrc.yml", ".eslintrc.yaml",
]


def find_eslint_config(qg) -> str | None:
    """Target repo's eslint config filename, 'package.json', or None."""
    for name in ESLINT_CONFIG_NAMES:
        if (qg.root / name).is_file():
            return name
    if (qg.root / "package.json").is_file() and qg.package_json().get("eslintConfig"):
        return "package.json"
    return None


def config_has_cognitive_rule(qg, config: str) -> bool:
    path = qg.root / ("package.json" if config == "package.json" else config)
    try:
        return "cognitive-complexity" in path.read_text()
    except OSError:
        return False


def local_bin(qg, name: str) -> list[str] | None:
    """Resolve an npm-style binary: repo-local install, PATH, then npx (auto tools only)."""
    local = qg.root / "node_modules" / ".bin" / name
    if local.is_file():
        return [str(local)]
    if qg.have(name):
        return [name]
    if qg.auto_tools and qg.have("npx"):
        return ["npx", "--yes", name]
    return None


def eslint_gates(qg, template: str) -> list[tuple[str, object]]:
    """lint + cognitive-complexity gates via the target repo's eslint config.

    `template` is the variant-relative config to copy when the repo has none,
    e.g. "quality/node/eslint.config.mjs".
    """
    config = find_eslint_config(qg)

    def lint() -> None:
        if config is None:
            qg.fail("lint", f"no eslint config found — copy {template} into this repo")
            return
        eslint = local_bin(qg, "eslint")
        if eslint is None:
            qg.fail("lint", "missing required tool: eslint "
                            "(install: npm install --save-dev eslint @eslint/js eslint-plugin-sonarjs)")
            return
        qg.run(eslint + ["."], gate="lint", fail_msg=f"eslint reported problems (config: {config})")

    def cognitive() -> None:
        gate = "cognitive-complexity"
        if config is None:
            qg.fail(gate, f"no eslint config found — copy {template} into this repo")
            return
        if not config_has_cognitive_rule(qg, config):
            qg.fail(gate, f"{config} lacks the sonarjs/cognitive-complexity rule "
                          f"(add eslint-plugin-sonarjs, threshold {qg.cognitive_max})")
            return
        eslint = local_bin(qg, "eslint")
        if eslint is None:
            qg.fail(gate, "missing required tool: eslint "
                          "(install: npm install --save-dev eslint eslint-plugin-sonarjs)")
            return
        qg.run(eslint + [".", "--rule",
                         f'{{"sonarjs/cognitive-complexity": ["error", {qg.cognitive_max}]}}'],
               gate=gate, fail_msg=f"cognitive complexity above {qg.cognitive_max} (or other eslint errors)")

    return [("lint", lint), ("cognitive-complexity", cognitive)]


def prettier_gate(qg) -> tuple[str, object]:
    def fmt() -> None:
        prettier = local_bin(qg, "prettier")
        if prettier is None:
            qg.fail("format", "missing required tool: prettier (install: npm install --save-dev prettier)")
            return
        qg.run(prettier + ["--check", "."], gate="format",
               fail_msg="formatting violations — run: prettier --write .")

    return ("format", fmt)

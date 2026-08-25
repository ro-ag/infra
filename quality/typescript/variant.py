"""TypeScript variant — same gates as node, plus requires tsconfig.json.

Reuses the node variant (the eslint template already applies
@typescript-eslint to **/*.ts); this variant only asserts the project is
actually TypeScript before delegating.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

_NODE_VARIANT = Path(__file__).resolve().parent.parent / "node" / "variant.py"
_spec = importlib.util.spec_from_file_location("qg_variant_node", _NODE_VARIANT)
_node = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_node)


def gates(qg) -> list[tuple[str, object]]:
    if (qg.root / "tsconfig.json").is_file() or qg.find("*.ts", "*.tsx"):
        return _node.gates(qg)

    def no_ts() -> None:
        qg.fail("lint", "no tsconfig.json and no .ts files — use the node variant for plain JS")

    rest = ("cognitive-complexity", "format", "security", "coverage")
    return [("lint", no_ts),
            *[(name, (lambda n=name: qg.skip(n, "not a TypeScript project"))) for name in rest],
            ("duplication", None)]

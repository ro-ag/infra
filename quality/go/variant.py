"""Go variant — golangci-lint (gocognit/gosec/staticcheck/revive), gofmt,
govulncheck, go test coverage, jscpd duplication."""

from __future__ import annotations

import re
import subprocess
import sys
import tempfile
from pathlib import Path

# jscpd v5 needs explicit formats; it silently skips extensions it doesn't auto-detect.
DUP_FORMATS = "go"

GO_HINT = "install Go: https://go.dev/doc/install"
GOLANGCI_HINT = "go install github.com/golangci/golangci-lint/v2/cmd/golangci-lint@latest"
GOVULNCHECK_HINT = "go install golang.org/x/vuln/cmd/govulncheck@latest"

GOCOGNIT_CONF = """\
version: "2"
linters:
  default: none
  enable:
    - gocognit
  settings:
    gocognit:
      min-complexity: {threshold}
"""

GOSEC_CONF = """\
version: "2"
linters:
  default: none
  enable:
    - gosec
"""


def _lint(qg) -> None:
    if not qg.need_tool("golangci-lint", GOLANGCI_HINT):
        qg.fail("lint", f"install golangci-lint: {GOLANGCI_HINT}")
        return
    config = next((f for f in (".golangci.yml", ".golangci.yaml", ".golangci.toml", ".golangci.json")
                   if (qg.root / f).is_file()), None)
    if config is None:
        config = str(qg.variant_dir / ".golangci.yml")
    qg.run(["golangci-lint", "run", "--config", config], gate="lint",
           fail_msg=f"golangci-lint findings (config: {config})")


def _cognitive(qg) -> None:
    gate = "cognitive-complexity"
    if not qg.need_tool("golangci-lint", GOLANGCI_HINT):
        qg.fail(gate, f"install golangci-lint: {GOLANGCI_HINT}")
        return
    # Single-linter temp config so the threshold is enforced even when the
    # target repo's own config omits gocognit.
    with tempfile.TemporaryDirectory(prefix="quality-") as tmp:
        conf = Path(tmp) / "gocognit.yml"
        conf.write_text(GOCOGNIT_CONF.format(threshold=qg.cognitive_max))
        qg.run(["golangci-lint", "run", "--config", str(conf)], gate=gate,
               fail_msg=f"gocognit: cognitive complexity > {qg.cognitive_max}")


def _format(qg) -> None:
    if not qg.need_tool("gofmt", GO_HINT):
        qg.fail("format", f"install gofmt: {GO_HINT}")
        return
    out = subprocess.run(["gofmt", "-l", "."], cwd=qg.root, capture_output=True, text=True).stdout
    unformatted = [f for f in out.splitlines() if f and not f.startswith("vendor/")]
    if unformatted:
        qg.fail("format", "gofmt: unformatted files (run: gofmt -w .)")
        print("\n".join(unformatted), file=sys.stderr)
    else:
        qg.ok("format")


def _security(qg) -> None:
    failed = False
    note = ""
    if not qg.need_tool("golangci-lint", GOLANGCI_HINT):
        failed = True
    else:
        with tempfile.TemporaryDirectory(prefix="quality-") as tmp:
            conf = Path(tmp) / "gosec.yml"
            conf.write_text(GOSEC_CONF)
            proc = subprocess.run(["golangci-lint", "run", "--config", str(conf)],
                                  cwd=qg.root, capture_output=True, text=True)
            if proc.returncode != 0:
                failed = True
                out = (proc.stdout + proc.stderr).strip()
                print(f"gosec findings:\n" + "\n".join(out.splitlines()[-20:]), file=sys.stderr)
    if qg.have("govulncheck"):
        proc = subprocess.run(["govulncheck", "./..."], cwd=qg.root, capture_output=True, text=True)
        if proc.returncode != 0:
            failed = True
            out = (proc.stdout + proc.stderr).strip()
            print("govulncheck findings:\n" + "\n".join(out.splitlines()[-20:]), file=sys.stderr)
    else:
        note = f"govulncheck skipped (install: {GOVULNCHECK_HINT})"
        print(f"missing optional tool: govulncheck (install: {GOVULNCHECK_HINT})", file=sys.stderr)
    if failed:
        qg.fail("security", "security findings (gosec/govulncheck)")
    else:
        qg.ok("security", note)


def _coverage(qg) -> None:
    if not qg.need_tool("go", GO_HINT):
        qg.fail("coverage", GO_HINT)
        return
    if not qg.find("*_test.go"):
        qg.skip("coverage", "no _test.go files")
        return
    cover = qg.root / "cover.out"
    try:
        if qg.run(["go", "test", "./...", "-coverprofile=cover.out"]) != 0:
            qg.fail("coverage", "go test failed")
            return
        out = subprocess.run(["go", "tool", "cover", "-func=cover.out"],
                             cwd=qg.root, capture_output=True, text=True).stdout
        m = re.search(r"^total:.*?([\d.]+)%", out, re.MULTILINE)
        total = float(m.group(1)) if m else 0.0
        if total >= qg.coverage_min:
            qg.ok("coverage", f"total: {total}%")
        else:
            qg.fail("coverage", f"coverage {total}% < {qg.coverage_min}%")
    finally:
        cover.unlink(missing_ok=True)


def gates(qg) -> list[tuple[str, object]]:
    return [
        ("lint", lambda: _lint(qg)),
        ("cognitive-complexity", lambda: _cognitive(qg)),
        ("format", lambda: _format(qg)),
        ("security", lambda: _security(qg)),
        ("coverage", lambda: _coverage(qg)),
        ("duplication", None),
    ]

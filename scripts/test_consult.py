#!/usr/bin/env python3
"""Smoke-test agy consultation command construction without invoking agy."""

from __future__ import annotations

import importlib.util
import tempfile
from argparse import Namespace
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "plugins" / "codex-agy-consultant" / "skills" / "agy-consultant" / "scripts" / "agy_consult.py"


def load_module():
    spec = importlib.util.spec_from_file_location("agy_consult", SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load {SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    module = load_module()
    args = Namespace(
        models=None,
        print_timeout=module.DEFAULT_PRINT_TIMEOUT,
        agent=None,
    )
    assert module.resolve_models(args) == [
        "Gemini 3.1 Pro (High)",
        "Gemini 3.5 Flash (High)",
    ]
    assert module.build_command("/usr/local/bin/agy", args, "payload", "Gemini 3.1 Pro (High)") == [
        "/usr/local/bin/agy",
        "--mode",
        "plan",
        "--sandbox",
        "--model",
        "Gemini 3.1 Pro (High)",
        "--print-timeout",
        "120s",
        "--print",
        "payload",
    ]

    args.models = ["Gemini 3.5 Flash (High)", "Gemini 3.1 Pro (High)"]
    assert module.resolve_models(args) == args.models

    compact = module.compact_report(
        """
        REPORT: One material compatibility risk.
        FINDING: HIGH | FACT | src/main.rs:12 | Input is accepted without validation. | Invalid state reaches the parser. | Normal input is unaffected; malformed input can crash the process. | High | Add a negative test and validate before parsing.
        FINDING: LOW | HYPOTHESIS | src/ui.tsx:44 | The label may not update after reload. | Users may see stale state. | Normal reload may show old data; worst case is misleading UI. | Medium | Exercise reload and inspect the rendered value.
        FINDING: MEDIUM | FACT | src/db.rs:9 | A lock is held across an await. | Requests can queue behind slow I/O. | Normal traffic is fine; worst case is contention. | High | Measure under concurrent requests.
        FINDING: LOW | FACT | README.md:4 | Documentation omits the fallback. | Operators may misconfigure it. | Normal setup needs clarification; worst case is failed startup. | High | Add a setup test.
        FINDING: LOW | FACT | ignored.rs:1 | This fifth finding must be omitted. | No material impact. | None. | Low | No action.
        UNCERTAINTY: The supplied context does not establish production traffic volume.
        """,
    )
    assert compact.count("FINDING:") == 4
    assert "REPORT: One material compatibility risk." in compact
    assert "ignored.rs" not in compact
    assert "UNCERTAINTY:" in compact

    fallback = module.compact_report("A long unstructured report\nwith extra whitespace.")
    assert fallback.startswith("UNSTRUCTURED_REPORT:")

    args.agent = "custom-agent"
    command = module.build_command("agy", args, "payload", args.models[0])
    assert command[-4:] == ["--agent", "custom-agent", "--print", "payload"]

    payload, selected = module.build_payload(ROOT, "plan", "test task", 80_000, ["README.md"])
    assert "tracked diff omitted for plan phase" in payload
    assert selected[0][0] == Path("README.md")

    with tempfile.TemporaryDirectory(prefix="codex-agy-materialize-test-") as temp:
        workspace = Path(temp)
        module.materialize_selected_files(workspace, [(Path("nested/context.txt"), "context")])
        assert (workspace / "nested" / "context.txt").read_text(encoding="utf-8") == "context"

    print("consult command smoke test: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

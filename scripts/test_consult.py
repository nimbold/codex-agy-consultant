#!/usr/bin/env python3
"""Smoke-test agy consultation command construction without invoking agy."""

from __future__ import annotations

import importlib.util
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
    assert module.resolve_models(args) == ["Gemini 3.5 Flash (High)"]
    assert module.build_command("/usr/local/bin/agy", args, "payload", "Gemini 3.5 Flash (High)") == [
        "/usr/local/bin/agy",
        "--mode",
        "accept-edits",
        "--sandbox",
        "--model",
        "Gemini 3.5 Flash (High)",
        "--print-timeout",
        "120s",
        "--print",
        "payload",
    ]

    args.models = ["Gemini 3.5 Flash (High)", "Gemini 3.1 Pro (High)"]
    assert module.resolve_models(args) == args.models

    args.agent = "custom-agent"
    command = module.build_command("agy", args, "payload", args.models[0])
    assert command[-4:] == ["--agent", "custom-agent", "--print", "payload"]

    print("consult command smoke test: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Smoke-test Hermes consultation command construction without invoking Hermes."""

from __future__ import annotations

import importlib.util
from argparse import Namespace
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "plugins" / "codex-consultants" / "skills" / "hermes-consult" / "scripts" / "hermes_consult.py"


def load_module():
    spec = importlib.util.spec_from_file_location("hermes_consult", SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load {SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    module = load_module()
    args = Namespace(
        provider=module.DEFAULT_PROVIDER,
        models=None,
        reasoning_effort=module.DEFAULT_REASONING_EFFORT,
        thinking_mode=None,
    )
    assert module.resolve_models(args) == ["minimaxai/minimax-m3"]
    assert module.DEFAULT_RETRIES == 0
    assert module.resolve_thinking_mode(args) == "enabled"
    args.reasoning_effort = "none"
    assert module.resolve_thinking_mode(args) == "disabled"
    args.thinking_mode = "adaptive"
    assert module.resolve_thinking_mode(args) == "adaptive"
    args.reasoning_effort = module.DEFAULT_REASONING_EFFORT
    args.thinking_mode = None
    assert module.build_command("/usr/local/bin/hermes", args, "payload", "minimaxai/minimax-m3") == [
        "/usr/local/bin/hermes",
        "--oneshot",
        "payload",
        "--provider",
        "custom:codex-consultants-nvidia",
        "--model",
        "minimaxai/minimax-m3",
        "--ignore-rules",
        "--toolsets",
        "file,terminal",
    ]
    isolated = module.build_isolated_config("minimaxai/minimax-m3", "enabled")
    assert isolated["providers"][module.ISOLATED_PROVIDER]["extra_body"] == {
        "chat_template_kwargs": {"thinking_mode": "enabled"}
    }
    disabled = module.build_isolated_config("minimaxai/minimax-m3", "disabled")
    assert disabled["providers"][module.ISOLATED_PROVIDER]["extra_body"]["chat_template_kwargs"]["thinking_mode"] == "disabled"

    args.models = ["minimaxai/minimax-m3", "other/model"]
    assert module.resolve_models(args) == args.models

    compact = module.COMMON.compact_report(
        "REPORT: The bounded Hermes consultation completed.\n"
        "FINDING: HIGH | FACT | src/main.rs:12 | Input is unchecked. | Invalid state reaches the parser. | Worst case is a process crash. | High | Add validation."
    )
    assert "REPORT: The bounded Hermes consultation completed." in compact
    assert "FINDING: HIGH" in compact

    print("hermes consultation smoke test: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

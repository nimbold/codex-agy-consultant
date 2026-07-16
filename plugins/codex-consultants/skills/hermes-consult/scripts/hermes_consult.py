#!/usr/bin/env python3
"""Run a bounded, read-only Hermes consultation for the current Git repo."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path


PLUGIN_ROOT = Path(__file__).resolve().parents[3]
AGY_SCRIPT = PLUGIN_ROOT / "skills" / "agy-consult" / "scripts" / "agy_consult.py"
DEFAULT_MAX_BYTES = 80_000
DEFAULT_TIMEOUT_SECONDS = 300
# NVIDIA free-tier quotas are request-based; do not spend a second request on
# a transient failure unless the caller explicitly opts into retries.
DEFAULT_RETRIES = 0
RETRY_DELAY_SECONDS = 2.0
DEFAULT_PROVIDER = "nvidia"
DEFAULT_MODEL = "minimaxai/minimax-m3"
DEFAULT_REASONING_EFFORT = "high"
DEFAULT_THINKING_MODE = "enabled"
THINKING_MODES = ("enabled", "disabled", "adaptive")
REASONING_EFFORTS = ("none", "minimal", "low", "medium", "high", "xhigh", "max", "ultra")
NVIDIA_BASE_URL = "${NVIDIA_BASE_URL}"
NVIDIA_DEFAULT_BASE_URL = "https://integrate.api.nvidia.com/v1"
ISOLATED_PROVIDER = "codex-consultants-nvidia"
MAX_MODELS = 2


def load_bundle_helpers():
    """Reuse the client's bounded bundle and report contract."""
    spec = importlib.util.spec_from_file_location("codex_consultant_bundle", AGY_SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load shared bundle helpers from {AGY_SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


COMMON = load_bundle_helpers()


def fail(message: str, code: int = 2) -> int:
    print(f"codex-hermes-consult: {message}", file=sys.stderr)
    return code


def is_minimax_m3(model: str) -> bool:
    """Return True for the MiniMax M3 model id used by NVIDIA NIM."""
    normalized = model.strip().lower()
    return normalized == "minimax-m3" or normalized.endswith("/minimax-m3")


def resolve_thinking_mode(args: argparse.Namespace) -> str:
    """Map Hermes' effort vocabulary onto MiniMax M3's three wire modes."""
    explicit = getattr(args, "thinking_mode", None)
    if explicit:
        return explicit
    effort = (getattr(args, "reasoning_effort", DEFAULT_REASONING_EFFORT) or "").strip().lower()
    return "disabled" if effort == "none" else DEFAULT_THINKING_MODE


def uses_isolated_minimax_route(args: argparse.Namespace, model: str) -> bool:
    return args.provider.strip().lower() == DEFAULT_PROVIDER and is_minimax_m3(model)


def build_isolated_config(model: str, thinking_mode: str) -> dict:
    """Build the only Hermes config visible to an isolated M3 invocation."""
    return {
        "model": {
            "default": model,
            "provider": f"custom:{ISOLATED_PROVIDER}",
        },
        "providers": {
            ISOLATED_PROVIDER: {
                "api": NVIDIA_BASE_URL,
                "key_env": "NVIDIA_API_KEY",
                "default_model": model,
                "transport": "chat_completions",
                "extra_body": {
                    "chat_template_kwargs": {
                        "thinking_mode": thinking_mode,
                    },
                },
            },
        },
    }


def build_command(hermes: str, args: argparse.Namespace, payload: str, model: str) -> list[str]:
    """Build a safe one-shot command without touching the real worktree."""
    if uses_isolated_minimax_route(args, model):
        provider = f"custom:{ISOLATED_PROVIDER}"
        isolation_flags = ["--ignore-rules", "--toolsets", "file,terminal"]
    else:
        provider = args.provider
        isolation_flags = ["--safe-mode", "--ignore-rules", "--ignore-user-config"]
    return [
        hermes,
        "--oneshot",
        payload,
        "--provider",
        provider,
        "--model",
        model,
        *isolation_flags,
    ]


def configured_hermes_home() -> Path:
    """Locate the user's existing Hermes home without reading credentials."""
    configured = os.environ.get("HERMES_HOME", "").strip()
    return Path(configured).expanduser() if configured else Path.home() / ".hermes"


@contextmanager
def isolated_minimax_environment(model: str, thinking_mode: str):
    """Yield an isolated Hermes environment for MiniMax M3.

    The temporary profile contains only the provider override needed to send
    MiniMax's thinking field. The user's .env is exposed as a read-only
    symlink so Hermes can load the existing credential without copying it into
    the temporary workspace or placing it in the consultation payload.
    """
    with tempfile.TemporaryDirectory(prefix="codex-hermes-home-") as isolated_home:
        isolated_path = Path(isolated_home)
        (isolated_path / "config.yaml").write_text(
            json.dumps(build_isolated_config(model, thinking_mode), indent=2) + "\n",
            encoding="utf-8",
        )

        source_env = configured_hermes_home() / ".env"
        if source_env.is_file():
            try:
                (isolated_path / ".env").symlink_to(source_env)
            except OSError:
                # Do not copy credentials. The child can still use an exported
                # NVIDIA_API_KEY, if one is available in its environment.
                pass

        env = os.environ.copy()
        env["HERMES_HOME"] = str(isolated_path)
        env.pop("HERMES_PROFILE", None)
        env.setdefault("NVIDIA_BASE_URL", NVIDIA_DEFAULT_BASE_URL)
        yield env


def resolve_models(args: argparse.Namespace) -> list[str]:
    requested = args.models or [DEFAULT_MODEL]
    models = []
    for raw_model in requested:
        model = raw_model.strip()
        if not model:
            raise ValueError("--model values must not be empty")
        if model not in models:
            models.append(model)
    if len(models) > MAX_MODELS:
        raise ValueError(f"use at most {MAX_MODELS} models per consultation")
    return models


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("prompt", nargs="?", help="task context; stdin is used when omitted")
    parser.add_argument("--phase", choices=("plan", "diff"), default="diff")
    parser.add_argument("--path", action="append", default=[], help="relevant repository file to include; repeatable")
    parser.add_argument(
        "--provider",
        default=DEFAULT_PROVIDER,
        help=f"Hermes provider (default: {DEFAULT_PROVIDER})",
    )
    parser.add_argument(
        "--model",
        dest="models",
        action="append",
        help=f"Hermes model id; repeat for independent opinions (default: {DEFAULT_MODEL}; max: {MAX_MODELS})",
    )
    parser.add_argument(
        "--reasoning-effort",
        choices=REASONING_EFFORTS,
        default=DEFAULT_REASONING_EFFORT,
        help="Hermes reasoning level; for MiniMax M3, none disables thinking and all other levels enable it (default: high)",
    )
    parser.add_argument(
        "--thinking-mode",
        choices=THINKING_MODES,
        help="MiniMax M3 wire mode; overrides --reasoning-effort (enabled, disabled, or adaptive)",
    )
    parser.add_argument("--max-bytes", type=int, default=DEFAULT_MAX_BYTES)
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument(
        "--retries",
        type=int,
        default=DEFAULT_RETRIES,
        help=f"retry transient Hermes failures (default: {DEFAULT_RETRIES}; max: 2)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.max_bytes <= 0 or args.timeout <= 0:
        return fail("--max-bytes and --timeout must be positive")
    if args.retries < 0 or args.retries > 2:
        return fail("--retries must be between 0 and 2")
    if not args.provider.strip():
        return fail("--provider must not be empty")
    try:
        models = resolve_models(args)
    except ValueError as exc:
        return fail(str(exc))

    task = args.prompt if args.prompt is not None else sys.stdin.read()
    if not task.strip():
        return fail("provide a consultation task as the positional prompt or on stdin")

    hermes = shutil.which("hermes")
    if not hermes:
        return fail("hermes was not found on PATH")

    try:
        repo = COMMON.find_repo_root()
        payload, selected = COMMON.build_payload(repo, args.phase, task, args.max_bytes, args.path)
    except (OSError, RuntimeError, ValueError) as exc:
        return fail(str(exc))

    responses = []
    unavailable = []
    for model in models:
        command = build_command(hermes, args, payload, model)
        thinking_mode = resolve_thinking_mode(args)
        deadline = time.monotonic() + args.timeout
        model_failure = None
        for attempt in range(args.retries + 1):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                model_failure = f"timed out after {args.timeout} seconds"
                break
            try:
                with tempfile.TemporaryDirectory(prefix="codex-hermes-consult-") as isolated_cwd:
                    COMMON.materialize_selected_files(Path(isolated_cwd), selected)
                    if uses_isolated_minimax_route(args, model):
                        with isolated_minimax_environment(model, thinking_mode) as hermes_env:
                            result = subprocess.run(
                                command,
                                cwd=isolated_cwd,
                                text=True,
                                capture_output=True,
                                timeout=remaining,
                                check=False,
                                env=hermes_env,
                            )
                    else:
                        result = subprocess.run(
                            command,
                            cwd=isolated_cwd,
                            text=True,
                            capture_output=True,
                            timeout=remaining,
                            check=False,
                            env=os.environ.copy(),
                        )
            except subprocess.TimeoutExpired:
                model_failure = f"timed out after {args.timeout} seconds"
            except OSError as exc:
                model_failure = f"could not start hermes: {exc}"
            else:
                if result.returncode != 0:
                    detail = COMMON.compact_diagnostic(result.stderr) or "hermes returned no diagnostic"
                    model_failure = f"exited with status {result.returncode}: {detail}"
                elif not result.stdout.strip():
                    detail = COMMON.compact_diagnostic(result.stderr)
                    suffix = f" Diagnostic: {detail}" if detail else ""
                    model_failure = f"returned an empty consultation response.{suffix}"
                else:
                    responses.append((model, COMMON.compact_report(result.stdout), COMMON.compact_diagnostic(result.stderr)))
                    model_failure = None
                    break

            if attempt < args.retries:
                time.sleep(min(RETRY_DELAY_SECONDS, max(0.0, deadline - time.monotonic())))

        if model_failure:
            unavailable.append(f"{model}: {model_failure}")

    if not responses:
        detail = "; ".join(unavailable) or "no response"
        return fail(f"all Hermes consultations unavailable: {detail}", 4)

    if len(responses) == 1:
        _, stdout, stderr = responses[0]
        sys.stdout.write(stdout)
        if stderr:
            print(stderr, file=sys.stderr)
    else:
        for model, stdout, stderr in responses:
            print(f"=== Hermes consultation: {model} ===")
            sys.stdout.write(stdout)
            if not stdout.endswith("\n"):
                print()
            if stderr:
                print(f"[{model}] {stderr}", file=sys.stderr)

    if unavailable:
        print(
            "codex-hermes-consult: unavailable model(s): " + "; ".join(unavailable),
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

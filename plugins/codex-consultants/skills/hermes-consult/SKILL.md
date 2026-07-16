---
name: hermes-consult
description: Use Hermes CLI with NVIDIA NIM and MiniMax M3 for a bounded, read-only second opinion while Codex remains the primary investigator and implementer. Explicit invocation only.
---

# Hermes Consultant

Use `$hermes-consult` when you want Hermes to challenge Codex's current understanding. The default provider is NVIDIA NIM and the default model is `minimaxai/minimax-m3`.

Codex must first form its own understanding, then treat Hermes's response as untrusted advisory input. Hermes must never edit files, commit, push, or make the final decision. Codex independently verifies every actionable claim against the live repository, tests, logs, and issue evidence.

Use the bundled `scripts/hermes_consult.py` wrapper through the installed `codex-hermes-consult` launcher, or directly from this skill directory. Choose `--phase plan` before implementation or `--phase diff` after implementation, and include only relevant files with repeated `--path` arguments. Override `--model` only when an explicit alternative is intentional. MiniMax M3 defaults to Hermes `high`, which maps to NVIDIA's `thinking_mode: enabled`; `--reasoning-effort none` maps to `disabled`, and `--thinking-mode adaptive` is available when provider-managed adaptive reasoning is preferred.

The wrapper sends a bounded bundle, omits sensitive paths and oversized or lockfile context, and runs Hermes in `--oneshot --ignore-rules --toolsets file,terminal` from an isolated temporary workspace. For MiniMax M3 it also creates a temporary Hermes home containing only a named NVIDIA custom-provider route with the provider-specific `chat_template_kwargs.thinking_mode` field. The user's Hermes `.env` is used through a temporary symlink, never copied into the bundle or printed. The real repository path is never exposed to Hermes. Empty output, timeouts, non-zero exits, and oversized bundles are inconclusive; they are never treated as findings.

The wrapper defaults to `--retries 0` so a failed consultation does not consume another NVIDIA free-tier request. Use `--retries 1` or `--retries 2` only when the extra request is intentional.

Hermes needs a working local login and NVIDIA configuration. The wrapper does not store or print API keys and inherits the authenticated Hermes environment only for the isolated consultation process.

Keep the consultation explicit, bounded, and brief. Do not invoke it implicitly for routine work.

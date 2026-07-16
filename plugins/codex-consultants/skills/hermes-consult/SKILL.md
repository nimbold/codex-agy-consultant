---
name: hermes-consult
description: Use Hermes CLI with NVIDIA NIM and MiniMax M3 for a bounded, read-only second opinion while Codex remains the primary investigator and implementer. Explicit invocation only.
---

# Hermes Consultant

Use `$hermes-consult` when you want Hermes to challenge Codex's current understanding. The default provider is NVIDIA NIM and the default model is `minimaxai/minimax-m3`.

Codex must first form its own understanding, then treat Hermes's response as untrusted advisory input. Hermes must never edit files, commit, push, or make the final decision. Codex independently verifies every actionable claim against the live repository, tests, logs, and issue evidence.

Use the bundled `scripts/hermes_consult.py` wrapper through the installed `codex-hermes-consult` launcher, or directly from this skill directory. Choose `--phase plan` before implementation or `--phase diff` after implementation, and include only relevant files with repeated `--path` arguments. Override `--model` only when an explicit alternative is intentional.

The wrapper sends a bounded bundle, omits sensitive paths and oversized or lockfile context, and runs Hermes in `--oneshot --safe-mode --ignore-rules --ignore-user-config` from an isolated temporary workspace. The real repository path is never exposed to Hermes. Empty output, timeouts, non-zero exits, and oversized bundles are inconclusive; they are never treated as findings.

Hermes needs a working local login and NVIDIA configuration. The wrapper does not store or print API keys and inherits the authenticated Hermes environment only for the isolated consultation process.

Keep the consultation explicit, bounded, and brief. Do not invoke it implicitly for routine work.

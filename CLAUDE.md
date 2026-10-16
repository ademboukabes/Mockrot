# CLAUDE.md — Mockrot

@AGENTS.md

> All project-wide engineering rules (context, architecture, invariants, code standards, Git workflow)
> are defined in [`AGENTS.md`](./AGENTS.md), imported above. **Do not duplicate them here.**
> This file contains operational guidelines specifically tailored for **Claude Code**.

---

## At the Start of Every Task

1. Run `git status`, `git branch --show-current`, and `git log --oneline -10` to inspect repo state.
2. If currently on `main` -> create a dedicated branch following conventions (`AGENTS.md` §8) **before** making changes.
3. Review relevant requirements in `docs/spec/v1-specification.md` and check critical invariants (`AGENTS.md` §4) and technical gotchas (`AGENTS.md` §5).
4. Read and understand existing affected code before proposing changes.

## Planning Workflow

- **Plan mode mandatory** if the task modifies more than one module, affects public APIs, changes `pyproject.toml`, touches CI workflows, or adds a dependency. Present: objective, impacted files, technical approach, tests planned, and potential risks. **Wait for approval** before writing code.
- Track progress sequentially; each step must yield a verifiable result.
- For deep library exploration (`unittest.mock`, `pydantic`, `pytest`), delegate to a subagent to preserve the primary context window.

## Implementation Loop

- Test-Driven Development: Red test -> minimal implementation -> refactor (`AGENTS.md` §6).
- After each edit: run targeted tests (`uv run pytest tests/unit/test_x.py -q`).
- Before each commit: run the full verification pipeline (`AGENTS.md` §10) and inspect output.
- If verification fails: fix the root cause. Never bypass with skips, `type: ignore` workarounds, or config relaxations without explicit consent.
- If stuck after two unsuccessful attempts on the same issue: stop and report analysis and available options to the maintainer.

## Git Permissions & Boundaries

| Allowed Autonomously | Requires Explicit Approval |
| :--- | :--- |
| Create a feature branch from up-to-date `main` | `git push` (to any branch) |
| `git add <explicit paths>` | Open or merge a Pull Request |
| Atomic Conventional Commits | `rebase -i` on already-pushed branches |
| `git commit --fixup` on local branch | Any `--force` or `--force-with-lease` |
| `git fetch`, `git rebase origin/main` (local) | Destructive operations (`reset --hard`, `clean -fd`, `branch -D`, release tags) |

Before committing: inspect `git diff --staged --stat`, ensure no out-of-scope files are included, and write a strict Conventional Commit message in English (imperative mood, lowercase summary, <= 72 characters, body explaining the *why*).

## Protected Files

Do not modify without explicit request: `docs/spec/v1-specification.md`, `AGENTS.md`, `CLAUDE.md`, `LICENSE`, `.github/workflows/*`, or the `[tool.ruff]` / `[tool.pyright]` configuration in `pyproject.toml`.
Exception: Document newly discovered technical gotchas in `AGENTS.md` §5 (notifying the user).

## Communication

- Maintainer interaction can be in French or English as preferred by the maintainer.
- All code, docstrings, comments, commit messages, PRs, and documentation must be strictly in **English**.
- At the end of each task, summarize:
  - **Done:** what changed (files, commits).
  - **Why:** key technical decisions and trade-offs.
  - **Verified:** commands executed and actual outputs.
  - **Next steps / Risks:** known limitations, unverified edge cases, open questions.
- Never assert a test passes without having executed it in the current session.

## Context Hygiene

- Keep tasks atomic.
- Avoid repeatedly dumping large files already in context; target specific line ranges.

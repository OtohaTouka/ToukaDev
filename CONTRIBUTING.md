# Contributing

ToukaDev is written mostly in Traditional Chinese. Issues and pull requests in English or Chinese are both welcome.
By contributing you agree that your contribution is licensed under the MIT License of this repository.

## Before you change anything

- Read [README.md](README.md) and the framework rules in [AGENTS.md](AGENTS.md). Changes to ToukaDev go through the
  same process the framework describes: tests first (TDD), one source of truth (SSOT), and an ADR for new rules,
  guards or architecture changes (`docs/adr/`, next free number, plus a row in `docs/adr/README.md`).
- Some rules exist because of real incidents and are protected: the 13 steps and review points, separating the writer
  from the reviewer, per-action consent (commit, multiple agents, sending data out, irreversible actions), safe
  deletion, data protection, the shared prohibitions, and the human gates of the improvement loop. A change that
  removes or weakens one of them needs its own explanation, including where the rule came from.
- The block between `<!-- toukadev:shared-rules:begin -->` and `<!-- toukadev:shared-rules:end -->` is copied into four
  files that must stay identical (the guard checks this). Changing it needs the maintainer's approval.
- Do not put secrets, personal data or quotes from private conversations into versioned files.

## Local checks

You need [uv](https://docs.astral.sh/uv/) 0.12.1 or newer (CI uses 0.12.1); uv installs Python 3.12 for you.

```bash
uv sync --locked
uv run --locked pytest tests
uv run --locked ruff check scripts tests project-init dev-workflow
uv run --locked python scripts/guard_framework.py
```

All four must pass. CI runs the same commands on Linux.

## Pull requests

- Branch from `dev` and open the pull request against `dev`. `main` is updated from `dev` by the maintainer.
- One topic per pull request. Behavior changes come with tests; say in the description which checks you ran.
- CI for a pull request from outside the repository (a fork) starts after a maintainer approves it.

## 中文摘要

- 改動照 ToukaDev 自己的流程：先寫測試、單一事實來源、新規則／守衛／架構改動寫 ADR 並更新索引。
- 受保護的規則（13 步驟與審核點、寫審分開、逐次同意、安全刪法、資料保護、共同禁止行為、改進迴圈的人類關卡）
  要移除或弱化時，單獨說明理由與源頭。共同區塊在四份檔案裡必須一致，改它要維護者同意。
- 本機跑上面四個檢查（uv 0.12.1 以上，CI 用 0.12.1），全過才開 PR；從 `dev` 開分支、PR 回 `dev`。
- 版控檔案不放金鑰、個資或私人對話的原話。從 fork 開的 PR，CI 要維護者核准後才會跑。

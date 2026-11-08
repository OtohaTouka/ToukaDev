"""比對進度紀錄和 git、GitHub 的實際狀態（progress-record.md「比對實際狀態」，ADR-051）。

用法：
    python -I sync_progress.py <.toukadev/progress 資料夾>
    python -I sync_progress.py <.toukadev/progress 資料夾> --apply --task <任務代號>

- 只比對這個資料夾直接底下的任務紀錄；不讀總覽板的「其他專案」，也不讀寫其他專案。
- 只用唯讀指令：git rev-parse、remote、config --get、worktree list、symbolic-ref、ls-remote、show-ref，
  以及 gh pr list；不 fetch、不 prune。每個指令有時限、關掉登入提示（使用者有自己的 ssh 設定時照用）；
  gh 沒裝、沒登入或沒網路時寫「查不到」。
- 結果印在畫面上，也寫進同資料夾的 sync-status.json（先寫暫存檔再替換），進度網頁會讀它。
- --apply 只由主代理執行：只改 --task 那一份紀錄的三種固定欄位，並在審核紀錄最後加一列。
  寫入前核對新舊內容只差那些格子與新加的一列；讀檔後內容被改過就整個放棄。

結束代碼：0 沒有對不上也沒有查不到（只有「沒比對」的列也是 0；--apply 時指改完之後）；
1 有對不上、查不到、讀不到紀錄、寫不進結果檔，或 --apply 被拒絕；2 參數或位置不對、Python 版本太舊。
紀錄解析與比對結果的格式都用同資料夾的 render_progress.py，不另寫一份。只用 Python 3.12 標準函式庫。
"""

from __future__ import annotations

import argparse
import codecs
import hashlib
import importlib.util
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from types import ModuleType
from typing import Protocol

RENDERER_FILE = "render_progress.py"
RENDERER_MODULE = "toukadev_render_progress_for_sync"
CLEANUP_FILE = "check_cleanup.py"
CLEANUP_MODULE = "toukadev_check_cleanup_for_sync"


def load_sibling(file_name: str, module_name: str) -> ModuleType:
    """載入同資料夾的程式（不另寫一份）；不在 Skill 安裝資料夾留下 __pycache__。"""
    previous = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        spec = importlib.util.spec_from_file_location(
            module_name, Path(__file__).with_name(file_name)
        )
        if spec is None or spec.loader is None:
            raise ImportError(f"載入不了 {file_name}")
        module = importlib.util.module_from_spec(spec)
        # @dataclass 在延後求值的型別標註下會到這裡找模組。
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        return module
    finally:
        sys.dont_write_bytecode = previous


rp = load_sibling(RENDERER_FILE, RENDERER_MODULE)
# 共用分支的名單用清理前檢查程式的那一份。
cc = load_sibling(CLEANUP_FILE, CLEANUP_MODULE)

# ── 規則（progress-record.md「比對實際狀態」）───────────────────────

MINIMUM_PYTHON = (3, 12)
TIMEOUT_SECONDS = 20
GH_PR_LIMIT = "5"
GH_FIELDS = "number,state,headRefName,headRefOid,isCrossRepository,mergedAt,mergeCommit,url"
PROMPT_OFF_ENV = {
    "GIT_TERMINAL_PROMPT": "0",
    "GCM_INTERACTIVE": "never",
    "GH_PROMPT_DISABLED": "1",
    "GH_NO_UPDATE_NOTIFIER": "1",
}
BRANCH_COLUMN = "工作分支"
ITEM_COLUMN = "項目"
TYPE_COLUMN = "類型"
LOCATION_COLUMN = "位置"
TYPE_REMOTE = "遠端分支"
TYPE_WORKTREE = "工作資料夾"
TYPE_LOCAL = "本機分支"
MERGED_STATUS = "已合併"
IN_USE_STATE = "使用中"
# PR 已合併時，工作清單那一列是這幾種狀態才算對得上。
MERGED_DONE = frozenset({MERGED_STATUS, "已完成", "已驗收", rp.MOVED_STATUS})
IN_REVIEW = frozenset({"待審", "審核中"})
# 分支名只認英數與 ._/-：紀錄裡的說明文字（例如「上述工作資料夾」）不會被當成分支。
BRANCH_PATTERN = re.compile(r"[A-Za-z0-9._/-]+")
PR_URL_PATTERN = re.compile(
    r"https://github\.com/(?P<repo>[A-Za-z0-9-]+/[A-Za-z0-9._-]+)/pull/(?P<number>\d+)"
)
GITHUB_REMOTE_PATTERN = re.compile(
    r"^(?:https://github\.com/|git@github\.com:|ssh://git@github\.com/)"
    r"(?P<repo>[A-Za-z0-9-]+/[A-Za-z0-9._-]+?)(?:\.git)?/?$"
)
# ssh 遠端不問密碼或主機金鑰：只在使用者沒有自己的 ssh 設定時，ls-remote 用 -c core.sshCommand 帶上。
SSH_BATCH = "ssh -o BatchMode=yes"
# 這些環境變數或 core.sshCommand 有設時，照使用者的設定跑，不加 BatchMode。
USER_SSH_ENV = ("GIT_SSH_COMMAND", "GIT_SSH")
# 工作資料夾的位置只認不含空白與全形字的路徑；網路路徑（\\host\share）不碰。
PATH_PATTERN = re.compile(r"[A-Za-z0-9._/\\:~-]+")
# str.splitlines 會在這些字元斷行，git 與一般編輯器不會；紀錄裡有這些字元時 --apply 不改。
SPECIAL_LINE_BREAKS = ("\x0b", "\x0c", "\x1c", "\x1d", "\x1e", "\x85", "\u2028", "\u2029")
EMPTY_NOTES = frozenset({"", "—", "-", "－"})
NOTE_JOINER = "；"
WAITING_NOTE = f"{rp.WAITING_PREFIX}：已合併，可以刪。"
REVIEW_CELLS = {
    "關卡": "自動比對",
    "審核對象": "進度紀錄固定欄位",
    "寫的人": "sync_progress",
    "審的人": "—",
    "結論": "已更新",
}
UNREACHABLE, UNCHECKED = "unreachable", "unchecked"


# ── 資料結構 ─────────────────────────────────────────────────────


@dataclass(frozen=True)
class CommandResult:
    """code 是 None 表示指令沒跑成（逾時、找不到、啟動失敗），problem 寫原因。"""

    code: int | None
    stdout: str
    problem: str = ""


class Runner(Protocol):
    def __call__(self, args: Sequence[str], cwd: Path) -> CommandResult: ...


@dataclass(frozen=True)
class PullRequest:
    number: int
    state: str
    head: str
    head_oid: str
    cross: bool
    merged_at: str | None
    merge_oid: str | None


@dataclass(frozen=True)
class RemoteHead:
    found: bool | None
    sha: str = ""
    problem: str = ""


@dataclass(frozen=True)
class Fix:
    """--apply 要改的一格狀態與備註；summary 寫進新加的審核紀錄。"""

    section: str
    row: int
    status: str
    note: str
    summary: str
    # 比對時那一列的格子；寫入前核對要改的那一行就是這一列。
    original: tuple[str, ...]


@dataclass(frozen=True)
class Outcome:
    finding: rp.SyncFinding
    fix: Fix | None = None


@dataclass(frozen=True)
class TableLocation:
    header: int
    rows: tuple[int, ...]
    end: int
    # 表格有任何一行在圍欄（``` 或 ~~~）裡：--apply 不改，也不在後面加列。
    fenced: bool = False


@dataclass
class Context:
    """一次比對共用的 git／gh 查詢；同樣的查詢只跑一次。"""

    runner: Runner
    project: Path
    root: Path
    remotes: dict[str, str]
    github: dict[str, str]
    # 使用者沒有自己的 ssh 設定時，連遠端的 ls-remote 加上 BatchMode。
    ssh_batch: bool = False
    pulls_cache: dict[tuple[str, str], list[PullRequest] | str] = field(default_factory=dict)
    heads_cache: dict[tuple[str, str], RemoteHead] = field(default_factory=dict)
    worktree_cache: list[tuple[set[str], Path | None] | str] = field(default_factory=list)
    default_cache: dict[str, str | None] = field(default_factory=dict)

    def git(self, *args: str) -> CommandResult:
        return self.runner(("git", *args), self.project)

    def remote_git(self, *args: str) -> CommandResult:
        """連遠端的 git 指令（ls-remote）；使用者沒有自己的 ssh 設定時不讓 ssh 問密碼。"""
        batch = ("-c", f"core.sshCommand={SSH_BATCH}") if self.ssh_batch else ()
        return self.git(*batch, *args)

    def pulls(self, repo: str, branch: str) -> list[PullRequest] | str:
        key = (repo, branch)
        if key not in self.pulls_cache:
            result = self.runner(
                ("gh", "pr", "list", "--repo", repo, "--head", branch, "--state", "all",
                 "--limit", GH_PR_LIMIT, "--json", GH_FIELDS),
                self.project,
            )
            self.pulls_cache[key] = read_pulls(result, repo)
        return self.pulls_cache[key]

    def remote_head(self, remote: str, branch: str) -> RemoteHead:
        key = (remote, branch)
        if key not in self.heads_cache:
            self.heads_cache[key] = read_remote_head(
                self.remote_git("ls-remote", "--heads", remote, f"refs/heads/{branch}"), branch
            )
        return self.heads_cache[key]

    def worktrees(self) -> tuple[set[str], Path | None] | str:
        """git 的工作資料夾清單與第一筆（主要工作資料夾）；查不到時回傳原因。"""
        if not self.worktree_cache:
            result = self.git("worktree", "list", "--porcelain")
            if result.code != 0:
                self.worktree_cache.append(f"git worktree list 查不到（{describe(result)}）")
            else:
                paths = [
                    Path(line.removeprefix("worktree "))
                    for line in result.stdout.splitlines()
                    if line.startswith("worktree ")
                ]
                main = paths[0] if paths else None
                self.worktree_cache.append(({path_key(path) for path in paths}, main))
        return self.worktree_cache[0]

    def default_branch(self, remote: str) -> str | None:
        """遠端的 HEAD 指到的分支：先看本機的 refs/remotes/<遠端>/HEAD，沒有再問遠端。

        查不到回傳 None；遠端沒有 HEAD 時回傳空字串。
        """
        if remote not in self.default_cache:
            result = self.git("symbolic-ref", "-q", f"refs/remotes/{remote}/HEAD")
            prefix = f"refs/remotes/{remote}/"
            head = result.stdout.strip()
            if result.code == 0 and head.startswith(prefix):
                self.default_cache[remote] = head.removeprefix(prefix)
            else:
                self.default_cache[remote] = read_symref(self.remote_git("ls-remote", "--symref", remote, "HEAD"))
        return self.default_cache[remote]

    def local_branch(self, name: str) -> bool | str:
        result = self.git("show-ref", "--verify", "--quiet", f"refs/heads/{name}")
        if result.code in (0, 1):
            return result.code == 0
        return f"git show-ref 查不到（{describe(result)}）"


class StopCheck(Exception):
    """比對沒辦法開始（例如 git 讀不到這個專案）。"""


class ApplyRefused(Exception):
    """--apply 不改紀錄的原因。"""


# ── 指令 ─────────────────────────────────────────────────────────


def run_command(args: Sequence[str], cwd: Path) -> CommandResult:
    """有時限、不接受輸入、關掉登入提示；不經過 shell。ssh 設定不動（見 Context.remote_git）。"""
    env = {**os.environ, **PROMPT_OFF_ENV}
    try:
        done = subprocess.run(
            list(args),
            cwd=cwd,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=TIMEOUT_SECONDS,
            env=env,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return CommandResult(None, "", f"{args[0]} 超過 {TIMEOUT_SECONDS} 秒沒有回應")
    except FileNotFoundError:
        return CommandResult(None, "", f"找不到 {args[0]}（沒有安裝或不在 PATH）")
    except OSError as error:
        return CommandResult(None, "", f"{args[0]} 跑不起來（{error}）")
    return CommandResult(done.returncode, done.stdout)


def describe(result: CommandResult) -> str:
    return result.problem if result.code is None else f"結束代碼 {result.code}"


def build_context(folder: Path, runner: Runner, environ: Mapping[str, str]) -> Context:
    """git 指令在紀錄所屬的專案裡跑；工作資料夾的相對路徑另從 git worktree list 第一筆算起。"""
    project = folder.parent.parent
    common = runner(("git", "rev-parse", "--path-format=absolute", "--git-common-dir"), project)
    if common.code != 0 or not common.stdout.strip():
        raise StopCheck(f"git 讀不到這個專案的 repo（{describe(common)}），沒有比對。")
    names = runner(("git", "remote"), project)
    if names.code != 0:
        raise StopCheck(f"git 讀不到遠端清單（{describe(names)}），沒有比對。")
    remotes: dict[str, str] = {}
    for name in names.stdout.split():
        url = runner(("git", "remote", "get-url", name), project)
        remotes[name] = url.stdout.strip() if url.code == 0 else ""
    # GitHub 的 owner/repo 不分大小寫，一律用小寫比。
    github = {
        name: match["repo"].lower()
        for name, url in remotes.items()
        if (match := GITHUB_REMOTE_PATTERN.match(url)) is not None
    }
    root = Path(common.stdout.strip()).parent
    return Context(runner, project, root, remotes, github, ssh_batch_allowed(runner, project, environ))


def ssh_batch_allowed(runner: Runner, project: Path, environ: Mapping[str, str]) -> bool:
    """使用者沒有自己的 ssh 設定（環境變數或 core.sshCommand）時才加 BatchMode；查不到就照原樣不加。"""
    if any(name in environ for name in USER_SSH_ENV):
        return False
    return runner(("git", "config", "--get", "core.sshCommand"), project).code == 1


def read_pulls(result: CommandResult, repo: str) -> list[PullRequest] | str:
    if result.code != 0:
        return f"gh 查不到 {repo} 的 PR（{describe(result)}）"
    try:
        return parse_pulls(result.stdout)
    except ValueError:
        return f"gh 回傳的 {repo} PR 資料看不懂"


def parse_pulls(text: str) -> list[PullRequest]:
    data = json.loads(text)
    if not isinstance(data, list):
        raise ValueError("不是清單")
    return [parse_pull(item) for item in data]


def parse_pull(item: object) -> PullRequest:
    if not isinstance(item, dict):
        raise ValueError("不是物件")
    merge = item.get("mergeCommit")
    merge_oid = merge.get("oid") if isinstance(merge, dict) else None
    fields = (item.get("number"), item.get("state"), item.get("headRefName"), item.get("headRefOid"))
    number, state, head, oid = fields
    if not rp.is_plain_int(number) or state not in ("OPEN", "CLOSED", "MERGED"):
        raise ValueError("編號或狀態不對")
    if not isinstance(head, str) or not isinstance(oid, str):
        raise ValueError("分支不對")
    cross = item.get("isCrossRepository")
    merged_at = item.get("mergedAt")
    if not isinstance(cross, bool) or not isinstance(merged_at, (str, type(None))):
        raise ValueError("欄位不對")
    if not isinstance(merge_oid, (str, type(None))):
        raise ValueError("合併 commit 不對")
    return PullRequest(number, state, head, oid, cross, merged_at, merge_oid)


def read_remote_head(result: CommandResult, branch: str) -> RemoteHead:
    if result.code != 0:
        return RemoteHead(None, problem=f"git ls-remote 查不到（{describe(result)}）")
    wanted = f"refs/heads/{branch}"
    for line in result.stdout.splitlines():
        sha, _, ref = line.partition("\t")
        if ref.strip() == wanted:
            return RemoteHead(True, sha.strip())
    return RemoteHead(False)


def read_symref(result: CommandResult) -> str | None:
    """git ls-remote --symref <遠端> HEAD 的「ref: refs/heads/<分支><tab>HEAD」；查不到回傳 None。"""
    if result.code != 0:
        return None
    for line in result.stdout.splitlines():
        target, _, name = line.partition("\t")
        if name.strip() == "HEAD" and target.startswith("ref: refs/heads/"):
            return target.removeprefix("ref: refs/heads/").strip()
    return ""


# ── 比對 ─────────────────────────────────────────────────────────


def check_record(ctx: Context, view: rp.RecordView) -> list[Outcome]:
    """工作清單先、暫存項目後，照列的順序。"""
    stem, work, temp = view.record.stem, view.work, view.temp
    outcomes: list[Outcome] = []
    # 工作清單用到的分支 → 這些列備註裡 PR 網址的 repo（判斷暫存項目的分支屬於哪個 repo）。
    branches: dict[str, set[str]] = {}
    if work is not None:
        for number, (status, row) in enumerate(zip(work.statuses, work.rows, strict=True), start=1):
            branch = clean_cell(row.get(BRANCH_COLUMN, ""))
            if is_branch(branch):
                repos = branches.setdefault(branch, set())
                repos.update(repo for repo, _ in note_urls(row.get(rp.NOTE_COLUMN, "")))
            outcomes.extend(check_work_row(ctx, Row(stem, rp.WORK, number, status, row)))
    if temp is not None:
        for number, (status, row) in enumerate(zip(temp.statuses, temp.rows, strict=True), start=1):
            outcomes.extend(check_temp_row(ctx, Row(stem, rp.TEMP, number, status, row), branches))
    return outcomes


@dataclass(frozen=True)
class Row:
    stem: str
    section: str
    number: int
    status: rp.StatusView
    cells: Mapping[str, str]

    @property
    def base(self) -> str:
        return self.status.base

    @property
    def raw(self) -> str:
        return self.status.raw or ""

    @property
    def note(self) -> str:
        return self.cells.get(rp.NOTE_COLUMN, "")

    @property
    def original(self) -> tuple[str, ...]:
        return tuple(value for key, value in self.cells.items() if key != rp.EXTRA_CELLS_COLUMN)

    def fix(self, status: str, note: str, change: str) -> Fix:
        summary = f"{self.section}第 {self.number} 列改{change}"
        return Fix(self.section, self.number, status, note, summary, self.original)

    def outcome(self, kind: str, message: str, fix: Fix | None = None) -> list[Outcome]:
        item = clip(next(iter(self.cells.values()), ""))
        finding = rp.SyncFinding(kind, clip(self.stem), self.section, self.number, item, clip(message))
        return [Outcome(finding, fix)]


def check_work_row(ctx: Context, row: Row) -> list[Outcome]:
    branch = clean_cell(row.cells.get(BRANCH_COLUMN, ""))
    # 已經是完成的狀態時，PR 怎樣都不會對不上，所以不查。
    if row.status.raw is None or row.base in MERGED_DONE or not is_branch(branch):
        return []
    urls = note_urls(row.note)
    if len(urls) > 1:
        return row.outcome(UNCHECKED, "這一列有不只一個 PR 網址")
    if urls:
        repo, url_number = next(iter(urls))
    else:
        if row.base == rp.TODO_STATUS:
            return []
        repos = set(ctx.github.values())
        if len(repos) != 1:
            return row.outcome(UNCHECKED, "沒有 PR 網址，專案也不是剛好一個 GitHub 遠端")
        repo, url_number = next(iter(repos)), None
    found = ctx.pulls(repo, branch)
    if isinstance(found, str):
        return row.outcome(UNREACHABLE, found)
    if not found:
        return row.outcome(UNCHECKED, f"網址的 PR 在 {repo} 查不到分支 {branch}") if urls else []
    problem = single_pull_problem(found, branch, url_number)
    if problem is not None:
        return row.outcome(UNCHECKED, problem)
    pull = found[0]
    if pull.state == "MERGED" and row.base not in MERGED_DONE:
        fix = None
        if url_number is not None and repo in ctx.github.values():
            fix = row.fix(MERGED_STATUS, append_note(row.note, merged_note(pull)), MERGED_STATUS)
        return row.outcome(rp.SYNC_MISMATCH, f"PR #{pull.number} 已合併，狀態卻是「{row.raw}」", fix)
    if pull.state == "CLOSED" and row.base in IN_REVIEW:
        return row.outcome(rp.SYNC_MISMATCH, f"PR #{pull.number} 已關閉沒有合併，狀態還是「{row.raw}」")
    return []


def single_pull_problem(found: Sequence[PullRequest], branch: str, url_number: int | None) -> str | None:
    """剛好一個、不是從 fork 開的、分支一致，而且（有網址時）就是網址那個 PR，才比對。"""
    if len(found) > 1:
        more = "以上的" if len(found) >= int(GH_PR_LIMIT) else ""
        return f"分支 {branch} 有 {len(found)} 個{more} PR"
    pull = found[0]
    if pull.cross:
        return f"PR #{pull.number} 是從 fork 開的"
    if url_number is not None and pull.number != url_number:
        return f"網址是 #{url_number}，分支查到的是 #{pull.number}"
    if pull.head != branch:
        return f"PR #{pull.number} 的分支是 {pull.head}，和工作分支欄不同"
    return None


def check_temp_row(ctx: Context, row: Row, branches: Mapping[str, set[str]]) -> list[Outcome]:
    if row.status.raw is None:
        return []
    kind = clean_cell(row.cells.get(TYPE_COLUMN, ""))
    if kind == TYPE_REMOTE:
        return check_remote(ctx, row, branches)
    if kind == TYPE_WORKTREE:
        return check_worktree(ctx, row)
    if kind == TYPE_LOCAL:
        return check_local(ctx, row)
    return []


@dataclass(frozen=True)
class RemoteTarget:
    remote: str
    branch: str
    # 從「位置」欄認出來的才給 --apply 改；從「項目」欄認出來的只偵測。
    from_location: bool


def check_remote(ctx: Context, row: Row, branches: Mapping[str, set[str]]) -> list[Outcome]:
    cleaned = row.base == rp.CLEANED_STATE
    target = remote_target(ctx, row.cells, branches)
    if target is None:
        if cleaned:
            return []
        return row.outcome(UNCHECKED, "位置不是「<遠端>/<分支>」，也不是這個任務用到的分支名")
    repo = ctx.github.get(target.remote)
    urls = branches.get(target.branch, set())
    if urls and repo not in urls:
        if cleaned:
            return []
        others = "、".join(sorted(urls))
        if repo is None:
            message = f"遠端 {target.remote} 不是 GitHub，對不上這個分支的 PR 網址（{others}），不判斷"
        else:
            message = f"這個分支的 PR 網址指向別的 repo（{others}），不拿 {target.remote} 判斷"
        return row.outcome(UNCHECKED, message)
    head = ctx.remote_head(target.remote, target.branch)
    if head.found is None:
        return row.outcome(UNREACHABLE, head.problem)
    name = f"{target.remote}/{target.branch}"
    # 只有位置欄寫明、而且同一份紀錄有這個分支屬於這個遠端的 PR 網址時，才給 --apply 改。
    fixable = target.from_location and repo is not None and repo in urls
    if not head.found:
        if cleaned:
            return []
        fix = row.fix(rp.CLEANED_STATE, row.note, rp.CLEANED_STATE) if fixable else None
        return row.outcome(rp.SYNC_MISMATCH, f"遠端分支 {name} 已經不在，狀態卻是「{row.raw}」", fix)
    if cleaned:
        return row.outcome(rp.SYNC_MISMATCH, f"寫已清理，但遠端分支 {name} 還在")
    return check_merged_remote(ctx, row, target, head, fixable)


def check_merged_remote(
    ctx: Context, row: Row, target: RemoteTarget, head: RemoteHead, fixable: bool
) -> list[Outcome]:
    """和刪遠端分支的前三個條件相同：不是預設或共用分支、PR 已合併、遠端目前的 commit 等於合併時的 head。"""
    remote, branch = target.remote, target.branch
    repo = ctx.github.get(remote)
    if repo is None:
        if row.base != IN_USE_STATE:
            return []
        return row.outcome(UNCHECKED, f"遠端 {remote} 不是 GitHub，查不到 PR")
    shared = f"{branch} 是預設或共用分支，不判斷可不可以刪"
    if cc.is_shared_branch(branch):
        return [] if row.base != IN_USE_STATE else row.outcome(UNCHECKED, shared)
    found = ctx.pulls(repo, branch)
    if isinstance(found, str):
        return row.outcome(UNREACHABLE, found)
    if not found:
        return []
    problem = single_pull_problem(found, branch, None)
    if problem is not None:
        return row.outcome(UNCHECKED, problem)
    pull = found[0]
    if pull.state != "MERGED":
        return []
    if head.sha != pull.head_oid:
        return row.outcome(UNCHECKED, f"PR #{pull.number} 已合併，但分支之後又有新 commit，不算可以刪")
    if row.base != IN_USE_STATE:
        return []
    # 預設分支要連遠端才可能知道，只在其他條件都符合時才查。
    default = ctx.default_branch(remote)
    # 遠端沒有回報 HEAD 指向（空字串）也當成查不到，不靠共用名單單獨保護。
    if not default:
        return row.outcome(UNREACHABLE, f"查不到 {remote} 的預設分支，不判斷可不可以刪")
    if branch == default:
        return row.outcome(UNCHECKED, shared)
    fix = row.fix(rp.KEPT_STATE, waiting_note(row.note), rp.KEPT_STATE) if fixable else None
    message = (
        f"PR #{pull.number} 已合併、遠端分支和合併時一樣，狀態還是「{row.raw}」："
        "應改「保留」等你決定刪不刪"
    )
    return row.outcome(rp.SYNC_MISMATCH, message, fix)


def remote_target(
    ctx: Context, cells: Mapping[str, str], branches: Mapping[str, set[str]]
) -> RemoteTarget | None:
    """先看位置、再看項目：寫成 <遠端>/<分支>，或只有一個遠端時這個任務用到的分支名。"""
    for column in (LOCATION_COLUMN, ITEM_COLUMN):
        text = clean_cell(cells.get(column, ""))
        first, slash, rest = text.partition("/")
        if slash and first in ctx.remotes and is_branch(rest):
            return RemoteTarget(first, rest, column == LOCATION_COLUMN)
        if is_branch(text) and len(ctx.remotes) == 1 and text in branches:
            return RemoteTarget(next(iter(ctx.remotes)), text, column == LOCATION_COLUMN)
    return None


def check_worktree(ctx: Context, row: Row) -> list[Outcome]:
    cleaned = row.base == rp.CLEANED_STATE
    text = clean_cell(row.cells.get(LOCATION_COLUMN, ""))
    if not looks_like_path(text):
        return [] if cleaned else row.outcome(UNCHECKED, "位置不是路徑")
    listing = ctx.worktrees()
    if isinstance(listing, str):
        return row.outcome(UNREACHABLE, listing)
    keys, main = listing
    path = Path(text)
    if not path.is_absolute():
        path = (main or ctx.root) / path
    listed = path_key(path) in keys
    on_disk = os.path.lexists(path)
    if listed != on_disk:
        where = "git 的清單有、磁碟上沒有" if listed else "磁碟上有、git 的清單沒有"
        return row.outcome(UNCHECKED, f"工作資料夾{where}")
    if not listed and not cleaned:
        # 上一層資料夾還在，才算位置寫的是真的地方，給 --apply 改。
        fixable = os.path.isdir(path.parent)
        fix = row.fix(rp.CLEANED_STATE, row.note, rp.CLEANED_STATE) if fixable else None
        message = f"工作資料夾已經不在（git 清單和磁碟都沒有），狀態卻是「{row.raw}」"
        return row.outcome(rp.SYNC_MISMATCH, message, fix)
    if listed and cleaned:
        return row.outcome(rp.SYNC_MISMATCH, "寫已清理，但工作資料夾還在")
    return []


def check_local(ctx: Context, row: Row) -> list[Outcome]:
    """本機分支只有 git show-ref 一個依據，所以只偵測、不給 --apply 改。"""
    cleaned = row.base == rp.CLEANED_STATE
    names = [clean_cell(row.cells.get(column, "")) for column in (LOCATION_COLUMN, ITEM_COLUMN)]
    name = next((candidate for candidate in names if is_branch(candidate)), None)
    if name is None:
        return [] if cleaned else row.outcome(UNCHECKED, "位置與項目都不是分支名")
    exists = ctx.local_branch(name)
    if isinstance(exists, str):
        return row.outcome(UNREACHABLE, exists)
    if not exists and not cleaned:
        return row.outcome(rp.SYNC_MISMATCH, f"本機分支 {name} 已經不在（只查了這個 repo），狀態卻是「{row.raw}」")
    if exists and cleaned:
        return row.outcome(rp.SYNC_MISMATCH, f"寫已清理，但本機分支 {name} 還在")
    return []


# ── 小工具 ───────────────────────────────────────────────────────


def clean_cell(text: str) -> str:
    """去掉前後空白；整格是一段 `code` 時去掉反引號。"""
    stripped = text.strip()
    if len(stripped) >= 2 and stripped[0] == stripped[-1] == "`":
        return stripped[1:-1].strip()
    return stripped


def is_branch(text: str) -> bool:
    return (
        BRANCH_PATTERN.fullmatch(text) is not None
        and not text.startswith(("-", "/"))
        and not text.endswith(("/", ".lock", "."))
        and ".." not in text
        and "//" not in text
    )


def looks_like_path(text: str) -> bool:
    """不含空白與全形字、不是網址或網路路徑，而且是絕對路徑或含分隔符號。"""
    if PATH_PATTERN.fullmatch(text) is None or "://" in text:
        return False
    if text.startswith(("\\\\", "//")):
        return False
    return Path(text).is_absolute() or "/" in text or "\\" in text


def note_urls(note: str) -> set[tuple[str, int]]:
    """只從備註欄讀 PR 網址（紀錄格式：開 PR 時那一列的備註寫完整網址）；repo 用小寫比。"""
    return {(match["repo"].lower(), int(match["number"])) for match in PR_URL_PATTERN.finditer(note)}


def path_key(path: Path) -> str:
    return os.path.normcase(os.path.abspath(path))


def clip(text: str) -> str:
    limit = rp.SYNC_MAX_TEXT
    return text if len(text) <= limit else text[: limit - 1] + "…"


def append_note(note: str, text: str) -> str:
    current = note.strip()
    return text if current in EMPTY_NOTES else f"{current}{NOTE_JOINER}{text}"


def waiting_note(note: str) -> str:
    """網頁只認備註開頭的「等你決定」；原本的字接在後面。"""
    current = note.strip()
    return WAITING_NOTE if current in EMPTY_NOTES else f"{WAITING_NOTE}{current}"


def merged_note(pull: PullRequest) -> str:
    moment = parse_github_time(pull.merged_at)
    when = short_time(moment) if moment is not None else "時間不明"
    sha = (pull.merge_oid or "")[:8]
    return f"PR 已合併 {when}（{sha}）" if sha else f"PR 已合併 {when}"


def parse_github_time(value: object) -> float | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def short_time(epoch: float) -> str:
    """紀錄用的本機時間 M/DD HH:MM。"""
    moment = time.localtime(epoch)
    return f"{moment.tm_mon}/{moment.tm_mday:02d} {moment.tm_hour:02d}:{moment.tm_min:02d}"


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# ── --apply：只改固定欄位 ─────────────────────────────────────────


def apply_task(
    ctx: Context, folder: Path, task: str, clock: Callable[[], float]
) -> tuple[list[Outcome], int, list[str]]:
    """回傳（改完後剩下的結果、紀錄的修改時間、改了哪些列）；不能改時丟 ApplyRefused。"""
    if rp.TASK_CODE_PATTERN.fullmatch(task) is None or task in rp.RESERVED_TASK_CODES:
        raise ApplyRefused(f"任務代號「{task}」不合法")
    path = folder / f"{task}.md"
    problem = rp.entry_problem(path, False)
    if problem is not None:
        raise ApplyRefused(f"{path} 不能改：{problem}")
    raw = path.read_bytes()
    before = digest(raw)
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise ApplyRefused(f"{path} 不是 UTF-8，不改") from error
    if any(mark in text for mark in SPECIAL_LINE_BREAKS):
        raise ApplyRefused(f"{path} 有特殊的換行字元（例如 U+2028），不改；手動改這份紀錄")
    view = rp.analyze_record(rp.parse_record(text, task), path.name, int(os.stat(path).st_mtime))
    outcomes = check_record(ctx, view)
    fixes = [outcome.fix for outcome in outcomes if outcome.fix is not None]
    if not fixes:
        return outcomes, view.modified_epoch, []
    lines = text.splitlines(keepends=True)
    new_lines, changes, insert_at = build_edit(lines, fixes, short_time(clock()))
    verify_edit(lines, new_lines, changes, insert_at)
    if digest(path.read_bytes()) != before:
        raise ApplyRefused(f"{path} 在比對期間被改過，這次不改；重跑一次。")
    bom = codecs.BOM_UTF8 if raw.startswith(codecs.BOM_UTF8) else b""
    write_bytes_atomic(path, bom + "".join(new_lines).encode("utf-8"))
    remaining = [outcome for outcome in outcomes if outcome.fix is None]
    return remaining, int(os.stat(path).st_mtime), [fix.summary for fix in fixes]


def locate_tables(lines: Sequence[str]) -> dict[str, TableLocation]:
    """每個區段第一張表格的表頭與資料列位置；切區段與表格的方式和 render_progress.py 相同。"""
    blocks: dict[str, list[int]] = {}
    seen: set[str] = set()
    fenced: set[int] = set()
    current: str | None = None
    in_fence = False
    for index, line in enumerate(lines):
        content = line.rstrip("\r\n")
        if rp.FENCE_PATTERN.match(content):
            in_fence = not in_fence
        if in_fence:
            fenced.add(index)
        match = None if in_fence else rp.SECTION_PATTERN.match(content)
        if match is not None:
            title = match["title"]
            current = None if title in seen else title
            seen.add(title)
            continue
        if current is None:
            continue
        block = blocks.setdefault(current, [])
        if content.strip().startswith("|"):
            if block and block[-1] != index - 1:
                current = None
                continue
            block.append(index)
        elif block:
            current = None
    return {title: table_location(lines, block, fenced) for title, block in blocks.items() if block}


def table_location(lines: Sequence[str], block: Sequence[int], fenced: set[int]) -> TableLocation:
    body = list(block[1:])
    if body and rp.is_separator_row(rp.split_row(lines[body[0]].rstrip("\r\n"))):
        body = body[1:]
    return TableLocation(block[0], tuple(body), block[-1], any(index in fenced for index in block))


def build_edit(
    lines: Sequence[str], fixes: Sequence[Fix], stamp: str
) -> tuple[list[str], dict[int, set[int]], int]:
    tables = locate_tables(lines)
    new_lines = list(lines)
    changes: dict[int, set[int]] = {}
    for fix in fixes:
        location = tables.get(fix.section)
        if location is None or not 1 <= fix.row <= len(location.rows):
            raise ApplyRefused(f"找不到{fix.section}第 {fix.row} 列")
        if location.fenced:
            raise ApplyRefused(f"{fix.section}的表格在圍欄（```）裡，不改；手動改這份紀錄")
        columns = header_columns(lines, location)
        index = location.rows[fix.row - 1]
        cells = rp.split_row(lines[index].rstrip("\r\n"))
        if tuple(cells[: len(fix.original)]) != fix.original:
            raise ApplyRefused(f"{fix.section}第 {fix.row} 列和比對時的那一列對不起來，不改")
        targets = {columns[rp.STATUS_COLUMN]: fix.status, columns[rp.NOTE_COLUMN]: fix.note}
        if max(targets) >= len(cells):
            raise ApplyRefused(f"{fix.section}第 {fix.row} 列的格子不夠")
        for column, value in targets.items():
            cells[column] = value
        new_lines[index] = rebuild_row(lines[index], cells)
        changes[index] = set(targets)
    review = tables.get(rp.REVIEWS)
    if review is None:
        raise ApplyRefused("審核紀錄沒有表格，沒辦法加一列")
    if review.fenced:
        raise ApplyRefused("審核紀錄的第一張表格在圍欄（```）裡，不加列；手動改這份紀錄")
    last = review.end
    ending = lines[last][len(lines[last].rstrip("\r\n")) :]
    if not ending:
        raise ApplyRefused("審核紀錄的表格在檔案最後一行，先換行再跑")
    names = rp.header_names(rp.split_row(lines[review.header].rstrip("\r\n")))
    values = {rp.REVIEW_TIME_COLUMN: stamp, **REVIEW_CELLS, rp.NOTE_COLUMN: "；".join(fix.summary for fix in fixes)}
    cells = [values.get(name, "—") for name in names]
    new_lines.insert(last + 1, rebuild_row("", cells) + ending)
    return new_lines, changes, last + 1


def header_columns(lines: Sequence[str], location: TableLocation) -> dict[str, int]:
    names = rp.header_names(rp.split_row(lines[location.header].rstrip("\r\n")))
    if rp.STATUS_COLUMN not in names or rp.NOTE_COLUMN not in names:
        raise ApplyRefused("表格缺「狀態」或「備註」欄")
    return {name: position for position, name in enumerate(names)}


def rebuild_row(line: str, cells: Sequence[str]) -> str:
    """保留原本的縮排與換行；格子裡的 | 照紀錄格式寫成 \\|。"""
    content = line.rstrip("\r\n")
    ending = line[len(content) :]
    indent = content[: len(content) - len(content.lstrip())]
    escaped = (cell.replace("|", "\\|") for cell in cells)
    return f"{indent}| {' | '.join(escaped)} |{ending}"


def verify_edit(
    old: Sequence[str], new: Sequence[str], changes: Mapping[int, set[int]], insert_at: int
) -> None:
    """新舊內容只差目標格子和新加的那一列；其他行一字不動。"""
    if len(new) != len(old) + 1:
        raise ApplyRefused("改動後的行數不對，不改")
    for index, line in enumerate(old):
        updated = new[index if index < insert_at else index + 1]
        if index not in changes:
            if updated != line:
                raise ApplyRefused(f"第 {index + 1} 行會被改到，不改")
            continue
        before = rp.split_row(line.rstrip("\r\n"))
        after = rp.split_row(updated.rstrip("\r\n"))
        same_ending = line[len(line.rstrip("\r\n")) :] == updated[len(updated.rstrip("\r\n")) :]
        if len(before) != len(after) or not same_ending:
            raise ApplyRefused(f"第 {index + 1} 行的格子數或換行不同，不改")
        for column, (was, now) in enumerate(zip(before, after, strict=True)):
            if column not in changes[index] and was != now:
                raise ApplyRefused(f"第 {index + 1} 行有不該改的格子，不改")


def write_bytes_atomic(path: Path, data: bytes) -> None:
    """先寫同資料夾的暫存檔再整份替換；替換前再確認目標不是連結。"""
    mode = stat.S_IMODE(os.stat(path).st_mode)
    descriptor, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temp = Path(temp_name)
    try:
        with open(descriptor, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temp, mode)
        problem = rp.entry_problem(path, False)
        if problem is not None:
            raise ApplyRefused(f"{path} 不能改：{problem}")
        os.replace(temp, path)
    except BaseException:
        temp.unlink(missing_ok=True)
        raise


# ── 整個資料夾 ───────────────────────────────────────────────────


@dataclass
class Report:
    records: dict[str, int] = field(default_factory=dict)
    outcomes: list[Outcome] = field(default_factory=list)
    unreadable: list[str] = field(default_factory=list)
    applied: list[str] = field(default_factory=list)

    @property
    def findings(self) -> list[rp.SyncFinding]:
        items = [outcome.finding for outcome in self.outcomes]
        items.sort(key=lambda item: item.kind != rp.SYNC_MISMATCH)
        return items[: rp.SYNC_MAX_FINDINGS]

    @property
    def failed(self) -> bool:
        kinds = {outcome.finding.kind for outcome in self.outcomes}
        return bool(self.unreadable) or bool(kinds & {rp.SYNC_MISMATCH, UNREACHABLE})


def collect(ctx: Context, folder: Path, skip: str | None) -> Report:
    report = Report()
    tasks, _ = rp.split_board(rp.list_records(folder))
    for path in tasks:
        if skip is not None and path.stem == skip:
            continue
        try:
            view = rp.load_view(path)
        except rp.RenderError as error:
            report.unreadable.append(str(error))
            continue
        report.records[view.record.stem] = view.modified_epoch
        report.outcomes.extend(check_record(ctx, view))
    return report


def write_status(folder: Path, report: Report, checked_at: int) -> Path:
    payload = {
        "format": rp.SYNC_FORMAT,
        "version": rp.SYNC_VERSION,
        "checked_at": checked_at,
        "records": dict(sorted(report.records.items())),
        "findings": [
            {
                "kind": item.kind,
                "record": item.record,
                "section": item.section,
                "row": item.row,
                "item": item.item,
                "message": item.message,
            }
            for item in report.findings
        ],
    }
    rp.parse_sync_payload(payload)
    path = folder / rp.SYNC_STATUS_FILENAME
    rp.write_atomic(path, json.dumps(payload, ensure_ascii=False, indent=1) + "\n")
    return path


def print_report(report: Report, path: Path) -> None:
    findings = report.findings
    mismatches = [item for item in findings if item.kind == rp.SYNC_MISMATCH]
    others = [item for item in findings if item.kind != rp.SYNC_MISMATCH]
    if report.applied:
        emit("已更新紀錄：" + "；".join(report.applied))
    if mismatches:
        emit(f"{rp.SYNC_SUMMARY} {len(mismatches)} 項：")
        for item in mismatches:
            emit(f"- {item.record}：{item.section}第 {item.row} 列「{item.item}」：{item.message}")
    else:
        emit("都對得上：沒有發現紀錄和實際狀態不一樣的地方。")
    for item in others:
        label = rp.SYNC_KINDS[item.kind]
        emit(f"-【{label}】{item.record}：{item.section}第 {item.row} 列「{item.item}」：{item.message}")
    for message in report.unreadable:
        emit_error(message)
    emit(f"結果寫在 {path}")


def emit(text: str) -> None:
    print(text)


def emit_error(text: str) -> None:
    print(text, file=sys.stderr)


def parse_arguments(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="比對進度紀錄和 git、GitHub 的實際狀態。")
    parser.add_argument("folder", help=".toukadev/progress 資料夾")
    parser.add_argument("--apply", action="store_true", help="只由主代理執行：改自己那份紀錄的固定欄位")
    parser.add_argument("--task", help="--apply 要改的任務代號")
    return parser.parse_args(argv)


def main(
    argv: Sequence[str] | None = None,
    runner: Runner | None = None,
    clock: Callable[[], float] | None = None,
    environ: Mapping[str, str] | None = None,
) -> int:
    rp.configure_streams()
    if sys.version_info[:2] < MINIMUM_PYTHON:
        emit_error("這支程式需要 Python 3.12 以上。")
        return 2
    try:
        args = parse_arguments(argv)
    except SystemExit as error:
        # --help 是 0，參數錯誤是 2。
        return error.code if isinstance(error.code, int) else 2
    if args.apply != (args.task is not None):
        emit_error("--apply 和 --task 要一起用。")
        return 2
    folder = Path(args.folder).absolute()
    problem = rp.other_folder_problem(folder)
    if problem is not None:
        emit_error(f"不處理 {folder}：{problem}；只比對 .toukadev/progress 資料夾。")
        return 2
    clock = clock or time.time
    checked_at = int(clock())
    report: Report | None = None
    try:
        ctx = build_context(folder, runner or run_command, os.environ if environ is None else environ)
        report = collect(ctx, folder, args.task)
        # 份數在改紀錄之前就檢查，超過時什麼都不改。
        if len(report.records) + (args.task is not None) > rp.SYNC_MAX_FINDINGS:
            raise StopCheck(
                f"紀錄超過 {rp.SYNC_MAX_FINDINGS} 份，結果檔放不下；先把舊紀錄搬到 archive 再比對。"
            )
        if args.task is not None:
            remaining, modified, applied = apply_task(ctx, folder, args.task, clock)
            report.records[args.task] = modified
            report.outcomes.extend(remaining)
            report.applied = applied
            if not applied:
                emit("沒有要改的固定欄位。")
        path = write_status(folder, report, checked_at)
    except (StopCheck, ApplyRefused) as error:
        emit_error(str(error))
        return 1
    except (OSError, rp.SyncFormatError, rp.RenderError) as error:
        # 紀錄已經改了才失敗時，照樣列出改了哪些列。
        if report is not None and report.applied:
            emit("已更新紀錄：" + "；".join(report.applied))
        emit_error(f"沒有完成：{error}")
        return 1
    print_report(report, path)
    return 1 if report.failed else 0


if __name__ == "__main__":
    sys.exit(main())

"""清理前檢查：只檢查，不刪除。

用法（在主要的專案資料夾執行）：
    python check_cleanup.py worktree <工作資料夾路徑> --branch <分支名>
    python check_cleanup.py tmp <暫存資料夾路徑> --task <任務代號>
    python check_cleanup.py branch <分支名>

全部條件都符合才印「可以清理」並 exit 0；否則列出每個原因並 exit 1。
這支程式只讀：不刪除、不修改任何檔案或 git 狀態（git 一律加 --no-optional-locks）。
工作資料夾裡只允許可重建快取（.venv 等）裡面的 POSIX symlink；junction 與其他
reparse point 不論在哪裡都不通過。
也不通過：skip-worktree／assume-unchanged 的檔案、巢狀的 .git（不分大小寫，快取裡外都算；
只有快取裡 uv 這類工具放的 0 位元組 .git 標記檔不算 repo）、掛載到其他磁碟的資料夾。
被忽略的建置產物，只有在 origin/HEAD 指到的預設分支上、根目錄 rebuildable-outputs.txt（一行一個路徑）
列出時才當可重建；任何一行不合法就整份不採用。列出的路徑本身與底下一律不沿用快取豁免，bare repo 也擋。
真正的刪除仍依 dev-workflow 的 progress-record.md 規定的安全刪法進行；
其他項目、條件不確定或指令失敗時，先問人類。只用 Python 3.12 標準函式庫。
"""

from __future__ import annotations

import argparse
import io
import os
import re
import stat
import string
import subprocess
import sys
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

MINIMUM_PYTHON = (3, 12)
SHARED_BRANCH_NAMES = ("main", "master", "dev", "develop", "trunk")
FALLBACK_DEFAULT_BRANCHES = ("main", "dev")
REBUILDABLE_CACHES = frozenset(
    {
        ".venv",
        ".uv-cache",
        ".ruff_cache",
        ".pytest_cache",
        ".mypy_cache",
        "__pycache__",
        "node_modules",
    }
)
TASK_CODE_PATTERN = re.compile(r"^[a-z0-9-]+$")
RESERVED_TASK_CODE = "index"
TOUKADEV_FOLDER = ".toukadev"
WORKTREES_FOLDER = "worktrees"
TMP_FOLDER = "tmp"
BRANCH_REF_PREFIX = "refs/heads/"
MAX_LISTED = 10
ORIGIN_HEAD = "refs/remotes/origin/HEAD"
ORIGIN_PREFIX = "refs/remotes/origin/"
DECLARATION_FILE = "rebuildable-outputs.txt"
LIST_MARKER = re.compile(r"(?:[-*+]|\d+[.)])\s")
VOID_NOTE = "任一條不合法就整份不採用"
ASCII_LOWER = str.maketrans(string.ascii_uppercase, string.ascii_lowercase)


class CheckError(Exception):
    """檢查沒辦法完成（找不到 git、不在主要的專案資料夾等）。"""


@dataclass
class Verdict:
    target: str
    reasons: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.reasons


@dataclass(frozen=True)
class WorktreeEntry:
    path: Path
    branch_ref: str | None


@dataclass(frozen=True)
class Declaration:
    """keys 只在採用時有值；revoked（檔案列出的路徑）採不採用都取消快取豁免；found 時一律印 message。"""

    keys: tuple[str, ...] = ()
    revoked: tuple[str, ...] = ()
    message: str | None = None
    found: bool = False


# ── 共用 ─────────────────────────────────────────────────────────


def run_git(
    args: Sequence[str], cwd: Path, stdin: bytes | None = None
) -> subprocess.CompletedProcess[bytes]:
    """只執行讀取用的 git 指令；--no-optional-locks 讓 git status 不改寫 index。"""
    try:
        return subprocess.run(
            ["git", "--no-optional-locks", "-C", str(cwd), *args],
            input=stdin,
            capture_output=True,
            check=False,
        )
    except OSError as error:
        raise CheckError(f"沒辦法執行 git：{error}") from error


def git_output(args: Sequence[str], cwd: Path) -> str | None:
    completed = run_git(args, cwd)
    if completed.returncode != 0:
        return None
    return completed.stdout.decode("utf-8", errors="replace")


def find_repo_root(start: Path) -> Path:
    """由目前目錄往上找含 .git 資料夾的主要專案資料夾。"""
    current = start.resolve()
    for candidate in (current, *current.parents):
        marker = candidate / ".git"
        if marker.is_dir():
            return candidate
        if marker.exists():
            raise CheckError(
                f"{candidate} 是工作資料夾，不是主要的專案資料夾；"
                "請到主要的專案資料夾執行。"
            )
    raise CheckError("往上找不到含 .git 的專案資料夾，請在專案資料夾裡執行。")


def resolve_argument(argument: str, cwd: Path) -> Path:
    path = Path(argument)
    return path if path.is_absolute() else cwd / path


def same_path(first: Path, second: Path) -> bool:
    return os.path.normcase(str(first)) == os.path.normcase(str(second))


def is_link(path: Path) -> bool:
    """symlink、junction，或 Windows 上帶 reparse point 屬性的項目。"""
    try:
        info = os.lstat(path)
    except OSError:
        return False
    return is_link_stat(info) or path.is_junction()


def is_link_stat(info: os.stat_result) -> bool:
    attributes = getattr(info, "st_file_attributes", 0)
    return stat.S_ISLNK(info.st_mode) or bool(
        attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT
    )


def list_worktrees(root: Path) -> list[WorktreeEntry]:
    output = git_output(["worktree", "list", "--porcelain", "-z"], root)
    if output is None:
        raise CheckError("讀不到 git worktree list。")
    entries: list[WorktreeEntry] = []
    path: Path | None = None
    branch_ref: str | None = None
    for line in [*output.split("\0"), ""]:
        if line.startswith("worktree "):
            path = Path(line.removeprefix("worktree ")).resolve()
        elif line.startswith("branch "):
            branch_ref = line.removeprefix("branch ")
        elif not line and path is not None:
            entries.append(WorktreeEntry(path, branch_ref))
            path, branch_ref = None, None
    return entries


def summarize(paths: Sequence[str]) -> str:
    shown = "、".join(paths[:MAX_LISTED])
    extra = f"（共 {len(paths)} 項）" if len(paths) > MAX_LISTED else ""
    return shown + extra


# ── worktree ─────────────────────────────────────────────────────


def check_worktree(root: Path, target: Path, branch: str) -> Verdict:
    verdict = Verdict(str(target))
    if not target.exists() and not is_link(target):
        verdict.reasons.append("找不到這個資料夾。")
        return verdict
    if is_link(target):
        verdict.reasons.append(
            "這個位置本身是捷徑連結（symlink／junction），不能自動清理。"
        )
        return verdict
    resolved = target.resolve()
    check_worktree_location(root, resolved, verdict)
    declaration, used = Declaration(), False
    if check_registered(root, resolved, verdict):
        declaration = read_declaration(root, resolved)
        check_head(resolved, branch, verdict)
        used = check_status(resolved, verdict, declaration)
        check_hidden_flags(resolved, verdict)
    check_tree(resolved, verdict, declaration.revoked)
    if declaration.found and declaration.message and (used or not verdict.ok or not declaration.keys):
        verdict.notes.append(declaration.message)
    return verdict


def check_worktree_location(root: Path, resolved: Path, verdict: Verdict) -> None:
    folder = root / TOUKADEV_FOLDER / WORKTREES_FOLDER
    if resolved.is_relative_to(folder) and not same_path(resolved, folder):
        return
    verdict.reasons.append(
        f"不在這個專案的 .toukadev/worktrees/ 底下（{folder}）；"
        "工具自己管理或放在別處的工作資料夾不自動清理。"
    )


def check_registered(root: Path, resolved: Path, verdict: Verdict) -> bool:
    """主要專案資料夾本身不算；只認 git worktree list 裡的其他工作資料夾。"""
    entries = list_worktrees(root)
    if any(same_path(entry.path, resolved) for entry in entries[1:]):
        return True
    verdict.reasons.append("git 不認得這個工作資料夾（git worktree list 裡沒有它）。")
    return False


def check_head(resolved: Path, branch: str, verdict: Verdict) -> None:
    expected = BRANCH_REF_PREFIX + branch.removeprefix(BRANCH_REF_PREFIX)
    head = git_output(["symbolic-ref", "-q", "HEAD"], resolved)
    if head is None:
        verdict.reasons.append(
            "工作資料夾的 HEAD 沒有指向分支（detached），可能有沒存到分支的 commit。"
        )
    elif head.strip() != expected:
        current = head.strip().removeprefix(BRANCH_REF_PREFIX)
        verdict.reasons.append(
            f"工作資料夾目前在分支 {current}，不是指定的 {expected.removeprefix(BRANCH_REF_PREFIX)}。"
        )


def check_status(resolved: Path, verdict: Verdict, declaration: Declaration) -> bool:
    """回傳有沒有被忽略的項目靠宣告才不擋（沒有就不印「已採用宣告」，輸出和沒有宣告一樣）。"""
    completed = run_git(
        ["status", "--porcelain=v1", "-z", "--ignored=matching"], resolved
    )
    if completed.returncode != 0:
        verdict.reasons.append("讀不到 git status，無法確認有沒有未存檔的東西。")
        return False
    changed, untracked, ignored = classify_status(completed.stdout)
    if changed:
        verdict.reasons.append(f"有還沒存檔（commit）的改動：{summarize(changed)}")
    if untracked:
        verdict.reasons.append(f"有還沒加入 git 的檔案：{summarize(untracked)}")
    keys = declaration.keys
    blocked = [p for p in ignored if not (is_rebuildable(p) or is_declared(p, keys))]
    if blocked:
        verdict.reasons.append(
            "有被 git 忽略、但不是可重建快取或已宣告建置產物的東西（可能是資料或設定）："
            f"{summarize(blocked)}"
        )
        if declaration.message is not None and not declaration.found:
            verdict.notes.append(declaration.message)
    return any(is_declared(p, keys) and not is_rebuildable(p) for p in ignored)


def classify_status(raw: bytes) -> tuple[list[str], list[str], list[str]]:
    changed: list[str] = []
    untracked: list[str] = []
    ignored: list[str] = []
    entries = raw.decode("utf-8", errors="replace").split("\0")
    index = 0
    while index < len(entries):
        entry = entries[index]
        index += 1
        if len(entry) < 4:
            continue
        code, path = entry[:2], entry[3:]
        if code == "!!":
            ignored.append(path)
        elif code == "??":
            untracked.append(path)
        else:
            changed.append(path)
            if "R" in code or "C" in code:
                index += 1
    return changed, untracked, ignored


def is_rebuildable(path: str) -> bool:
    parts = [part for part in path.replace("\\", "/").split("/") if part]
    return any(part in REBUILDABLE_CACHES for part in parts)


def read_declaration(root: Path, worktree: Path) -> Declaration:
    """只讀 origin/HEAD 指到的遠端預設分支上的根 rebuildable-outputs.txt；不退回 main／dev 或目前分支。

    沒有這個檔、空檔或只有空行＝沒有宣告，不印附註。每個非空行都是路徑（BOM 與行尾 \\r 去掉）。
    """
    ref = (git_output(["symbolic-ref", "-q", ORIGIN_HEAD], root) or "").strip()
    if not ref.startswith(ORIGIN_PREFIX) or ref == ORIGIN_HEAD:
        return unused(f"讀不到 {ORIGIN_HEAD} 指到的遠端預設分支")
    commit = (git_output(["rev-parse", "--verify", "-q", f"{ref}^{{commit}}"], root) or "").strip()
    if not commit:
        return unused(f"讀不到預設分支 {ref}")
    mode = (git_output(["ls-tree", commit, "--", DECLARATION_FILE], root) or "").split(" ")[0]
    if mode and mode not in ("100644", "100755"):
        return unused(f"預設分支 {ref} 上的 {DECLARATION_FILE} 不是一般檔（例如 symlink）", True)
    text = git_output(["cat-file", "blob", f"{commit}:{DECLARATION_FILE}"], root) or ""
    lines = [line.removesuffix("\r") for line in text.removeprefix("\ufeff").split("\n")]
    entries = [(number, path) for number, path in enumerate(lines, 1) if path]
    if not entries:
        return Declaration()
    branch = ref.removeprefix(ORIGIN_PREFIX)
    taken = {(entry.branch_ref or "").casefold() for entry in list_worktrees(root)[1:]}
    if (BRANCH_REF_PREFIX + branch).casefold() in taken:
        return unused(f"{ref} 和工作資料夾的分支 {branch} 同名", True)
    problem = None
    for number, path in entries:
        reason = None if problem else path_problem(path) or ignore_problem(worktree, path)
        if reason is not None:
            shown = path if path.isprintable() else repr(path)  # 看不見的字元用跳脫字元顯示
            problem = f"{DECLARATION_FILE} 第 {number} 行「{shown}」{reason}，{VOID_NOTE}"
    revoked = tuple(path_key(path) for _, path in entries)
    if problem is not None:
        return unused(f"預設分支 {ref} 上的 {problem}", True, revoked)
    listed = summarize([path for _, path in entries])
    return Declaration(revoked, revoked, f"已採用宣告（{ref} @ {commit[:7]}）：{listed}", True)


def unused(reason: str, found: bool = False, revoked: tuple[str, ...] = ()) -> Declaration:
    return Declaration((), revoked, f"這次沒有採用建置產物宣告：{reason}。", found)


def path_problem(path: str) -> str | None:
    """宣告路徑的格式；合法時回傳 None。"""
    parts = path.removesuffix("/").split("/")
    if not path.isprintable() or not path.strip() or path != path.strip():
        return "是空的、前後有空白，或含看不見的字元（控制字元、零寬字元、多出來的 BOM 等）"
    if LIST_MARKER.match(path) or "`" in path or " #" in path or any(p.startswith("#") for p in parts):
        return "含清單符號、反引號、行尾註解（空白後接 #）或 # 開頭的段（每行只能是路徑本身）"
    if path.startswith("/") or ":" in path or "\\" in path:
        return "不是從 repo 根算起、用 / 分隔的相對路徑（不得是絕對路徑或含磁碟代號）"
    if any(mark in path for mark in "*?["):
        return "含萬用字元（*、?、[）"
    if any(part in ("", ".", "..") for part in parts):
        return "含空的、. 或 .. 路徑段"
    if any(part.casefold() in (".git", TOUKADEV_FOLDER) for part in parts):
        return "指到 .git 或 .toukadev"
    if any(part.casefold() in REBUILDABLE_CACHES for part in parts):
        return "已是可重建快取，不必宣告"
    return None


def ignore_problem(worktree: Path, path: str) -> str | None:
    """宣告路徑要在被清理的工作資料夾裡被 git 忽略；加不加尾斜線都試（認得 dist/ 規則）。

    只認非空、不是 ! 開頭的規則：CRLF 檔裡只有 \\r 的空行，git 會讀成空規則、命中任何加尾斜線的路徑；
    -v 也會列出命中的 ! 規則。
    """
    forms = (path.removesuffix("/"), path.removesuffix("/") + "/")
    data = b"".join(form.encode("utf-8") + b"\0" for form in forms)
    done = run_git(["check-ignore", "-v", "-z", "--stdin"], worktree, data)
    if done.returncode not in (0, 1):
        return "沒辦法用 git check-ignore 確認有沒有被忽略"
    rules = done.stdout.split(b"\0")[2::4]  # 每筆四欄：來源、行號、規則、路徑
    if any(rule and not rule.startswith(b"!") for rule in rules):
        return None
    tracked = (git_output(["ls-files", "-z", "--", forms[0]], worktree) or "").split("\0")
    if tracked[0]:
        return f"在這個工作資料夾裡沒被 git 忽略：底下有被 git 追蹤的檔（例如 {tracked[0]}）"
    return "在這個工作資料夾裡沒被 git 忽略（git check-ignore）"


def path_key(path: str) -> str:
    """比對用的路徑：Windows 上只把 ASCII 字母轉小寫、\\ 當成 /；去掉結尾的 /。"""
    if os.name == "nt":
        path = path.replace("\\", "/").translate(ASCII_LOWER)
    return path.rstrip("/")


def is_declared(path: str, keys: Sequence[str]) -> bool:
    """等於某個宣告路徑或在它底下；逐段比對（dist 不涵蓋 dist-data）。"""
    key = path_key(path)
    return any(key == declared or key.startswith(declared + "/") for declared in keys)


def check_hidden_flags(resolved: Path, verdict: Verdict) -> None:
    """skip-worktree／assume-unchanged 的檔案改了也不會出現在 git status。"""
    output = git_output(["ls-files", "-v", "-z"], resolved)
    if output is None:
        verdict.reasons.append("讀不到 git ls-files，無法確認有沒有被隱藏的改動。")
        return
    hidden = [
        entry[2:]
        for entry in output.split("\0")
        if len(entry) > 2 and is_hidden_change_tag(entry[0])
    ]
    if hidden:
        verdict.reasons.append(
            "有標記成 skip-worktree 或 assume-unchanged 的檔案（git 不會顯示它們的改動，"
            f"清理會連改動一起刪掉）：{summarize(hidden)}"
        )


def is_hidden_change_tag(tag: str) -> bool:
    return tag == "S" or tag.islower()


@dataclass
class TreeFindings:
    links: list[str] = field(default_factory=list)
    nested_git: list[str] = field(default_factory=list)
    other_device: list[str] = field(default_factory=list)
    unreadable: list[str] = field(default_factory=list)
    declared_markers: list[str] = field(default_factory=list)


def check_tree(resolved: Path, verdict: Verdict, declared: Sequence[str] = ()) -> None:
    findings = scan_tree(resolved, declared)
    if findings.links:
        verdict.reasons.append(
            "裡面有不允許的捷徑連結（快取以外或宣告路徑裡的 symlink，或任何 junction），"
            f"不能自動清理：{summarize(findings.links)}"
        )
    if findings.nested_git:
        markers = findings.declared_markers
        note = f"（{summarize(markers)} 是空白 .git 標記；宣告路徑裡不沿用快取豁免）" if markers else ""
        verdict.reasons.append(
            "裡面有另一個 git repo 的 .git 或 bare repo（可能有還沒推上去的 commit）："
            f"{summarize(findings.nested_git)}{note}"
        )
    if findings.other_device:
        verdict.reasons.append(
            "裡面有掛載到其他磁碟的資料夾，刪除可能波及其他磁碟的檔案："
            f"{summarize(findings.other_device)}"
        )
    if findings.unreadable:
        verdict.reasons.append(
            f"有讀不到的資料夾，無法確認裡面：{summarize(findings.unreadable)}"
        )


def device_of(path: Path) -> int:
    return os.lstat(path).st_dev


def scan_tree(start: Path, declared: Sequence[str] = ()) -> TreeFindings:
    """逐層走整個工作資料夾（含快取），不進任何連結，也不跨到其他裝置。"""
    findings = TreeFindings()
    root_device = device_of(start)
    pending = [start]
    while pending:
        directory = pending.pop()
        try:
            with os.scandir(directory) as entries:
                for entry in entries:
                    visit(entry, start, root_device, pending, findings, declared)
        except OSError:
            findings.unreadable.append(relative_text(directory, start))
    return findings


def visit(
    entry: os.DirEntry[str],
    start: Path,
    root_device: int,
    pending: list[Path],
    findings: TreeFindings,
    declared: Sequence[str] = (),
) -> None:
    path = Path(entry.path)
    parts = path.relative_to(start).parts
    info = entry.stat(follow_symlinks=False)
    is_junction = entry.is_junction()
    # 宣告路徑本身與底下不沿用快取豁免（連結、空白 .git 標記一律擋），bare repo 也擋。
    exempt = not is_declared("/".join(parts), declared)
    nested = is_nested_git(entry.name, parts)
    if nested and not exempt and is_empty_cache_marker(info, is_junction, parts):
        findings.declared_markers.append(relative_text(path, start))
    if nested and not (exempt and is_empty_cache_marker(info, is_junction, parts)):
        findings.nested_git.append(relative_text(path, start))
    if is_junction or is_link_stat(info):
        if not (exempt and is_allowed_cache_link(info, is_junction, parts)):
            findings.links.append(relative_text(path, start))
    elif stat.S_ISDIR(info.st_mode):
        if not (exempt or nested) and is_bare_repo(path):
            findings.nested_git.append(relative_text(path, start))
        if device_of(path) != root_device:
            findings.other_device.append(relative_text(path, start))
        else:
            pending.append(path)


def is_nested_git(name: str, relative_parts: Sequence[str]) -> bool:
    """工作資料夾最上層自己的 .git 以外的 .git；不分大小寫（Windows 上 .GIT 也是 repo）。"""
    return name.casefold() == ".git" and len(relative_parts) > 1


def is_empty_cache_marker(
    info: object, is_junction: bool, relative_parts: Sequence[str]
) -> bool:
    """可重建快取裡 0 位元組的一般檔案 .git（uv 放的標記檔），不是 repo。

    資料夾、非空檔案（例如 gitdir: 指標）或捷徑連結都不算標記檔。
    """
    mode = getattr(info, "st_mode", 0)
    attributes = getattr(info, "st_file_attributes", 0)
    plain_file = (
        stat.S_ISREG(mode)
        and not is_junction
        and not attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT
    )
    inside_cache = any(part in REBUILDABLE_CACHES for part in relative_parts[:-1])
    return plain_file and getattr(info, "st_size", -1) == 0 and inside_cache


def is_bare_repo(path: Path) -> bool:
    """同時有 HEAD 檔與 objects/、refs/ 資料夾（bare repo）；不跟著連結走。"""
    try:
        modes = [os.lstat(path / name).st_mode for name in ("HEAD", "objects", "refs")]
    except OSError:
        return False
    return stat.S_ISREG(modes[0]) and all(stat.S_ISDIR(mode) for mode in modes[1:])


def is_allowed_cache_link(
    info: object, is_junction: bool, relative_parts: Sequence[str]
) -> bool:
    """只允許可重建快取「裡面」的 POSIX symlink（例如 .venv/bin/python）。

    junction 與帶 reparse point 屬性的項目（含 Windows 的 symlink）不論在哪裡都不允許；
    快取資料夾本身是連結、或連結在快取以外，也不允許。
    """
    mode = getattr(info, "st_mode", 0)
    attributes = getattr(info, "st_file_attributes", 0)
    posix_symlink = (
        stat.S_ISLNK(mode)
        and not is_junction
        and not attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT
    )
    inside_cache = any(part in REBUILDABLE_CACHES for part in relative_parts[:-1])
    return posix_symlink and inside_cache


def relative_text(path: Path, start: Path) -> str:
    try:
        return path.relative_to(start).as_posix() or "."
    except ValueError:
        return str(path)


# ── tmp ──────────────────────────────────────────────────────────


def check_tmp(root: Path, target: Path, task: str) -> Verdict:
    verdict = Verdict(str(target))
    expected = root / TOUKADEV_FOLDER / TMP_FOLDER / task
    check_task_code(task, verdict)
    if not target.exists() and not is_link(target):
        verdict.reasons.append("找不到這個資料夾。")
        return verdict
    if is_link(target):
        verdict.reasons.append(
            "這個位置本身是捷徑連結（symlink／junction），不能自動清理。"
        )
        return verdict
    for parent in (root / TOUKADEV_FOLDER, root / TOUKADEV_FOLDER / TMP_FOLDER):
        if is_link(parent):
            verdict.reasons.append(f"{parent} 是捷徑連結，不能自動清理裡面的東西。")
    resolved = target.resolve()
    if not same_path(resolved, expected):
        verdict.reasons.append(
            f"位置必須正好是本任務的暫存資料夾 {expected}，目前是 {resolved}。"
        )
    check_no_worktree_inside(root, resolved, verdict)
    return verdict


def check_task_code(task: str, verdict: Verdict) -> None:
    if not TASK_CODE_PATTERN.match(task):
        verdict.reasons.append(f"任務代號「{task}」只能用小寫英文、數字和 -。")
    elif task == RESERVED_TASK_CODE:
        verdict.reasons.append("任務代號不能是 index（保留給進度總覽）。")


def check_no_worktree_inside(root: Path, resolved: Path, verdict: Verdict) -> None:
    inside = [
        str(entry.path)
        for entry in list_worktrees(root)
        if entry.path.is_relative_to(resolved)
    ]
    if inside:
        verdict.reasons.append(
            f"裡面有 git 工作資料夾，要先處理工作資料夾：{summarize(inside)}"
        )


# ── branch ───────────────────────────────────────────────────────


def check_branch(root: Path, name: str) -> Verdict:
    verdict = Verdict(name)
    branch = name.removeprefix(BRANCH_REF_PREFIX)
    if is_shared_branch(branch):
        verdict.reasons.append(
            "是共用分支（main、master、dev、develop、trunk 之一），永遠不自動刪除。"
        )
    check_default_branch(root, branch, verdict)
    current = git_output(["symbolic-ref", "-q", "--short", "HEAD"], root)
    if current is not None and current.strip() == branch:
        verdict.reasons.append("是主要專案資料夾目前所在的分支。")
    users = [
        str(entry.path)
        for entry in list_worktrees(root)[1:]
        if entry.branch_ref == BRANCH_REF_PREFIX + branch
    ]
    if users:
        verdict.reasons.append(f"有工作資料夾正在使用這個分支：{summarize(users)}")
    return verdict


def is_shared_branch(name: str) -> bool:
    value = name.casefold()
    for prefix in ("refs/heads/", "refs/remotes/", "remotes/"):
        value = value.removeprefix(prefix)
    candidates = {value, value.split("/", 1)[-1]}
    return bool(candidates & set(SHARED_BRANCH_NAMES))


def check_default_branch(root: Path, branch: str, verdict: Verdict) -> None:
    origin_head = git_output(["symbolic-ref", "-q", "refs/remotes/origin/HEAD"], root)
    if origin_head is None:
        defaults = FALLBACK_DEFAULT_BRANCHES
    else:
        defaults = (origin_head.strip().removeprefix("refs/remotes/origin/"),)
    if branch in defaults:
        verdict.reasons.append(f"是預設分支（{'、'.join(defaults)}），永遠不自動刪除。")


# ── 指令列 ───────────────────────────────────────────────────────


def unsupported_python_message(version: Sequence[int]) -> str | None:
    if tuple(version[:2]) >= MINIMUM_PYTHON:
        return None
    return (
        f"這支程式需要 Python 3.12 以上，目前是 {version[0]}.{version[1]}。"
        "請改用 3.12 以上的 Python 執行；不確定能不能清理時，請先問人類。"
    )


def parse_arguments(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="清理前檢查：只檢查，不刪除。")
    commands = parser.add_subparsers(dest="command", required=True)
    worktree = commands.add_parser("worktree", help="檢查一個工作資料夾")
    worktree.add_argument("path")
    worktree.add_argument("--branch", required=True)
    tmp = commands.add_parser("tmp", help="檢查本任務的暫存資料夾")
    tmp.add_argument("path")
    tmp.add_argument("--task", required=True)
    branch = commands.add_parser("branch", help="檢查一個本機分支")
    branch.add_argument("name")
    return parser.parse_args(argv)


def run_check(args: argparse.Namespace, root: Path, cwd: Path) -> Verdict:
    if args.command == "worktree":
        return check_worktree(root, resolve_argument(args.path, cwd), args.branch)
    if args.command == "tmp":
        return check_tmp(root, resolve_argument(args.path, cwd), args.task)
    return check_branch(root, args.name)


def report(verdict: Verdict) -> int:
    print(f"{'可以清理' if verdict.ok else '不能自動清理'}：{verdict.target}")
    for reason in verdict.reasons:
        print(f"- {reason}")
    for note in verdict.notes:
        print(f"附註：{note}")
    return 0 if verdict.ok else 1


def configure_streams() -> None:
    """主控台編碼顯示不了的字元（例如檔名裡的表情符號）改成跳脫字元，不讓程式中斷。"""
    for stream in (sys.stdout, sys.stderr):
        if isinstance(stream, io.TextIOWrapper):
            stream.reconfigure(errors="backslashreplace")


def main(argv: Sequence[str] | None = None, cwd: Path | None = None) -> int:
    configure_streams()
    too_old = unsupported_python_message(sys.version_info)
    if too_old is not None:
        print(too_old, file=sys.stderr)
        return 2
    args = parse_arguments(argv)
    base = Path.cwd() if cwd is None else cwd
    try:
        root = find_repo_root(base)
        return report(run_check(args, root, base))
    except CheckError as error:
        print(f"不能自動清理（檢查沒辦法完成）：{error}")
        return 1


if __name__ == "__main__":
    sys.exit(main())

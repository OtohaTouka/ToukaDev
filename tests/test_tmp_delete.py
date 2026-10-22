"""暫存資料夾的刪法：dev-workflow/assets/progress/delete_tmp.py（ADR-037、ADR-038）。

腳本從檔案載入測試，不另抄一份。「取消唯讀再刪」的每個條件都由這裡的測試鎖住：
任何一項不成立，都必須照原錯誤停下。刪之前的路徑自我檢查（在同一個程序裡重跑
check_cleanup.py 的 tmp 檢查）沒通過、沒辦法完成或載入失敗時，什麼都不刪，以非 0 結束。
tmp 檢查需要 repo 根的 `.git` 與 `git worktree list`，所以實際執行都在拋棄式 git repo 的根目錄。
Windows 專屬的實刪案例在 CI（ubuntu）會跳過，要另附本機 Windows 實跑證據。
"""

import contextlib
import importlib.util
import ntpath
import os
import re
import shutil
import stat
import subprocess
import sys
from collections.abc import Callable, Iterator
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "dev-workflow" / "assets" / "progress" / "delete_tmp.py"
PROGRESS_RECORD = ROOT / "dev-workflow" / "references" / "progress-record.md"
DOCUMENTED_RUN = (
    "python -I <dev-workflow 安裝根>/assets/progress/delete_tmp.py"
    " <路徑> --task <任務代號>"
)
HANDLER_NAME = "clear_readonly_then_unlink"
TASK = "demo"
IS_WINDOWS = sys.platform == "win32"
WINDOWS_ONLY = "Windows 專屬實刪：CI（ubuntu）跳過，另附本機實跑證據"
GIT_TEST_CONFIG = (
    *("-c", "user.name=ToukaDev Test", "-c", "user.email=test@example.invalid"),
    *("-c", "commit.gpgsign=false", "-c", "core.autocrlf=false"),
)
PYTHON_RUN = re.compile(
    r"\bpython(?:3(?:\.\d+)?)?(?:\.exe)?\s+(?P<middle>[^`\n]*?)delete_tmp\.py"
)


def lstat_result(mode: int, *attributes: int, links: int = 1) -> SimpleNamespace:
    flags = 0
    for attribute in attributes:
        flags |= attribute
    return SimpleNamespace(st_mode=mode, st_file_attributes=flags, st_nlink=links)


READONLY, REPARSE = stat.FILE_ATTRIBUTE_READONLY, stat.FILE_ATTRIBUTE_REPARSE_POINT
# 條件全部成立時的 lstat：一般檔案、確實有唯讀屬性、不是 reparse point、沒有其他硬連結。
READONLY_FILE = lstat_result(
    stat.S_IFREG | 0o444, stat.FILE_ATTRIBUTE_ARCHIVE, READONLY
)
# 每一列只讓一個條件不成立，其他都照 READONLY_FILE、Windows、os.unlink、PermissionError。
REFUSED = {
    "non-windows-linux": {"platform": "linux"},
    "non-windows-darwin": {"platform": "darwin"},
    "non-windows-cygwin": {"platform": "cygwin"},
    "rmdir": {"func": os.rmdir},
    "scandir": {"func": os.scandir},
    "remove-is-not-unlink": {"func": os.remove},
    "not-permission-error-not-found": {"exc": FileNotFoundError(2, "No such file")},
    "not-permission-error-oserror": {"exc": OSError(32, "In use")},
    "not-permission-error-timeout": {"exc": TimeoutError("slow")},
    "directory": {"info": lstat_result(stat.S_IFDIR | 0o555, READONLY)},
    "symlink-mode": {"info": lstat_result(stat.S_IFLNK | 0o777, READONLY)},
    "reparse-point-file": {"info": lstat_result(stat.S_IFREG, REPARSE, READONLY)},
    "reparse-point-directory": {"info": lstat_result(stat.S_IFDIR, REPARSE, READONLY)},
    "not-readonly": {"info": lstat_result(stat.S_IFREG | 0o666)},
    "hardlinked": {"info": lstat_result(stat.S_IFREG | 0o444, READONLY, links=2)},
    "link-count-unknown": {
        "info": lstat_result(stat.S_IFREG | 0o444, READONLY, links=0)
    },
    "lstat-fails": {"lstat_error": FileNotFoundError(2, "gone")},
    "outside-sibling-same-prefix": {"path": lambda s: str(s.sibling)},
    "outside-parent": {"path": lambda s: str(Path(s.root).parent / "object")},
    "outside-dotdot": {"path": lambda s: str(Path(s.root, "..", "task-other", "x"))},
    "root-itself": {"path": lambda s: s.root},
}


def load_script(name: str = "toukadev_delete_tmp") -> ModuleType:
    """從檔案載入；名稱不是 __main__，所以不會執行刪除。"""
    spec = importlib.util.spec_from_file_location(name, SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_main(*arguments: str) -> SimpleNamespace:
    """在本程序把腳本當主程式執行；shutil.rmtree 換成 mock，只觀察收到什麼。"""
    spec = importlib.util.spec_from_file_location("__main__", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    rmtree = MagicMock(name="rmtree")
    code: object = 0
    with (
        patch.dict(sys.modules),
        patch.object(sys, "dont_write_bytecode", sys.dont_write_bytecode),
        patch.object(sys, "argv", [str(SCRIPT), *arguments]),
        patch.object(shutil, "rmtree", rmtree),
    ):
        try:
            spec.loader.exec_module(module)
        except SystemExit as stopped:
            code = stopped.code
    return SimpleNamespace(module=module, rmtree=rmtree, code=code)


def git(*args: str, cwd: Path) -> None:
    subprocess.run(
        ["git", *GIT_TEST_CONFIG, *args], cwd=cwd, capture_output=True, check=True
    )


@pytest.fixture(scope="module")
def handler() -> Callable[..., None]:
    return getattr(load_script(), HANDLER_NAME)


@pytest.fixture
def scene(tmp_path: Path) -> SimpleNamespace:
    """要刪的資料夾 `task` 裡有一個檔案；旁邊有名稱開頭相同的 `task-other`。"""
    root, sibling = tmp_path / "task", tmp_path / "task-other" / "object"
    target = root / "sub" / "object"
    for path in (target, sibling):
        path.parent.mkdir(parents=True)
        path.write_text("x", encoding="utf-8")
    return SimpleNamespace(
        root=str(root), path=str(target), target=target, sibling=sibling
    )


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    """拋棄式 git repo（git 設定與使用者的全域設定隔離）。

    本任務的暫存資料夾 `.toukadev/tmp/demo/` 與其他任務的 `.toukadev/tmp/other/`
    裡各有一個檔案。
    """
    config = tmp_path / "gitconfig"
    config.write_text("", encoding="utf-8")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(config))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))
    root = tmp_path / "repo"
    root.mkdir()
    git("init", "-q", cwd=root)
    tmp = root / ".toukadev" / "tmp"
    folder, other = tmp / TASK, tmp / "other"
    for path in (folder / "sub" / "log.txt", other / "keep.txt"):
        path.parent.mkdir(parents=True)
        path.write_text("x", encoding="utf-8")
    return SimpleNamespace(
        root=root,
        tmp=tmp,
        folder=folder,
        other=other,
        kept=(folder / "sub" / "log.txt", other / "keep.txt"),
    )


def nothing_deleted(repo: SimpleNamespace) -> bool:
    return all(path.exists() for path in repo.kept)


@contextlib.contextmanager
def windows_like(
    *,
    platform: str = "win32",
    info: object = READONLY_FILE,
    lstat_error: BaseException | None = None,
    follow_symlinks: bool = False,
) -> Iterator[MagicMock]:
    """固定平台與 lstat 結果；chmod 換成 mock，只觀察有沒有被呼叫。"""
    chmod = MagicMock(name="chmod")
    lstat = MagicMock(return_value=info, side_effect=lstat_error)
    with (
        patch.object(sys, "platform", platform),
        patch.object(os, "lstat", lstat),
        patch.object(os, "chmod", chmod),
        patch.object(
            os, "supports_follow_symlinks", {chmod} if follow_symlinks else set()
        ),
    ):
        yield chmod


def denied(path: str) -> PermissionError:
    return PermissionError(13, "Access is denied", path)


# ── 文件與主程式 ─────────────────────────────────────────────────


def project_documents() -> list[Path]:
    """git 追蹤或會追蹤的 Markdown（.toukadev 等被忽略的資料夾不算）。"""
    listed = subprocess.run(
        ["git", "-C", str(ROOT), "ls-files", "-z", "--cached", "--others"]
        + ["--exclude-standard", "--", "*.md"],
        capture_output=True,
        check=True,
    )
    names = listed.stdout.decode("utf-8").split("\0")
    return [ROOT / name for name in names if name and (ROOT / name).is_file()]


def test_documents_run_the_script_only_in_isolated_mode() -> None:
    """`-I`：腳本所在與目前資料夾不進模組搜尋路徑，同名 .py 不會取代標準函式庫。"""
    assert DOCUMENTED_RUN in PROGRESS_RECORD.read_text(encoding="utf-8")
    runs = []
    for path in [*project_documents(), SCRIPT]:
        for match in PYTHON_RUN.finditer(path.read_text(encoding="utf-8")):
            runs.append(match.group(0))
            assert match.group("middle").startswith("-I "), (path, match.group(0))
    assert DOCUMENTED_RUN.removesuffix(" <路徑> --task <任務代號>") in runs


@pytest.mark.parametrize("relative", (False, True), ids=("absolute", "relative"))
def test_main_passes_only_the_bound_handler_to_rmtree(
    repo: SimpleNamespace, monkeypatch: pytest.MonkeyPatch, relative: bool
) -> None:
    """root 改傳別的路徑、改用 ignore_errors 或多傳參數，在 ubuntu 也會被抓到。"""
    monkeypatch.chdir(repo.root)
    argument = ".toukadev/tmp/demo" if relative else str(repo.folder)
    checked = str(Path.cwd() / argument) if relative else argument
    result = run_main(argument, "--task", TASK)
    assert result.code == 0
    result.rmtree.assert_called_once()
    args, kwargs = result.rmtree.call_args
    assert args == (checked,)
    assert set(kwargs) == {"onexc"}
    onexc = kwargs["onexc"]
    assert onexc.func is getattr(result.module, HANDLER_NAME)
    assert onexc.args == (checked,)
    assert not onexc.keywords
    assert nothing_deleted(repo)


def test_loading_the_script_does_not_delete_anything(
    repo: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(repo.root)
    rmtree = MagicMock(name="rmtree")
    with (
        patch.object(sys, "argv", [str(SCRIPT), str(repo.folder), "--task", TASK]),
        patch.object(shutil, "rmtree", rmtree),
    ):
        load_script()
    rmtree.assert_not_called()
    assert nothing_deleted(repo)


# Python 版本（None 表示目前的版本）與參數。
WRONG_RUNS = {
    "python-3.11": ((3, 11, 9), ("{folder}", "--task", TASK)),
    "no-arguments": (None, ()),
    "path-only": (None, ("{folder}",)),
    "task-without-code": (None, ("{folder}", "--task")),
    "wrong-option": (None, ("{folder}", "--name", TASK)),
    "option-first": (None, ("--task", TASK, "{folder}")),
    "extra-argument": (None, ("{folder}", "--task", TASK, "again")),
}


@pytest.mark.parametrize("version,arguments", WRONG_RUNS.values(), ids=WRONG_RUNS.keys())
def test_script_stops_on_old_python_or_wrong_arguments(
    repo: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
    version: tuple | None,
    arguments: tuple[str, ...],
) -> None:
    monkeypatch.chdir(repo.root)
    filled = [argument.format(folder=repo.folder) for argument in arguments]
    with patch.object(sys, "version_info", version or sys.version_info):
        result = run_main(*filled)
    assert result.code not in (0, None)
    result.rmtree.assert_not_called()
    assert nothing_deleted(repo)


# ── 路徑自我檢查：不通過就什麼都不刪 ─────────────────────────────


# 給腳本的路徑與任務代號；每一列都不是 repo 根下 `.toukadev/tmp/<合法代號>` 這一層。
REFUSED_TARGETS = {
    "outside-repo": (lambda r: r.root.parent / "elsewhere", TASK),
    "other-folder-in-repo": (lambda r: r.root / "data", TASK),
    "repo-root": (lambda r: r.root, TASK),
    "toukadev-folder": (lambda r: r.root / ".toukadev", TASK),
    "tmp-itself": (lambda r: r.tmp, TASK),
    "other-task-folder": (lambda r: r.other, TASK),
    "dotdot-to-other-task": (lambda r: r.folder / ".." / "other", TASK),
    "below-task-folder": (lambda r: r.folder / "sub", TASK),
    "missing-folder": (lambda r: r.tmp / "gone", "gone"),
    "code-uppercase": (lambda r: r.folder, "Demo"),
    "code-with-slash": (lambda r: r.folder, "demo/"),
    "code-with-dotdot": (lambda r: r.folder, "../demo"),
    "code-empty": (lambda r: r.folder, ""),
    "code-reserved-index": (lambda r: r.tmp / "index", "index"),
}


@pytest.mark.parametrize(
    "path,task", REFUSED_TARGETS.values(), ids=REFUSED_TARGETS.keys()
)
def test_self_check_refusal_deletes_nothing(
    repo: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    path: Callable[[SimpleNamespace], Path],
    task: str,
) -> None:
    for folder in (repo.root.parent / "elsewhere", repo.root / "data", repo.tmp / "index"):
        folder.mkdir(exist_ok=True)
    monkeypatch.chdir(repo.root)
    result = run_main(str(path(repo)), "--task", task)
    assert result.code not in (0, None)
    result.rmtree.assert_not_called()
    assert nothing_deleted(repo)
    assert "Not deleted" in capsys.readouterr().err


# `.git` 是檔案（工作資料夾，find_repo_root 丟 CheckError）或空資料夾（git worktree list
# 失敗，丟 CheckError）；或在真的 repo 裡讓 subprocess.run 失敗：找不到 git（CheckError）、其他例外。
UNFINISHED_CHECKS = {
    "worktree-checkout": ("file", None),
    "broken-git-folder": ("folder", None),
    "git-missing": (None, FileNotFoundError(2, "git not found")),
    "other-exception": (None, RuntimeError("unexpected")),
}


@pytest.mark.parametrize(
    "git_marker,failure", UNFINISHED_CHECKS.values(), ids=UNFINISHED_CHECKS.keys()
)
def test_check_error_or_any_exception_deletes_nothing(
    repo: SimpleNamespace,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    git_marker: str | None,
    failure: BaseException | None,
) -> None:
    base = repo.root if git_marker is None else tmp_path / "checkout"
    folder = base / ".toukadev" / "tmp" / TASK
    folder.mkdir(parents=True, exist_ok=True)
    if git_marker == "file":
        (base / ".git").write_text("gitdir: elsewhere\n", encoding="utf-8")
    elif git_marker == "folder":
        (base / ".git").mkdir()
    monkeypatch.chdir(base)
    stub = patch.object(subprocess, "run", side_effect=failure)
    with stub if failure is not None else contextlib.nullcontext():
        result = run_main(str(folder), "--task", TASK)
    assert result.code not in (0, None)
    result.rmtree.assert_not_called()
    assert folder.exists() and nothing_deleted(repo)
    assert "did not finish" in capsys.readouterr().err


# 腳本旁的 check_cleanup.py 內容；None 表示沒有這個檔。
BROKEN_CHECKERS = {
    "missing": None,
    "import-error": "raise ImportError('broken checker')\n",
    "exits-zero-on-load": "import sys\nsys.exit(0)\n",
    "no-functions": "VALUE = 1\n",
}


@pytest.mark.parametrize("checker", BROKEN_CHECKERS.values(), ids=BROKEN_CHECKERS.keys())
def test_checker_load_failure_deletes_nothing(
    repo: SimpleNamespace, tmp_path: Path, checker: str | None
) -> None:
    """腳本只從自己的資料夾載入 check_cleanup.py；載入不了或不完整就不刪，以非 0 結束。"""
    copy = tmp_path / "copy" / SCRIPT.name
    copy.parent.mkdir()
    shutil.copyfile(SCRIPT, copy)
    if checker is not None:
        copy.with_name("check_cleanup.py").write_text(checker, encoding="utf-8")
    completed = run_script(repo.root, repo.folder, script=copy)
    assert completed.returncode != 0
    assert b"Not deleted" in completed.stderr
    assert nothing_deleted(repo)


# ── 條件全部成立：取消唯讀再刪 ───────────────────────────────────


@pytest.mark.parametrize("follow_symlinks", (False, True))
def test_readonly_regular_file_inside_root_is_cleared_and_unlinked(
    handler: Callable[..., None], scene: SimpleNamespace, follow_symlinks: bool
) -> None:
    """chmod 只在有支援時才帶 follow_symlinks=False。"""
    with windows_like(follow_symlinks=follow_symlinks) as chmod:
        handler(scene.root, os.unlink, scene.path, denied(scene.path))
    extra = {"follow_symlinks": False} if follow_symlinks else {}
    chmod.assert_called_once_with(scene.path, stat.S_IWRITE, **extra)
    assert not scene.target.exists()


def test_case_difference_still_counts_as_inside_on_windows_paths(
    handler: Callable[..., None],
) -> None:
    unlink = MagicMock(name="unlink")
    path = r"d:\work\.toukadev\tmp\demo\sub\object"
    with (
        windows_like() as chmod,
        patch.object(os, "path", ntpath),
        patch.object(os, "unlink", unlink),
    ):
        handler(r"D:\Work\.toukadev\TMP\demo", unlink, path, denied(path))
    chmod.assert_called_once_with(path, stat.S_IWRITE)
    unlink.assert_called_once_with(path)


# ── 任何一項不成立：照原錯誤停下 ─────────────────────────────────


@pytest.mark.parametrize("change", REFUSED.values(), ids=REFUSED.keys())
def test_every_failed_condition_reraises_the_original_error(
    handler: Callable[..., None], scene: SimpleNamespace, change: dict[str, Any]
) -> None:
    path = change.get("path", lambda s: s.path)(scene)
    exc = change.get("exc") or denied(path)
    environment = {
        key: change[key] for key in ("platform", "info", "lstat_error") if key in change
    }
    with windows_like(**environment) as chmod, pytest.raises(type(exc)) as caught:
        handler(scene.root, change.get("func", os.unlink), path, exc)
    assert caught.value is exc
    chmod.assert_not_called()
    assert scene.target.exists() and scene.sibling.exists()


def test_path_on_another_drive_reraises_the_original_error(
    handler: Callable[..., None],
) -> None:
    """不同磁碟時 commonpath 會丟 ValueError；要接住，改丟原本的錯誤。"""
    path = r"E:\work\.toukadev\tmp\demo\object"
    exc = denied(path)
    with (
        windows_like() as chmod,
        patch.object(os, "path", ntpath),
        pytest.raises(PermissionError) as caught,
    ):
        handler(r"D:\work\.toukadev\tmp\demo", os.unlink, path, exc)
    assert caught.value is exc
    chmod.assert_not_called()


# ── 用 `python -I delete_tmp.py <路徑> --task <任務代號>` 實際執行 ──────


def run_script(
    cwd: Path, folder: Path, *, task: str = TASK, script: Path = SCRIPT
) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-I", str(script), str(folder), "--task", task],
        cwd=cwd,
        capture_output=True,
        check=False,
    )


def make_readonly_file(path: Path, text: str = "keep") -> Path:
    path.write_text(text, encoding="utf-8")
    os.chmod(path, stat.S_IREAD)
    return path


def is_readonly(path: Path) -> bool:
    return bool(os.lstat(path).st_file_attributes & READONLY)


def test_real_run_removes_only_the_task_folder(repo: SimpleNamespace) -> None:
    completed = run_script(repo.root, repo.folder)
    assert completed.returncode == 0, completed.stderr
    assert not repo.folder.exists()
    assert repo.tmp.is_dir() and (repo.other / "keep.txt").exists()


def test_real_run_writes_no_bytecode_next_to_the_script(
    repo: SimpleNamespace, tmp_path: Path
) -> None:
    """腳本與 check_cleanup.py 放在 Skill 安裝根；載入時不在那裡留下 __pycache__。"""
    copy = tmp_path / "skill" / SCRIPT.name
    copy.parent.mkdir()
    for source in (SCRIPT, SCRIPT.with_name("check_cleanup.py")):
        shutil.copyfile(source, copy.with_name(source.name))
    completed = run_script(repo.root, repo.folder, script=copy)
    assert completed.returncode == 0, completed.stderr
    assert not repo.folder.exists()
    assert not (copy.parent / "__pycache__").exists()


def test_real_run_refuses_another_task_folder(repo: SimpleNamespace) -> None:
    completed = run_script(repo.root, repo.other)
    assert completed.returncode != 0
    assert b"Not deleted" in completed.stderr
    assert nothing_deleted(repo)


def make_folder_link(link: Path, target: Path) -> None:
    """Windows 用 junction，其他平台用 symlink。"""
    if not IS_WINDOWS:
        link.symlink_to(target, target_is_directory=True)
        return
    made = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(link), str(target)],
        capture_output=True,
        check=False,
    )
    assert made.returncode == 0, made.stderr


@pytest.mark.parametrize("linked", (".toukadev/tmp/demo", ".toukadev/tmp", ".toukadev"))
def test_real_run_refuses_when_the_folder_or_a_parent_is_a_link(
    repo: SimpleNamespace, tmp_path: Path, linked: str
) -> None:
    """要刪的資料夾本身、`.toukadev` 或 `.toukadev/tmp` 是連結：不刪，連結指向的內容不動。"""
    link, outside = repo.root / linked, tmp_path / "outside"
    shutil.move(link, outside)
    make_folder_link(link, outside)
    try:
        completed = run_script(repo.root, repo.folder)
    finally:
        # 只移除連結本身：junction 用 rmdir，symlink 用 unlink。
        if IS_WINDOWS:
            os.rmdir(link)
        else:
            os.unlink(link)
    assert completed.returncode == 1
    assert b"Not deleted" in completed.stderr
    kept = outside / repo.kept[0].relative_to(link)
    assert kept.read_text(encoding="utf-8") == "x"


def test_real_run_refuses_a_folder_holding_a_git_worktree(
    repo: SimpleNamespace,
) -> None:
    (repo.root / "README.md").write_text("demo\n", encoding="utf-8")
    git("add", "README.md", cwd=repo.root)
    git("commit", "-q", "-m", "init", cwd=repo.root)
    worktree = repo.folder / "checkout"
    git("worktree", "add", "-q", "-b", "wt/demo", str(worktree), cwd=repo.root)
    completed = run_script(repo.root, repo.folder)
    assert completed.returncode == 1
    assert b"Not deleted" in completed.stderr
    assert (worktree / "README.md").exists() and nothing_deleted(repo)


@pytest.mark.skipif(IS_WINDOWS, reason="POSIX symlink；Windows 由 junction 案例涵蓋")
def test_real_run_does_not_follow_posix_symlink(
    repo: SimpleNamespace, tmp_path: Path
) -> None:
    kept = tmp_path / "outside" / "kept.txt"
    kept.parent.mkdir()
    kept.write_text("keep", encoding="utf-8")
    (repo.folder / "dir-link").symlink_to(kept.parent, target_is_directory=True)
    (repo.folder / "file-link").symlink_to(kept)
    completed = run_script(repo.root, repo.folder)
    assert completed.returncode == 0, completed.stderr
    assert not repo.folder.exists()
    assert kept.read_text(encoding="utf-8") == "keep"


@pytest.mark.skipif(not IS_WINDOWS, reason=WINDOWS_ONLY)
def test_windows_real_run_deletes_git_repo_with_readonly_objects(
    repo: SimpleNamespace,
) -> None:
    review = repo.folder / "review-repo"
    review.mkdir()
    (review / "README.md").write_text("demo\n", encoding="utf-8")
    for args in (("init", "-q"), ("add", "README.md"), ("commit", "-q", "-m", "init")):
        git(*args, cwd=review)
    objects = (review / ".git" / "objects").rglob("*")
    assert any(path.is_file() and is_readonly(path) for path in objects)
    completed = run_script(repo.root, repo.folder)
    assert completed.returncode == 0, completed.stderr
    assert not repo.folder.exists()


@pytest.mark.skipif(not IS_WINDOWS, reason=WINDOWS_ONLY)
def test_windows_real_run_does_not_follow_junction(
    repo: SimpleNamespace, tmp_path: Path
) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    kept = outside / "kept.txt"
    kept.write_text("keep", encoding="utf-8")
    locked = make_readonly_file(outside / "readonly.txt")
    make_readonly_file(repo.folder / "readonly.txt")
    junction = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(repo.folder / "junction"), str(outside)],
        capture_output=True,
        check=False,
    )
    assert junction.returncode == 0, junction.stderr
    completed = run_script(repo.root, repo.folder)
    assert completed.returncode == 0, completed.stderr
    assert not repo.folder.exists()
    assert kept.read_text(encoding="utf-8") == locked.read_text(encoding="utf-8")
    assert is_readonly(locked)
    os.chmod(locked, stat.S_IWRITE)


@pytest.mark.skipif(not IS_WINDOWS, reason=WINDOWS_ONLY)
def test_windows_real_run_stops_on_hard_link_to_outside_file(
    repo: SimpleNamespace, tmp_path: Path
) -> None:
    """唯讀屬性跟著檔案本身走、硬連結共用：取消唯讀會改到資料夾外那份，所以照原錯誤停下。"""
    outside = make_readonly_file(tmp_path / "outside-object")
    os.link(outside, repo.folder / "linked-object")
    assert os.lstat(outside).st_nlink == 2
    completed = run_script(repo.root, repo.folder)
    assert completed.returncode != 0
    assert b"PermissionError" in completed.stderr
    assert outside.read_text(encoding="utf-8") == "keep"
    assert is_readonly(outside)
    os.chmod(outside, stat.S_IWRITE)


@pytest.mark.skipif(not IS_WINDOWS, reason=WINDOWS_ONLY)
def test_windows_real_run_stops_on_file_in_use(repo: SimpleNamespace) -> None:
    """不是唯讀造成的權限錯誤（檔案被別的程式開著）：照原錯誤停下。"""
    busy = repo.folder / "busy.log"
    busy.write_text("x", encoding="utf-8")
    with busy.open("rb"):
        completed = run_script(repo.root, repo.folder)
    assert completed.returncode != 0
    assert b"PermissionError" in completed.stderr
    assert busy.exists()

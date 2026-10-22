"""清理前檢查程式（dev-workflow/assets/progress/check_cleanup.py）的測試。

每個測試都在 TemporaryDirectory 建立拋棄式 git repo，git 設定與使用者的全域設定隔離；
不讀寫實體 .toukadev/ 或任何真實 repo。
"""

import ast
import contextlib
import importlib.util
import io
import os
import stat
import subprocess
import sys
import tokenize
from collections.abc import Callable
from pathlib import Path
from tempfile import TemporaryDirectory
from types import ModuleType, SimpleNamespace
from unittest import TestCase, skipIf, skipUnless
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "dev-workflow" / "assets" / "progress"
SCRIPTS = (
    ASSETS / "check_cleanup.py",
    ASSETS / "render_progress.py",
    ASSETS / "delete_tmp.py",
)
IS_WINDOWS = sys.platform == "win32"
JUNCTION_SKIP_REASON = "junction 是 Windows 專屬功能；非 Windows 由 symlink 案例涵蓋"
WINDOWS_SYMLINK_SKIP_REASON = (
    "Windows 的 symlink 是 reparse point，一律不通過；POSIX 允許快取裡的 symlink，"
    "由 POSIX 專屬案例涵蓋"
)
POSIX_ONLY_SKIP_REASON = (
    "POSIX symlink 案例（快取裡允許、快取外不通過）；Windows 的 symlink 是 reparse point，"
    "一律不通過，由 Windows 案例涵蓋"
)
GIT_TEST_CONFIG = (
    "-c",
    "user.name=ToukaDev Test",
    "-c",
    "user.email=test@example.invalid",
    "-c",
    "commit.gpgsign=false",
    "-c",
    "core.autocrlf=false",
)
IGNORE_RULES = (
    ".toukadev/\n.venv/\n.uv-cache/\nnode_modules/\n__pycache__/\ndata/\n.env\n"
)
BUILD_IGNORES = "dist/\ndist-data/\n*.tsbuildinfo\n"
# CRLF 檔裡只有 \r 的空行：git 去掉 \r 後變成空規則，會命中任何加尾斜線的路徑。
CRLF_IGNORES = (IGNORE_RULES + "\n" + BUILD_IGNORES).replace("\n", "\r\n")
ORIGIN_MAIN = "refs/remotes/origin/main"
DECLARATION = "rebuildable-outputs.txt"
WINDOWS_CASE_SKIP_REASON = "只有 Windows 不分大小寫、\\ 等於 /；其他平台逐字比對（較嚴）"


def load_script(path: Path, name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"無法載入 {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


cc = load_script(ASSETS / "check_cleanup.py", "check_cleanup")


def make_junction(link: Path, target: Path) -> None:
    completed = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(link), str(target)],
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        raise OSError(completed.stderr.decode(errors="replace"))


def make_symlink_or_skip(test: TestCase, link: Path, target: Path) -> None:
    try:
        os.symlink(target, link, target_is_directory=target.is_dir())
    except (OSError, NotImplementedError) as error:
        test.skipTest(
            "這台電腦不能建立 symlink（Windows 需要開發人員模式或系統管理員權限）："
            f"{error}"
        )


class GitSandbox:
    """拋棄式 git repo；離開 with 區塊時整個刪掉。"""

    def __init__(self) -> None:
        self._tmp = TemporaryDirectory()
        self.base = Path(self._tmp.name).resolve()
        self.root = self.base / "repo"
        self.root.mkdir()
        empty_config = self.base / "empty-gitconfig"
        empty_config.write_text("", encoding="utf-8")
        self._env = patch.dict(
            os.environ,
            {"GIT_CONFIG_GLOBAL": str(empty_config), "GIT_CONFIG_NOSYSTEM": "1"},
        )

    def __enter__(self) -> "GitSandbox":
        self._env.start()
        self.git("init", "-q", "-b", "main")
        self.write(".gitignore", IGNORE_RULES)
        self.write("README.md", "demo\n")
        self.git("add", ".gitignore", "README.md")
        self.git("commit", "-q", "-m", "init")
        return self

    def __exit__(self, *exc_info: object) -> None:
        self._env.stop()
        self._tmp.cleanup()

    def git(self, *args: str, cwd: Path | None = None) -> str:
        completed = subprocess.run(
            ["git", *GIT_TEST_CONFIG, *args],
            cwd=cwd or self.root,
            capture_output=True,
            check=False,
        )
        if completed.returncode != 0:
            raise AssertionError(completed.stderr.decode(errors="replace"))
        return completed.stdout.decode("utf-8", errors="replace")

    def write(self, relative: str, text: str, base: Path | None = None) -> Path:
        path = (base or self.root) / relative
        if not path.resolve().is_relative_to(self.base):
            raise AssertionError(f"寫入目標不在暫存資料夾裡：{path}")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")
        return path

    def add_worktree(
        self, relative: str = ".toukadev/worktrees/demo-a", branch: str = "wt/demo-a"
    ) -> Path:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        self.git("worktree", "add", "-q", "-b", branch, str(path))
        return path

    def check(self, *argv: str, cwd: Path | None = None) -> tuple[int, str]:
        output = io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            code = cc.main(list(argv), cwd=cwd or self.root)
        return code, output.getvalue()


def snapshot(*folders: Path) -> dict[str, tuple[int, int]]:
    state: dict[str, tuple[int, int]] = {}
    for folder in folders:
        for current, directories, files in os.walk(folder):
            for name in [*directories, *files]:
                info = os.lstat(os.path.join(current, name))
                state[os.path.join(current, name)] = (info.st_mtime_ns, info.st_size)
    return state


def commit_declaration(sandbox: GitSandbox, *items: str, text: str | None = None) -> None:
    """提交忽略規則與根 rebuildable-outputs.txt（一行一個 item，或原樣的 text；兩者都沒有就不建檔）。"""
    sandbox.write(".gitignore", IGNORE_RULES + BUILD_IGNORES)
    if text is not None or items:
        sandbox.write(DECLARATION, "".join(f"{item}\n" for item in items) if text is None else text)
    sandbox.git("add", "--all")
    sandbox.git("commit", "-q", "-m", "declare build outputs")


def link_outside(link: str) -> Callable[[GitSandbox, Path], None]:
    """在工作資料夾的 link 位置建立指到暫存區外部資料夾的連結（Windows 用 junction）。"""

    def prepare(sandbox: GitSandbox, worktree: Path) -> None:
        (sandbox.base / "outside").mkdir()
        (worktree / link).parent.mkdir(parents=True, exist_ok=True)
        if IS_WINDOWS:
            make_junction(worktree / link, sandbox.base / "outside")
        else:
            os.symlink(sandbox.base / "outside", worktree / link, True)

    return prepare


class WorktreeCheckTests(TestCase):
    def test_clean_worktree_with_rebuildable_caches_passes(self) -> None:
        with GitSandbox() as sandbox:
            worktree = sandbox.add_worktree()
            sandbox.write(".venv/lib/site.txt", "x", base=worktree)
            sandbox.write("pkg/__pycache__/module.pyc", "x", base=worktree)
            code, output = sandbox.check(
                "worktree", str(worktree), "--branch", "wt/demo-a"
            )
        self.assertEqual(code, 0, output)
        self.assertIn("可以清理", output)

    def test_relative_path_is_resolved_from_current_folder(self) -> None:
        with GitSandbox() as sandbox:
            sandbox.add_worktree()
            code, output = sandbox.check(
                "worktree", ".toukadev/worktrees/demo-a", "--branch", "wt/demo-a"
            )
        self.assertEqual(code, 0, output)

    def assert_worktree_refused(self, prepare: str, expected: str) -> None:
        with GitSandbox() as sandbox:
            worktree = sandbox.add_worktree()
            if prepare == "data":
                sandbox.write("data/real.db", "x", base=worktree)
            elif prepare == "env":
                sandbox.write(".env", "TOKEN=x\n", base=worktree)
            elif prepare == "untracked":
                sandbox.write("new-notes.txt", "x", base=worktree)
            elif prepare == "modified":
                sandbox.write("README.md", "changed\n", base=worktree)
            elif prepare == "detached":
                sandbox.git("checkout", "-q", "--detach", cwd=worktree)
            code, output = sandbox.check(
                "worktree", str(worktree), "--branch", "wt/demo-a"
            )
        self.assertEqual(code, 1, output)
        self.assertIn("不能自動清理", output)
        self.assertIn(expected, output)

    def test_ignored_data_folder_is_refused(self) -> None:
        self.assert_worktree_refused("data", "data")

    def test_ignored_env_file_is_refused(self) -> None:
        self.assert_worktree_refused("env", ".env")

    def test_untracked_file_is_refused(self) -> None:
        self.assert_worktree_refused("untracked", "new-notes.txt")

    def test_modified_file_is_refused(self) -> None:
        self.assert_worktree_refused("modified", "README.md")

    def test_detached_head_is_refused(self) -> None:
        self.assert_worktree_refused("detached", "detached")

    def test_wrong_branch_is_refused(self) -> None:
        with GitSandbox() as sandbox:
            worktree = sandbox.add_worktree()
            code, output = sandbox.check(
                "worktree", str(worktree), "--branch", "wt/other"
            )
        self.assertEqual(code, 1, output)
        self.assertIn("wt/other", output)

    def test_worktree_outside_toukadev_worktrees_is_refused(self) -> None:
        with GitSandbox() as sandbox:
            worktree = sandbox.add_worktree("elsewhere/demo-b", "wt/demo-b")
            code, output = sandbox.check(
                "worktree", str(worktree), "--branch", "wt/demo-b"
            )
        self.assertEqual(code, 1, output)
        self.assertIn(".toukadev/worktrees", output)

    def test_plain_folder_is_not_a_worktree(self) -> None:
        with GitSandbox() as sandbox:
            fake = sandbox.root / ".toukadev" / "worktrees" / "fake"
            fake.mkdir(parents=True)
            code, output = sandbox.check("worktree", str(fake), "--branch", "main")
        self.assertEqual(code, 1, output)
        self.assertIn("git worktree list", output)

    @skipUnless(IS_WINDOWS, JUNCTION_SKIP_REASON)
    def test_junction_inside_worktree_is_refused(self) -> None:
        with GitSandbox() as sandbox:
            worktree = sandbox.add_worktree()
            outside = sandbox.base / "outside"
            outside.mkdir()
            (worktree / ".venv").mkdir()
            make_junction(worktree / ".venv" / "link", outside)
            code, output = sandbox.check(
                "worktree", str(worktree), "--branch", "wt/demo-a"
            )
        self.assertEqual(code, 1, output)
        self.assertIn("連結", output)

    @skipUnless(IS_WINDOWS, WINDOWS_SYMLINK_SKIP_REASON)
    def test_windows_symlink_inside_cache_is_refused(self) -> None:
        with GitSandbox() as sandbox:
            worktree = sandbox.add_worktree()
            outside = sandbox.base / "outside"
            outside.mkdir()
            (worktree / ".venv").mkdir()
            make_symlink_or_skip(self, worktree / ".venv" / "link", outside)
            code, output = sandbox.check(
                "worktree", str(worktree), "--branch", "wt/demo-a"
            )
        self.assertEqual(code, 1, output)
        self.assertIn("連結", output)

    @skipIf(IS_WINDOWS, POSIX_ONLY_SKIP_REASON)
    def test_posix_symlink_inside_cache_passes_and_remove_keeps_target(self) -> None:
        with GitSandbox() as sandbox:
            worktree = sandbox.add_worktree()
            outside = sandbox.base / "outside"
            outside.mkdir()
            (outside / "keep.txt").write_text("keep", encoding="utf-8")
            (worktree / ".venv" / "bin").mkdir(parents=True)
            os.symlink(outside, worktree / ".venv" / "bin" / "external", True)
            os.symlink(outside / "keep.txt", worktree / ".venv" / "bin" / "python")
            code, output = sandbox.check(
                "worktree", str(worktree), "--branch", "wt/demo-a"
            )
            self.assertEqual(code, 0, output)
            sandbox.git("worktree", "remove", str(worktree))
            self.assertFalse(worktree.exists())
            self.assertEqual(
                sorted(path.name for path in outside.iterdir()), ["keep.txt"]
            )
            self.assertEqual((outside / "keep.txt").read_text("utf-8"), "keep")

    @skipIf(IS_WINDOWS, POSIX_ONLY_SKIP_REASON)
    def test_posix_symlink_outside_cache_is_refused(self) -> None:
        with GitSandbox() as sandbox:
            outside = sandbox.base / "outside"
            outside.mkdir()
            os.symlink("../outside", sandbox.root / "linked-docs", True)
            sandbox.git("add", "linked-docs")
            sandbox.git("commit", "-q", "-m", "tracked link")
            worktree = sandbox.add_worktree()
            code, output = sandbox.check(
                "worktree", str(worktree), "--branch", "wt/demo-a"
            )
        self.assertEqual(code, 1, output)
        self.assertIn("連結", output)
        self.assertIn("linked-docs", output)
        self.assertNotIn("還沒", output)

    def test_only_posix_symlinks_inside_caches_are_allowed(self) -> None:
        reparse = stat.FILE_ATTRIBUTE_REPARSE_POINT
        posix_link = SimpleNamespace(st_mode=stat.S_IFLNK)
        windows_link = SimpleNamespace(st_mode=stat.S_IFLNK, st_file_attributes=reparse)
        junction = SimpleNamespace(st_mode=stat.S_IFDIR, st_file_attributes=reparse)
        cases = (
            (posix_link, False, (".venv", "bin", "python"), True),
            (posix_link, False, ("pkg", "__pycache__", "x"), True),
            (posix_link, False, ("node_modules", ".bin", "tool"), True),
            (posix_link, False, ("docs", "link"), False),
            (posix_link, False, (".venv",), False),
            (posix_link, True, (".venv", "link"), False),
            (windows_link, False, (".venv", "link"), False),
            (junction, False, (".venv", "link"), False),
            (junction, True, (".venv", "link"), False),
        )
        for info, is_junction, parts, expected in cases:
            with self.subTest(parts=parts, is_junction=is_junction):
                self.assertEqual(
                    cc.is_allowed_cache_link(info, is_junction, parts), expected
                )

    def test_hidden_changes_flags_are_refused(self) -> None:
        for flag in ("--skip-worktree", "--assume-unchanged"):
            with self.subTest(flag=flag), GitSandbox() as sandbox:
                worktree = sandbox.add_worktree()
                sandbox.git("update-index", flag, "README.md", cwd=worktree)
                sandbox.write("README.md", "hidden change\n", base=worktree)
                code, output = sandbox.check(
                    "worktree", str(worktree), "--branch", "wt/demo-a"
                )
                self.assertEqual(code, 1, output)
                self.assertIn("skip-worktree", output)
                self.assertIn("README.md", output)

    def test_nested_repository_inside_cache_is_refused(self) -> None:
        for relative, as_folder in (
            (".venv/src/package/.git", True),
            ("node_modules/dep/.git", False),
        ):
            with self.subTest(relative=relative), GitSandbox() as sandbox:
                worktree = sandbox.add_worktree()
                nested = worktree / relative
                if as_folder:
                    sandbox.write("HEAD", "ref: refs/heads/main\n", base=nested)
                else:
                    sandbox.write(relative, "gitdir: elsewhere\n", base=worktree)
                code, output = sandbox.check(
                    "worktree", str(worktree), "--branch", "wt/demo-a"
                )
                self.assertEqual(code, 1, output)
                self.assertIn(".git", output)
                self.assertIn(relative.rsplit("/", 1)[0], output)

    def test_git_entries_inside_and_outside_caches(self) -> None:
        """uv 在快取裡放的 0 位元組 .git 標記檔不算 repo；其他 .git 一律不通過。"""
        cases = (
            (".uv-cache/sdists-v9/.git", "empty-file", True),
            (".uv-cache/sdists-v9/.git", "folder", False),
            (".uv-cache/sdists-v9/.git", "gitdir-file", False),
            (".uv-cache/sdists-v9/.GIT", "folder", False),
            (".venv/lib/.Git", "gitdir-file", False),
            ("tools/.git", "empty-file", False),
        )
        for relative, kind, passes in cases:
            with self.subTest(relative=relative, kind=kind), GitSandbox() as sandbox:
                worktree = sandbox.add_worktree()
                sandbox.write(".uv-cache/CACHEDIR.TAG", "Signature\n", base=worktree)
                marker = worktree / relative
                marker.parent.mkdir(parents=True, exist_ok=True)
                if kind == "empty-file":
                    marker.write_bytes(b"")
                elif kind == "folder":
                    sandbox.write("HEAD", "ref: refs/heads/main\n", base=marker)
                else:
                    marker.write_text("gitdir: elsewhere\n", encoding="utf-8")
                code, output = sandbox.check(
                    "worktree", str(worktree), "--branch", "wt/demo-a"
                )
                if passes:
                    self.assertEqual(code, 0, output)
                    continue
                self.assertEqual(code, 1, output)
                nested_lines = [
                    line for line in output.splitlines() if "另一個 git repo" in line
                ]
                self.assertEqual(len(nested_lines), 1, output)
                self.assertIn(relative, nested_lines[0])

    @skipIf(IS_WINDOWS, POSIX_ONLY_SKIP_REASON)
    def test_git_marker_that_is_a_link_is_refused(self) -> None:
        with GitSandbox() as sandbox:
            worktree = sandbox.add_worktree()
            empty = sandbox.base / "empty"
            empty.write_bytes(b"")
            (worktree / ".uv-cache" / "sdists-v9").mkdir(parents=True)
            os.symlink(empty, worktree / ".uv-cache" / "sdists-v9" / ".git")
            code, output = sandbox.check(
                "worktree", str(worktree), "--branch", "wt/demo-a"
            )
        self.assertEqual(code, 1, output)
        self.assertIn(".uv-cache/sdists-v9/.git", output)

    def test_folder_on_another_device_is_refused(self) -> None:
        with GitSandbox() as sandbox:
            worktree = sandbox.add_worktree()
            (worktree / ".venv" / "mounted").mkdir(parents=True)
            real_device = cc.device_of

            def fake_device(path: Path) -> int:
                return real_device(path) + (1 if path.name == "mounted" else 0)

            with patch.object(cc, "device_of", side_effect=fake_device):
                code, output = sandbox.check(
                    "worktree", str(worktree), "--branch", "wt/demo-a"
                )
        self.assertEqual(code, 1, output)
        self.assertIn("其他磁碟", output)
        self.assertIn(".venv/mounted", output)

    def test_checks_never_modify_the_repository(self) -> None:
        with GitSandbox() as sandbox:
            worktree = sandbox.add_worktree()
            sandbox.write("README.md", "changed\n", base=worktree)
            (sandbox.root / ".toukadev" / "tmp" / "demo").mkdir(parents=True)
            before = snapshot(sandbox.root, worktree)
            sandbox.check("worktree", str(worktree), "--branch", "wt/demo-a")
            sandbox.check(
                "tmp", str(sandbox.root / ".toukadev/tmp/demo"), "--task", "demo"
            )
            sandbox.check("branch", "wt/demo-a")
            after = snapshot(sandbox.root, worktree)
        self.assertEqual(before, after)


class BuildOutputDeclarationTests(TestCase):
    """預設分支（只認 origin/HEAD）上根 rebuildable-outputs.txt 的建置產物宣告。"""

    def run_declared(
        self,
        items: tuple[str, ...],
        files: tuple[str, ...] = ("web/dist/app.js",),
        prepare: Callable[[GitSandbox, Path], None] | None = None,
        origin: tuple[str, str | None] = ("HEAD", ORIGIN_MAIN),
        text: str | None = None,
    ) -> tuple[int, str]:
        """origin＝（遠端 main 指的 commit, origin/HEAD 指向，None 不設）；也確認沒寫入。"""
        with GitSandbox() as sandbox:
            commit_declaration(sandbox, *items, text=text)
            sandbox.git("update-ref", ORIGIN_MAIN, origin[0])
            if origin[1] is not None:
                sandbox.git("symbolic-ref", "refs/remotes/origin/HEAD", origin[1])
            worktree = sandbox.add_worktree()
            for relative in files:
                sandbox.write(relative, "", base=worktree)
            if prepare is not None:
                prepare(sandbox, worktree)
            before = snapshot(sandbox.root, worktree)
            result = sandbox.check("worktree", str(worktree), "--branch", "wt/demo-a")
            self.assertEqual(snapshot(sandbox.root, worktree), before)
        return result

    def assert_refused(self, result: tuple[int, str], *needles: str) -> None:
        self.assertEqual(result[0], 1, result[1])
        for needle in needles:
            self.assertIn(needle, result[1])

    def test_declared_build_outputs_pass(self) -> None:
        built = ("web/dist/app.js", "web/dist/assets/a.css", "web/tsconfig.tsbuildinfo")
        code, output = self.run_declared(
            ("web/dist/", "web/tsconfig.tsbuildinfo"), (*built, ".venv/lib/site.txt")
        )
        self.assertEqual(code, 0, output)

    def test_directory_only_rule_with_and_without_trailing_slash(self) -> None:
        """dist/ 只比對資料夾；宣告有沒有尾斜線、dist 有沒有建出來都要認得。"""
        for item in ("web/dist/", "web/dist"):
            for built in ((), ("web/dist/app.js",)):
                with self.subTest(item=item, built=built):
                    files = ("web/tsconfig.tsbuildinfo", *built)
                    code, output = self.run_declared((item, files[0]), files)
                    self.assertEqual(code, 0, output)

    def test_sibling_with_same_name_prefix_is_refused(self) -> None:
        code, output = self.run_declared(
            ("web/dist",), ("web/dist/app.js", "web/dist-data/real.db")
        )
        blocked = [line for line in output.splitlines() if "被 git 忽略" in line]
        self.assertEqual((code, len(blocked)), (1, 1), output)
        self.assertIn("web/dist-data/", blocked[0])
        self.assertNotIn("web/dist/", blocked[0])

    def test_one_invalid_line_voids_the_whole_declaration(self) -> None:
        for bad, reason in (
            ("- web/dist/", "清單符號"),
            ("# 說明", "# 開頭"),
            ("web/dist/ ", "前後有空白"),
            ("src/generated/", "沒被 git 忽略"),
        ):
            with self.subTest(bad=bad):
                result = self.run_declared(("web/dist/", bad))
                self.assert_refused(result, "web/dist/", f"第 2 行「{bad}」", reason)

    def test_missing_or_empty_file_is_no_declaration(self) -> None:
        """沒有檔、空檔或只有空行都是沒有宣告：照舊擋下，不印附註。"""
        for text in (None, "", "\n\r\n\n"):
            with self.subTest(text=text):
                result = self.run_declared((), text=text)
                self.assert_refused(result, "web/dist/")
                self.assertNotIn("附註", result[1])

    def test_bom_and_crlf_are_stripped(self) -> None:
        text = "\ufeffweb/dist/\r\n\r\nweb/tsconfig.tsbuildinfo\r\n"
        code, output = self.run_declared((), ("web/dist/app.js", "web/tsconfig.tsbuildinfo"), text=text)
        self.assertEqual(code, 0, output)

    def test_adopted_note_only_when_the_declaration_is_used(self) -> None:
        for files, expected in (((".venv/x",), (0, False)), (("web/dist/a",), (0, True)), (("data/x",), (1, True))):
            with self.subTest(files=files):
                code, output = self.run_declared(("web/dist/",), files)
                self.assertEqual((code, "附註：已採用宣告" in output), expected, output)

    def test_symlink_declaration_file_is_refused_without_reading_its_target(self) -> None:
        def link_on_default_branch(sandbox: GitSandbox, worktree: Path) -> None:
            blob = sandbox.git("hash-object", "-w", str(sandbox.write("t", "web/dist/", base=sandbox.base)))
            sandbox.git("update-index", "--add", "--cacheinfo", f"120000,{blob.strip()},{DECLARATION}")
            sandbox.git("commit", "-q", "-m", "symlink declaration")
            sandbox.git("update-ref", ORIGIN_MAIN, "HEAD")

        result = self.run_declared((), prepare=link_on_default_branch)
        self.assert_refused(result, "web/dist/", f"{ORIGIN_MAIN} 上的 {DECLARATION} 不是一般檔（例如 symlink）")

    def test_invisible_characters_and_trailing_comments_are_invalid(self) -> None:
        invisible = ((f"web/di{c}st", "看不見的字元") for c in (chr(0), chr(13), chr(0x200B), chr(0xFEFF), "\t"))
        for path, reason in (*invisible, ("web/dist/ # x", "行尾註解"), ("web/dist #x", "行尾註解")):
            with self.subTest(path=path):
                self.assertIn(reason, cc.path_problem(path) or "")
        self.assert_refused(self.run_declared((), text=f"web/dist/\nweb/{chr(0)}x\n"), "第 2 行", "看不見的字元")

    def test_declaration_only_on_a_work_branch_is_refused(self) -> None:
        """遠端預設分支停在宣告之前；主要資料夾目前分支與工作分支上的宣告都不算。"""
        result = self.run_declared(("web/dist/",), origin=("HEAD~1", ORIGIN_MAIN))
        self.assert_refused(result, "web/dist/")
        self.assertNotIn("附註", result[1])

    def test_unreadable_default_branch_is_refused(self) -> None:
        for head in ("refs/remotes/origin/missing", "refs/heads/main"):
            with self.subTest(head=head):
                result = self.run_declared(("web/dist/",), origin=("HEAD", head))
                self.assert_refused(result, "web/dist/", "沒有採用建置產物宣告")

    def test_missing_origin_head_does_not_fall_back_to_main_or_dev(self) -> None:
        def add_dev(sandbox: GitSandbox, worktree: Path) -> None:
            sandbox.git("branch", "dev")
            sandbox.git("update-ref", "refs/remotes/origin/dev", "HEAD")

        result = self.run_declared(("web/dist/",), prepare=add_dev, origin=("HEAD", None))
        self.assert_refused(result, "web/dist/", "讀不到 refs/remotes/origin/HEAD")

    def test_git_entries_under_declared_path_are_refused(self) -> None:
        """宣告路徑底下不沿用快取豁免：快取名稱資料夾裡的空白 .git 也擋。"""
        for marker in (
            "web/dist/.git",
            "web/dist/node_modules/pkg/.git",
            "web/dist/sub/.git/HEAD",
        ):
            with self.subTest(marker=marker):
                code, output = self.run_declared(("web/dist/",), (marker,))
                nested = [line for line in output.splitlines() if "另一個 git repo" in line]
                self.assertEqual((code, len(nested)), (1, 1), output)
                self.assertIn(marker.removesuffix("/HEAD"), nested[0])

    def test_links_at_or_under_declared_path_are_refused(self) -> None:
        """Windows 用 junction、其他平台用 POSIX symlink（快取名稱資料夾裡也擋）。"""
        for declared, link in (
            ("web/dist/", "web/dist"),
            ("web/dist/", "web/dist/node_modules/.bin/tool"),
            ("node_modules/.cache/build/", "node_modules/.cache/build"),
        ):
            with self.subTest(link=link):
                result = self.run_declared((declared,), (), link_outside(link))
                self.assert_refused(result, "連結", link)

    @skipUnless(IS_WINDOWS, WINDOWS_CASE_SKIP_REASON)
    def test_windows_case_and_separator_differences_match(self) -> None:
        code, output = self.run_declared(("web/dist/",), ("Web/DIST/app.js",))
        self.assertEqual(code, 0, output)

    def test_path_keys_fold_ascii_case_only_on_windows(self) -> None:
        declared = (cc.path_key("web/dist/"),)
        self.assertEqual(cc.is_declared("Web\\DIST\\app.js", declared), IS_WINDOWS)
        self.assertEqual(cc.is_declared("WEB/dist/", declared), IS_WINDOWS)
        self.assertTrue(cc.is_declared("web/dist/", declared))
        self.assertFalse(cc.is_declared("web/dist-data/x", declared))
        self.assertFalse(cc.is_declared("web", declared))
        self.assertNotEqual(cc.path_key("Ä"), cc.path_key("ä"))
        self.assertNotEqual(cc.path_key("straße"), cc.path_key("STRASSE"))

    def test_declared_path_rules(self) -> None:
        for path in ("web/dist", "web/dist/", "web/a.tsbuildinfo", "src/generated"):
            with self.subTest(path=path):
                self.assertIsNone(cc.path_problem(path))
        for path in (
            *("", " dist", "/", ".", "./", "/srv/dist", "C:/dist", "C:dist"),
            *("web\\dist", "..", "../x", "web/../x", "web/./x", "web//x", "dist/*"),
            *("a?b", "[ab]", ".git/x", "web/.GIT", ".toukadev/x", "a/.Toukadev"),
            *("- web/dist/", "+ web", "1. web", "`web/dist/`", "# 說明", "web/#x", "web/dist\r"),
        ):
            with self.subTest(path=path):
                self.assertIsNotNone(cc.path_problem(path))

    def test_cache_name_segments_cannot_be_declared(self) -> None:
        """快取名稱不必宣告（整份不採用）；但檔案列出的路徑底下仍不沿用快取豁免。"""
        for path in (".venv", "web/node_modules/", "pkg/__pycache__/x", "Web/.UV-Cache"):
            with self.subTest(path=path):
                self.assertIn("已是可重建快取，不必宣告", cc.path_problem(path) or "")
        files = ("web/dist/app.js", "web/node_modules/pkg/.git")
        result = self.run_declared(("web/dist/", "web/node_modules/"), files)
        self.assert_refused(result, "第 2 行「web/node_modules/」已是可重建快取，不必宣告")
        self.assertRegex(result[1], "web/node_modules/pkg/.git.*宣告路徑裡不沿用快取豁免")

    def test_origin_head_naming_a_work_branch_is_not_used(self) -> None:
        """主要資料夾在預設分支上照常採用（宣告路徑外的快取豁免還在）；指到連結工作資料夾的分支就不採用。"""
        files = ("web/dist/app.js", ".uv-cache/git-v0/checkouts/abc/.git")
        code, output = self.run_declared(("web/dist/",), files)
        self.assertEqual(code, 0, output)
        self.assertRegex(output, f"(?m)^附註：已採用宣告（{ORIGIN_MAIN} @ [0-9a-f]{{7}}）：web/dist/$")
        for branch, items in (("wt/demo-a", ("web/dist/",)), ("wt/demo-b", ("web/dist/",)), ("wt/demo-a", ())):

            def point_at(sandbox: GitSandbox, worktree: Path, branch: str = branch) -> None:
                if branch == "wt/demo-b":
                    sandbox.add_worktree(".toukadev/worktrees/demo-b", branch)
                sandbox.git("update-ref", f"refs/remotes/origin/{branch}", branch)
                sandbox.git("symbolic-ref", "refs/remotes/origin/HEAD", f"refs/remotes/origin/{branch}")

            with self.subTest(branch=branch, items=items):
                code, output = self.run_declared(items, prepare=point_at)
                self.assertEqual(code, 1, output)
                note = f"附註：這次沒有採用建置產物宣告：refs/remotes/origin/{branch} 和工作資料夾的分支 {branch} 同名。"
                self.assertEqual(note in output.splitlines(), bool(items), output)
                self.assertEqual("附註" in output, bool(items), output)

    def test_bare_repository_under_declared_path_is_refused(self) -> None:
        def bare(sandbox: GitSandbox, worktree: Path) -> None:
            sandbox.git("init", "-q", "--bare", str(worktree / "web" / "dist" / "mirror.git"))

        code, output = self.run_declared(("web/dist/",), prepare=bare)
        self.assertEqual(code, 1, output)
        self.assertRegex(output, "(?m)^- 裡面有另一個 git repo.*web/dist/mirror.git")
        self.assertRegex(output, "(?m)^附註：已採用宣告（.+）：web/dist/$")

    def test_unignored_declared_path_names_a_tracked_file(self) -> None:
        with GitSandbox() as sandbox:
            sandbox.write("web/dist/keep.txt", "k")
            sandbox.git("add", "web/dist/keep.txt")
            tracked = cc.ignore_problem(sandbox.root, "web/dist/") or ""
            plain = cc.ignore_problem(sandbox.root, "src/generated/") or ""
        self.assertIn("沒被 git 忽略：底下有被 git 追蹤的檔（例如 web/dist/keep.txt）", tracked)
        self.assertIn("沒被 git 忽略（git check-ignore）", plain)

    def test_crlf_blank_line_does_not_count_as_ignored(self) -> None:
        """CRLF 的 .gitignore：被忽略的 web/dist/ 照常認得，沒被忽略的 src/generated/ 讓整份不採用。"""

        def crlf_ignores(sandbox: GitSandbox, worktree: Path) -> None:
            sandbox.write(".gitignore", CRLF_IGNORES, base=worktree)
            sandbox.git("commit", "-q", "-am", "crlf ignores", cwd=worktree)

        result = self.run_declared(("web/dist/", "src/generated/"), prepare=crlf_ignores)
        self.assert_refused(result, "web/dist/", "第 2 行「src/generated/」", "沒被 git 忽略")

    def test_only_non_empty_non_negated_rules_count_as_ignored(self) -> None:
        """空規則（CRLF 空行）與 ! 開頭的規則命中都不算被忽略；git 出錯時說確認不了。"""
        unignored, negated = "沒被 git 忽略（git check-ignore）", "dist/\n!web/dist/\n"
        cases = (
            (CRLF_IGNORES, "web/dist/", None),
            (CRLF_IGNORES, "src/generated/", unignored),
            (negated, "app/dist/", None),
            (negated, "web/dist/", unignored),
        )
        for ignores, path, expected in cases:
            with self.subTest(ignores=ignores, path=path), GitSandbox() as sandbox:
                sandbox.write(".gitignore", ignores)
                sandbox.write("web/dist/app.js", "")
                problem = cc.ignore_problem(sandbox.root, path)
                if expected is None:
                    self.assertIsNone(problem)
                else:
                    self.assertIn(expected, problem or "")
        with GitSandbox() as sandbox:
            failed = cc.ignore_problem(sandbox.base / "missing", "web/dist/")
        self.assertEqual(failed, "沒辦法用 git check-ignore 確認有沒有被忽略")

    @skipIf(IS_WINDOWS, POSIX_ONLY_SKIP_REASON)
    def test_posix_cache_symlink_outside_declared_paths_still_passes(self) -> None:
        def venv_link(sandbox: GitSandbox, worktree: Path) -> None:
            (worktree / ".venv" / "bin").mkdir(parents=True)
            os.symlink(sandbox.base / "python", worktree / ".venv" / "bin" / "python")

        code, output = self.run_declared(("web/dist/",), prepare=venv_link)
        self.assertEqual(code, 0, output)

    def test_fake_posix_symlink_under_declared_path_is_refused(self) -> None:
        """用假的 stat（S_IFLNK、沒有 reparse 屬性），Windows 上也驗 POSIX symlink 的覆寫。"""
        start, fake = Path("sim"), SimpleNamespace(st_mode=stat.S_IFLNK, st_size=5)
        for declared, relative, blocked in (
            (("web/dist",), "web/dist/node_modules/.bin/tool", True),
            (("node_modules/.cache/build",), "node_modules/.cache/build", True),
            ((), "web/dist/node_modules/.bin/tool", False),
        ):
            with self.subTest(declared=declared):
                name, stat_of, junction = relative.rsplit("/", 1)[-1], lambda follow_symlinks: fake, bool
                entry = SimpleNamespace(path=str(start / relative), name=name, stat=stat_of, is_junction=junction)
                findings = cc.TreeFindings()
                cc.visit(entry, start, 0, [], findings, declared)
                self.assertEqual(bool(findings.links), blocked)


class TmpCheckTests(TestCase):
    def test_own_task_folder_passes(self) -> None:
        with GitSandbox() as sandbox:
            sandbox.write(".toukadev/tmp/demo/red.log", "x")
            code, output = sandbox.check(
                "tmp", str(sandbox.root / ".toukadev/tmp/demo"), "--task", "demo"
            )
            relative_code, _ = sandbox.check(
                "tmp", ".toukadev/tmp/demo", "--task", "demo"
            )
        self.assertEqual(code, 0, output)
        self.assertIn("可以清理", output)
        self.assertEqual(relative_code, 0)

    def test_wrong_level_is_refused(self) -> None:
        with GitSandbox() as sandbox:
            sandbox.write(".toukadev/tmp/demo/sub/red.log", "x")
            for location in (".toukadev/tmp", ".toukadev/tmp/demo/sub", ".toukadev"):
                with self.subTest(location=location):
                    code, output = sandbox.check(
                        "tmp", str(sandbox.root / location), "--task", "demo"
                    )
                    self.assertEqual(code, 1, output)
                    self.assertIn("正好", output)

    def test_invalid_task_code_is_refused(self) -> None:
        with GitSandbox() as sandbox:
            for task in ("Demo", "index", "a_b", "demo/x"):
                with self.subTest(task=task):
                    folder = sandbox.root / ".toukadev" / "tmp" / task
                    folder.mkdir(parents=True, exist_ok=True)
                    code, output = sandbox.check("tmp", str(folder), "--task", task)
                    self.assertEqual(code, 1, output)
                    self.assertIn("任務代號", output)

    def test_worktree_inside_is_refused(self) -> None:
        with GitSandbox() as sandbox:
            sandbox.add_worktree(".toukadev/tmp/demo/wt", "wt/inside")
            code, output = sandbox.check(
                "tmp", str(sandbox.root / ".toukadev/tmp/demo"), "--task", "demo"
            )
        self.assertEqual(code, 1, output)
        self.assertIn("工作資料夾", output)

    @skipUnless(IS_WINDOWS, JUNCTION_SKIP_REASON)
    def test_junction_start_is_refused(self) -> None:
        with GitSandbox() as sandbox:
            outside = sandbox.base / "outside"
            outside.mkdir()
            (sandbox.root / ".toukadev" / "tmp").mkdir(parents=True)
            make_junction(sandbox.root / ".toukadev/tmp/demo", outside)
            code, output = sandbox.check(
                "tmp", str(sandbox.root / ".toukadev/tmp/demo"), "--task", "demo"
            )
        self.assertEqual(code, 1, output)
        self.assertIn("連結", output)

    def test_symlink_start_is_refused(self) -> None:
        with GitSandbox() as sandbox:
            outside = sandbox.base / "outside"
            outside.mkdir()
            (sandbox.root / ".toukadev" / "tmp").mkdir(parents=True)
            make_symlink_or_skip(self, sandbox.root / ".toukadev/tmp/demo", outside)
            code, output = sandbox.check(
                "tmp", str(sandbox.root / ".toukadev/tmp/demo"), "--task", "demo"
            )
        self.assertEqual(code, 1, output)
        self.assertIn("連結", output)


class BranchCheckTests(TestCase):
    def test_free_task_branch_passes(self) -> None:
        with GitSandbox() as sandbox:
            sandbox.git("branch", "wt/old")
            code, output = sandbox.check("branch", "wt/old")
        self.assertEqual(code, 0, output)
        self.assertIn("可以清理", output)

    def test_shared_branches_are_refused(self) -> None:
        with GitSandbox() as sandbox:
            for name in (*cc.SHARED_BRANCH_NAMES, "origin/dev", "remotes/origin/main"):
                with self.subTest(name=name):
                    code, output = sandbox.check("branch", name)
                    self.assertEqual(code, 1, output)
                    self.assertIn("共用分支", output)

    def test_current_branch_is_refused(self) -> None:
        with GitSandbox() as sandbox:
            sandbox.git("checkout", "-q", "-b", "topic")
            code, output = sandbox.check("branch", "topic")
        self.assertEqual(code, 1, output)
        self.assertIn("目前所在", output)

    def test_branch_used_by_worktree_is_refused(self) -> None:
        with GitSandbox() as sandbox:
            sandbox.add_worktree()
            code, output = sandbox.check("branch", "wt/demo-a")
        self.assertEqual(code, 1, output)
        self.assertIn("工作資料夾", output)

    def test_default_branch_from_origin_head_is_refused(self) -> None:
        with GitSandbox() as sandbox:
            sandbox.git("branch", "release")
            sandbox.git("update-ref", "refs/remotes/origin/release", "HEAD")
            sandbox.git(
                "symbolic-ref",
                "refs/remotes/origin/HEAD",
                "refs/remotes/origin/release",
            )
            code, output = sandbox.check("branch", "release")
        self.assertEqual(code, 1, output)
        self.assertIn("預設分支", output)


class CommandTests(TestCase):
    def test_outside_any_repository_fails(self) -> None:
        with TemporaryDirectory() as folder:
            output = io.StringIO()
            with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
                code = cc.main(["branch", "wt/x"], cwd=Path(folder))
        self.assertEqual(code, 1)
        self.assertIn(".git", output.getvalue())

    def test_running_inside_a_worktree_fails(self) -> None:
        with GitSandbox() as sandbox:
            worktree = sandbox.add_worktree()
            sandbox.git("branch", "wt/old")
            code, output = sandbox.check("branch", "wt/old", cwd=worktree)
        self.assertEqual(code, 1, output)
        self.assertIn("主要的專案資料夾", output)

    def test_old_python_gets_a_friendly_message(self) -> None:
        self.assertIn("3.12", cc.unsupported_python_message((3, 11, 4)))
        self.assertIn("3.11", cc.unsupported_python_message((3, 11, 4)))
        self.assertIsNone(cc.unsupported_python_message((3, 12, 0)))
        output = io.StringIO()
        with patch.object(cc.sys, "version_info", (3, 11, 4)):
            with contextlib.redirect_stderr(output):
                code = cc.main(["branch", "wt/x"], cwd=ROOT)
        self.assertEqual(code, 2)
        self.assertIn("3.12", output.getvalue())

    def test_runs_as_a_script(self) -> None:
        with GitSandbox() as sandbox:
            sandbox.git("branch", "wt/old")
            passed = subprocess.run(
                [sys.executable, str(SCRIPTS[0]), "branch", "wt/old"],
                cwd=sandbox.root,
                capture_output=True,
                check=False,
                env={**os.environ, "PYTHONIOENCODING": "utf-8"},
            )
            refused = subprocess.run(
                [sys.executable, str(SCRIPTS[0]), "branch", "main"],
                cwd=sandbox.root,
                capture_output=True,
                check=False,
                env={**os.environ, "PYTHONIOENCODING": "utf-8"},
            )
        self.assertEqual(passed.returncode, 0, passed.stderr)
        self.assertIn("可以清理", passed.stdout.decode("utf-8"))
        self.assertEqual(refused.returncode, 1)
        self.assertIn("共用分支", refused.stdout.decode("utf-8"))

    def test_unencodable_file_names_do_not_crash_the_output(self) -> None:
        with GitSandbox() as sandbox:
            worktree = sandbox.add_worktree()
            sandbox.write("note-😀.txt", "x", base=worktree)
            buffer = io.BytesIO()
            narrow = io.TextIOWrapper(buffer, encoding="cp950", errors="strict")
            with contextlib.redirect_stdout(narrow), contextlib.redirect_stderr(narrow):
                code = cc.main(
                    ["worktree", str(worktree), "--branch", "wt/demo-a"],
                    cwd=sandbox.root,
                )
            narrow.flush()
            script = subprocess.run(
                [sys.executable, str(SCRIPTS[0]), "worktree", str(worktree)]
                + ["--branch", "wt/demo-a"],
                cwd=sandbox.root,
                capture_output=True,
                check=False,
                env={**os.environ, "PYTHONIOENCODING": "cp950"},
            )
        text = buffer.getvalue().decode("cp950")
        self.assertEqual(code, 1)
        self.assertIn("不能自動清理", text)
        self.assertIn("note-", text)
        self.assertEqual(script.returncode, 1, script.stderr.decode("cp950", "replace"))
        self.assertNotIn(b"Traceback", script.stderr)
        self.assertIn("note-", script.stdout.decode("cp950"))

    def test_shared_branch_list(self) -> None:
        self.assertEqual(
            cc.SHARED_BRANCH_NAMES, ("main", "master", "dev", "develop", "trunk")
        )

    def test_checker_has_no_deleting_or_writing_operations(self) -> None:
        source = SCRIPTS[0].read_text(encoding="utf-8")
        for needle in (
            "shutil",
            ".unlink(",
            ".rmdir(",
            "os.remove",
            "rmtree",
            "os.rename",
            "os.replace",
            "write_text",
            "write_bytes",
            "open(",
        ):
            with self.subTest(needle=needle):
                self.assertNotIn(needle, source)
        constants = {
            node.value
            for node in ast.walk(ast.parse(source))
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
        }
        forbidden = {
            "add",
            "checkout",
            "clean",
            "commit",
            "delete",
            "-d",
            "-D",
            "--delete",
            "gc",
            "prune",
            "push",
            "remove",
            "reset",
            "update-ref",
        }
        self.assertEqual(constants & forbidden, set())


class OldPythonCompatibilityTests(TestCase):
    """舊版 Python 至少要能讀進檔案，才看得到「需要 3.12」的友善訊息。"""

    def test_scripts_parse_with_python_38_grammar(self) -> None:
        for script in SCRIPTS:
            with self.subTest(script=script.name):
                source = script.read_text(encoding="utf-8")
                ast.parse(source, feature_version=(3, 8))
                self.assertIn("from __future__ import annotations", source)

    def test_fstrings_do_not_use_python_312_only_syntax(self) -> None:
        for script in SCRIPTS:
            with self.subTest(script=script.name):
                self.assertEqual(fstring_problems(script), [])


def quote_of(token_text: str) -> str:
    body = token_text.lstrip("rRbBuUfF")
    return body[:3] if body[:3] in ('"""', "'''") else body[:1]


def fstring_problems(script: Path) -> list[int]:
    """找出只有 3.12 起才合法的 f-string：內層用同一種引號，或運算式裡有反斜線。"""
    problems: list[int] = []
    enclosing: list[str] = []
    with tokenize.open(script) as handle:
        for token in tokenize.generate_tokens(handle.readline):
            if token.type == tokenize.FSTRING_START:
                quote = quote_of(token.string)
                if any(outer[0] == quote[0] for outer in enclosing):
                    problems.append(token.start[0])
                enclosing.append(quote)
            elif token.type == tokenize.FSTRING_END:
                enclosing.pop()
            elif token.type == tokenize.STRING and enclosing:
                quote = quote_of(token.string)
                nested_same = any(outer[0] == quote[0] for outer in enclosing)
                if nested_same or "\\" in token.string:
                    problems.append(token.start[0])
    return problems

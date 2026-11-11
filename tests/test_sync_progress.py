"""進度紀錄比對程式（dev-workflow/assets/progress/sync_progress.py，ADR-051）的測試。

全部在 TemporaryDirectory 的假專案資料夾裡執行；git、gh 都換成假的執行器，不連網、不碰真的 repo。
假的執行器只認得程式允許的唯讀指令，遇到其他指令就讓測試失敗。
"""

import codecs
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import time
from collections.abc import Callable, Sequence
from pathlib import Path
from tempfile import TemporaryDirectory
from types import ModuleType
from unittest import SkipTest, TestCase
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "dev-workflow" / "assets" / "progress"
SCRIPT_PATH = ASSETS / "sync_progress.py"
PROGRESS_RECORD_DOC = ROOT / "dev-workflow" / "references" / "progress-record.md"
NOW = 1_762_560_000  # 固定的「現在」，不看當下時間
RECORD_MTIME = NOW - 3600
REPO = "acme/app"
REMOTE_URL = "https://github.com/acme/app.git"
SHA_HEAD = "a" * 40
SHA_OTHER = "b" * 40
SHA_MERGE = "c0ffee12" + "0" * 32
MERGED_AT = "2025-11-07T18:36:39Z"


def load_module(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"無法載入 {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


sp = load_module("sync_progress_under_test", SCRIPT_PATH)
rp = sp.rp


def merged_local(iso: str = MERGED_AT) -> str:
    moment = sp.parse_github_time(iso)
    assert moment is not None
    return sp.short_time(moment)


# ── 假的 git／gh ─────────────────────────────────────────────────


class FakeRunner:
    """只回答程式允許的唯讀指令；其他指令一律讓測試失敗。"""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.common_dir: Path | str = root / ".git"
        self.remotes: dict[str, str] = {"origin": REMOTE_URL}
        self.prs: dict[tuple[str, str], object] = {}
        self.heads: dict[tuple[str, str], object] = {}
        self.worktrees: object = [root]
        self.locals: dict[str, object] = {}
        self.default_heads: dict[str, str] = {}
        # 遠端 HEAD 指到的分支（git ls-remote --symref）；"fail" 是查不到，None 是遠端沒有 HEAD。
        self.symref_heads: dict[str, object] = {}
        # git config --get core.sshCommand：None 是沒設，"fail" 是查不到。
        self.ssh_command: object = None
        self.calls: list[tuple[str, ...]] = []
        self.raw_calls: list[tuple[str, ...]] = []
        self.hooks: list[Callable[[tuple[str, ...]], None]] = []

    def __call__(self, args: Sequence[str], cwd: Path) -> object:
        argv = tuple(args)
        # raw_calls 是原樣；calls 拿掉 ls-remote 前面的 -c core.sshCommand=…，方便比對指令本身。
        self.raw_calls.append(argv)
        self.calls.append(("git", *argv[3:]) if argv[:2] == ("git", "-c") else argv)
        for hook in self.hooks:
            hook(argv)
        return self.answer(argv)

    def answer(self, argv: tuple[str, ...]) -> object:
        if argv[:2] == ("git", "-c"):
            # 只有連遠端的 ls-remote 會帶 BatchMode；其他指令不該帶。
            assert argv[2] == f"core.sshCommand={sp.SSH_BATCH}" and argv[3] == "ls-remote", argv
            argv = ("git", *argv[3:])
        if argv == ("git", "config", "--get", "core.sshCommand"):
            if self.ssh_command == "fail":
                return sp.CommandResult(None, "", "逾時")
            if self.ssh_command is None:
                return sp.CommandResult(1, "")
            return sp.CommandResult(0, f"{self.ssh_command}\n")
        if argv[:3] == ("git", "ls-remote", "--symref") and len(argv) == 5:
            assert argv[4] == "HEAD", argv
            value = self.symref_heads.get(argv[3], "main")
            if value == "fail":
                return sp.CommandResult(128, "")
            ref = "" if value is None else f"ref: refs/heads/{value}\tHEAD\n"
            return sp.CommandResult(0, f"{ref}{SHA_OTHER}\tHEAD\n")
        if argv == ("git", "rev-parse", "--path-format=absolute", "--git-common-dir"):
            if self.common_dir == "fail":
                return sp.CommandResult(128, "")
            return sp.CommandResult(0, f"{Path(self.common_dir).as_posix()}\n")
        if argv == ("git", "remote"):
            return sp.CommandResult(0, "".join(f"{name}\n" for name in self.remotes))
        if argv[:3] == ("git", "remote", "get-url") and len(argv) == 4:
            return sp.CommandResult(0, f"{self.remotes[argv[3]]}\n")
        if argv == ("git", "worktree", "list", "--porcelain"):
            if self.worktrees == "fail":
                return sp.CommandResult(None, "", "逾時")
            text = "".join(
                f"worktree {Path(path).as_posix()}\nHEAD {SHA_HEAD}\nbranch refs/heads/x\n\n"
                for path in self.worktrees  # type: ignore[union-attr]
            )
            return sp.CommandResult(0, text)
        if argv[:3] == ("git", "symbolic-ref", "-q") and len(argv) == 4:
            remote = argv[3].removeprefix("refs/remotes/").removesuffix("/HEAD")
            head = self.default_heads.get(remote)
            if head is None:
                return sp.CommandResult(1, "")
            return sp.CommandResult(0, f"refs/remotes/{remote}/{head}\n")
        if argv[:3] == ("git", "ls-remote", "--heads") and len(argv) == 5:
            remote, ref = argv[3], argv[4]
            assert ref.startswith("refs/heads/"), argv
            value = self.heads.get((remote, ref.removeprefix("refs/heads/")))
            if value == "fail":
                return sp.CommandResult(128, "")
            if value is None:
                return sp.CommandResult(0, "")
            return sp.CommandResult(0, f"{value}\t{ref}\n")
        if argv[:4] == ("git", "show-ref", "--verify", "--quiet") and len(argv) == 5:
            value = self.locals.get(argv[4].removeprefix("refs/heads/"), False)
            if value == "fail":
                return sp.CommandResult(None, "", "逾時")
            return sp.CommandResult(0 if value else 1, "")
        if argv[:3] == ("gh", "pr", "list"):
            options = dict(zip(argv[3::2], argv[4::2]))
            assert options["--state"] == "all", argv
            assert options["--json"] == sp.GH_FIELDS, argv
            value = self.prs.get((options["--repo"], options["--head"]), [])
            if value == "fail":
                return sp.CommandResult(1, "")
            if isinstance(value, str):
                return sp.CommandResult(0, value)
            return sp.CommandResult(0, json.dumps(value))
        raise AssertionError(f"未預期的指令：{argv}")

    def gh_calls(self) -> list[tuple[str, ...]]:
        return [call for call in self.calls if call[0] == "gh"]


def pull(
    number: int = 12,
    state: str = "MERGED",
    head: str = "wt/demo-a",
    oid: str = SHA_HEAD,
    cross: bool = False,
) -> dict[str, object]:
    return {
        "number": number,
        "state": state,
        "headRefName": head,
        "headRefOid": oid,
        "isCrossRepository": cross,
        "mergedAt": MERGED_AT if state == "MERGED" else None,
        "mergeCommit": {"oid": SHA_MERGE} if state == "MERGED" else None,
        "url": f"https://github.com/{REPO}/pull/{number}",
    }


# ── 假的專案與紀錄 ───────────────────────────────────────────────

WORK_HEADER = "| 項目 | 狀態 | 負責 | 審核者 | 工作分支 | commit | 備註 |\n|---|---|---|---|---|---|---|"
REVIEW_TABLE = (
    "| 時間 | 關卡 | 審核對象 | 寫的人 | 審的人 | 結論 | 備註 |\n|---|---|---|---|---|---|---|\n"
    "| 11/07 10:00 | DEV-A | 計畫 | 主代理 | reviewer | 通過 | — |"
)
TEMP_HEADER = "| 項目 | 類型 | 位置 | 建立者 | 狀態 | 備註 |\n|---|---|---|---|---|---|"
PR_URL = f"https://github.com/{REPO}/pull/12"


def work_row(item: str, status: str, branch: str = "wt/demo-a", note: str = "—") -> str:
    return f"| {item} | {status} | 主代理 | — | {branch} | — | {note} |"


def temp_row(item: str, kind: str, location: str, status: str, note: str = "—") -> str:
    return f"| {item} | {kind} | {location} | 主代理 | {status} | {note} |"


def record(
    work: Sequence[str] = (), temp: Sequence[str] = (), state: str = "進行中", reviews: str = REVIEW_TABLE
) -> str:
    return "\n".join(
        [
            "# 測試任務",
            "",
            f"任務狀態：{state}",
            "",
            "## 需要你決定的事",
            "",
            "目前沒有。",
            "",
            "## 工作清單",
            "",
            WORK_HEADER,
            *work,
            "",
            "## 審核紀錄",
            "",
            reviews,
            "",
            "## 暫存項目",
            "",
            TEMP_HEADER,
            *temp,
            "",
            "## 尚未驗證與已知問題",
            "",
            "- 沒有。",
            "",
        ]
    )


class Project:
    """假專案：<base>/repo 是主要專案資料夾，進度紀錄在 repo/.toukadev/progress。"""

    def __init__(self) -> None:
        self._tmp = TemporaryDirectory()
        self.base = Path(self._tmp.name).resolve()
        self.root = self.base / "repo"
        self.progress = self.root / ".toukadev" / "progress"
        self.progress.mkdir(parents=True)
        self.runner = FakeRunner(self.root)

    def __enter__(self) -> "Project":
        return self

    def __exit__(self, *exc: object) -> None:
        self._tmp.cleanup()

    def write(self, stem: str, text: str, *, newline: str = "\n", bom: bool = False) -> Path:
        path = self.progress / f"{stem}.md"
        data = text.replace("\n", newline).encode("utf-8")
        path.write_bytes((codecs.BOM_UTF8 if bom else b"") + data)
        os.utime(path, (RECORD_MTIME, RECORD_MTIME))
        return path

    def run(self, *extra: str, environ: dict[str, str] | None = None) -> tuple[int, str, str]:
        out, err = [], []
        with patch.object(sp, "emit", out.append), patch.object(sp, "emit_error", err.append):
            code = sp.main(
                [str(self.progress), *extra],
                runner=self.runner,
                clock=lambda: NOW,
                environ={} if environ is None else environ,
            )
        return code, "\n".join(out), "\n".join(err)

    def status(self) -> dict[str, object]:
        return json.loads((self.progress / rp.SYNC_STATUS_FILENAME).read_text(encoding="utf-8"))

    def findings(self, kind: str | None = None) -> list[dict[str, object]]:
        items = self.status()["findings"]
        assert isinstance(items, list)
        return [item for item in items if kind is None or item["kind"] == kind]


def messages(project: Project, kind: str) -> list[str]:
    return [str(item["message"]) for item in project.findings(kind)]


# ── 契約：檔案格式與共用常數 ─────────────────────────────────────


class ContractTests(TestCase):
    def test_reuses_the_renderer_from_the_same_folder(self) -> None:
        self.assertEqual(Path(rp.__file__).resolve(), (ASSETS / "render_progress.py").resolve())

    def test_status_file_is_accepted_by_the_renderer(self) -> None:
        with Project() as project:
            project.runner.prs[(REPO, "wt/demo-a")] = [pull()]
            project.write("demo", record([work_row("A", "執行中", note=PR_URL)]))
            project.run()
            raw = (project.progress / rp.SYNC_STATUS_FILENAME).read_bytes()
            status = rp.parse_sync_payload(json.loads(raw.decode("utf-8")))
            self.assertEqual(status.checked_at, NOW)
            self.assertEqual(dict(status.records), {"demo": RECORD_MTIME})
            self.assertEqual([item.kind for item in status.findings], ["mismatch"])
            # 網頁讀得到、不顯示過時。
            rp.render_folder(project.progress)
            page = (project.progress / "index.html").read_text(encoding="utf-8")
            self.assertIn(rp.SYNC_SUMMARY, page)
            self.assertNotIn(rp.SYNC_STALE_TEXT, page)
            self.assertEqual(
                sorted(path.name for path in project.progress.iterdir() if path.name.startswith(".")),
                [],
            )

    def test_doc_describes_the_command_and_the_exception(self) -> None:
        text = PROGRESS_RECORD_DOC.read_text(encoding="utf-8")
        self.assertIn("python -I <dev-workflow 安裝根>/assets/progress/sync_progress.py", text)
        self.assertIn("--apply --task <任務代號>", text)
        self.assertIn("`<遠端>/<分支>`", text)
        self.assertIn("只有主代理", text)


# ── 工作清單 ─────────────────────────────────────────────────────


class WorkRowTests(TestCase):
    def check(self, rows: Sequence[str], prs: object = None, **runner: object) -> Project:
        project = Project()
        if prs is not None:
            project.runner.prs[(REPO, "wt/demo-a")] = prs
        for key, value in runner.items():
            setattr(project.runner, key, value)
        project.write("demo", record(rows))
        project.code, project.out, project.err = project.run()  # type: ignore[attr-defined]
        return project

    def test_merged_pr_with_unfinished_status_is_a_mismatch(self) -> None:
        with self.check([work_row("A", "執行中", note=PR_URL)], [pull()]) as project:
            found = project.findings("mismatch")
            self.assertEqual(len(found), 1)
            self.assertEqual(found[0]["section"], "工作清單")
            self.assertEqual(found[0]["row"], 1)
            self.assertEqual(found[0]["item"], "A")
            self.assertIn("#12 已合併", found[0]["message"])
            self.assertEqual(project.code, 1)  # type: ignore[attr-defined]

    def test_finished_rows_are_not_queried(self) -> None:
        # 已經是完成的狀態，PR 怎樣都不會對不上，所以不查、也不列「沒比對」。
        two_urls = f"{PR_URL} https://github.com/{REPO}/pull/13"
        for status in ("已合併", "已完成", "已驗收", "已移出（移到 other）"):
            for note in (PR_URL, two_urls, "—"):
                with self.subTest(status=status, note=note), self.check(
                    [work_row("A", status, note=note)], [pull()], remotes={"origin": REMOTE_URL, "fork": "git@github.com:me/app.git"}
                ) as project:
                    self.assertEqual(project.findings(), [])
                    self.assertEqual(project.runner.gh_calls(), [])
                    self.assertEqual(project.code, 0)  # type: ignore[attr-defined]

    def test_pr_count_wording(self) -> None:
        with self.check([work_row("A", "執行中")], [pull(), pull(number=13)]) as project:
            self.assertIn("有 2 個 PR", messages(project, "unchecked")[0])
        many = [pull(number=number) for number in range(int(sp.GH_PR_LIMIT))]
        with self.check([work_row("A", "執行中")], many) as project:
            self.assertIn(f"有 {sp.GH_PR_LIMIT} 個以上的 PR", messages(project, "unchecked")[0])

    def test_closed_pr_still_in_review_is_a_mismatch(self) -> None:
        for status, expected in (("審核中", 1), ("待審", 1), ("執行中", 0)):
            with self.subTest(status=status), self.check(
                [work_row("A", status, note=PR_URL)], [pull(state="CLOSED")]
            ) as project:
                self.assertEqual(len(project.findings("mismatch")), expected)

    def test_row_without_url_uses_the_only_github_remote(self) -> None:
        with self.check([work_row("A", "執行中")], [pull()]) as project:
            self.assertEqual(len(project.findings("mismatch")), 1)
            self.assertEqual(len(project.runner.gh_calls()), 1)

    def test_todo_row_without_url_is_not_reported(self) -> None:
        # 同一分支接著開第二個 PR 時，還沒開的那一列會查到前一個已合併的 PR。
        with self.check([work_row("A", "待辦")], [pull()]) as project:
            self.assertEqual(project.findings(), [])
            self.assertEqual(project.runner.gh_calls(), [])

    def test_row_without_a_branch_is_skipped(self) -> None:
        for branch in ("—", "", "各自分支", "-x", "a..b", "wt/x y"):
            with self.subTest(branch=branch), self.check([work_row("A", "執行中", branch=branch)]) as project:
                self.assertEqual(project.findings(), [])
                self.assertEqual(project.runner.gh_calls(), [])

    def test_backticked_branch_is_read(self) -> None:
        with self.check([work_row("A", "執行中", branch="`wt/demo-a`")], [pull()]) as project:
            self.assertEqual(len(project.findings("mismatch")), 1)

    def test_cases_that_cannot_be_matched_are_listed_as_unchecked(self) -> None:
        other_url = f"https://github.com/{REPO}/pull/13"
        cases = {
            "兩個網址": ([work_row("A", "執行中", note=f"{PR_URL} {other_url}")], [pull()], {}),
            "兩個 PR": ([work_row("A", "執行中")], [pull(), pull(number=13)], {}),
            "從 fork 開的": ([work_row("A", "執行中")], [pull(cross=True)], {}),
            "網址和查到的不同": ([work_row("A", "執行中", note=other_url)], [pull()], {}),
            "網址查不到分支": ([work_row("A", "執行中", note=PR_URL)], [], {}),
            "兩個 GitHub 遠端": (
                [work_row("A", "執行中")],
                [pull()],
                {"remotes": {"origin": REMOTE_URL, "fork": "git@github.com:me/app.git"}},
            ),
        }
        for name, (rows, prs, runner) in cases.items():
            with self.subTest(case=name), self.check(rows, prs, **runner) as project:
                self.assertEqual(project.findings("mismatch"), [])
                self.assertEqual(len(project.findings("unchecked")), 1, project.findings())

    def test_no_pr_yet_and_no_url_is_quiet(self) -> None:
        with self.check([work_row("A", "執行中")], []) as project:
            self.assertEqual(project.findings(), [])

    def test_gh_failures_are_unreachable_not_missing(self) -> None:
        for value in ("fail", "not json", json.dumps([{"number": "x"}])):
            with self.subTest(value=value), self.check([work_row("A", "執行中", note=PR_URL)], value) as project:
                self.assertEqual(project.findings("mismatch"), [])
                self.assertEqual(len(project.findings("unreachable")), 1)
                self.assertEqual(project.code, 1)  # type: ignore[attr-defined]

    def test_same_branch_is_queried_once(self) -> None:
        rows = [work_row("A", "已完成"), work_row("B", "執行中", note=PR_URL)]
        with self.check(rows, [pull()]) as project:
            self.assertEqual(len(project.runner.gh_calls()), 1)


# ── 暫存項目：遠端分支、工作資料夾、本機分支 ─────────────────────


class TempRowTests(TestCase):
    def check(
        self, temps: Sequence[str], work: Sequence[str] = (), setup: Callable[[Project], None] | None = None
    ) -> Project:
        project = Project()
        if setup is not None:
            setup(project)
        project.write("demo", record(work, temps))
        project.code, project.out, project.err = project.run()  # type: ignore[attr-defined]
        return project

    def test_remote_branch_that_is_gone_should_be_cleaned(self) -> None:
        for status, expected in (("保留", 1), ("使用中", 1), ("已清理", 0)):
            with self.subTest(status=status), self.check(
                [temp_row("遠端", "遠端分支", "origin/wt/demo-a", status)]
            ) as project:
                self.assertEqual(len(project.findings("mismatch")), expected)
                self.assertEqual(project.runner.gh_calls(), [])

    def test_merged_remote_branch_in_use_should_be_kept_for_you(self) -> None:
        def setup(project: Project) -> None:
            project.runner.heads[("origin", "wt/demo-a")] = SHA_HEAD
            project.runner.prs[(REPO, "wt/demo-a")] = [pull()]

        with self.check([temp_row("遠端", "遠端分支", "origin/wt/demo-a", "使用中")], setup=setup) as project:
            found = project.findings("mismatch")
            self.assertEqual(len(found), 1)
            self.assertIn("保留", found[0]["message"])
        with self.check([temp_row("遠端", "遠端分支", "origin/wt/demo-a", "保留", "等你決定：可以刪")], setup=setup) as project:
            self.assertEqual(project.findings(), [])

    def test_new_commit_after_merge_is_not_deletable(self) -> None:
        def setup(project: Project) -> None:
            project.runner.heads[("origin", "wt/demo-a")] = SHA_OTHER
            project.runner.prs[(REPO, "wt/demo-a")] = [pull()]

        with self.check([temp_row("遠端", "遠端分支", "origin/wt/demo-a", "使用中")], setup=setup) as project:
            self.assertEqual(project.findings("mismatch"), [])
            self.assertIn("新 commit", messages(project, "unchecked")[0])

    def test_remote_branch_cases(self) -> None:
        def heads(project: Project) -> None:
            project.runner.heads[("origin", "wt/demo-a")] = SHA_HEAD

        cases = {
            "兩個 PR": (
                "origin/wt/demo-a",
                "使用中",
                lambda p: (heads(p), p.runner.prs.update({(REPO, "wt/demo-a"): [pull(), pull(number=13)]})),
                "unchecked",
            ),
            "寫已清理但還在": ("origin/wt/demo-a", "已清理", heads, "mismatch"),
            "查不到": (
                "origin/wt/demo-a",
                "使用中",
                lambda p: p.runner.heads.update({("origin", "wt/demo-a"): "fail"}),
                "unreachable",
            ),
            "分支名有斜線": (
                "origin/wt/a/b",
                "保留",
                lambda p: None,
                "mismatch",
            ),
        }
        for name, (location, status, setup, kind) in cases.items():
            with self.subTest(case=name), self.check(
                [temp_row("遠端", "遠端分支", location, status)], setup=setup
            ) as project:
                self.assertEqual([item["kind"] for item in project.findings()], [kind])
        with self.check([temp_row("遠端", "遠端分支", "origin/wt/a/b", "保留")]) as project:
            self.assertIn(("git", "ls-remote", "--heads", "origin", "refs/heads/wt/a/b"), project.runner.calls)

    def test_bare_branch_name_needs_one_remote_and_a_branch_of_this_task(self) -> None:
        work = [work_row("A", "已完成", branch="wt/demo-a")]
        with self.check([temp_row("遠端", "遠端分支", "wt/demo-a", "使用中")], work) as project:
            self.assertEqual(len(project.findings("mismatch")), 1)
        with self.check([temp_row("遠端", "遠端分支", "GitHub", "使用中")], work) as project:
            self.assertEqual(project.findings("mismatch"), [])
            self.assertEqual(len(project.findings("unchecked")), 1)
        with self.check([temp_row("遠端", "遠端分支", "GitHub", "已清理")], work) as project:
            self.assertEqual(project.findings(), [])

        def two(project: Project) -> None:
            project.runner.remotes = {"origin": REMOTE_URL, "history": "https://example.invalid/x.git"}

        with self.check([temp_row("遠端", "遠端分支", "wt/demo-a", "使用中")], work, setup=two) as project:
            self.assertEqual(len(project.findings("unchecked")), 1)

    def test_item_cell_is_read_when_location_is_not_a_branch(self) -> None:
        with self.check([temp_row("origin/wt/demo-a", "遠端分支", "GitHub", "使用中")]) as project:
            self.assertEqual(len(project.findings("mismatch")), 1)

    def test_worktree_must_be_gone_from_both_git_and_disk(self) -> None:
        def present_on_disk(project: Project) -> None:
            (project.root / ".toukadev" / "worktrees" / "demo-a").mkdir(parents=True)

        def listed(project: Project) -> None:
            project.runner.worktrees = [project.root, project.root / ".toukadev" / "worktrees" / "demo-a"]

        location = ".toukadev/worktrees/demo-a"
        cases = {
            "兩邊都沒有": (lambda p: None, "使用中", ["mismatch"]),
            "兩邊都沒有、已清理": (lambda p: None, "已清理", []),
            "兩邊都有、寫已清理": (lambda p: (present_on_disk(p), listed(p)), "已清理", ["mismatch"]),
            "兩邊都有、使用中": (lambda p: (present_on_disk(p), listed(p)), "使用中", []),
            "只在磁碟": (present_on_disk, "使用中", ["unchecked"]),
            "只在 git 清單": (listed, "使用中", ["unchecked"]),
            "git 清單讀不到": (lambda p: setattr(p.runner, "worktrees", "fail"), "使用中", ["unreachable"]),
        }
        for name, (setup, status, kinds) in cases.items():
            with self.subTest(case=name), self.check(
                [temp_row("資料夾", "工作資料夾", location, status)], setup=setup
            ) as project:
                # 只看這一列；整個專案的列（清單讀不到時另有一項）由 WorktreeLocationTests 測。
                rows = [item["kind"] for item in project.findings() if item["record"]]
                self.assertEqual(rows, kinds)

    def test_relative_worktree_is_resolved_from_the_main_project_folder(self) -> None:
        # 紀錄放在工具管理的工作資料夾裡時，相對路徑仍從主要專案資料夾算起。
        def setup(project: Project) -> None:
            main = project.base / "main"
            (main / ".toukadev" / "worktrees" / "demo-a").mkdir(parents=True)
            project.runner.common_dir = main / ".git"
            project.runner.worktrees = [main, main / ".toukadev" / "worktrees" / "demo-a"]

        with self.check(
            [temp_row("資料夾", "工作資料夾", ".toukadev/worktrees/demo-a", "已清理")], setup=setup
        ) as project:
            self.assertEqual([item["kind"] for item in project.findings()], ["mismatch"])

    def test_location_that_is_not_a_path_is_not_guessed(self) -> None:
        with self.check([temp_row("資料夾", "工作資料夾", "上述工作資料夾", "使用中")]) as project:
            self.assertEqual([item["kind"] for item in project.findings()], ["unchecked"])

    def test_local_branch_is_detected_only(self) -> None:
        cases = {
            "不在了": ("wt/demo-a", "使用中", lambda p: None, ["mismatch"]),
            "還在但寫已清理": ("wt/demo-a", "已清理", lambda p: p.runner.locals.update({"wt/demo-a": True}), ["mismatch"]),
            "還在": ("wt/demo-a", "使用中", lambda p: p.runner.locals.update({"wt/demo-a": True}), []),
            "查不到": ("wt/demo-a", "使用中", lambda p: p.runner.locals.update({"wt/demo-a": "fail"}), ["unreachable"]),
        }
        for name, (location, status, setup, kinds) in cases.items():
            with self.subTest(case=name), self.check([temp_row("分支", "本機分支", location, status)], setup=setup) as project:
                self.assertEqual([item["kind"] for item in project.findings()], kinds)
        # 位置不是分支名時改看項目欄。
        with self.check([temp_row("wt/demo-a", "本機分支", "上述工作資料夾", "使用中")]) as project:
            self.assertIn(("git", "show-ref", "--verify", "--quiet", "refs/heads/wt/demo-a"), project.runner.calls)


# ── 範圍、安全與結束代碼 ─────────────────────────────────────────


class SafetyTests(TestCase):
    def test_only_read_only_commands_are_used(self) -> None:
        with Project() as project:
            project.runner.heads[("origin", "wt/demo-a")] = SHA_HEAD
            project.runner.prs[(REPO, "wt/demo-a")] = [pull()]
            project.write(
                "demo",
                record(
                    [work_row("A", "執行中", note=PR_URL)],
                    [
                        temp_row("遠端", "遠端分支", "origin/wt/demo-a", "使用中"),
                        temp_row("資料夾", "工作資料夾", ".toukadev/worktrees/x", "使用中"),
                        temp_row("分支", "本機分支", "wt/demo-a", "使用中"),
                    ],
                ),
            )
            project.run()
            for call in project.runner.calls:
                with self.subTest(call=call):
                    self.assertIn(call[:2], {("git", "rev-parse"), ("git", "remote"), ("git", "config"), ("git", "worktree"), ("git", "ls-remote"), ("git", "show-ref"), ("git", "symbolic-ref"), ("gh", "pr")})
                    self.assertNotIn("fetch", call)
                    self.assertNotIn("prune", call)

    def test_real_runner_has_a_time_limit_and_no_prompts(self) -> None:
        completed = subprocess.CompletedProcess(["git"], 0, stdout="ok", stderr="")
        with patch.object(sp.subprocess, "run", return_value=completed) as run:
            result = sp.run_command(["git", "remote"], Path("."))
        self.assertEqual(result.code, 0)
        kwargs = run.call_args.kwargs
        self.assertEqual(kwargs["timeout"], sp.TIMEOUT_SECONDS)
        self.assertIs(kwargs["stdin"], subprocess.DEVNULL)
        self.assertFalse(kwargs.get("shell", False))
        for key, value in sp.PROMPT_OFF_ENV.items():
            self.assertEqual(kwargs["env"][key], value)

    def test_real_runner_failures_are_not_exit_codes(self) -> None:
        cases = {
            "逾時": subprocess.TimeoutExpired(["gh"], 1),
            "找不到": FileNotFoundError("gh"),
            "其他": OSError("x"),
        }
        for name, error in cases.items():
            with self.subTest(case=name), patch.object(sp.subprocess, "run", side_effect=error):
                result = sp.run_command(["gh", "pr", "list"], Path("."))
                self.assertIsNone(result.code)
                self.assertTrue(result.problem)

    def test_only_this_folder_is_read_and_written(self) -> None:
        with Project() as project:
            project.write("demo", record([work_row("A", "執行中", note=PR_URL)]))
            (project.progress / "index.md").write_text("# 總覽板\n\n## 其他專案\n\n/elsewhere/.toukadev/progress\n", encoding="utf-8")
            project.run()
            self.assertEqual(set(project.status()["records"]), {"demo"})  # type: ignore[arg-type]

    def test_wrong_location_is_refused(self) -> None:
        with TemporaryDirectory() as raw:
            folder = Path(raw) / "notes"
            folder.mkdir()
            code = sp.main([str(folder)], runner=FakeRunner(Path(raw)), clock=lambda: NOW)
            self.assertEqual(code, 2)
            self.assertFalse((folder / rp.SYNC_STATUS_FILENAME).exists())

    def test_linked_progress_folder_is_refused(self) -> None:
        with Project() as project:
            link_root = project.base / "other" / ".toukadev"
            link_root.mkdir(parents=True)
            link = link_root / "progress"
            try:
                os.symlink(project.progress, link, target_is_directory=True)
            except (OSError, NotImplementedError) as error:
                raise SkipTest(f"這台機器不能建立 symlink：{error}") from error
            code = sp.main([str(link)], runner=project.runner, clock=lambda: NOW)
            self.assertEqual(code, 2)
            self.assertFalse((project.progress / rp.SYNC_STATUS_FILENAME).exists())

    def test_git_unavailable_stops_with_a_reason(self) -> None:
        with Project() as project:
            project.runner.common_dir = "fail"
            project.write("demo", record([work_row("A", "執行中", note=PR_URL)]))
            code, _, err = project.run()
            self.assertEqual(code, 1)
            self.assertIn("git", err)
            self.assertFalse((project.progress / rp.SYNC_STATUS_FILENAME).exists())

    def test_all_matched_exits_zero(self) -> None:
        with Project() as project:
            project.write("demo", record([work_row("A", "已合併", note=PR_URL)]))
            project.runner.prs[(REPO, "wt/demo-a")] = [pull()]
            code, out, _ = project.run()
            self.assertEqual(code, 0)
            self.assertIn("都對得上", out)


# ── --apply：合併後自動填固定欄位 ─────────────────────────────────


class ApplyTests(TestCase):
    def merged_project(self, **write: object) -> Project:
        project = Project()
        project.runner.prs[(REPO, "wt/demo-a")] = [pull()]
        project.runner.heads[("origin", "wt/demo-a")] = SHA_HEAD
        (project.root / ".toukadev" / "worktrees").mkdir()
        text = record(
            [work_row("A", "執行中", note=f"開 PR {PR_URL}"), work_row("B", "審核中", note="—")],
            [
                temp_row("遠端", "遠端分支", "origin/wt/demo-a", "使用中", "PR 合併後刪"),
                temp_row("資料夾", "工作資料夾", ".toukadev/worktrees/demo-a", "使用中"),
                temp_row("分支", "本機分支", "wt/demo-a", "使用中"),
            ],
        )
        project.path = project.write("demo", text, **write)  # type: ignore[attr-defined]
        project.before = project.path.read_bytes()  # type: ignore[attr-defined]
        return project

    def test_fixes_only_the_fixed_fields_and_appends_one_review_row(self) -> None:
        with self.merged_project() as project:
            code, out, err = project.run("--apply", "--task", "demo")
            after = project.path.read_text(encoding="utf-8")  # type: ignore[attr-defined]
            before = project.before.decode("utf-8")  # type: ignore[attr-defined]
            stamp = sp.short_time(NOW)
            expected = (
                before.replace(
                    f"| A | 執行中 | 主代理 | — | wt/demo-a | — | 開 PR {PR_URL} |",
                    f"| A | 已合併 | 主代理 | — | wt/demo-a | — | 開 PR {PR_URL}；PR 已合併 {merged_local()}（c0ffee12） |",
                )
                .replace(
                    "| 遠端 | 遠端分支 | origin/wt/demo-a | 主代理 | 使用中 | PR 合併後刪 |",
                    "| 遠端 | 遠端分支 | origin/wt/demo-a | 主代理 | 保留 | 等你決定：已合併，可以刪。PR 合併後刪 |",
                )
                .replace(
                    "| 資料夾 | 工作資料夾 | .toukadev/worktrees/demo-a | 主代理 | 使用中 | — |",
                    "| 資料夾 | 工作資料夾 | .toukadev/worktrees/demo-a | 主代理 | 已清理 | — |",
                )
                .replace(
                    "| 11/07 10:00 | DEV-A | 計畫 | 主代理 | reviewer | 通過 | — |",
                    "| 11/07 10:00 | DEV-A | 計畫 | 主代理 | reviewer | 通過 | — |\n"
                    f"| {stamp} | 自動比對 | 進度紀錄固定欄位 | sync_progress | — | 已更新 | "
                    "工作清單第 1 列改已合併；暫存項目第 1 列改保留；暫存項目第 2 列改已清理 |",
                )
            )
            self.assertEqual(after, expected)
            # B 沒有網址、本機分支只偵測：都不改。
            self.assertIn("| B | 審核中 |", after)
            self.assertIn("| 分支 | 本機分支 | wt/demo-a | 主代理 | 使用中 | — |", after)
            self.assertEqual(code, 1, (out, err))  # B 與本機分支仍對不上
            remaining = [(item["section"], item["row"]) for item in project.findings("mismatch")]
            self.assertEqual(remaining, [("工作清單", 2), ("暫存項目", 3)])
            self.assertEqual(project.status()["records"], {"demo": int(project.path.stat().st_mtime)})  # type: ignore[attr-defined]
            # 網頁不標過時。
            rp.render_folder(project.progress)
            self.assertNotIn(rp.SYNC_STALE_TEXT, (project.progress / "index.html").read_text(encoding="utf-8"))
            # 改完的紀錄沒有格式警告（存檔時間設成「現在」之後一分鐘，不看當下時鐘）。
            os.utime(project.path, (NOW + 60, NOW + 60))  # type: ignore[attr-defined]
            self.assertEqual(rp.load_view(project.path).warnings, [])  # type: ignore[attr-defined]

    def test_line_endings_and_bom_are_kept(self) -> None:
        with self.merged_project(newline="\r\n", bom=True) as project:
            project.run("--apply", "--task", "demo")
            raw = project.path.read_bytes()  # type: ignore[attr-defined]
            self.assertTrue(raw.startswith(codecs.BOM_UTF8))
            body = raw[len(codecs.BOM_UTF8) :]
            self.assertEqual(body.count(b"\n"), body.count(b"\r\n"))
            self.assertEqual(body.count(b"\r\n"), project.before.count(b"\r\n") + 1)  # type: ignore[attr-defined]

    def test_other_records_are_never_changed(self) -> None:
        with self.merged_project() as project:
            other = project.write("other", record([work_row("A", "執行中", note=PR_URL)]))
            before = other.read_bytes()
            project.run("--apply", "--task", "demo")
            self.assertEqual(other.read_bytes(), before)
            self.assertIn("other", {item["record"] for item in project.findings("mismatch")})

    def test_change_during_the_check_cancels_the_write(self) -> None:
        with self.merged_project() as project:
            def touch(argv: tuple[str, ...]) -> None:
                if argv[0] == "gh":
                    with project.path.open("a", encoding="utf-8") as handle:  # type: ignore[attr-defined]
                        handle.write("- 別人剛加的一行\n")

            project.runner.hooks.append(touch)
            code, _, err = project.run("--apply", "--task", "demo")
            self.assertEqual(code, 1)
            self.assertIn("被改過", err)
            text = project.path.read_text(encoding="utf-8")  # type: ignore[attr-defined]
            self.assertIn("| A | 執行中 |", text)
            self.assertTrue(text.endswith("- 別人剛加的一行\n"))

    def test_refusals_leave_the_file_alone(self) -> None:
        cases = {
            "任務代號不合法": ("Demo", None),
            "保留字": ("index", None),
            "紀錄不存在": ("missing", None),
            "沒有審核紀錄表格": ("demo", record([work_row("A", "執行中", note=PR_URL)], reviews="（還沒有）")),
            "不是 UTF-8": ("demo", b"\xff\xfe"),
        }
        for name, (task, content) in cases.items():
            with self.subTest(case=name), self.merged_project() as project:
                if isinstance(content, str):
                    project.write("demo", content)
                elif isinstance(content, bytes):
                    project.path.write_bytes(content)  # type: ignore[attr-defined]
                before = project.path.read_bytes()  # type: ignore[attr-defined]
                code, _, err = project.run("--apply", "--task", task)
                self.assertNotEqual(code, 0)
                self.assertTrue(err)
                self.assertEqual(project.path.read_bytes(), before)  # type: ignore[attr-defined]

    def test_linked_record_is_refused(self) -> None:
        with self.merged_project() as project:
            target = project.base / "elsewhere.md"
            target.write_bytes(project.before)  # type: ignore[attr-defined]
            project.path.unlink()  # type: ignore[attr-defined]
            try:
                os.symlink(target, project.path)  # type: ignore[attr-defined]
            except (OSError, NotImplementedError) as error:
                raise SkipTest(f"這台機器不能建立 symlink：{error}") from error
            code, _, err = project.run("--apply", "--task", "demo")
            self.assertNotEqual(code, 0)
            self.assertEqual(target.read_bytes(), project.before)  # type: ignore[attr-defined]

    def test_nothing_to_fix_leaves_the_file_alone(self) -> None:
        with Project() as project:
            path = project.write("demo", record([work_row("A", "已合併", note=PR_URL)]))
            project.runner.prs[(REPO, "wt/demo-a")] = [pull()]
            before = path.read_bytes()
            code, out, _ = project.run("--apply", "--task", "demo")
            self.assertEqual(code, 0)
            self.assertIn("沒有要改的", out)
            self.assertEqual(path.read_bytes(), before)

    def test_pr_from_another_repo_or_branch_is_not_fixed(self) -> None:
        cases = {
            "別的 repo": ("https://github.com/other/app/pull/12", ("other/app", "wt/demo-a"), pull()),
            "分支不一致": (PR_URL, (REPO, "wt/demo-a"), pull(head="wt/else")),
        }
        for name, (url, key, pr) in cases.items():
            with self.subTest(case=name), Project() as project:
                project.runner.prs[key] = [pr]
                path = project.write("demo", record([work_row("A", "執行中", note=url)]))
                before = path.read_bytes()
                project.run("--apply", "--task", "demo")
                self.assertEqual(path.read_bytes(), before)

    def test_apply_needs_a_task(self) -> None:
        with Project() as project:
            project.write("demo", record())
            code, _, _ = project.run("--apply")
            self.assertEqual(code, 2)
            code, _, _ = project.run("--task", "demo")
            self.assertEqual(code, 2)


class VerifyEditTests(TestCase):
    def test_any_other_difference_is_refused(self) -> None:
        old = ["| a | 待辦 | x |\n", "| b | 待辦 | y |\n", "tail\n"]
        good = ["| a | 已合併 | x |\n", "| b | 待辦 | y |\n", "| new |\n", "tail\n"]
        sp.verify_edit(old, good, {0: {1}}, 2)
        bad_cases = {
            "改到別的格子": ["| a | 已合併 | z |\n", "| b | 待辦 | y |\n", "| new |\n", "tail\n"],
            "改到別的行": ["| a | 已合併 | x |\n", "| b | 待辦 | y |\n", "| new |\n", "TAIL\n"],
            "少了一行": ["| a | 已合併 | x |\n", "| new |\n", "tail\n"],
            "格子數不同": ["| a | 已合併 | x | w |\n", "| b | 待辦 | y |\n", "| new |\n", "tail\n"],
        }
        for name, new in bad_cases.items():
            with self.subTest(case=name), self.assertRaises(sp.ApplyRefused):
                sp.verify_edit(old, new, {0: {1}}, 2)


class HashTests(TestCase):
    def test_digest_is_sha256_of_the_raw_bytes(self) -> None:
        self.assertEqual(sp.digest(b"abc"), hashlib.sha256(b"abc").hexdigest())


class TimeTests(TestCase):
    def test_short_time_uses_local_time(self) -> None:
        local = time.localtime(NOW)
        self.assertEqual(
            sp.short_time(NOW), f"{local.tm_mon}/{local.tm_mday:02d} {local.tm_hour:02d}:{local.tm_min:02d}"
        )

    def test_github_time_parse(self) -> None:
        self.assertIsNotNone(sp.parse_github_time(MERGED_AT))
        self.assertIsNone(sp.parse_github_time("yesterday"))
        self.assertIsNone(sp.parse_github_time(None))

    def test_short_time_reads_local_time_not_utc(self) -> None:
        with patch.object(sp.time, "localtime", wraps=time.localtime) as local:
            sp.short_time(NOW)
        local.assert_called_once_with(NOW)


# ── DEV-B 第 1 輪後補的情況 ──────────────────────────────────────


TRICKY_RECORDS = {
    "重複區段取第一段": record([work_row("A", "執行中"), work_row("B", "待辦")])
    + "\n## 工作清單\n\n" + WORK_HEADER + "\n" + work_row("Z", "執行中") + "\n",
    "表格前有文字、後面有第二張表": record(
        [work_row("A", "執行中"), work_row("B", "待辦"), "", "說明", "", WORK_HEADER, work_row("Z", "執行中")]
    ).replace(WORK_HEADER, "先說明一句。\n\n" + WORK_HEADER, 1),
    "沒有分隔線": record([work_row("A", "執行中"), work_row("B", "待辦")]).replace(
        WORK_HEADER, WORK_HEADER.splitlines()[0], 1
    ),
    "圍欄裡的表格": record([work_row("A", "執行中"), work_row("B", "待辦")]).replace(
        "## 工作清單\n\n", "## 工作清單\n\n```\n## 審核紀錄\n```\n\n", 1
    ),
    "CRLF": record([work_row("A", "執行中"), work_row("B", "待辦")]).replace("\n", "\r\n"),
    "圍欄裡真的有表格": record(
        [work_row("A", "執行中"), work_row("B", "待辦")],
        reviews="```text\n" + REVIEW_TABLE + "\n```\n\n" + REVIEW_TABLE,
    ),
}


class TableLocationTests(TestCase):
    def test_rows_match_the_renderer(self) -> None:
        for name, text in TRICKY_RECORDS.items():
            with self.subTest(case=name):
                view = rp.analyze_record(rp.parse_record(text, "demo"), "demo.md", RECORD_MTIME)
                lines = text.splitlines(keepends=True)
                tables = sp.locate_tables(lines)
                for section, table in ((rp.WORK, view.work), (rp.TEMP, view.temp), (rp.REVIEWS, view.reviews)):
                    assert table is not None
                    located = [rp.split_row(lines[index].rstrip("\r\n")) for index in tables[section].rows] if section in tables else []
                    expected = [list(row.values())[: len(table.columns)] for row in table.rows]
                    self.assertEqual([cells[: len(table.columns)] for cells in located], expected, section)

    def test_edit_refuses_a_line_that_is_not_the_checked_row(self) -> None:
        text = record([work_row("A", "執行中", note=PR_URL)])
        lines = text.splitlines(keepends=True)
        fix = sp.Fix(rp.WORK, 1, "已合併", "x", "工作清單第 1 列改已合併", ("B", "執行中"))
        with self.assertRaises(sp.ApplyRefused):
            sp.build_edit(lines, [fix], "1/01 00:00")


class ReviewFollowUpTests(TestCase):
    def run_record(self, text: str, setup: Callable[[Project], None] | None = None, *extra: str) -> Project:
        project = Project()
        if setup is not None:
            setup(project)
        project.path = project.write("demo", text)  # type: ignore[attr-defined]
        project.before = project.path.read_bytes()  # type: ignore[attr-defined]
        project.code, project.out, project.err = project.run(*extra)  # type: ignore[attr-defined]
        return project

    def test_url_is_read_from_the_note_only(self) -> None:
        row = f"| A {PR_URL} | 執行中 | 主代理 | — | wt/demo-a | — | — |"
        with self.run_record(record([row]), lambda p: p.runner.prs.update({(REPO, "wt/demo-a"): [pull()]}), "--apply", "--task", "demo") as project:
            self.assertEqual(len(project.findings("mismatch")), 1)
            self.assertEqual(project.path.read_bytes(), project.before)  # type: ignore[attr-defined]

    def test_shared_and_default_branches_are_never_deletable(self) -> None:
        for branch, default in (("dev", None), ("main", None), ("release", "release")):
            def setup(project: Project, branch: str = branch, default: str | None = default) -> None:
                project.runner.heads[("origin", branch)] = SHA_HEAD
                project.runner.prs[(REPO, branch)] = [pull(head=branch)]
                if default is not None:
                    project.runner.default_heads["origin"] = default

            temps = [temp_row("遠端", "遠端分支", f"origin/{branch}", "使用中")]
            with self.subTest(branch=branch), self.run_record(record([], temps), setup, "--apply", "--task", "demo") as project:
                self.assertEqual(project.findings("mismatch"), [])
                self.assertIn("共用", messages(project, "unchecked")[0])
                self.assertEqual(project.path.read_bytes(), project.before)  # type: ignore[attr-defined]

    def test_branch_from_the_item_column_is_detected_but_not_changed(self) -> None:
        temps = [temp_row("origin/wt/demo-a", "遠端分支", "GitHub", "使用中")]
        work = [work_row("A", "已合併", note=PR_URL)]
        with self.run_record(record(work, temps), None, "--apply", "--task", "demo") as project:
            self.assertEqual(len(project.findings("mismatch")), 1)
            self.assertEqual(project.path.read_bytes(), project.before)  # type: ignore[attr-defined]

    def test_remote_branch_needs_a_pr_url_of_its_repo_to_be_changed(self) -> None:
        temps = [temp_row("遠端", "遠端分支", "origin/wt/demo-a", "使用中")]
        with self.run_record(record([], temps), None, "--apply", "--task", "demo") as project:
            # 查得到「已經不在」，但同一份紀錄沒有這個分支屬於本專案的 PR 網址：只偵測。
            self.assertEqual(len(project.findings("mismatch")), 1)
            self.assertEqual(project.path.read_bytes(), project.before)  # type: ignore[attr-defined]
        work = [work_row("A", "已合併", note=PR_URL)]
        with self.run_record(record(work, temps), None, "--apply", "--task", "demo") as project:
            self.assertIn("| 遠端 | 遠端分支 | origin/wt/demo-a | 主代理 | 已清理 | — |", project.path.read_text(encoding="utf-8"))  # type: ignore[attr-defined]

    def test_branch_whose_pr_is_in_another_repo_is_not_judged(self) -> None:
        work = [work_row("A", "已合併", note="https://github.com/other/app/pull/3")]
        temps = [temp_row("遠端", "遠端分支", "origin/wt/demo-a", "使用中")]
        with self.run_record(record(work, temps), None, "--apply", "--task", "demo") as project:
            self.assertEqual(project.findings("mismatch"), [])
            self.assertIn("別的 repo", messages(project, "unchecked")[0])
            self.assertEqual(project.path.read_bytes(), project.before)  # type: ignore[attr-defined]

    def test_worktree_location_must_be_a_plain_path(self) -> None:
        for location in ("`.toukadev/worktrees/demo-a`（舊）", "同 A / B 的資料夾", "\\\\host\\share\\x", "//host/share/x", "https://example.invalid/x"):
            temps = [temp_row("資料夾", "工作資料夾", location, "使用中")]
            with self.subTest(location=location), self.run_record(record([], temps), None, "--apply", "--task", "demo") as project:
                self.assertEqual([item["kind"] for item in project.findings()], ["unchecked"])
                self.assertEqual(project.path.read_bytes(), project.before)  # type: ignore[attr-defined]

    def test_worktree_is_changed_only_when_its_parent_folder_exists(self) -> None:
        temps = [temp_row("資料夾", "工作資料夾", ".toukadev/worktrees/demo-a", "使用中")]
        with self.run_record(record([], temps), None, "--apply", "--task", "demo") as project:
            self.assertEqual(len(project.findings("mismatch")), 1)
            self.assertEqual(project.path.read_bytes(), project.before)  # type: ignore[attr-defined]

    def test_relative_worktree_uses_the_main_working_folder_from_git(self) -> None:
        def setup(project: Project) -> None:
            main = project.base / "main"
            (main / ".toukadev" / "worktrees" / "demo-a").mkdir(parents=True)
            project.runner.common_dir = project.base / "elsewhere" / "modules" / "x"
            project.runner.worktrees = [main, main / ".toukadev" / "worktrees" / "demo-a"]

        temps = [temp_row("資料夾", "工作資料夾", ".toukadev/worktrees/demo-a", "已清理")]
        with self.run_record(record([], temps), setup) as project:
            self.assertEqual([item["kind"] for item in project.findings()], ["mismatch"])

    def test_non_github_remote_in_use_is_listed_as_unchecked(self) -> None:
        def setup(project: Project) -> None:
            project.runner.remotes = {"origin": "https://example.invalid/app.git"}
            project.runner.heads[("origin", "wt/demo-a")] = SHA_HEAD

        temps = [temp_row("遠端", "遠端分支", "origin/wt/demo-a", "使用中")]
        with self.run_record(record([], temps), setup) as project:
            self.assertIn("不是 GitHub", messages(project, "unchecked")[0])

    def test_location_whose_first_part_is_not_a_remote(self) -> None:
        temps = [temp_row("遠端", "遠端分支", "upstream/wt/demo-a", "使用中")]
        with self.run_record(record([], temps)) as project:
            self.assertEqual([item["kind"] for item in project.findings()], ["unchecked"])
            self.assertFalse([call for call in project.runner.calls if call[:2] == ("git", "ls-remote")])

    def test_only_unchecked_rows_exit_zero(self) -> None:
        temps = [temp_row("資料夾", "工作資料夾", "上述工作資料夾", "使用中")]
        with self.run_record(record([], temps)) as project:
            self.assertEqual([item["kind"] for item in project.findings()], ["unchecked"])
            self.assertEqual(project.code, 0)  # type: ignore[attr-defined]

    def test_special_line_breaks_refuse_apply(self) -> None:
        text = record([work_row("A", "執行中", note=f"{PR_URL}\u2028")])
        with self.run_record(text, lambda p: p.runner.prs.update({(REPO, "wt/demo-a"): [pull()]}), "--apply", "--task", "demo") as project:
            self.assertEqual(project.code, 1)  # type: ignore[attr-defined]
            self.assertIn("特殊的換行", project.err)  # type: ignore[attr-defined]
            self.assertEqual(project.path.read_bytes(), project.before)  # type: ignore[attr-defined]

    def test_escaped_bar_and_file_mode_are_kept(self) -> None:
        row = f"| A \\| 舊名 | 執行中 | 主代理 | — | wt/demo-a | — | {PR_URL} |"
        with Project() as project:
            project.runner.prs[(REPO, "wt/demo-a")] = [pull()]
            path = project.write("demo", record([row]))
            os.chmod(path, 0o644)
            mode = os.stat(path).st_mode & 0o777
            project.run("--apply", "--task", "demo")
            self.assertIn("| A \\| 舊名 | 已合併 |", path.read_text(encoding="utf-8"))
            self.assertEqual(os.stat(path).st_mode & 0o777, mode)

    def test_link_check_right_before_replace(self) -> None:
        with Project() as project:
            project.runner.prs[(REPO, "wt/demo-a")] = [pull()]
            path = project.write("demo", record([work_row("A", "執行中", note=PR_URL)]))
            before = path.read_bytes()
            real = rp.entry_problem
            calls: list[Path] = []

            def second_time_link(target: Path, want_folder: bool) -> str | None:
                if target == path:
                    calls.append(target)
                    if len(calls) == 2:
                        return "是連結"
                return real(target, want_folder)

            with patch.object(sp.rp, "entry_problem", side_effect=second_time_link):
                code, _, err = project.run("--apply", "--task", "demo")
            self.assertEqual(code, 1)
            self.assertIn("連結", err)
            self.assertEqual(path.read_bytes(), before)
            self.assertEqual([item.name for item in project.progress.iterdir() if item.name.startswith(".")], [])

    def test_too_many_records_stop_cleanly(self) -> None:
        with Project() as project:
            for number in range(rp.SYNC_MAX_FINDINGS + 1):
                project.write(f"r{number}", record())
            code, _, err = project.run()
            self.assertEqual(code, 1)
            self.assertIn(str(rp.SYNC_MAX_FINDINGS), err)
            self.assertFalse((project.progress / rp.SYNC_STATUS_FILENAME).exists())

    def test_write_failure_is_reported_not_raised(self) -> None:
        with Project() as project:
            project.write("demo", record())
            with patch.object(sp.rp, "write_atomic", side_effect=PermissionError("鎖住了")):
                code, _, err = project.run()
            self.assertEqual(code, 1)
            self.assertIn("鎖住了", err)

    def test_help_exits_zero(self) -> None:
        with patch.object(sys, "stdout"):
            self.assertEqual(sp.main(["--help"]), 0)

    def test_run_command_leaves_ssh_settings_alone(self) -> None:
        completed = subprocess.CompletedProcess(["git"], 0, stdout="", stderr="")
        with patch.object(sp.subprocess, "run", return_value=completed) as run, patch.dict(os.environ, {}, clear=False):
            os.environ.pop("GIT_SSH_COMMAND", None)
            sp.run_command(["git", "remote"], Path("."))
            self.assertNotIn("GIT_SSH_COMMAND", run.call_args.kwargs["env"])
            for key, value in sp.PROMPT_OFF_ENV.items():
                self.assertEqual(run.call_args.kwargs["env"][key], value)

    def test_doc_lists_the_follow_up_rules(self) -> None:
        text = PROGRESS_RECORD_DOC.read_text(encoding="utf-8")
        for phrase in ("預設或共用分支", "別的 repo", "只從備註", "上一層資料夾", "寫已清理，但"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, text)


class VerifyEndingTests(TestCase):
    def test_changed_line_ending_is_refused(self) -> None:
        old = ["| a | 待辦 | x |\r\n", "tail\n"]
        new = ["| a | 已合併 | x |\n", "| new |\n", "tail\n"]
        with self.assertRaises(sp.ApplyRefused):
            sp.verify_edit(old, new, {0: {1}}, 1)


# ── DEV-B 第 2 輪後補的情況 ──────────────────────────────────────

FENCED_REVIEWS = "```text\n" + REVIEW_TABLE + "\n```\n\n" + REVIEW_TABLE
OTHER_URL = "https://github.com/other/app/pull/3"


class ReviewRoundTwoTests(TestCase):
    run_record = ReviewFollowUpTests.run_record

    def remote_row_project(self, environ: dict[str, str], config: object) -> Project:
        project = Project()
        project.runner.ssh_command = config
        project.runner.heads[("origin", "wt/demo-a")] = SHA_HEAD
        project.write("demo", record([], [temp_row("遠端", "遠端分支", "origin/wt/demo-a", "使用中")]))
        project.run(environ=environ)
        return project

    def test_batch_mode_only_without_the_users_own_ssh_setting(self) -> None:
        cases = (
            ({}, None, True),
            ({}, "ssh -i ~/.ssh/work", False),
            ({}, "fail", False),
            ({"GIT_SSH": "plink"}, None, False),
            ({"GIT_SSH_COMMAND": "my-ssh"}, None, False),
        )
        for environ, config, batch in cases:
            with self.subTest(environ=environ, config=config), self.remote_row_project(environ, config) as project:
                remote_calls = [call for call in project.runner.raw_calls if "ls-remote" in call]
                self.assertTrue(remote_calls)
                for call in remote_calls:
                    self.assertEqual(call[1:3] == ("-c", f"core.sshCommand={sp.SSH_BATCH}"), batch, call)

    def test_default_branch_is_asked_from_the_remote_when_not_known_locally(self) -> None:
        def setup(project: Project, symref: object) -> None:
            project.runner.symref_heads["origin"] = symref
            project.runner.heads[("origin", "release")] = SHA_HEAD
            project.runner.prs[(REPO, "release")] = [pull(head="release")]

        # 工作清單有這個分支屬於本專案的 PR 網址，原本會給 --apply 改；預設分支照樣擋下。
        work = [work_row("A", "已合併", branch="release", note=PR_URL)]
        temps = [temp_row("遠端", "遠端分支", "origin/release", "使用中")]
        cases = (
            ("release", "unchecked", "預設或共用", 0),
            ("fail", "unreachable", "查不到 origin 的預設分支", 1),
            (None, "unreachable", "查不到 origin 的預設分支", 1),
        )
        for symref, kind, phrase, code in cases:
            with self.subTest(symref=symref), self.run_record(
                record(work, temps), lambda p, s=symref: setup(p, s), "--apply", "--task", "demo"
            ) as project:
                self.assertEqual(project.findings("mismatch"), [])
                self.assertIn(phrase, messages(project, kind)[0])
                self.assertEqual(project.code, code)  # type: ignore[attr-defined]
                self.assertEqual(project.path.read_bytes(), project.before)  # type: ignore[attr-defined]

    def test_default_branch_is_asked_only_when_it_would_matter(self) -> None:
        # PR 沒合併、或合併後又有新 commit 時，不需要知道預設分支，也不連遠端去問。
        for pulled, expected in ((pull(state="OPEN"), []), (pull(oid=SHA_OTHER), ["unchecked"])):
            def setup(project: Project, pulled: dict[str, object] = pulled) -> None:
                project.runner.symref_heads["origin"] = "fail"
                project.runner.heads[("origin", "wt/demo-a")] = SHA_HEAD
                project.runner.prs[(REPO, "wt/demo-a")] = [pulled]

            temps = [temp_row("遠端", "遠端分支", "origin/wt/demo-a", "保留")]
            with self.subTest(state=pulled["state"]), self.run_record(record([], temps), setup) as project:
                self.assertEqual([item["kind"] for item in project.findings()], expected)
                self.assertFalse([call for call in project.runner.calls if "--symref" in call])

    def test_work_table_inside_a_fence_is_never_edited(self) -> None:
        row = work_row("A", "執行中", note=PR_URL)
        text = record([row]).replace(f"{WORK_HEADER}\n{row}\n", f"```text\n{WORK_HEADER}\n{row}\n```\n", 1)
        self.assertIn("```text", text)
        with self.run_record(
            text, lambda p: p.runner.prs.update({(REPO, "wt/demo-a"): [pull()]}), "--apply", "--task", "demo"
        ) as project:
            self.assertEqual(project.code, 1)  # type: ignore[attr-defined]
            self.assertIn("工作清單的表格在圍欄", project.err)  # type: ignore[attr-defined]
            self.assertEqual(project.path.read_bytes(), project.before)  # type: ignore[attr-defined]

    def test_unreadable_folder_is_reported_not_raised(self) -> None:
        with Project() as project:
            with patch.object(sp.rp, "list_records", side_effect=rp.RenderError("讀不到資料夾 x")):
                code, _, err = project.run()
            self.assertEqual(code, 1)
            self.assertIn("讀不到資料夾", err)

    def test_local_default_branch_needs_no_remote_query(self) -> None:
        def setup(project: Project) -> None:
            project.runner.default_heads["origin"] = "release"
            project.runner.heads[("origin", "release")] = SHA_HEAD
            project.runner.prs[(REPO, "release")] = [pull(head="release")]

        temps = [temp_row("遠端", "遠端分支", "origin/release", "使用中")]
        with self.run_record(record([], temps), setup) as project:
            self.assertIn("預設或共用", messages(project, "unchecked")[0])
            self.assertFalse([call for call in project.runner.calls if "--symref" in call])

    def test_table_inside_a_fence_is_never_edited(self) -> None:
        text = record([work_row("A", "執行中", note=PR_URL)], reviews=FENCED_REVIEWS)
        with self.run_record(
            text, lambda p: p.runner.prs.update({(REPO, "wt/demo-a"): [pull()]}), "--apply", "--task", "demo"
        ) as project:
            self.assertEqual(project.code, 1)  # type: ignore[attr-defined]
            self.assertIn("圍欄", project.err)  # type: ignore[attr-defined]
            self.assertEqual(project.path.read_bytes(), project.before)  # type: ignore[attr-defined]

    def test_sources_have_no_invisible_line_breaks(self) -> None:
        for path in (SCRIPT_PATH, Path(__file__)):
            text = path.read_text(encoding="utf-8")
            with self.subTest(path=path.name):
                self.assertNotIn("\u2028", text)
                self.assertNotIn("\u2029", text)

    def test_record_limit_is_checked_before_anything_is_changed(self) -> None:
        with Project() as project:
            project.runner.prs[(REPO, "wt/demo-a")] = [pull()]
            path = project.write("demo", record([work_row("A", "執行中", note=PR_URL)]))
            project.write("other", record())
            before = path.read_bytes()
            with patch.object(sp.rp, "SYNC_MAX_FINDINGS", 1):
                code, _, err = project.run("--apply", "--task", "demo")
            self.assertEqual(code, 1)
            self.assertIn("超過 1 份", err)
            self.assertEqual(path.read_bytes(), before)

    def test_write_failure_after_apply_still_lists_the_changes(self) -> None:
        with Project() as project:
            project.runner.prs[(REPO, "wt/demo-a")] = [pull()]
            path = project.write("demo", record([work_row("A", "執行中", note=PR_URL)]))
            with patch.object(sp, "write_status", side_effect=PermissionError("鎖住了")):
                code, out, err = project.run("--apply", "--task", "demo")
            self.assertEqual(code, 1)
            self.assertIn("鎖住了", err)
            self.assertIn("已更新紀錄", out)
            self.assertIn("| A | 已合併 |", path.read_text(encoding="utf-8"))

    def test_cleaned_row_with_another_repo_url_is_not_listed(self) -> None:
        work = [work_row("A", "已合併", note=OTHER_URL)]
        temps = [temp_row("遠端", "遠端分支", "origin/wt/demo-a", "已清理")]
        with self.run_record(record(work, temps)) as project:
            self.assertEqual(project.findings(), [])

    def test_non_github_remote_with_a_pr_url_says_so(self) -> None:
        def setup(project: Project) -> None:
            project.runner.remotes = {"origin": "https://example.invalid/app.git"}

        work = [work_row("A", "已合併", note=PR_URL)]
        temps = [temp_row("遠端", "遠端分支", "origin/wt/demo-a", "使用中")]
        with self.run_record(record(work, temps), setup) as project:
            found = messages(project, "unchecked")
            self.assertEqual(len(found), 1)
            self.assertIn("不是 GitHub", found[0])
            self.assertNotIn("別的 repo", found[0])

    def test_repo_names_compare_without_case(self) -> None:
        cases = (
            ("https://github.com/Acme/App/pull/12", REMOTE_URL),
            (PR_URL, "https://github.com/ACME/app.git"),
        )
        for note, remote in cases:
            def setup(project: Project, remote: str = remote) -> None:
                project.runner.remotes = {"origin": remote}
                project.runner.prs[(REPO, "wt/demo-a")] = [pull()]

            with self.subTest(note=note, remote=remote), self.run_record(
                record([work_row("A", "執行中", note=note)]), setup, "--apply", "--task", "demo"
            ) as project:
                self.assertIn("| A | 已合併 |", project.path.read_text(encoding="utf-8"))  # type: ignore[attr-defined]

    def test_docs_follow_the_round_two_changes(self) -> None:
        self.assertIn("symbolic-ref", sp.__doc__)
        self.assertIn("core.sshCommand", PROGRESS_RECORD_DOC.read_text(encoding="utf-8"))


# ── 工作資料夾放錯位置（不屬於任何紀錄，整個專案一項）────────────


class WorktreeLocationTests(TestCase):
    """git 的工作資料夾清單裡，放在 .toukadev/tmp/ 底下的列成「整個專案」的對不上，不靠紀錄有沒有登記。"""

    def run_with(self, *extra_worktrees: str, args: Sequence[str] = ()) -> tuple[int, str, list[dict[str, object]], Project]:
        project = Project()
        project.write("demo", record())
        project.runner.worktrees = [project.root, *(project.root / path for path in extra_worktrees)]
        code, out, _ = project.run(*args)
        return code, out, project.findings(), project

    def project_rows(self, findings: list[dict[str, object]]) -> list[dict[str, object]]:
        return [item for item in findings if item["record"] == ""]

    def test_worktree_under_tmp_is_a_project_wide_mismatch(self) -> None:
        code, out, findings, project = self.run_with(".toukadev/tmp/demo/repro", ".toukadev/worktrees/demo-a")
        with project:
            rows = self.project_rows(findings)
            self.assertEqual(code, 1, out)
            self.assertEqual(len(rows), 1, findings)
            self.assertEqual(rows[0]["kind"], "mismatch")
            self.assertEqual(rows[0]["section"], rp.TEMP)
            self.assertEqual(rows[0]["row"], 0)
            self.assertIn("repro", str(rows[0]["item"]))
            self.assertIn(".toukadev/tmp/", str(rows[0]["message"]))
            self.assertIn(rp.SYNC_PROJECT_TEXT, out)
            self.assertEqual(project.status()["version"], 2)

    def test_tmp_folder_itself_counts_but_a_lookalike_name_does_not(self) -> None:
        for location, expected in ((".toukadev/tmp", 1), (".toukadev/tmpx/demo", 0), (".toukadev/worktrees/tmp/demo", 0)):
            with self.subTest(location=location):
                code, out, findings, project = self.run_with(location)
                with project:
                    self.assertEqual(len(self.project_rows(findings)), expected, findings)
                    self.assertEqual(code, expected, out)

    def test_worktrees_elsewhere_are_fine(self) -> None:
        code, out, findings, project = self.run_with(".toukadev/worktrees/demo-a", "../elsewhere")
        with project:
            self.assertEqual(self.project_rows(findings), [])
            self.assertEqual(code, 0, out)

    def test_case_follows_the_platform(self) -> None:
        code, _, findings, project = self.run_with(".TOUKADEV/TMP/demo/repro")
        with project:
            expected = 1 if os.path.normcase("A") == "a" else 0
            self.assertEqual(len(self.project_rows(findings)), expected, findings)
            self.assertEqual(code, expected)

    def test_unreadable_worktree_list_is_reported_once_for_the_project(self) -> None:
        project = Project()
        with project:
            project.write("demo", record())
            project.runner.worktrees = "fail"
            code, _, _ = project.run()
            rows = [item for item in project.findings() if item["record"] == ""]
            self.assertEqual(code, 1)
            self.assertEqual([item["kind"] for item in rows], ["unreachable"])

    def test_apply_leaves_the_record_alone(self) -> None:
        project = Project()
        with project:
            path = project.write("demo", record())
            before = path.read_bytes()
            project.runner.worktrees = [project.root, project.root / ".toukadev/tmp/demo/repro"]
            code, _, _ = project.run("--apply", "--task", "demo")
            self.assertEqual(path.read_bytes(), before)
            self.assertEqual(len([item for item in project.findings() if item["record"] == ""]), 1)
            self.assertEqual(code, 1)

    def test_renderer_reads_the_project_wide_row(self) -> None:
        code, _, _, project = self.run_with(".toukadev/tmp/demo/repro")
        with project:
            self.assertEqual(code, 1)
            rp.render_folder(project.progress)
            page = (project.progress / "index.html").read_text(encoding="utf-8")
            self.assertIn(rp.SYNC_PROJECT_TEXT, page)
            self.assertNotIn("格式不對", page)

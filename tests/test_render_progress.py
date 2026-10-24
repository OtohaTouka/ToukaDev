"""進度網頁產生程式（dev-workflow/assets/progress/render_progress.py）的測試。

所有測試都在 TemporaryDirectory 建立的假專案資料夾裡執行，不讀寫實體 .toukadev/。
"""

import base64
import contextlib
import hashlib
import html as html_module
import importlib.util
import io
import json
import os
import re
import stat
import subprocess
import sys
import time
from collections.abc import Sequence
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path
from tempfile import TemporaryDirectory
from types import ModuleType, SimpleNamespace
from unittest import SkipTest, TestCase, skipUnless
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "dev-workflow" / "assets" / "progress" / "render_progress.py"
EXAMPLE_PATH = MODULE_PATH.parent / "example.md"
PROGRESS_RECORD_DOC = ROOT / "dev-workflow" / "references" / "progress-record.md"
IS_WINDOWS = sys.platform == "win32"
NOW = 1_760_000_000
RECORD_MTIME = NOW - 10 * 60
JUNCTION_SKIP_REASON = "junction 是 Windows 專屬功能；非 Windows 由 symlink 案例涵蓋"


def load_renderer() -> ModuleType:
    spec = importlib.util.spec_from_file_location("render_progress", MODULE_PATH)
    if spec is None or spec.loader is None:
        raise ImportError(f"無法載入 {MODULE_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


rp = load_renderer()


# ── 測試用的 HTML 樹 ─────────────────────────────────────────────

VOID_TAGS = frozenset(
    {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta"}
)


class Node:
    def __init__(
        self, tag: str, attrs: list[tuple[str, str | None]], parent: "Node | None"
    ) -> None:
        self.tag = tag
        self.attrs = {name: value or "" for name, value in attrs}
        self.parent = parent
        self.children: list["Node | str"] = []

    def text(self) -> str:
        return "".join(
            child if isinstance(child, str) else child.text() for child in self.children
        )

    def classes(self) -> set[str]:
        return set(self.attrs.get("class", "").split())

    def descendants(self) -> list["Node"]:
        found: list[Node] = []
        for child in self.children:
            if isinstance(child, Node):
                found.append(child)
                found.extend(child.descendants())
        return found


class Page(HTMLParser):
    def __init__(self, source: str) -> None:
        super().__init__(convert_charrefs=True)
        self.source = source
        self.root = Node("#root", [], None)
        self.nodes: list[Node] = []
        self._current = self.root
        self.feed(source)
        self.close()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        node = Node(tag, attrs, self._current)
        self._current.children.append(node)
        self.nodes.append(node)
        if tag not in VOID_TAGS:
            self._current = node

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        node = Node(tag, attrs, self._current)
        self._current.children.append(node)
        self.nodes.append(node)

    def handle_endtag(self, tag: str) -> None:
        node = self._current
        while node.parent is not None and node.tag != tag:
            node = node.parent
        if node.parent is not None:
            self._current = node.parent

    def handle_data(self, data: str) -> None:
        self._current.children.append(data)

    def find_all(
        self,
        tag: str | None = None,
        cls: str | None = None,
        attrs: dict[str, str] | None = None,
        within: Node | None = None,
    ) -> list[Node]:
        pool = within.descendants() if within is not None else self.nodes
        return [
            node
            for node in pool
            if (tag is None or node.tag == tag)
            and (cls is None or cls in node.classes())
            and all(
                node.attrs.get(key) == value for key, value in (attrs or {}).items()
            )
        ]

    def find(
        self,
        tag: str | None = None,
        cls: str | None = None,
        attrs: dict[str, str] | None = None,
        within: Node | None = None,
    ) -> Node:
        found = self.find_all(tag, cls, attrs, within)
        if not found:
            raise AssertionError(f"找不到 tag={tag} class={cls} attrs={attrs}")
        return found[0]

    def section(self, title: str) -> Node:
        return self.find("section", attrs={"data-section": title})

    def warnings(self) -> list[str]:
        boxes = self.find_all("div", cls="warnings")
        return [
            item.text() for box in boxes for item in self.find_all("li", within=box)
        ]

    def text(self) -> str:
        return self.root.text()


# ── 測試用的紀錄 ─────────────────────────────────────────────────

# 格式正本（progress-record.md）的表頭與暫存類型。網頁照表頭顯示，程式不另存一份。
WORK_HEADER = ("項目", "狀態", "負責", "審核者", "工作分支", "commit", "備註")
REVIEW_HEADER = ("時間", "關卡", "審核對象", "寫的人", "審的人", "結論", "備註")
TEMP_HEADER = ("項目", "類型", "位置", "建立者", "狀態", "備註")
TEMP_TYPES = ("工作資料夾", "本機分支", "遠端分支", "暫存資料夾", "其他")

WORK_TABLE = """\
| 項目 | 狀態 | 負責 | 審核者 | 工作分支 | commit | 備註 |
|---|---|---|---|---|---|---|
| 規劃 | 已完成 | 主代理 | reviewer | — | — | — |
| A：功能 | 已驗收 | 執行者 A | 主代理 | wt/{stem}-a | abc1234 | — |
| B：文件 | 執行中（04:17 開始） | 執行者 B | 主代理 | wt/{stem}-b | — | — |
| C：合併 | 已合併 | 主代理 | — | — | def5678 | — |
| D：收尾 | 待辦 | 主代理 | — | — | — | — |"""

REVIEW_TABLE = """\
| 時間 | 關卡 | 審核對象 | 寫的人 | 審的人 | 結論 | 備註 |
|---|---|---|---|---|---|---|
| 10/10 03:27 | DEV-A 第 1 輪 | 計畫 v1 | 主代理 | reviewer | 要修改 | 第一筆 |
| 10/10 05:00 | DEV-A 第 2 輪 | 計畫 v2 | 主代理 | reviewer | 通過 | 第二筆 |"""

TEMP_TABLE = """\
| 項目 | 類型 | 位置 | 建立者 | 狀態 | 備註 |
|---|---|---|---|---|---|
| 本任務暫存資料夾 | 暫存資料夾 | .toukadev/tmp/{stem} | 主代理 | 使用中 | — |
| A 的工作分支 | 本機分支 | wt/{stem}-a | 主代理 | 已清理 | — |"""

DEFAULT_SECTIONS: dict[str, str | None] = {
    "需要你決定的事": "目前沒有。",
    "工作清單": WORK_TABLE,
    "審核紀錄": REVIEW_TABLE,
    "暫存項目": TEMP_TABLE,
    "尚未驗證與已知問題": "- 還沒在 macOS 試過。",
}

# 舊寫法的紀錄：多一行「更新時間：」、沒有任務狀態、舊欄位「審核」「審核者」、沒有暫存項目區段。
OLD_RECORD = """\
# 舊寫法範例：多單位批次

更新時間：2026-10-10 03:49（已完成）

## 需要你決定的事

目前沒有。（你已回覆「照改」。）

## 工作清單

| 項目 | 狀態 | 負責 | 工作分支 | commit | 審核 |
|---|---|---|---|---|---|
| R：核心規則 | 已驗收 | 執行者 R | wt/sample-r | 1111111 | 主代理驗收：補正後通過 |
| P：周邊文件 | 已驗收 | 執行者 P | wt/sample-p | 2222222 | 主代理驗收：範圍與換行一致 |
| 完成後審核（3 位） | 第 1 輪完成：要修正 | reviewer ×3 | — | 2222222 | 2 個嚴重 |
| 修正第 1 輪 | 已完成 | R、P | 各自分支 | 3333333（最終版本） | 主代理驗收 |
| 審核結果交你決定 | 已核准上傳合併；另開小 PR（補一項） | 你 | — | 3333333 | — |
| 推上 GitHub、PR 到 dev、合併進 dev | 已合併 | 主代理 | chore/sample | 4444444 | CI 綠燈 |
| 補一項的小 PR | 已合併，分支已刪 | 主代理 | — | dev 7777777 | CI 綠燈 |

## 審核紀錄

| 時間 | 關卡 | 審核對象 | 審核者 | 結論 | 備註 |
|---|---|---|---|---|---|
| 10/10 | 計畫審核第 1 輪 | 計畫 v1 | reviewer | 要修改 | 3 個嚴重問題 |
| 10/10 01:20 | 你核准 | 一頁計畫 v3 | 你 | 核准，完成後選 A | |
| 10/10 01:36 | 單位驗收 R | 5555555 | 主代理 | 退回修正 | 兩句禁令交回改寫 |
| 10/10 03:07 | 合併 | PR #1 | 主代理 | 已合併進 dev（4444444） | |
| 10/10 03:43 | 你決定 | 收窄措辭 | 你 | 照改 | 加三個限定詞 |

## 尚未驗證與已知問題

- 額度約三倍是估計，不是量測結果。
"""


def build_record(
    *,
    title: str = "測試任務",
    updated: str | None = None,
    state: str | None = "進行中",
    stem: str = "demo",
    sections: dict[str, str | None] | None = None,
    extra: str = "",
) -> str:
    lines = [f"# {title}", ""]
    if updated is not None:
        lines.append(f"更新時間：{updated}")
    if state is not None:
        lines.append(f"任務狀態：{state}")
    for name, body in {**DEFAULT_SECTIONS, **(sections or {})}.items():
        if body is None:
            continue
        lines.extend(["", f"## {name}", "", body.replace("{stem}", stem)])
    if extra:
        lines.extend(["", extra])
    return "\n".join(lines) + "\n"


class RepoSandbox:
    """有 .toukadev/progress 的假專案資料夾；離開 with 區塊時整個刪掉。"""

    def __init__(self) -> None:
        self._tmp = TemporaryDirectory()
        self.base = Path(self._tmp.name).resolve()
        self.root = self.base / "repo"
        self.progress = self.root / ".toukadev" / "progress"
        self.progress.mkdir(parents=True)

    def __enter__(self) -> "RepoSandbox":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self._tmp.cleanup()

    def write_record(self, stem: str, text: str, mtime: int = RECORD_MTIME) -> Path:
        path = self.progress / f"{stem}.md"
        path.write_text(text, encoding="utf-8", newline="\n")
        os.utime(path, (mtime, mtime))
        return path

    def render(self, text: str, stem: str = "demo", mtime: int = RECORD_MTIME) -> Page:
        path = self.write_record(stem, text, mtime)
        outcome = rp.render_file(path)
        return Page(outcome.output.read_text(encoding="utf-8"))


def make_junction(link: Path, target: Path) -> None:
    completed = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(link), str(target)],
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        raise OSError(completed.stderr.decode(errors="replace"))


def make_symlink_or_skip(link: Path, target: Path) -> None:
    try:
        os.symlink(target, link, target_is_directory=target.is_dir())
    except (OSError, NotImplementedError) as error:
        raise SkipTest(
            "這台電腦不能建立 symlink（Windows 需要開發人員模式或系統管理員權限）："
            f"{error}"
        )


def sha256_source(text: str) -> str:
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    return "'sha256-" + base64.b64encode(digest).decode("ascii") + "'"


def csp_directives(page: Page) -> dict[str, str]:
    meta = page.find("meta", attrs={"http-equiv": "Content-Security-Policy"})
    directives: dict[str, str] = {}
    for part in meta.attrs["content"].split(";"):
        name, _, value = part.strip().partition(" ")
        if name:
            directives[name] = value.strip()
    return directives


def script_in(page: Page, parent: str) -> str:
    """回傳直接放在 <head> 或 <body> 裡的那一段腳本；不是正好一段就失敗。"""
    scripts = [
        node
        for node in page.find_all("script")
        if node.parent is not None and node.parent.tag == parent
    ]
    if len(scripts) != 1:
        raise AssertionError(f"<{parent}> 裡應該正好一段腳本，實際 {len(scripts)} 段")
    return scripts[0].text()


def css_rules(style: str) -> list[tuple[list[str], dict[str, str]]]:
    """把 CSS 拆成（選擇器清單, 宣告）；@media 只取裡面的規則。"""
    rules: list[tuple[list[str], dict[str, str]]] = []
    for match in re.finditer(r"([^{}]+)\{([^{}]*)\}", style):
        selectors = [name.strip() for name in match.group(1).split(",")]
        declarations: dict[str, str] = {}
        for part in match.group(2).split(";"):
            name, _, value = part.partition(":")
            if name.strip():
                declarations[name.strip()] = value.strip()
        rules.append((selectors, declarations))
    return rules


def display_rules(style: str, target: str) -> list[tuple[str, str]]:
    """所有設定 target 的 display 的（選擇器, 值）。"""
    return [
        (selector, declarations["display"])
        for selectors, declarations in css_rules(style)
        if "display" in declarations
        for selector in selectors
        if selector.split()[-1] == target
    ]


def run_main(argv: list[str]) -> tuple[int, str, str]:
    stdout, stderr = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        code = rp.main(argv)
    return code, stdout.getvalue(), stderr.getvalue()


def work_rows(page: Page) -> list[Node]:
    return page.find_all("tr", cls="work-row")


# ── 格式正本 ─────────────────────────────────────────────────────


class FormatContractTests(TestCase):
    def test_constants_match_plan_section_3(self) -> None:
        self.assertEqual(
            rp.REQUIRED_SECTIONS,
            (
                "需要你決定的事",
                "工作清單",
                "審核紀錄",
                "暫存項目",
                "尚未驗證與已知問題",
            ),
        )
        self.assertEqual(
            rp.WORK_STATUSES,
            (
                "待辦",
                "執行中",
                "待審",
                "審核中",
                "退回修正",
                "已驗收",
                "已合併",
                "已完成",
            ),
        )
        self.assertEqual(rp.CHECKED_STATUSES, frozenset({"已驗收", "已合併"}))
        self.assertEqual(rp.TASK_STATES, ("進行中", "已結束"))
        self.assertEqual(rp.TEMP_STATES, ("使用中", "已清理", "保留"))

    def test_example_uses_exact_table_headers(self) -> None:
        text = EXAMPLE_PATH.read_text(encoding="utf-8")
        for columns in (WORK_HEADER, REVIEW_HEADER, TEMP_HEADER):
            with self.subTest(columns=columns):
                self.assertIn("| " + " | ".join(columns) + " |", text)
        for title in rp.REQUIRED_SECTIONS:
            with self.subTest(title=title):
                self.assertIn(f"\n## {title}\n", text)

    def test_progress_record_doc_matches_renderer(self) -> None:
        text = PROGRESS_RECORD_DOC.read_text(encoding="utf-8")
        for columns in (WORK_HEADER, REVIEW_HEADER, TEMP_HEADER):
            with self.subTest(columns=columns):
                self.assertIn("| " + " | ".join(columns) + " |", text)
        for title in rp.REQUIRED_SECTIONS:
            with self.subTest(title=title):
                self.assertIn(f"## {title}", text)
        # 網頁只認這些狀態，正本列出的必須完全一樣。
        for values in (rp.WORK_STATUSES, rp.TEMP_STATES, TEMP_TYPES):
            with self.subTest(values=values):
                self.assertIn("：" + "、".join(values), text)
        # 審核時間警告的門檻，正本寫的必須和程式一樣。
        late = f"晚 {rp.FUTURE_MIN_SECONDS // 60 + 1}～{rp.FUTURE_MAX_SECONDS // 60} 分鐘"
        self.assertIn(late, text)
        self.assertIn(f"晚超過 {rp.YEAR_BACK_SECONDS // 86400} 天", text)

    def test_example_temp_items_stay_in_its_own_task_folder(self) -> None:
        text = EXAMPLE_PATH.read_text(encoding="utf-8")
        locations = [
            line.split("|")[3].strip()
            for line in text.splitlines()
            if ".toukadev/tmp/" in line
        ]
        self.assertTrue(locations)
        for location in locations:
            with self.subTest(location=location):
                self.assertEqual(location.split("/")[2], "example")


# ── 範例與呈現 ───────────────────────────────────────────────────


class ExampleRenderingTests(TestCase):
    def render_example(self) -> Page:
        with RepoSandbox() as sandbox:
            text = EXAMPLE_PATH.read_text(encoding="utf-8")
            return sandbox.render(text, stem="example")

    def test_example_shows_every_section_and_row(self) -> None:
        page = self.render_example()
        for title in rp.REQUIRED_SECTIONS:
            with self.subTest(title=title):
                section = page.section(title)
                self.assertNotIn("missing-section", section.classes())
        example = EXAMPLE_PATH.read_text(encoding="utf-8")
        for line in example.splitlines():
            if line.startswith("| ") and not line.startswith("| 項目 |"):
                first_cell = line.split("|")[1].strip()
                if first_cell not in {"時間"}:
                    with self.subTest(cell=first_cell):
                        self.assertIn(first_cell, page.text())

    def test_example_has_no_format_warnings(self) -> None:
        page = self.render_example()
        self.assertEqual(page.warnings(), [])

    def test_example_covers_every_status_and_type(self) -> None:
        page = self.render_example()
        statuses = {row.attrs["data-status"] for row in work_rows(page)}
        self.assertEqual(statuses, set(rp.WORK_STATUSES))
        temp_table = page.find("table", cls="temp-table")
        types = {
            cell.text()
            for cell in page.find_all("td", cls="col-類型", within=temp_table)
        }
        self.assertEqual(types, set(TEMP_TYPES))
        temp_states = {
            row.attrs["data-status"] for row in page.find_all("tr", cls="temp-row")
        }
        self.assertEqual(temp_states, set(rp.TEMP_STATES))

    def test_check_mark_only_for_accepted_and_merged(self) -> None:
        page = self.render_example()
        rows = work_rows(page)
        self.assertTrue(rows)
        for row in rows:
            status = row.attrs["data-status"]
            mark_cell = page.find("td", cls="mark", within=row)
            with self.subTest(status=status):
                if status in {"已驗收", "已合併"}:
                    self.assertEqual(row.attrs["data-mark"], "check")
                    self.assertEqual(mark_cell.text().strip(), "✔")
                elif status == "已完成":
                    self.assertEqual(row.attrs["data-mark"], "complete")
                    self.assertEqual(mark_cell.text().strip(), "完成")
                    self.assertNotIn("✔", row.text())
                else:
                    self.assertEqual(row.attrs["data-mark"], "none")
                    self.assertNotIn("✔", row.text())
        table = page.find("table", cls="work-table")
        self.assertEqual(
            table.text().count("✔"),
            sum(1 for row in rows if row.attrs["data-mark"] == "check"),
        )

    def test_work_summary_counts_every_finished_item(self) -> None:
        summary = self.render_example().find("p", cls="work-summary").text()
        self.assertEqual(summary, "完成 4／9 項・其中 2 項經驗收或合併")

    def test_status_note_is_kept(self) -> None:
        page = self.render_example()
        doing = page.find("tr", cls="work-row", attrs={"data-status": "執行中"})
        self.assertIn("執行中（14:10 開始）", doing.text())

    def test_status_label_stays_short_and_note_sits_beside_it(self) -> None:
        table = WORK_TABLE + (
            "\n| E：長說明 | 退回修正（總覽同步更新、過期改看紀錄修改時間） "
            "| 執行者 E | 主代理 | — | — | — |"
        )
        temp = (
            TEMP_TABLE
            + "\n| F 的分支 | 本機分支 | wt/demo-f | 主代理 | 保留（等 PR） | 等 PR |"
        )
        with RepoSandbox() as sandbox:
            page = sandbox.render(
                build_record(sections={"工作清單": table, "暫存項目": temp})
            )
        rework = page.find("tr", cls="work-row", attrs={"data-status": "退回修正"})
        self.assertEqual(
            page.find("span", cls="chip", within=rework).text(), "退回修正"
        )
        self.assertEqual(
            page.find("span", cls="status-note", within=rework).text(),
            "（總覽同步更新、過期改看紀錄修改時間）",
        )
        kept = page.find("tr", cls="temp-row", attrs={"data-status": "保留"})
        self.assertEqual(page.find("span", cls="chip", within=kept).text(), "保留")
        self.assertEqual(
            page.find("span", cls="status-note", within=kept).text(), "（等 PR）"
        )
        self.assertIn("min-width", re.search(r"\ntable \{[^}]*\}", rp.STYLE).group(0))

    def test_pending_decisions_are_prominent(self) -> None:
        page = self.render_example()
        section = page.section("需要你決定的事")
        self.assertIn("pending", section.classes())
        self.assertEqual(section.attrs["data-count"], "1")
        self.assertIn("3 次還是 5 次", section.text())

    def test_reviews_keep_record_order(self) -> None:
        # 時間倒過來也照紀錄原本的順序顯示，不重排；已結束的紀錄不查時間。
        table = REVIEW_TABLE.replace("10/10 03:27", "10/10 06:00")
        with RepoSandbox() as sandbox:
            page = sandbox.render(
                build_record(state="已結束", sections={"審核紀錄": table})
            )
        self.assertEqual(page.warnings(), [])
        rows = page.find_all("tr", cls="review-row")
        self.assertEqual(len(rows), 2)
        self.assertIn("第一筆", rows[0].text())
        self.assertIn("第二筆", rows[1].text())

    def test_valid_record_has_no_warnings(self) -> None:
        with RepoSandbox() as sandbox:
            page = sandbox.render(build_record())
        self.assertEqual(page.warnings(), [])

    def test_other_sections_are_shown_as_is(self) -> None:
        with RepoSandbox() as sandbox:
            page = sandbox.render(
                build_record(extra="## 備忘\n\n自訂 <b>粗體</b> 文字\n第二行")
            )
        raw = page.section("備忘")
        self.assertIn("自訂 <b>粗體</b> 文字\n第二行", raw.text())
        self.assertEqual(page.find_all("b"), [])

    def test_decisions_nothing_pending_variants(self) -> None:
        cases = {
            "目前沒有。": "0",
            "目前沒有。（你已回覆「照改」。）": "0",
            "- 目前沒有。": "0",
            "- 要不要加 X？\n- 要不要加 Y？": "2",
            "- 目前沒有。\n- 目前沒有。": "0",
        }
        for body, expected in cases.items():
            with self.subTest(body=body), RepoSandbox() as sandbox:
                page = sandbox.render(build_record(sections={"需要你決定的事": body}))
                section = page.section("需要你決定的事")
                self.assertEqual(section.attrs["data-count"], expected)
                self.assertEqual("pending" in section.classes(), expected != "0")

    def test_nothing_pending_mixed_with_requests_still_waits(self) -> None:
        cases = {
            "目前沒有。\n\n請決定要不要加 X。": "1",
            "- 目前沒有阻礙，但請決定 X": "1",
            "目前沒有。\n- 請決定 A\n- 請決定 B": "2",
            "目前沒有。\n（請你決定：要不要加 X）": "1",
            "目前沒有。（說明）\n請決定 Y": "1",
        }
        for body, expected in cases.items():
            with self.subTest(body=body), RepoSandbox() as sandbox:
                page = sandbox.render(build_record(sections={"需要你決定的事": body}))
                section = page.section("需要你決定的事")
                self.assertEqual(section.attrs["data-count"], expected)
                self.assertIn("pending", section.classes())
                stamp = page.find("span", cls="age-stamp")
                self.assertEqual(stamp.attrs["data-stale-mode"], "waiting")
                self.assertIn("等你決定", stamp.text())


# ── 需要你決定的事：編號與子項目 ──────────────────────────────────

# 2 格與 4 格縮排的選項都要掛在上一項底下；編號 1、3 照原號。
DECISION_OPTIONS = """\
1. 要選哪個方案？
  - 甲：先做 A
  - 乙：先做 B
3. 要不要另開 PR？
    - 要
    - 不要"""


def render_in(tmp_path: Path, decisions: str, extra: str = "") -> Page:
    """在 tmp_path 底下建 .toukadev/progress，產生這份紀錄的網頁與總覽。"""
    progress = tmp_path / ".toukadev" / "progress"
    progress.mkdir(parents=True)
    path = progress / "demo.md"
    record = build_record(sections={"需要你決定的事": decisions}, extra=extra)
    path.write_text(record, encoding="utf-8", newline="\n")
    return Page(rp.render_file(path).output.read_text(encoding="utf-8"))


def child_nodes(node: Node, tag: str) -> list[Node]:
    return [c for c in node.children if isinstance(c, Node) and c.tag == tag]


def own_text(node: Node) -> str:
    """只取這個節點直接帶的文字，不含巢狀清單。"""
    return "".join(child for child in node.children if isinstance(child, str))


def shown_numbers(ordered: Node) -> list[int]:
    """照瀏覽器的算法：有 value 用 value，沒有就接上一項加 1（起點看 start）。"""
    number = int(ordered.attrs.get("start", "1")) - 1
    shown: list[int] = []
    for item in child_nodes(ordered, "li"):
        number = int(item.attrs["value"]) if "value" in item.attrs else number + 1
        shown.append(number)
    return shown


def test_numbered_decisions_keep_every_original_number(tmp_path: Path) -> None:
    page = render_in(tmp_path, "1. 第一件？\n3. 第三件？\n7. 第七件？")
    section = page.section("需要你決定的事")
    assert page.find_all("ul", within=section) == []
    (ordered,) = page.find_all("ol", within=section)
    assert shown_numbers(ordered) == [1, 3, 7]
    texts = [own_text(item) for item in child_nodes(ordered, "li")]
    assert texts == ["第一件？", "第三件？", "第七件？"]
    assert section.attrs["data-count"] == "3"


def test_indented_options_nest_under_their_item(tmp_path: Path) -> None:
    section = render_in(tmp_path, DECISION_OPTIONS).section("需要你決定的事")
    (text,) = child_nodes(section, "div")
    (ordered,) = child_nodes(text, "ol")
    items = child_nodes(ordered, "li")
    assert shown_numbers(ordered) == [1, 3]
    assert [own_text(item) for item in items] == ["要選哪個方案？", "要不要另開 PR？"]
    options = [
        [own_text(option) for option in child_nodes(child_nodes(item, "ul")[0], "li")]
        for item in items
    ]
    assert options == [["甲：先做 A", "乙：先做 B"], ["要", "不要"]]
    assert section.attrs["data-count"] == "2"
    assert "pending" in section.classes()


def test_overview_counts_only_top_level_decisions(tmp_path: Path) -> None:
    render_in(tmp_path, DECISION_OPTIONS)
    index = tmp_path / ".toukadev" / "progress" / "index.html"
    cell = Page(index.read_text(encoding="utf-8")).find("td", cls="pending")
    assert cell.attrs["data-count"] == "2"
    assert cell.text() == "2 項"


def test_plain_bullets_and_nothing_pending_are_unchanged(tmp_path: Path) -> None:
    cases = {
        "- 問題一？\n- 問題二？": (["ul"], "2"),
        "目前沒有。": (["p"], "0"),
        "1. 目前沒有。": (["ol"], "0"),
        # 「目前沒有」底下還有子項目時不能算 0。
        "- 目前沒有。\n  - 其實要決定 X": (["ul"], "1"),
    }
    for number, (body, (tags, count)) in enumerate(cases.items()):
        section = render_in(tmp_path / str(number), body).section("需要你決定的事")
        (text,) = child_nodes(section, "div")
        assert [c.tag for c in text.children if isinstance(c, Node)] == tags, body
        assert section.attrs["data-count"] == count, body
    plain = render_in(tmp_path / "plain", "- 問題一？\n- 問題二？")
    bullets = plain.find("ul", within=plain.section("需要你決定的事"))
    assert [own_text(item) for item in child_nodes(bullets, "li")] == [
        "問題一？",
        "問題二？",
    ]


def test_other_sections_and_escaping_are_unchanged(tmp_path: Path) -> None:
    body = "1. <script>alert(1)</script> 要不要？\n   - <b>甲</b>"
    page = render_in(tmp_path, body, extra="## 備忘\n\n1. 原樣\n  - 顯示")
    decisions = page.section("需要你決定的事")
    ordered = page.find("ol", within=decisions)
    first = child_nodes(ordered, "li")[0]
    assert own_text(first) == "<script>alert(1)</script> 要不要？"
    assert page.find("li", within=page.find("ul", within=ordered)).text() == "<b>甲</b>"
    nodes = decisions.descendants()
    assert {node.tag for node in nodes} <= {"h2", "div", "ol", "ul", "li"}
    assert all(set(node.attrs) <= {"value"} for node in nodes if node.tag != "div")
    issues = page.section("尚未驗證與已知問題")
    assert [item.text() for item in page.find_all("li", within=issues)] == [
        "還沒在 macOS 試過。"
    ]
    memo = page.section("備忘")
    assert page.find("pre", within=memo).text() == "1. 原樣\n  - 顯示"
    assert page.find_all("li", within=memo) == []


# ── 安全：跳脫、CSP、沒有外部資源 ────────────────────────────────

# 只允許同資料夾的「<任務代號>.html」相對連結（總覽 ↔ 任務頁）；其他 href 一律不行。
SAFE_HREF = re.compile(r"[a-z0-9-]+\.html")
ALLOWED_TAGS = frozenset(
    {
        "a",
        "html",
        "head",
        "meta",
        "title",
        "style",
        "script",
        "body",
        "main",
        "header",
        "footer",
        "section",
        "div",
        "h1",
        "h2",
        "p",
        "span",
        "strong",
        "code",
        "pre",
        "ul",
        "li",
        "table",
        "thead",
        "tbody",
        "tr",
        "th",
        "td",
        "button",
    }
)
# 唯一的按鈕是主題切換；只能有這些屬性（沒有 formaction、沒有行內事件或樣式）。
BUTTON_ATTRIBUTES = frozenset({"type", "class", "title"})
FORBIDDEN_ATTRIBUTES = frozenset(
    {
        "src",
        "href",
        "srcset",
        "action",
        "formaction",
        "poster",
        "background",
        "manifest",
        "ping",
        "data",
        "codebase",
        "cite",
        "longdesc",
        "usemap",
        "xlink:href",
        "style",
    }
)
HOSTILE_TITLE = '<script>alert("t")</script> & 標題'
HOSTILE_PREAMBLE = "<img src=x onerror=alert(9)> 開頭的說明"
HOSTILE_WORK_STATUS = '已驗收"><script>alert(2)</script>'
HOSTILE_TEMP_STATUS = '<i>使用中</i>">'
# 欄名裡的雙引號：沒有跳脫成 &quot; 的話，會跳出屬性、多出 on* 事件。
HOSTILE_COLUMN = 'x" onmouseover="alert(1)" class="live'
# 通用表格會照表頭顯示紀錄寫的欄名、多出的格子與表格外的文字，所以每一種都放一段。
HOSTILE_REVIEW_TABLE = f"""\
| 時間 | 關卡 | <script>alert(5)</script> | 寫的人 | 審的人 | 結論 | {HOSTILE_COLUMN} |
|---|---|---|---|---|---|---|
| 10/10 05:00 | <img src=x onerror=alert(6)> | x | 主代理 | reviewer | 通過 | a | <b>多出的格子</b> |

<i>表格外的文字</i>"""
HOSTILE_RECORD = build_record(
    title=HOSTILE_TITLE,
    sections={
        "需要你決定的事": '- 要不要用 "引號" & <b>粗體</b>？',
        "工作清單": WORK_TABLE
        + f"\n| <img src=x onerror=alert(1)> | {HOSTILE_WORK_STATUS} "
        "| [文件](https://example.com/x) | — | — | — | — |",
        "審核紀錄": HOSTILE_REVIEW_TABLE,
        "暫存項目": TEMP_TABLE
        + f"\n| <img src=x onerror=alert(7)> | 其他 | ../<b>x</b> | 主代理 | {HOSTILE_TEMP_STATUS} | — |",
        "尚未驗證與已知問題": "- <img src=x onerror=alert(8)> **<i>粗體</i>** `<b>code</b>`",
    },
    extra="## 備忘\n\n</pre><script>alert(3)</script>",
).replace("任務狀態：進行中", f"任務狀態：進行中\n{HOSTILE_PREAMBLE}", 1)
# 每個呈現區段：紀錄裡寫的文字都要原樣看得到，而且不能變成任何標籤。
HOSTILE_SECTIONS = {
    "需要你決定的事": ['要不要用 "引號" & <b>粗體</b>？'],
    "工作清單": [
        "<img src=x onerror=alert(1)>",
        HOSTILE_WORK_STATUS,
        "[文件](https://example.com/x)",
    ],
    "審核紀錄": [
        "<script>alert(5)</script>",
        HOSTILE_COLUMN,
        "<img src=x onerror=alert(6)>",
        "<b>多出的格子</b>",
        "<i>表格外的文字</i>",
    ],
    "暫存項目": ["<img src=x onerror=alert(7)>", "../<b>x</b>", HOSTILE_TEMP_STATUS],
    "尚未驗證與已知問題": [
        "<img src=x onerror=alert(8)>",
        "<i>粗體</i>",
        "<b>code</b>",
    ],
    "備忘": ["</pre><script>alert(3)</script>"],
}
INJECTED_TAGS = ("script", "img", "b", "i", "a")


class SafetyTests(TestCase):
    def render_pages(self) -> list[Page]:
        with RepoSandbox() as sandbox:
            record_page = sandbox.render(HOSTILE_RECORD)
            sandbox.write_record("other", build_record(stem="other"))
            rp.render_folder(sandbox.progress)
            index_page = Page(
                (sandbox.progress / "index.html").read_text(encoding="utf-8")
            )
        return [record_page, index_page]

    def assert_inert(self, page: Page, region: Node, texts: Sequence[str]) -> None:
        for text in texts:
            with self.subTest(text=text):
                self.assertIn(text, region.text())
        for tag in INJECTED_TAGS:
            with self.subTest(tag=tag):
                self.assertEqual(page.find_all(tag, within=region), [])

    def test_record_text_is_escaped(self) -> None:
        page = self.render_pages()[0]
        self.assertEqual(page.source.count("<script"), 2)
        self.assertEqual(
            [node.text() for node in page.find_all("script")],
            [rp.HEAD_SCRIPT, rp.SCRIPT],
        )
        self.assertIn(html_module.escape('<script>alert("t")</script>'), page.source)
        self.assertIn("&amp; 標題", page.source)
        self.assertIn("&quot;引號&quot; &amp; &lt;b&gt;粗體&lt;/b&gt;", page.source)
        self.assertIn("&lt;img src=x onerror=alert(1)&gt;", page.source)
        self.assertEqual(page.find_all("img"), [])
        self.assertEqual(page.find_all("b"), [])
        self.assertIn('<script>alert("t")</script> & 標題', page.text())
        self.assertIn("</pre><script>alert(3)</script>", page.text())

    def test_hostile_column_name_is_escaped_without_event_attributes(self) -> None:
        page = self.render_pages()[0]
        escaped = "x&quot; onmouseover=&quot;alert(1)&quot; class=&quot;live"
        self.assertIn(f"<th>{escaped}</th>", page.source)
        self.assertNotIn(HOSTILE_COLUMN, page.source)
        self.assertIn(HOSTILE_COLUMN, [th.text() for th in page.find_all("th")])
        names = [name for node in page.nodes for name in node.attrs]
        self.assertEqual([name for name in names if name.startswith("on")], [])
        self.assertEqual(page.find_all(cls="live"), [])

    def test_every_record_section_shows_text_without_tags(self) -> None:
        page = self.render_pages()[0]
        for title, texts in HOSTILE_SECTIONS.items():
            with self.subTest(section=title):
                self.assert_inert(page, page.section(title), texts)
        self.assertEqual(page.find_all("i"), [])

    def test_header_and_warnings_show_text_without_tags(self) -> None:
        page = self.render_pages()[0]
        header = page.find("header")
        self.assertEqual(page.find_all("h1", within=header)[0].text(), HOSTILE_TITLE)
        self.assertIn(HOSTILE_PREAMBLE, header.text())
        links = page.find_all("a", within=header)
        self.assertEqual([link.attrs["href"] for link in links], ["index.html"])
        for tag in ("script", "img", "b", "i"):
            self.assertEqual(page.find_all(tag, within=header), [])
        warnings = page.find("div", cls="warnings")
        self.assert_inert(page, warnings, [HOSTILE_WORK_STATUS, HOSTILE_TEMP_STATUS])

    def test_overview_shows_text_without_tags(self) -> None:
        index = self.render_pages()[1]
        overview = index.section("總覽")
        row = index.find("tr", cls="overview-row", attrs={"data-record": "demo"})
        links = index.find_all("a", within=row)
        self.assertEqual([link.attrs["href"] for link in links], ["demo.html"])
        self.assertEqual(links[0].text(), HOSTILE_TITLE)
        self.assertEqual(index.find_all("a", within=links[0]), [])
        for tag in ("script", "img", "b", "i"):
            self.assertEqual(index.find_all(tag, within=overview), [])
        self.assertIn(html_module.escape(HOSTILE_TITLE), index.source)

    def test_markdown_links_are_not_turned_into_links(self) -> None:
        page = self.render_pages()[0]
        self.assertIn("[文件](https://example.com/x)", page.text())
        links = page.find_all("a")
        self.assertEqual([link.attrs.get("href") for link in links], ["index.html"])
        self.assertNotIn("文件", links[0].text())

    def test_pages_declare_strict_csp(self) -> None:
        for page in self.render_pages():
            directives = csp_directives(page)
            scripts = page.find_all("script")
            styles = page.find_all("style")
            self.assertEqual(page.source.count("<script"), 2)
            self.assertEqual(
                [node.text() for node in scripts], [rp.HEAD_SCRIPT, rp.SCRIPT]
            )
            self.assertEqual(len(styles), 1)
            self.assertEqual(directives["default-src"], "'none'")
            self.assertEqual(
                directives["script-src"],
                f"{sha256_source(rp.HEAD_SCRIPT)} {sha256_source(rp.SCRIPT)}",
            )
            self.assertEqual(
                directives["script-src"],
                " ".join(sha256_source(node.text()) for node in scripts),
            )
            self.assertEqual(directives["style-src"], sha256_source(styles[0].text()))
            self.assertEqual(directives["base-uri"], "'none'")
            self.assertEqual(directives["form-action"], "'none'")
            self.assertNotIn(
                "unsafe",
                page.find(
                    "meta", attrs={"http-equiv": "Content-Security-Policy"}
                ).attrs["content"],
            )
            self.assertLess(
                page.source.index("Content-Security-Policy"),
                page.source.index("<style"),
            )
            self.assertLess(
                page.source.index("Content-Security-Policy"),
                page.source.index("<script"),
            )

    def test_pages_load_no_external_resources(self) -> None:
        # 協定白名單是 head 腳本裡唯一允許出現 http 的地方；拿掉它再檢查。
        whitelist = json.dumps(list(rp.LIVE_PROTOCOLS))
        for page in self.render_pages():
            for node in page.nodes:
                with self.subTest(tag=node.tag, attrs=node.attrs):
                    self.assertIn(node.tag, ALLOWED_TAGS)
                    if node.tag == "a":
                        self.assertLessEqual(set(node.attrs), {"href", "class"})
                        self.assertTrue(SAFE_HREF.fullmatch(node.attrs["href"]))
                    elif node.tag == "button":
                        self.assertLessEqual(set(node.attrs), BUTTON_ATTRIBUTES)
                        self.assertEqual(node.attrs["type"], "button")
                    else:
                        self.assertFalse(FORBIDDEN_ATTRIBUTES & set(node.attrs))
            style_text = page.find("style").text()
            head_script = script_in(page, "head")
            body_script = script_in(page, "body")
            self.assertEqual(head_script.count(whitelist), 1)
            self.assertNotIn(whitelist, body_script)
            for needle in ("url(", "@import", "http"):
                self.assertNotIn(needle, style_text)
            for script_text in (head_script.replace(whitelist, ""), body_script):
                for needle in (
                    "fetch(",
                    "XMLHttpRequest",
                    "import(",
                    "http",
                    "src",
                    "//",
                    "WebSocket",
                    "sendBeacon",
                ):
                    self.assertNotIn(needle, script_text)
            for meta in page.find_all("meta"):
                equiv = meta.attrs.get("http-equiv")
                if equiv is not None:
                    self.assertEqual(equiv, "Content-Security-Policy")

    def test_chips_and_badges_never_wrap(self) -> None:
        declarations: dict[str, list[str]] = {}
        for rule in rp.STYLE.split("}"):
            selector, _, body = rule.partition("{")
            match = re.search(r"white-space:\s*([a-z-]+)", body)
            if match is None:
                continue
            for name in selector.split(","):
                declarations.setdefault(name.strip(), []).append(match.group(1))
        for name in (".chip", ".badge", ".mark", ".stale"):
            with self.subTest(selector=name):
                self.assertEqual(declarations.get(name, [])[-1:], ["nowrap"])
        wrapping = [
            name
            for name, values in declarations.items()
            if re.match(r"\.(?:st-|t-|badge|chip|stale|mark)", name)
            and values[-1] != "nowrap"
        ]
        self.assertEqual(wrapping, [])

    def test_refresh_comes_only_from_the_script(self) -> None:
        # 沒有 <noscript> 的 meta refresh：網頁程式不執行時就不自動更新，和畫面上的提醒一致。
        for page in self.render_pages():
            self.assertEqual(page.find_all("noscript"), [])
            self.assertNotIn(
                "refresh", [m.attrs.get("http-equiv") for m in page.find_all("meta")]
            )
            self.assertIn("5000", script_in(page, "body"))

    def test_no_inline_event_handlers_or_styles(self) -> None:
        for page in self.render_pages():
            for node in page.nodes:
                with self.subTest(tag=node.tag, attrs=node.attrs):
                    self.assertNotIn("style", node.attrs)
                    self.assertEqual(
                        [name for name in node.attrs if name.startswith("on")], []
                    )
            self.assertNotIn("javascript:", page.source)
            for name in ("onclick", "onload", " style=", "style.", "cssText"):
                self.assertNotIn(name, rp.HEAD_SCRIPT + rp.SCRIPT)


# ── 畫面更新時間、暫停提示、主題切換 ─────────────────────────────

SNAPSHOT_WARNING = "此畫面不會自動更新：請用一般瀏覽器開啟 index.html"
PAUSED_NOTICE = "已暫停自動更新：你選取了文字（取消選取即恢復）"
THEME_CHECK = re.compile(
    r'if \(theme === "light" \|\| theme === "dark"\) \{\s*'
    r'root\.setAttribute\("data-theme", theme\);\s*\}'
)


class PageToolsTests(TestCase):
    def render_pages(self) -> list[Page]:
        with RepoSandbox() as sandbox:
            record_page = sandbox.render(build_record())
            index_page = Page(
                (sandbox.progress / "index.html").read_text(encoding="utf-8")
            )
        return [record_page, index_page]

    def test_every_page_has_refresh_time_pause_notice_and_theme_toggle(self) -> None:
        for page in self.render_pages():
            tools = page.find("div", cls="page-tools")
            live = page.find("span", cls="refresh-live", within=tools)
            self.assertEqual(live.text(), "畫面更新於 ")
            self.assertEqual(page.find("span", cls="loaded-at", within=live).text(), "")
            notice = page.find("p", cls="pause-notice")
            self.assertEqual(notice.text(), PAUSED_NOTICE)
            self.assertIn("hidden", notice.attrs)
            self.assertEqual(notice.attrs.get("role"), "status")
            button = page.find("button", cls="theme-toggle", within=tools)
            self.assertEqual(button.attrs["type"], "button")
            labels = [
                page.find("span", cls=f"theme-{name}", within=button).text()
                for name in ("system", "light", "dark")
            ]
            self.assertEqual(labels, ["主題：跟隨系統", "主題：淺色", "主題：深色"])

    def test_default_text_is_snapshot_warning(self) -> None:
        for page in self.render_pages():
            snapshot = page.find("span", cls="refresh-snapshot")
            self.assertEqual(snapshot.text(), f"⚠ {SNAPSHOT_WARNING}")
        self.assertEqual(rp.SNAPSHOT_TEXT, SNAPSHOT_WARNING)
        # 沒有任何腳本時：畫面更新時間藏起來，警告照常顯示。
        self.assertIn(
            (".refresh-live", "none"), display_rules(rp.STYLE, ".refresh-live")
        )
        for selector, value in display_rules(rp.STYLE, ".refresh-live"):
            if value != "none":
                self.assertEqual(selector, "html.live .refresh-live")
        self.assertEqual(
            display_rules(rp.STYLE, ".refresh-snapshot"),
            [("html.live .refresh-snapshot", "none")],
        )

    def test_live_class_only_for_file_and_web_protocols(self) -> None:
        self.assertEqual(rp.LIVE_PROTOCOLS, ("file:", "http:", "https:"))
        whitelist = json.dumps(list(rp.LIVE_PROTOCOLS))
        self.assertIn(
            f"var live = {whitelist}.indexOf(window.location.protocol) !== -1;",
            rp.HEAD_SCRIPT,
        )
        self.assertIn(
            'root.setAttribute("class", live ? "js live" : "js");', rp.HEAD_SCRIPT
        )

    def test_protocol_whitelist_exists_only_once(self) -> None:
        # body 腳本只讀 head 腳本設好的 class，不另寫第二份協定清單。
        whitelist = json.dumps(list(rp.LIVE_PROTOCOLS))
        scripts = rp.HEAD_SCRIPT + rp.SCRIPT
        self.assertEqual(scripts.count(whitelist), 1)
        for name in ("protocol", "file:", "http", "data:"):
            self.assertNotIn(name, rp.SCRIPT)
        self.assertEqual(rp.SCRIPT.count('"live"'), 1)
        self.assertIn(
            'var LIVE = document.documentElement.classList.contains("live");',
            rp.SCRIPT,
        )
        source = MODULE_PATH.read_text(encoding="utf-8")
        self.assertEqual(source.count('("file:", "http:", "https:")'), 1)

    def test_head_script_runs_before_the_page_is_drawn(self) -> None:
        for page in self.render_pages():
            self.assertEqual(script_in(page, "head"), rp.HEAD_SCRIPT)
            self.assertEqual(script_in(page, "body"), rp.SCRIPT)
            head_script = page.source.index("<script")
            self.assertLess(head_script, page.source.index("</head>"))
            self.assertLess(head_script, page.source.index("<body"))

    def test_theme_storage_accepts_only_light_and_dark(self) -> None:
        self.assertTrue(rp.THEME_STORAGE_KEY.startswith("toukadev-progress-"))
        head = rp.HEAD_SCRIPT
        self.assertEqual(
            head.count(
                f"window.localStorage.getItem({json.dumps(rp.THEME_STORAGE_KEY)})"
            ),
            1,
        )
        self.assertEqual(len(THEME_CHECK.findall(head)), 1)
        # 讀到的值只出現在：讀取、白名單比對、套用；不拿去做別的事。
        self.assertEqual(len(re.findall(r"(?<![\w-])theme(?![\w-])", head)), 4)
        # head 腳本只用 setAttribute 改畫面：一次套用協定 class、一次套用主題。
        self.assertEqual(head.count(".setAttribute("), 2)
        for name in ("className", "classList", "textContent", ".hidden", "style"):
            self.assertNotIn(name, head)
        for script in (head, rp.SCRIPT):
            for name in (
                "innerHTML",
                "outerHTML",
                "insertAdjacent",
                "document.write",
                "eval(",
                "Function(",
            ):
                self.assertNotIn(name, script)
        # 切換時只寫入固定的三種值。
        self.assertIn(
            'var NEXT_THEME = { system: "light", light: "dark", dark: "system" };',
            rp.SCRIPT,
        )
        self.assertIn(
            'return theme === "light" || theme === "dark" ? theme : "system";',
            rp.SCRIPT,
        )
        self.assertEqual(rp.SCRIPT.count(".setAttribute("), 1)
        self.assertIn(
            'document.documentElement.setAttribute("data-theme", theme);', rp.SCRIPT
        )

    def test_every_storage_access_is_inside_try(self) -> None:
        for script in (rp.HEAD_SCRIPT, rp.SCRIPT):
            for match in re.finditer(r"(?:local|session)Storage", script):
                before = script[: match.start()]
                with self.subTest(script=script[:40], at=match.start()):
                    self.assertGreater(before.rfind("try {"), before.rfind("} catch"))
        self.assertIn("localStorage", rp.HEAD_SCRIPT)
        self.assertIn("localStorage", rp.SCRIPT)

    def test_reload_is_scheduled_first_and_only_when_live(self) -> None:
        # 最外層會執行的敘述（不含 var、function 定義與其內容）。
        statements = [
            line.strip()
            for line in rp.SCRIPT.splitlines()
            if re.match(r"  [^ }]", line)
            and not line.startswith(("  var ", "  function ", '  "use strict"'))
        ]
        self.assertEqual(statements[0], "if (LIVE) { scheduleReload(); }")
        self.assertEqual(statements.count("if (LIVE) { scheduleReload(); }"), 1)
        self.assertNotIn("scheduleReload();", statements)
        # 快照時不排重新整理，也就不會呼叫 reload。
        self.assertEqual(rp.SCRIPT.count("window.location.reload()"), 1)
        self.assertEqual(
            len(re.findall(r"(?<!function )scheduleReload\(\)", rp.SCRIPT)), 2
        )

    def test_theme_choice_sets_color_scheme(self) -> None:
        rules = css_rules(rp.STYLE)
        schemes = {
            selector: declarations["color-scheme"]
            for selectors, declarations in rules
            if "color-scheme" in declarations
            for selector in selectors
        }
        self.assertEqual(
            schemes,
            {
                ":root": "light dark",
                ':root[data-theme="light"]': "light",
                ':root[data-theme="dark"]': "dark",
            },
        )
        dark = {
            selector: declarations
            for selectors, declarations in rules
            for selector in selectors
            if selector
            in (':root[data-theme="dark"]', ':root:not([data-theme="light"])')
        }
        self.assertEqual(len(dark), 2)
        palettes = [
            {k: v for k, v in declarations.items() if k.startswith("--")}
            for declarations in dark.values()
        ]
        self.assertEqual(palettes[0], palettes[1])
        self.assertEqual(palettes[0]["--bg"], "#13171c")
        self.assertIn("@media (prefers-color-scheme: dark)", rp.STYLE)

    def test_pause_notice_is_fixed_so_layout_does_not_move(self) -> None:
        notice = [
            declarations
            for selectors, declarations in css_rules(rp.STYLE)
            if ".pause-notice" in selectors
        ]
        self.assertEqual(notice[0]["position"], "fixed")
        self.assertIn("selectionchange", rp.SCRIPT)
        self.assertIn(
            ("html:not(.live) .pause-notice", "none"),
            display_rules(rp.STYLE, ".pause-notice"),
        )

    def test_footer_says_refresh_needs_a_normal_browser(self) -> None:
        for page in self.render_pages():
            footer = page.find("footer").text()
            self.assertIn("用一般瀏覽器開啟時每 5 秒自動重新整理", footer)


# ── 格式警告：缺必要區段、未知狀態值與審核時間 ───────────────────


class FormatWarningTests(TestCase):
    def test_missing_required_section_is_prominent(self) -> None:
        with RepoSandbox() as sandbox:
            page = sandbox.render(build_record(sections={"審核紀錄": None}))
        section = page.section("審核紀錄")
        self.assertIn("missing-section", section.classes())
        self.assertEqual(section.attrs.get("role"), "alert")
        self.assertIn("紀錄缺少這一區", section.text())
        self.assertNotIn("目前沒有", section.text().replace("不代表「目前沒有」", ""))
        self.assertTrue(any("審核紀錄" in warning for warning in page.warnings()))
        self.assertEqual(page.find("div", cls="warnings").attrs.get("role"), "alert")

    def test_every_required_section_can_be_reported_missing(self) -> None:
        for title in rp.REQUIRED_SECTIONS:
            with self.subTest(title=title), RepoSandbox() as sandbox:
                page = sandbox.render(build_record(sections={title: None}))
                self.assertIn("missing-section", page.section(title).classes())
                self.assertTrue(any(title in item for item in page.warnings()))

    def test_unknown_status_is_highlighted_and_warned(self) -> None:
        table = WORK_TABLE + "\n| E：其他 | 做到一半 | 主代理 | — | — | — | — |"
        temp = TEMP_TABLE + (
            "\n| 奇怪的東西 | 快取 | .toukadev/tmp/demo | 主代理 | 不知道 | — |"
            "\n| 留著的分支 | 本機分支 | wt/demo-x | 主代理 | 保留 |  |"
        )
        with RepoSandbox() as sandbox:
            page = sandbox.render(
                build_record(sections={"工作清單": table, "暫存項目": temp})
            )
        row = page.find("tr", cls="work-row", attrs={"data-status": "做到一半"})
        self.assertEqual(row.attrs["data-mark"], "unknown")
        self.assertTrue(page.find_all("span", cls="st-unknown", within=row))
        temp_row = page.find("tr", cls="temp-row", attrs={"data-status": "不知道"})
        self.assertEqual(temp_row.attrs["data-mark"], "unknown")
        self.assertTrue(page.find_all("span", cls="st-unknown", within=temp_row))
        self.assertIn("不是規定的狀態", temp_row.text())
        warnings = page.warnings()
        self.assertTrue(any("做到一半" in warning for warning in warnings))
        self.assertTrue(any("不知道" in warning for warning in warnings))
        # 類型寫錯、「保留」沒寫理由不另外警告；只有兩個狀態值被警告。
        self.assertEqual(len(warnings), 2)

    def test_unknown_column_is_kept(self) -> None:
        lines = WORK_TABLE.splitlines()
        lines[0] += " 優先度 |"
        lines[1] += "---|"
        lines[2:] = [line + " 高 |" for line in lines[2:]]
        with RepoSandbox() as sandbox:
            page = sandbox.render(build_record(sections={"工作清單": "\n".join(lines)}))
        headers = [header.text() for header in page.find_all("th")]
        self.assertIn("優先度", headers)
        self.assertEqual(len(page.find_all("td", cls="col-優先度")), 5)
        self.assertEqual(page.warnings(), [])

    def test_row_with_missing_and_extra_cells_is_kept(self) -> None:
        table = (
            WORK_TABLE
            + "\n| 短列 | 待辦 |\n| 長列 | 待辦 | a | b | c | d | e | 多一格 |"
        )
        with RepoSandbox() as sandbox:
            page = sandbox.render(build_record(sections={"工作清單": table}))
        self.assertIn("多一格", page.text())
        short = page.find_all("tr", cls="work-row")[-2]
        self.assertEqual(len(page.find_all("td", cls="missing", within=short)), 6)
        extra = page.find_all("td", cls="col-（多出的格子）")
        self.assertEqual(
            [cell.text() for cell in extra if cell.text() != "—"], ["多一格"]
        )
        self.assertIn("（多出的格子）", [th.text() for th in page.find_all("th")])
        self.assertEqual(page.warnings(), [])

    def test_text_outside_table_is_not_dropped(self) -> None:
        with RepoSandbox() as sandbox:
            page = sandbox.render(
                build_record(sections={"工作清單": "說明：先做 A。\n\n" + WORK_TABLE})
            )
        self.assertIn("說明：先做 A。", page.section("工作清單").text())


# 本機時間 2026-10-11 20:00:00；用 os.utime 設成紀錄檔的修改時間，不看當下時間。
SAVED_AT = int(datetime(2026, 10, 11, 20, 0).timestamp())


def review_table(times: Sequence[str]) -> str:
    rows = [f"| {moment} | 關卡 | 對象 | 主代理 | reviewer | 通過 | — |" for moment in times]
    return "\n".join([*REVIEW_TABLE.splitlines()[:2], *rows])


def review_time_warnings(
    times: Sequence[str], state: str | None = "進行中", saved_at: int = SAVED_AT
) -> list[str]:
    with RepoSandbox() as sandbox:
        record = build_record(state=state, sections={"審核紀錄": review_table(times)})
        return sandbox.render(record, mtime=saved_at).warnings()


class ReviewTimeWarningTests(TestCase):
    """只查進行中紀錄的審核時間：比上一列早，或比存檔時間晚 2～59 分鐘。"""

    def test_earlier_than_previous_row_warns_and_equal_is_allowed(self) -> None:
        warnings = review_time_warnings(
            ["10/11 19:00", "10/11 19:00", "10/11 18:30", "10/11 19:10"]
        )
        self.assertEqual(warnings, ["審核紀錄第 3 列的時間「10/11 18:30」比上一列早。"])

    def test_future_window_is_2_to_59_minutes(self) -> None:
        for moment, warned in (
            ("10/11 20:01", False),
            ("10/11 20:02", True),
            ("10/11 20:59", True),
            ("10/11 21:00", False),
        ):
            with self.subTest(moment=moment):
                expected = (
                    f"審核紀錄第 1 列的時間「{moment}」晚於紀錄存檔時間（多半是估的）。"
                )
                self.assertEqual(
                    review_time_warnings([moment]), [expected] if warned else []
                )

    def test_month_day_uses_save_year_and_rolls_back_after_30_days(self) -> None:
        new_year = int(datetime(2027, 1, 5, 10, 0).timestamp())
        times = ["12/31 23:50", "1/5 09:00"]
        self.assertEqual(review_time_warnings(times, saved_at=new_year), [])
        # 晚 29 天多仍算同一年，所以下一列比它早；晚 31 天多才當成前一年。
        self.assertEqual(
            review_time_warnings(["11/09 21:00", "10/11 19:00"]),
            ["審核紀錄第 2 列的時間「10/11 19:00」比上一列早。"],
        )
        self.assertEqual(review_time_warnings(["11/11 21:00", "10/11 19:00"]), [])

    def test_unreadable_cells_are_skipped(self) -> None:
        times = ["10/11 19:00", "10/10", "不知道", "2/30 10:00", "10/11 25:00"]
        times += ["10/11 18:30（補記）", "10/11 18:00"]
        self.assertEqual(
            review_time_warnings(times),
            ["審核紀錄第 7 列的時間「10/11 18:00」比上一列早。"],
        )

    def test_about_prefix_and_both_date_formats(self) -> None:
        warnings = review_time_warnings(
            ["約 10/11 19:00", "2026-10-11 18:30", "約2026-10-11 20:30"]
        )
        self.assertEqual(
            warnings,
            [
                "審核紀錄第 2 列的時間「2026-10-11 18:30」比上一列早。",
                "審核紀錄第 3 列的時間「約2026-10-11 20:30」晚於紀錄存檔時間（多半是估的）。",
            ],
        )

    def test_only_running_records_are_checked(self) -> None:
        for state in ("已結束", None):
            with self.subTest(state=state):
                times = ["10/11 20:30", "10/11 19:00"]
                self.assertEqual(review_time_warnings(times, state=state), [])

    def test_overview_and_command_line_count_time_warnings(self) -> None:
        table = review_table(["10/11 20:30", "10/11 19:00"])
        with RepoSandbox() as sandbox:
            record = build_record(sections={"審核紀錄": table})
            sandbox.write_record("demo", record, mtime=SAVED_AT)
            code, _, stderr = run_main([str(sandbox.progress)])
            index = Page((sandbox.progress / "index.html").read_text("utf-8"))
        self.assertEqual(code, 0)
        self.assertIn("格式警告 2 項", stderr)
        badge = index.find("span", cls="badge-unknown")
        self.assertEqual(badge.text(), "⚠ 格式警告 2")


class OldRecordTests(TestCase):
    """舊紀錄用通用表格照樣顯示；「更新時間：」略過，不另標舊格式。"""

    def render_old(self) -> Page:
        with RepoSandbox() as sandbox:
            return sandbox.render(OLD_RECORD, stem="old-batch")

    def test_old_columns_are_shown_as_written(self) -> None:
        page = self.render_old()
        work_cells = page.find_all("td", cls="col-審核")
        self.assertEqual(len(work_cells), 7)
        self.assertIn("主代理驗收：補正後通過", work_cells[0].text())
        review_table = page.find("table", cls="review-table")
        review_cells = page.find_all("td", cls="col-審核者", within=review_table)
        self.assertEqual(
            [cell.text() for cell in review_cells],
            ["reviewer", "你", "主代理", "主代理", "你"],
        )
        self.assertEqual(page.section("需要你決定的事").attrs["data-count"], "0")
        self.assertIn("missing-section", page.section("暫存項目").classes())
        self.assertIn("已合併，分支已刪", page.text())
        self.assertIn("加三個限定詞", page.text())

    def test_old_record_marks_only_accepted_and_merged(self) -> None:
        page = self.render_old()
        marks = [row.attrs["data-mark"] for row in work_rows(page)]
        self.assertEqual(
            marks,
            ["check", "check", "unknown", "complete", "unknown", "check", "unknown"],
        )

    def test_old_record_warns_only_about_missing_section_and_statuses(self) -> None:
        page = self.render_old()
        warnings = page.warnings()
        self.assertEqual(len(warnings), 4)
        self.assertTrue(any("暫存項目" in warning for warning in warnings))
        for word in ("舊", "更新時間", "欄位", "任務狀態"):
            with self.subTest(word=word):
                self.assertFalse(any(word in warning for warning in warnings))
        self.assertNotIn("舊格式", page.text())
        self.assertNotIn("2026-10-10 03:49", page.text())
        stamp = page.find("span", cls="age-stamp")
        self.assertEqual(stamp.attrs["data-stale-mode"], "off")

    def test_update_time_line_is_ignored(self) -> None:
        for updated in ("不知道", "2026-10-10 24:00", "2026-10-10 04:20"):
            with self.subTest(updated=updated), RepoSandbox() as sandbox:
                page = sandbox.render(build_record(updated=updated))
                self.assertEqual(page.warnings(), [])
                self.assertNotIn(updated, page.text())
                self.assertNotIn("更新時間：", page.text())
                stamp = page.find("span", cls="age-stamp")
                self.assertEqual(stamp.attrs["data-stale-mode"], "running")


# ── 紀錄最後更新與過期提示 ───────────────────────────────────────


def clock(epoch: int) -> str:
    return time.strftime("%H:%M", time.localtime(epoch))


class StalePromptTests(TestCase):
    def generated(self, text: str) -> tuple[Node, Page]:
        with RepoSandbox() as sandbox:
            page = sandbox.render(text)
        return page.find("span", cls="age-stamp"), page

    def test_pages_show_no_generation_time(self) -> None:
        with RepoSandbox() as sandbox:
            page = sandbox.render(build_record())
            index = Page((sandbox.progress / "index.html").read_text("utf-8"))
        for shown in (page, index):
            self.assertEqual(shown.find_all(cls="generated-at"), [])
            self.assertNotIn("產生於", shown.text())
        header = index.find("header")
        self.assertEqual(index.find_all("span", cls="age-stamp", within=header), [])

    def test_stale_prompt_uses_record_modification_time(self) -> None:
        node, _ = self.generated(build_record())
        self.assertEqual(node.attrs["data-epoch"], str(RECORD_MTIME))
        self.assertIn(f"紀錄最後更新：{clock(RECORD_MTIME)}", node.text())
        self.assertNotIn("data-generated-epoch", node.attrs)

    def test_running_task_enables_stale_prompt(self) -> None:
        node, page = self.generated(build_record(state="進行中"))
        self.assertEqual(node.attrs["data-stale-mode"], "running")
        self.assertEqual(node.attrs["data-warn-after"], "1800")
        self.assertEqual(node.attrs["data-alert-after"], "7200")
        script = script_in(page, "body")
        self.assertIn("分鐘沒更新：可能還在做，也可能忘了更新", script)
        self.assertIn("data-epoch", script)
        self.assertIn("data-warn-after", script)
        self.assertIn("data-alert-after", script)

    def test_thresholds_are_30_and_120_minutes(self) -> None:
        self.assertEqual(rp.STALE_WARN_SECONDS, 30 * 60)
        self.assertEqual(rp.STALE_ALERT_SECONDS, 120 * 60)
        self.assertEqual(rp.REFRESH_SECONDS, 5)

    def test_finished_task_has_no_stale_prompt(self) -> None:
        node, page = self.generated(build_record(state="已結束"))
        self.assertEqual(node.attrs["data-stale-mode"], "off")
        self.assertEqual(page.warnings(), [])

    def test_missing_task_state_has_no_stale_prompt(self) -> None:
        node, page = self.generated(build_record(state=None))
        self.assertEqual(node.attrs["data-stale-mode"], "off")
        self.assertIn("缺少或看不懂", page.find("header").text())

    def test_unknown_task_state_has_no_stale_prompt_but_warns(self) -> None:
        node, page = self.generated(build_record(state="暫停"))
        self.assertEqual(node.attrs["data-stale-mode"], "off")
        self.assertTrue(any("暫停" in warning for warning in page.warnings()))

    def test_pending_decision_shows_waiting_instead_of_stale(self) -> None:
        node, _ = self.generated(
            build_record(sections={"需要你決定的事": "- 要選 A 還是 B？"})
        )
        self.assertEqual(node.attrs["data-stale-mode"], "waiting")
        self.assertIn("等你決定", node.text())

    def test_finished_task_with_pending_decision_is_not_waiting(self) -> None:
        node, _ = self.generated(
            build_record(state="已結束", sections={"需要你決定的事": "- 要選 A？"})
        )
        self.assertEqual(node.attrs["data-stale-mode"], "off")
        self.assertNotIn("等你決定", node.text())


class FreshnessTests(TestCase):
    """另一個任務重產資料夾時，沒動過的紀錄不能看起來像剛更新。"""

    def stamp_epoch(self, page: Page) -> str:
        return page.find("span", cls="age-stamp").attrs["data-epoch"]

    def test_untouched_record_keeps_its_stale_time(self) -> None:
        old = NOW - 3 * 60 * 60
        with RepoSandbox() as sandbox:
            first = sandbox.write_record("a", build_record(stem="a"), mtime=old)
            sandbox.write_record("b", build_record(stem="b"), mtime=old)
            rp.render_folder(sandbox.progress)
            os.utime(first, (NOW + 300, NOW + 300))
            rp.render_folder(sandbox.progress)
            pages = {
                stem: Page((sandbox.progress / f"{stem}.html").read_text("utf-8"))
                for stem in ("a", "b", "index")
            }
        self.assertEqual(self.stamp_epoch(pages["a"]), str(NOW + 300))
        self.assertEqual(self.stamp_epoch(pages["b"]), str(old))
        rows = {
            row.attrs["data-record"]: pages["index"]
            .find("span", cls="age-stamp", within=row)
            .attrs["data-epoch"]
            for row in pages["index"].find_all("tr", cls="overview-row")
        }
        self.assertEqual(rows, {"a": str(NOW + 300), "b": str(old)})


# ── 總覽 ─────────────────────────────────────────────────────────


class OverviewTests(TestCase):
    def build_folder(self, sandbox: RepoSandbox) -> None:
        sandbox.write_record(
            "alpha",
            build_record(
                stem="alpha",
                sections={"需要你決定的事": "- 問題一？\n- 問題二？"},
            ),
            mtime=NOW - 600,
        )
        sandbox.write_record(
            "beta", build_record(stem="beta", state="已結束"), mtime=NOW - 60
        )
        sandbox.write_record("gamma", OLD_RECORD, mtime=NOW - 2000)
        # 紀錄裡寫的更新時間不算：delta 寫了最晚的時間，仍依 .md 修改時間排在最後。
        sandbox.write_record(
            "delta",
            build_record(stem="delta", updated="2099-12-31 23:59"),
            mtime=NOW - 3000,
        )

    def render_index(self) -> Page:
        with RepoSandbox() as sandbox:
            self.build_folder(sandbox)
            result = rp.render_folder(sandbox.progress)
            self.assertEqual(result.failures, [])
            return Page((sandbox.progress / "index.html").read_text(encoding="utf-8"))

    def test_rows_sorted_by_record_modification_time_newest_first(self) -> None:
        page = self.render_index()
        order = [
            row.attrs["data-record"] for row in page.find_all("tr", cls="overview-row")
        ]
        self.assertEqual(order, ["beta", "alpha", "gamma", "delta"])

    def test_rows_with_the_same_time_are_sorted_by_name(self) -> None:
        with RepoSandbox() as sandbox:
            for stem in ("zeta", "eta", "theta"):
                sandbox.write_record(stem, build_record(stem=stem), mtime=NOW)
            rp.render_folder(sandbox.progress)
            page = Page((sandbox.progress / "index.html").read_text(encoding="utf-8"))
        order = [
            row.attrs["data-record"] for row in page.find_all("tr", cls="overview-row")
        ]
        self.assertEqual(order, ["eta", "theta", "zeta"])

    def test_row_statistics(self) -> None:
        page = self.render_index()
        rows = {
            row.attrs["data-record"]: row
            for row in page.find_all("tr", cls="overview-row")
        }
        alpha = rows["alpha"]
        self.assertEqual(
            page.find("td", cls="pending", within=alpha).attrs["data-count"], "2"
        )
        progress = page.find("td", cls="progress", within=alpha)
        self.assertEqual(progress.attrs["data-checked"], "2")
        self.assertEqual(progress.attrs["data-total"], "5")
        self.assertEqual(progress.attrs["data-complete"], "1")
        self.assertEqual(progress.text(), "完成 3／5其中 2 項經驗收或合併")
        temp = page.find("td", cls="temp", within=alpha)
        self.assertEqual(temp.attrs["data-open"], "1")
        self.assertEqual(temp.text(), "1 項")
        self.assertEqual(
            page.find("td", cls="state", within=rows["beta"]).attrs["data-state"],
            "已結束",
        )
        self.assertEqual(
            page.find("td", cls="state", within=rows["gamma"]).attrs["data-state"], ""
        )
        gamma_progress = page.find("td", cls="progress", within=rows["gamma"])
        self.assertEqual(gamma_progress.attrs["data-checked"], "3")
        self.assertEqual(gamma_progress.attrs["data-total"], "7")
        self.assertEqual(gamma_progress.text(), "完成 4／7其中 3 項經驗收或合併")
        self.assertEqual(
            page.find("td", cls="temp", within=rows["gamma"]).attrs["data-open"],
            "unknown",
        )
        self.assertIn("gamma.html", rows["gamma"].text())

    def test_row_stale_modes(self) -> None:
        page = self.render_index()
        modes = {
            row.attrs["data-record"]: page.find(
                "span", cls="age-stamp", within=row
            ).attrs["data-stale-mode"]
            for row in page.find_all("tr", cls="overview-row")
        }
        self.assertEqual(
            modes,
            {"alpha": "waiting", "beta": "off", "gamma": "off", "delta": "running"},
        )

    def test_missing_decision_section_count_is_unknown(self) -> None:
        with RepoSandbox() as sandbox:
            sandbox.write_record(
                "solo", build_record(sections={"需要你決定的事": None})
            )
            rp.render_folder(sandbox.progress)
            page = Page((sandbox.progress / "index.html").read_text(encoding="utf-8"))
        cell = page.find("td", cls="pending")
        self.assertEqual(cell.attrs["data-count"], "unknown")
        self.assertIn("?", cell.text())

    def test_folder_writes_every_page(self) -> None:
        with RepoSandbox() as sandbox:
            self.build_folder(sandbox)
            result = rp.render_folder(sandbox.progress)
            names = sorted(path.name for path in result.outputs)
            self.assertEqual(
                names,
                ["alpha.html", "beta.html", "delta.html", "gamma.html", "index.html"],
            )
            self.assertTrue(all(path.is_file() for path in result.outputs))

    def test_index_md_is_the_board_not_a_skipped_record(self) -> None:
        with RepoSandbox() as sandbox:
            sandbox.write_record("index", BOARD)
            sandbox.write_record("alpha", build_record(stem="alpha"))
            result = rp.render_folder(sandbox.progress)
            page = Page((sandbox.progress / "index.html").read_text(encoding="utf-8"))
        self.assertEqual(result.skipped, [])
        self.assertEqual(result.failures, [])
        self.assertEqual(
            sorted(path.name for path in result.outputs), ["alpha.html", "index.html"]
        )
        self.assertEqual(page.find_all("div", cls="warnings"), [])
        self.assertNotIn("略過", page.text())
        board = page.section("總覽板")
        self.assertEqual(page.find("h2", within=board).text(), "團隊總覽")
        order = [
            row.attrs["data-record"] for row in page.find_all("tr", cls="overview-row")
        ]
        self.assertEqual(order, ["alpha"])

    def test_single_board_only_rebuilds_the_overview(self) -> None:
        with RepoSandbox() as sandbox:
            sandbox.write_record("alpha", build_record(stem="alpha"))
            board = sandbox.write_record("index", "# 舊總覽\n")
            rp.render_folder(sandbox.progress)
            alpha_page = sandbox.progress / "alpha.html"
            os.utime(alpha_page, (NOW - 5000, NOW - 5000))
            before = alpha_page.read_bytes()
            sandbox.write_record("index", BOARD, mtime=NOW)
            code, stdout, stderr = run_main([str(board)])
            index = Page((sandbox.progress / "index.html").read_text("utf-8"))
            names = sorted(path.name for path in sandbox.progress.iterdir())
            self.assertEqual(alpha_page.read_bytes(), before)
            self.assertEqual(int(alpha_page.stat().st_mtime), NOW - 5000)
        self.assertEqual(code, 0, stderr)
        self.assertEqual(stdout.splitlines(), [str(sandbox.progress / "index.html")])
        self.assertEqual(stderr, "")
        self.assertEqual(names, ["alpha.html", "alpha.md", "index.html", "index.md"])
        board_section = index.section("總覽板")
        self.assertEqual(index.find("h2", within=board_section).text(), "團隊總覽")
        rows = index.find_all("tr", cls="overview-row")
        self.assertEqual([row.attrs["data-record"] for row in rows], ["alpha"])

    def test_overview_header_names_record_update_time(self) -> None:
        page = self.render_index()
        headers = [header.text() for header in page.find_all("th")]
        self.assertIn("紀錄最後更新", headers)
        self.assertIn("進度（完成／全部）", headers)

    def test_finished_work_reads_all_done(self) -> None:
        head = WORK_TABLE.splitlines()[:2]
        tables = {
            "done": "\n".join([*head, "| A | 已驗收 |", "| B | 已完成 |"]),
            "todo": "\n".join([*head, "| A | 待辦 |"]),
        }
        with RepoSandbox() as sandbox:
            for stem, table in tables.items():
                record = build_record(stem=stem, sections={"工作清單": table})
                sandbox.write_record(stem, record)
            rp.render_folder(sandbox.progress)
            index = Page((sandbox.progress / "index.html").read_text("utf-8"))
        cells = {
            row.attrs["data-record"]: index.find("td", cls="progress", within=row).text()
            for row in index.find_all("tr", cls="overview-row")
        }
        self.assertEqual(cells, {"done": "完成 2／2其中 1 項經驗收或合併", "todo": "完成 0／1"})


class NavigationLinkTests(TestCase):
    """總覽 → 任務頁、任務頁 → 總覽；連結只由檔名（任務代號）產生。"""

    def render_folder_pages(self, stems: Sequence[str]) -> dict[str, Page]:
        with RepoSandbox() as sandbox:
            for stem in stems:
                sandbox.write_record(
                    stem,
                    build_record(
                        stem=stem,
                        title=f"任務 {stem} https://example.com/{stem}",
                        sections={
                            "需要你決定的事": "- 看 https://example.com/x 再決定"
                        },
                    ),
                )
            rp.render_folder(sandbox.progress)
            return {
                path.stem: Page(path.read_text(encoding="utf-8"))
                for path in sandbox.progress.glob("*.html")
            }

    def test_overview_rows_link_to_task_pages(self) -> None:
        pages = self.render_folder_pages(["alpha", "beta-2"])
        index = pages["index"]
        for row in index.find_all("tr", cls="overview-row"):
            stem = row.attrs["data-record"]
            with self.subTest(stem=stem):
                links = index.find_all("a", within=row)
                self.assertEqual(len(links), 1)
                self.assertEqual(links[0].attrs["href"], f"{stem}.html")
                self.assertEqual(
                    links[0].text(), f"任務 {stem} https://example.com/{stem}"
                )

    def test_invalid_task_code_gets_no_link(self) -> None:
        pages = self.render_folder_pages(["alpha", "Demo_Task"])
        index = pages["index"]
        rows = {
            row.attrs["data-record"]: row
            for row in index.find_all("tr", cls="overview-row")
        }
        self.assertEqual(index.find_all("a", within=rows["Demo_Task"]), [])
        self.assertIn("任務 Demo_Task", rows["Demo_Task"].text())
        self.assertEqual(len(index.find_all("a", within=rows["alpha"])), 1)

    def test_task_pages_link_back_to_overview(self) -> None:
        pages = self.render_folder_pages(["alpha", "Demo_Task"])
        for stem in ("alpha", "Demo_Task"):
            with self.subTest(stem=stem):
                links = pages[stem].find_all("a")
                self.assertEqual([link.attrs["href"] for link in links], ["index.html"])
                self.assertIn("回總覽", links[0].text())

    def test_record_text_urls_stay_plain_text(self) -> None:
        pages = self.render_folder_pages(["alpha"])
        for name, page in pages.items():
            with self.subTest(page=name):
                self.assertIn("https://example.com/", page.text())
                for link in page.find_all("a"):
                    href = link.attrs["href"]
                    self.assertTrue(SAFE_HREF.fullmatch(href), href)
                    self.assertNotIn("://", href)
        decision = pages["alpha"].section("需要你決定的事")
        self.assertEqual(pages["alpha"].find_all("a", within=decision), [])

    def test_task_code_check_is_exact(self) -> None:
        for stem, valid in (
            ("alpha", True),
            ("beta-2", True),
            ("index", False),
            ("Alpha", False),
            ("demo_task", False),
            ("demo\n", False),
            ("../x", False),
            ("", False),
        ):
            with self.subTest(stem=stem):
                self.assertEqual(rp.is_linkable_task_code(stem), valid)


class SingleRecordIndexTests(TestCase):
    """只給一份紀錄時，也重產同資料夾的 index.html，但不改寫其他紀錄的網頁。"""

    def test_index_reflects_updated_record_without_rewriting_others(self) -> None:
        with RepoSandbox() as sandbox:
            alpha = sandbox.write_record("alpha", build_record(stem="alpha"))
            sandbox.write_record("beta", build_record(stem="beta", state="已結束"))
            rp.render_folder(sandbox.progress)
            beta_page = sandbox.progress / "beta.html"
            os.utime(beta_page, (NOW - 5000, NOW - 5000))
            beta_before = beta_page.read_bytes()
            updated = build_record(
                stem="alpha",
                sections={
                    "需要你決定的事": "- 要選 A 還是 B？",
                    "工作清單": WORK_TABLE.replace(
                        "| D：收尾 | 待辦 |", "| D：收尾 | 已驗收 |"
                    ),
                },
            )
            sandbox.write_record("alpha", updated, mtime=NOW + 30)
            outcome = rp.render_file(alpha)
            index = Page((sandbox.progress / "index.html").read_text("utf-8"))
            self.assertEqual(beta_page.read_bytes(), beta_before)
            self.assertEqual(int(beta_page.stat().st_mtime), NOW - 5000)
        self.assertEqual(outcome.index, sandbox.progress / "index.html")
        rows = {
            row.attrs["data-record"]: row
            for row in index.find_all("tr", cls="overview-row")
        }
        self.assertEqual(set(rows), {"alpha", "beta"})
        alpha_row = rows["alpha"]
        progress = index.find("td", cls="progress", within=alpha_row)
        self.assertEqual(progress.attrs["data-checked"], "3")
        pending = index.find("td", cls="pending", within=alpha_row)
        self.assertEqual(pending.attrs["data-count"], "1")
        stamp = index.find("span", cls="age-stamp", within=alpha_row)
        self.assertEqual(stamp.attrs["data-epoch"], str(NOW + 30))
        self.assertEqual(stamp.attrs["data-stale-mode"], "waiting")
        beta_stamp = index.find("span", cls="age-stamp", within=rows["beta"])
        self.assertEqual(beta_stamp.attrs["data-epoch"], str(RECORD_MTIME))

    def test_single_record_index_reports_unreadable_siblings(self) -> None:
        with RepoSandbox() as sandbox:
            (sandbox.progress / "broken.md").write_bytes(b"# \xff\xfe broken\n")
            sandbox.write_record("index", build_record(stem="index"))
            alpha = sandbox.write_record("alpha", build_record(stem="alpha"))
            code, stdout, stderr = run_main([str(alpha)])
            index = Page((sandbox.progress / "index.html").read_text("utf-8"))
            self.assertTrue(alpha.with_suffix(".html").is_file())
            self.assertFalse((sandbox.progress / "broken.html").exists())
        self.assertEqual(code, 1)
        self.assertIn("broken.md", stderr)
        self.assertIn("broken.md", index.text())
        self.assertIn("總覽板：index.md", index.section("總覽板").text())
        self.assertNotIn("任務代號不得為 index", index.text())
        self.assertIn(str(alpha.with_suffix(".html")), stdout.splitlines())


# ── 總覽板（index.md）與自動彙總 ─────────────────────────────────

BOARD = """\
# 團隊總覽

開頭說明 <b>不是標籤</b>

## 任務順序

1. alpha
2. beta

## 之後的候選

- 候選 <script>alert(1)</script>
"""


def progress_folder(root: Path) -> Path:
    folder = root / ".toukadev" / "progress"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def put(folder: Path, name: str, text: str, mtime: int = RECORD_MTIME) -> Path:
    path = folder / name
    path.write_text(text, encoding="utf-8", newline="\n")
    os.utime(path, (mtime, mtime))
    return path


def overview_page(folder: Path) -> Page:
    result = rp.render_folder(folder)
    assert result.failures == []
    return Page((folder / "index.html").read_text(encoding="utf-8"))


def work_table(*rows: tuple[str, str, str]) -> str:
    """工作清單：每列只給（項目, 狀態, 備註），其他欄位用固定值。"""
    body = [
        f"| {item} | {status} | 主代理 | — | — | — | {note} |"
        for item, status, note in rows
    ]
    return "\n".join([*WORK_TABLE.splitlines()[:2], *body])


NOW_NEXT_TABLE = work_table(
    ("規劃", "已完成", "—"),
    ("A：寫程式", "執行中（10:00 開始）", "寫測試中"),
    ("B：文件", "待審", "等主代理"),
    ("C：整合", "審核中", "—"),
    ("D：修正", "退回修正", "缺測試"),
    ("E：收尾", "待辦", "先做"),
    ("F：發布", "待辦", "後做"),
    ("G：介面", "已驗收", "—"),
    ("H：奇怪", "做到一半", "—"),
)
# （種類, 狀態, 顯示文字）：四種狀態照工作清單的順序，再加第一個待辦。
EXPECTED_NOW_NEXT = [
    ("now", "執行中", "執行中（10:00 開始） A：寫程式 — 寫測試中"),
    ("now", "待審", "待審 B：文件 — 等主代理"),
    ("now", "審核中", "審核中 C：整合"),
    ("now", "退回修正", "退回修正 D：修正 — 缺測試"),
    ("next", "待辦", "下一步 E：收尾 — 先做"),
]


def now_next_rows(page: Page, region: Node) -> list[tuple[str, str, str]]:
    return [
        (
            "next" if "next-item" in item.classes() else "now",
            item.attrs["data-status"],
            item.text(),
        )
        for item in page.find_all("li", within=region)
        if {"now-item", "next-item"} & item.classes()
    ]


def hrefs(page: Page, region: Node) -> list[str]:
    return [link.attrs["href"] for link in page.find_all("a", within=region)]


def test_board_is_shown_below_the_summary(tmp_path: Path) -> None:
    folder = progress_folder(tmp_path)
    put(folder, "index.md", BOARD)
    put(folder, "alpha.md", build_record(stem="alpha"))
    page = overview_page(folder)
    board = page.section("總覽板")
    assert page.find("h2", within=board).text() == "團隊總覽"
    assert "index.md" in board.text()
    assert "開頭說明 <b>不是標籤</b>" in board.text()
    sections = page.find_all("section", cls="board-section")
    assert [section.attrs["data-section"] for section in sections] == ["任務順序", "之後的候選"]
    assert page.find("pre", within=sections[0]).text() == "1. alpha\n2. beta"
    candidates = page.find("pre", within=sections[1]).text()
    assert candidates == "- 候選 <script>alert(1)</script>"
    assert page.source.count("<script") == 2
    assert page.find_all("b") == []
    titles = ("要你決定", "現在／下一步", "總覽板", "總覽")
    order = [page.nodes.index(page.section(title)) for title in titles]
    assert order == sorted(order)


def test_overview_without_board_still_has_the_summary(tmp_path: Path) -> None:
    folder = progress_folder(tmp_path)
    put(folder, "alpha.md", build_record(stem="alpha"))
    page = overview_page(folder)
    assert page.find_all("section", attrs={"data-section": "總覽板"}) == []
    assert page.find_all("section", cls="board-section") == []
    assert page.section("要你決定").attrs["data-count"] == "0"
    assert page.find_all("li", cls="now-task", within=page.section("現在／下一步"))


def test_board_with_only_a_title_or_no_title(tmp_path: Path) -> None:
    for name, text, title in (
        ("only-title", "# 只有標題\n", "只有標題"),
        ("no-title", "說明一行\n", "總覽板"),
    ):
        folder = progress_folder(tmp_path / name)
        put(folder, "index.md", text)
        page = overview_page(folder)
        assert page.find("h2", within=page.section("總覽板")).text() == title, name
        assert page.find_all("section", cls="board-section") == [], name


def test_board_shows_its_update_time_and_may_be_stale(tmp_path: Path) -> None:
    # 只看已結束的紀錄：進行中的紀錄比總覽板新不算。
    for name, finished_at, stale in (("newer", NOW, True), ("older", NOW - 600, False)):
        folder = progress_folder(tmp_path / name)
        put(folder, "index.md", BOARD, NOW - 300)
        put(folder, "done.md", build_record(stem="done", state="已結束"), finished_at)
        put(folder, "live.md", build_record(stem="live"), NOW + 600)
        page = overview_page(folder)
        board = page.section("總覽板")
        stamp = page.find("span", cls="age-stamp", within=board)
        assert stamp.attrs["data-epoch"] == str(NOW - 300), name
        assert stamp.attrs["data-stale-mode"] == "off", name
        assert f"最後更新：{clock(NOW - 300)}" in stamp.text(), name
        assert bool(page.find_all(cls="board-stale", within=board)) is stale, name
        assert ("總覽板可能過期" in board.text()) is stale, name


def test_unreadable_board_is_reported(tmp_path: Path) -> None:
    folder = progress_folder(tmp_path)
    (folder / "index.md").write_bytes(b"# \xff\xfe\n")
    put(folder, "alpha.md", build_record(stem="alpha"))
    code, stdout, stderr = run_main([str(folder)])
    page = Page((folder / "index.html").read_text(encoding="utf-8"))
    assert code == 1
    assert "index.md" in stderr
    assert "index.md" in page.find("div", cls="warnings").text()
    assert page.find_all("section", attrs={"data-section": "總覽板"}) == []
    assert str(folder / "alpha.html") in stdout.splitlines()


def test_summary_lists_every_pending_decision_with_a_link(tmp_path: Path) -> None:
    folder = progress_folder(tmp_path)
    records = {
        "alpha": ("進行中", "1. 第一件？\n   - 甲：子項目\n   - 乙：子項目\n3. 第三件？"),
        "beta": ("已結束", "1. 收尾清理清單：要刪哪些？"),
        "gamma": ("進行中", "目前沒有。"),
        "delta": ("已結束", "目前沒有。（你已回覆）"),
        "Bad_Name": ("進行中", "- 要不要改名？"),
    }
    for offset, (stem, (state, decisions)) in enumerate(records.items()):
        record = build_record(
            title=f"任務 {stem}", stem=stem, state=state, sections={"需要你決定的事": decisions}
        )
        put(folder, f"{stem}.md", record, NOW - 100 * (offset + 1))
    page = overview_page(folder)
    section = page.section("要你決定")
    assert "pending" in section.classes()
    assert section.attrs["data-count"] == "4"
    assert page.find("h2", within=section).text() == "要你決定（4 項）"
    items = page.find_all("li", cls="decision-item", within=section)
    shown = [
        (item.attrs["data-record"], item.text(), hrefs(page, item)) for item in items
    ]
    assert shown == [
        ("alpha", "任務 alpha：1. 第一件？", ["alpha.html"]),
        ("alpha", "任務 alpha：3. 第三件？", ["alpha.html"]),
        ("beta", "任務 beta已結束：1. 收尾清理清單：要刪哪些？", ["beta.html"]),
        # 不是編號項目照樣列出，另標要修（ADR-046 D8）。
        ("Bad_Name", "任務 Bad_Name：要不要改名？⚠ 格式待修，可能是待決", []),
    ]
    assert "子項目" not in section.text()


def test_summary_without_pending_decisions(tmp_path: Path) -> None:
    folder = progress_folder(tmp_path)
    put(folder, "alpha.md", build_record(stem="alpha"))
    page = overview_page(folder)
    section = page.section("要你決定")
    assert section.attrs["data-count"] == "0"
    assert "pending" not in section.classes()
    assert page.find("h2", within=section).text() == "要你決定"
    assert page.find_all("li", cls="decision-item") == []
    assert "目前沒有" in section.text()


def test_now_next_lists_active_items_and_the_first_todo(tmp_path: Path) -> None:
    folder = progress_folder(tmp_path)
    for offset, (stem, state) in enumerate(
        (("alpha", "進行中"), ("done", "已結束"), ("unknown", None))
    ):
        sections = {"工作清單": NOW_NEXT_TABLE}
        record = build_record(
            title=f"任務 {stem}", stem=stem, state=state, sections=sections
        )
        put(folder, f"{stem}.md", record, NOW - 100 * (offset + 1))
    page = overview_page(folder)
    section = page.section("現在／下一步")
    tasks = page.find_all("li", cls="now-task", within=section)
    assert [task.attrs["data-record"] for task in tasks] == ["alpha"]
    assert hrefs(page, tasks[0]) == ["alpha.html"]
    assert "任務 alpha" in tasks[0].text()
    assert now_next_rows(page, tasks[0]) == EXPECTED_NOW_NEXT


def test_now_next_without_running_items(tmp_path: Path) -> None:
    folder = progress_folder(tmp_path)
    put(folder, "done.md", build_record(stem="done", state="已結束"))
    page = overview_page(folder)
    section = page.section("現在／下一步")
    assert page.find_all("li", cls="now-task") == []
    assert "目前沒有" in section.text()


def test_task_page_shows_its_own_now_and_next_at_the_top(tmp_path: Path) -> None:
    folder = progress_folder(tmp_path)
    sections = {"工作清單": NOW_NEXT_TABLE}
    path = put(folder, "alpha.md", build_record(stem="alpha", sections=sections))
    page = Page(rp.render_file(path).output.read_text(encoding="utf-8"))
    section = page.section("現在／下一步")
    assert now_next_rows(page, section) == EXPECTED_NOW_NEXT
    assert page.find_all("a", within=section) == []
    nodes = [page.find("header"), section, page.section("需要你決定的事")]
    order = [page.nodes.index(node) for node in nodes]
    assert order == sorted(order)
    done = put(
        folder, "done.md", build_record(stem="done", state="已結束", sections=sections)
    )
    done_page = Page(rp.render_file(done).output.read_text(encoding="utf-8"))
    assert done_page.find_all("section", attrs={"data-section": "現在／下一步"}) == []


# ── 總覽板的「其他專案」：只讀對方的任務紀錄 ──────────────────────
# 「其他專案」一律是 tmp_path 裡造的假專案。


def listing_board(*folders: Path | str, extra: str = "") -> str:
    lines = "\n".join(str(folder) for folder in folders)
    return f"# 總覽\n\n## 其他專案\n\n{lines}\n{extra}"


def pending_record(stem: str, title: str, decision: str) -> str:
    return build_record(
        stem=stem, title=title, sections={"需要你決定的事": f"1. {decision}"}
    )


def summary_rows(page: Page) -> list[tuple[str, str, list[str]]]:
    """要你決定的每一項：（專案, 文字, 連結）；本專案的專案欄是空字串。"""
    return [
        (item.attrs.get("data-project", ""), item.text(), hrefs(page, item))
        for item in page.find_all("li", cls="decision-item")
    ]


def snapshot(folder: Path) -> dict[str, tuple[bytes, int]]:
    return {
        str(path.relative_to(folder)): (
            path.read_bytes() if path.is_file() else b"",
            path.stat().st_mtime_ns,
        )
        for path in sorted(folder.rglob("*"))
    }


def test_other_project_joins_the_summary_read_only(tmp_path: Path) -> None:
    home = progress_folder(tmp_path / "home")
    far = progress_folder(tmp_path / "far")
    put(home, "near.md", pending_record("near", "本專案任務", "本專案的事？"))
    put(home, "index.md", listing_board(far))
    hostile = '<script>alert("t")</script>'
    decision = "對方 <b>要決定</b>？"
    put(far, "far.md", pending_record("far", f"對方 {hostile}", decision))
    put(far, "far.html", "對方自己的網頁")
    put(far, "quiet.md", pending_record("quiet", "沒有網頁", "沒有網頁也要列"))
    (far / "broken.md").write_bytes(b"# \xff\xfe\n")
    put(far, "index.md", "# 對方總覽\n\n1. 對方總覽板裡的字\n")
    put(progress_folder(far / "sub"), "deep.md", pending_record("deep", "深層", "深層"))
    before = snapshot(tmp_path / "far")
    code, _, stderr = run_main([str(home)])
    page = Page((home / "index.html").read_text(encoding="utf-8"))
    assert snapshot(tmp_path / "far") == before
    assert code == 0
    assert summary_rows(page) == [
        ("", "本專案任務：1. 本專案的事？", ["near.html"]),
        ("far", f"far對方 {hostile}：1. {decision}", [(far / "far.html").as_uri()]),
        ("far", "far沒有網頁：1. 沒有網頁也要列", []),
    ]
    tasks = page.find_all("li", cls="now-task")
    projects = [task.attrs.get("data-project", "") for task in tasks]
    assert projects == ["", "far", "far"]
    assert page.source.count("<script") == 2
    assert page.find_all("b") == []
    assert "深層" not in page.text()
    assert "對方總覽板裡的字" not in page.text()
    assert "broken.md" in page.find("div", cls="warnings").text()
    assert "broken.md" in stderr


def test_other_project_paths_must_be_absolute_toukadev_progress(tmp_path: Path) -> None:
    home = progress_folder(tmp_path / "home")
    relative = progress_folder(tmp_path / "rel")
    wrong = tmp_path / "wrong" / "notes" / "progress"
    wrong.mkdir(parents=True)
    ghost = tmp_path / "ghost" / ".toukadev" / "progress"
    for folder in (relative, wrong):
        put(folder, "far.md", pending_record("far", "不該出現", "不該出現"))
    put(home, "index.md", listing_board("rel/.toukadev/progress", wrong, ghost))
    with contextlib.chdir(tmp_path):
        result = rp.render_folder(home)
    page = Page((home / "index.html").read_text(encoding="utf-8"))
    assert summary_rows(page) == []
    assert "不該出現" not in page.text()
    reasons = ("絕對路徑", ".toukadev/progress", "讀不到")
    assert len(result.skipped) == len(reasons)
    for message, reason in zip(result.skipped, reasons):
        assert reason in message, message


def test_projects_listing_each_other_show_each_task_once(tmp_path: Path) -> None:
    first = progress_folder(tmp_path / "first")
    second = progress_folder(tmp_path / "second")
    put(first, "a.md", pending_record("a", "甲任務", "甲要決定？"))
    put(second, "b.md", pending_record("b", "乙任務", "乙要決定？"))
    # 列兩次、也列自己：同一個資料夾只讀一次；對方總覽板裡寫的東西不讀。
    put(first, "index.md", listing_board(second, second, first))
    extra = "\n## 需要你決定的事\n\n1. 乙總覽板裡的待決？\n"
    put(second, "index.md", listing_board(first, extra=extra))
    expected = {
        first: ["甲任務：1. 甲要決定？", "second乙任務：1. 乙要決定？"],
        second: ["乙任務：1. 乙要決定？", "first甲任務：1. 甲要決定？"],
    }
    for folder, texts in expected.items():
        result = rp.render_folder(folder)
        page = Page((folder / "index.html").read_text(encoding="utf-8"))
        assert [text for _, text, _ in summary_rows(page)] == texts
        assert len(page.find_all("li", cls="now-task")) == 2
        assert len(result.skipped) == (2 if folder == first else 0), result.skipped


def assert_only_link_is_skipped(tmp_path: Path, *names: str) -> None:
    """home 的總覽板列出 far；far 裡只有連結，全部略過並說原因，沒有任何項目。"""
    home = progress_folder(tmp_path / "home")
    folders = [tmp_path / name / ".toukadev" / "progress" for name in names]
    put(home, "index.md", listing_board(*folders))
    result = rp.render_folder(home)
    page = Page((home / "index.html").read_text(encoding="utf-8"))
    assert summary_rows(page) == []
    assert "不該出現" not in page.text()
    assert len(result.skipped) == len(names)
    assert all("連結" in message for message in result.skipped), result.skipped


def test_linked_other_project_folders_are_skipped(tmp_path: Path) -> None:
    """progress 本身或上一層 .toukadev 是連結：Windows 用 junction，其他平台用 symlink。"""
    real = progress_folder(tmp_path / "real")
    put(real, "far.md", pending_record("far", "不該出現", "不該出現"))
    j1, j2 = tmp_path / "j1" / ".toukadev", tmp_path / "j2"
    j1.mkdir(parents=True)
    j2.mkdir()
    for link, target in ((j1 / "progress", real), (j2 / ".toukadev", real.parent)):
        if IS_WINDOWS:
            make_junction(link, target)
        else:
            os.symlink(target, link, target_is_directory=True)
    assert_only_link_is_skipped(tmp_path, "j1", "j2")


def test_reparse_point_record_in_other_project_is_skipped(tmp_path: Path) -> None:
    far = progress_folder(tmp_path / "far")
    put(far, "reparse.md", pending_record("reparse", "不該出現", "不該出現"))
    real_lstat = os.lstat

    def fake_lstat(path: object, *args: object, **kwargs: object) -> object:
        info = real_lstat(path, *args, **kwargs)
        if Path(str(path)).name != "reparse.md":
            return info
        reparse = stat.FILE_ATTRIBUTE_REPARSE_POINT
        return SimpleNamespace(st_mode=info.st_mode, st_file_attributes=reparse)

    with patch.object(rp.os, "lstat", fake_lstat):
        assert_only_link_is_skipped(tmp_path, "far")


def test_symlinked_record_in_other_project_is_skipped(tmp_path: Path) -> None:
    far = progress_folder(tmp_path / "far")
    outside = put(tmp_path, "outside.md", pending_record("x", "不該出現", "不該出現"))
    make_symlink_or_skip(far / "linked.md", outside)
    assert_only_link_is_skipped(tmp_path, "far")


def temp_table(*items: tuple[str, str]) -> str:
    """暫存項目表：每項只給（狀態, 備註），其他欄位用固定值。"""
    rows = [
        f"| 項目 {number} | 其他 | — | 主代理 | {status} | {note} |"
        for number, (status, note) in enumerate(items, start=1)
    ]
    return "\n".join([*TEMP_TABLE.splitlines()[:2], *rows])


class TempSummaryTests(TestCase):
    def summary(self, state: str | None, *items: tuple[str, str]) -> Node:
        sections = {"暫存項目": temp_table(*items)}
        with RepoSandbox() as sandbox:
            page = sandbox.render(build_record(state=state, sections=sections))
        return page.find("p", cls="temp-summary")

    def test_open_temp_count_is_prominent(self) -> None:
        temp = TEMP_TABLE + (
            "\n| 留著的分支 | 本機分支 | wt/demo-x | 主代理 | 保留 | 等 PR |"
            "\n| 沒寫狀態 | 其他 | — | 主代理 |"
        )
        with RepoSandbox() as sandbox:
            page = sandbox.render(build_record(sections={"暫存項目": temp}))
        summary = page.find("p", cls="temp-summary")
        self.assertIn("open", summary.classes())
        self.assertEqual(summary.attrs["data-open"], "3")
        self.assertEqual(summary.text(), "未清理 3 項")
        cleaned = page.find("tr", cls="temp-row", attrs={"data-status": "已清理"})
        self.assertIn(
            "t-cleaned", page.find("span", cls="chip", within=cleaned).classes()
        )

    def test_all_cleaned_and_empty_tables_are_calm(self) -> None:
        cases = {
            TEMP_TABLE.replace("| 使用中 |", "| 已清理 |"): "全部已清理。",
            "\n".join(TEMP_TABLE.splitlines()[:2]): "還沒有登記任何暫存項目。",
        }
        for table, expected in cases.items():
            with self.subTest(expected=expected), RepoSandbox() as sandbox:
                page = sandbox.render(build_record(sections={"暫存項目": table}))
                summary = page.find("p", cls="temp-summary")
                self.assertNotIn("open", summary.classes())
                self.assertEqual(summary.attrs["data-open"], "0")
                self.assertEqual(summary.text(), expected)

    # 收尾規則：任務結束時，有寫理由的「保留」和「已清理」一樣算收好，另列件數。
    def test_finished_task_kept_with_reason_is_not_open(self) -> None:
        summary = self.summary(
            "已結束",
            ("已清理", "—"),
            ("保留", "PR 還沒合併"),
            ("保留", "收尾時問你"),
        )
        self.assertNotIn("open", summary.classes())
        self.assertEqual(summary.attrs["data-open"], "0")
        self.assertEqual(summary.attrs.get("data-kept"), "2")
        self.assertEqual(summary.text(), "沒有未清理的項目；保留 2 項（有寫理由）。")

    def test_finished_task_kept_without_reason_stays_open(self) -> None:
        for note in ("", "—", "-", "－"):
            with self.subTest(note=note):
                summary = self.summary("已結束", ("保留", note))
                self.assertIn("open", summary.classes())
                self.assertEqual(summary.attrs["data-open"], "1")
                self.assertEqual(summary.attrs.get("data-kept"), "0")
                self.assertEqual(summary.text(), "未清理 1 項")

    def test_running_or_unknown_task_kept_with_reason_stays_open(self) -> None:
        for state in ("進行中", None, "暫停"):
            with self.subTest(state=state):
                summary = self.summary(state, ("保留", "PR 還沒合併"))
                self.assertIn("open", summary.classes())
                self.assertEqual(summary.attrs["data-open"], "1")
                self.assertEqual(summary.attrs.get("data-kept"), "0")
                self.assertEqual(summary.text(), "未清理 1 項")

    def test_unknown_temp_status_stays_open_in_finished_task(self) -> None:
        for status in ("不知道", ""):
            with self.subTest(status=status):
                summary = self.summary("已結束", (status, "PR 還沒合併"))
                self.assertIn("open", summary.classes())
                self.assertEqual(summary.attrs["data-open"], "1")
                self.assertEqual(summary.attrs.get("data-kept"), "0")

    def test_finished_task_mixed_text(self) -> None:
        summary = self.summary("已結束", ("使用中", "—"), ("保留", "PR 還沒合併"))
        self.assertIn("open", summary.classes())
        self.assertEqual(summary.attrs["data-open"], "1")
        self.assertEqual(summary.attrs.get("data-kept"), "1")
        self.assertEqual(summary.text(), "未清理 1 項；另保留 1 項（有寫理由）")

    def test_overview_open_and_kept_by_task_state(self) -> None:
        records = {
            "done-kept": ("已結束", "PR 還沒合併"),
            "done-blank": ("已結束", "—"),
            "running-kept": ("進行中", "PR 還沒合併"),
        }
        with RepoSandbox() as sandbox:
            for stem, (state, note) in records.items():
                sections = {"暫存項目": temp_table(("保留", note))}
                record = build_record(stem=stem, state=state, sections=sections)
                sandbox.write_record(stem, record)
            rp.render_folder(sandbox.progress)
            index = Page((sandbox.progress / "index.html").read_text("utf-8"))
        cells = {
            row.attrs["data-record"]: index.find("td", cls="temp", within=row)
            for row in index.find_all("tr", cls="overview-row")
        }
        # （data-open, data-kept, 醒目, 格子文字）；數字只算未清理，保留另用小字。
        expected = {
            "done-kept": ("0", "1", False, "0 項另保留 1 項"),
            "done-blank": ("1", "0", True, "1 項"),
            "running-kept": ("1", "0", True, "1 項"),
        }
        for stem, (open_count, kept, prominent, text) in expected.items():
            with self.subTest(stem=stem):
                cell = cells[stem]
                self.assertEqual(cell.attrs["data-open"], open_count)
                self.assertEqual(cell.attrs.get("data-kept"), kept)
                self.assertEqual("open" in cell.classes(), prominent)
                self.assertEqual(cell.text(), text)
        self.assertIn("未清暫存", [header.text() for header in index.find_all("th")])

    def test_finished_hold_waiting_for_you_stays_open(self) -> None:
        summary = self.summary(
            "已結束",
            ("保留", "等你決定：要不要刪"),
            ("保留", "PR 還沒合併"),
            ("保留", "待你決定：打錯字"),
        )
        self.assertIn("open", summary.classes())
        self.assertEqual(summary.attrs["data-open"], "1")
        self.assertEqual(summary.attrs.get("data-kept"), "2")
        self.assertEqual(summary.text(), "未清理 1 項；另保留 2 項（有寫理由）")


KEPT = rp.StatusView("保留", "保留", "none")


def test_waiting_note_ignores_surrounding_spaces() -> None:
    cases = (
        ("  等你決定：要不要刪", True),
        ("　等你決定", True),
        ("等你決定", True),
        ("待你決定：打錯字", False),
        ("說明：等你決定", False),
        ("", False),
    )
    for note, waiting in cases:
        assert rp.waits_for_you(KEPT, {"備註": note}) is waiting, note
    active = rp.StatusView("使用中", "使用中", "none")
    assert rp.waits_for_you(active, {"備註": "等你決定"}) is False
    assert rp.temp_kind(KEPT, {"備註": "  等你決定：要不要刪"}, True) == rp.TEMP_OPEN
    assert rp.temp_kind(KEPT, {"備註": "  PR 還沒合併"}, True) == rp.TEMP_KEPT


class WaitingHoldCrossCheckTests(TestCase):
    """已結束的紀錄有等你決定的保留，「需要你決定的事」卻沒有項目時，給格式警告。"""

    def render(self, state: str, decisions: str, *items: tuple[str, str]) -> Page:
        sections = {"暫存項目": temp_table(*items), "需要你決定的事": decisions}
        with RepoSandbox() as sandbox:
            return sandbox.render(build_record(state=state, sections=sections))

    def test_nothing_pending_or_no_items_warns(self) -> None:
        for decisions in ("目前沒有。", ""):
            with self.subTest(decisions=decisions):
                page = self.render("已結束", decisions, ("保留", "等你決定：要不要刪"))
                (warning,) = page.warnings()
                self.assertIn("暫存項目第 1 列", warning)
                self.assertIn("等你決定", warning)
                self.assertIn("需要你決定的事", warning)

    def test_pending_decision_or_running_task_does_not_warn(self) -> None:
        cases = (
            ("已結束", "1. 收尾清理清單：要刪哪些？"),
            ("進行中", "目前沒有。"),
        )
        for state, decisions in cases:
            with self.subTest(state=state):
                page = self.render(state, decisions, ("保留", "等你決定：要不要刪"))
                self.assertEqual(page.warnings(), [])

    def test_typo_does_not_count_and_does_not_hide_a_real_hold(self) -> None:
        typo = self.render("已結束", "目前沒有。", ("保留", "待你決定：打錯字"))
        self.assertEqual(typo.warnings(), [])
        mixed = self.render(
            "已結束", "目前沒有。", ("保留", "待你決定：打錯字"), ("保留", "等你決定：要不要刪")
        )
        (warning,) = mixed.warnings()
        self.assertIn("暫存項目第 2 列", warning)

    def test_overview_counts_the_cross_check_warning(self) -> None:
        sections = {"暫存項目": temp_table(("保留", "等你決定：要不要刪"))}
        with RepoSandbox() as sandbox:
            sandbox.write_record("demo", build_record(state="已結束", sections=sections))
            code, _, stderr = run_main([str(sandbox.progress)])
            index = Page((sandbox.progress / "index.html").read_text("utf-8"))
        self.assertEqual(code, 0)
        self.assertIn("格式警告 1 項", stderr)
        self.assertEqual(index.find("span", cls="badge-unknown").text(), "⚠ 格式警告 1")


# ── 原子寫入與指令列 ─────────────────────────────────────────────


class AtomicWriteTests(TestCase):
    def assert_old_page_survives(self, failing_target: str) -> None:
        with RepoSandbox() as sandbox:
            path = sandbox.write_record("demo", build_record())
            page = path.with_suffix(".html")
            old_page = rp.GENERATOR_MARKER + "OLD PAGE"
            page.write_text(old_page, encoding="utf-8")
            with patch.object(rp.os, failing_target, side_effect=OSError("磁碟已滿")):
                with self.assertRaises(rp.RenderError):
                    rp.render_file(path)
            self.assertEqual(page.read_text(encoding="utf-8"), old_page)
            self.assertEqual(
                sorted(item.name for item in sandbox.progress.iterdir()),
                ["demo.html", "demo.md"],
            )

    def test_failed_replace_keeps_old_page(self) -> None:
        self.assert_old_page_survives("replace")

    def test_failed_flush_keeps_old_page(self) -> None:
        self.assert_old_page_survives("fsync")

    def test_written_page_is_utf8_with_lf(self) -> None:
        with RepoSandbox() as sandbox:
            path = sandbox.write_record("demo", build_record())
            output = rp.render_file(path).output
            data = output.read_bytes()
        self.assertNotIn(b"\r\n", data)
        self.assertTrue(data.decode("utf-8").startswith("<!doctype html>"))


class CommandLineTests(TestCase):
    def test_file_mode_prints_page_and_index_paths(self) -> None:
        with RepoSandbox() as sandbox:
            path = sandbox.write_record("demo", build_record())
            code, stdout, stderr = run_main([str(path)])
            self.assertTrue(path.with_suffix(".html").is_file())
            self.assertTrue((sandbox.progress / "index.html").is_file())
        self.assertEqual(code, 0)
        self.assertEqual(
            stdout.splitlines(),
            [str(path.with_suffix(".html")), str(sandbox.progress / "index.html")],
        )
        self.assertEqual(stderr, "")

    def test_folder_mode_prints_every_output(self) -> None:
        with RepoSandbox() as sandbox:
            sandbox.write_record("alpha", build_record(stem="alpha"))
            sandbox.write_record("beta", build_record(stem="beta"))
            code, stdout, _ = run_main([str(sandbox.progress)])
            expected = {
                str(sandbox.progress / name)
                for name in ("alpha.html", "beta.html", "index.html")
            }
        self.assertEqual(code, 0)
        self.assertEqual(set(stdout.splitlines()), expected)

    def test_format_warnings_are_reported_without_failing(self) -> None:
        with RepoSandbox() as sandbox:
            path = sandbox.write_record(
                "demo", build_record(sections={"審核紀錄": None})
            )
            code, _, stderr = run_main([str(path)])
        self.assertEqual(code, 0)
        self.assertIn("格式警告", stderr)

    def test_missing_path_fails(self) -> None:
        with RepoSandbox() as sandbox:
            code, stdout, stderr = run_main([str(sandbox.progress / "nope.md")])
        self.assertNotEqual(code, 0)
        self.assertEqual(stdout, "")
        self.assertIn("nope.md", stderr)

    def test_non_markdown_file_fails(self) -> None:
        with RepoSandbox() as sandbox:
            path = sandbox.progress / "notes.txt"
            path.write_text("x", encoding="utf-8")
            code, _, stderr = run_main([str(path)])
        self.assertNotEqual(code, 0)
        self.assertIn("notes.txt", stderr)

    def test_unreadable_record_fails_with_reason(self) -> None:
        with RepoSandbox() as sandbox:
            path = sandbox.progress / "broken.md"
            path.write_bytes(b"# \xff\xfe broken\n")
            code, _, stderr = run_main([str(path)])
            self.assertFalse(path.with_suffix(".html").exists())
        self.assertEqual(code, 1)
        self.assertIn("broken.md", stderr)

    def test_unreadable_record_in_folder_fails_but_others_render(self) -> None:
        with RepoSandbox() as sandbox:
            (sandbox.progress / "broken.md").write_bytes(b"# \xff\xfe broken\n")
            sandbox.write_record("alpha", build_record(stem="alpha"))
            code, stdout, stderr = run_main([str(sandbox.progress)])
            index = Page((sandbox.progress / "index.html").read_text(encoding="utf-8"))
            self.assertTrue((sandbox.progress / "alpha.html").is_file())
        self.assertEqual(code, 1)
        self.assertIn("broken.md", stderr)
        self.assertIn("broken.md", index.text())
        self.assertIn("alpha.html", stdout)

    def test_write_failure_fails_with_reason(self) -> None:
        with RepoSandbox() as sandbox:
            path = sandbox.write_record("demo", build_record())
            with patch.object(rp.os, "replace", side_effect=OSError("磁碟已滿")):
                code, stdout, stderr = run_main([str(path)])
        self.assertEqual(code, 1)
        self.assertEqual(stdout, "")
        self.assertIn("磁碟已滿", stderr)

    def test_unencodable_output_does_not_crash(self) -> None:
        # Windows 的 cp950 主控台印不出 emoji；configure_streams 讓它改用跳脫字元，不當機。
        with RepoSandbox() as sandbox:
            path = sandbox.write_record("demo-😀", build_record())
            script = subprocess.run(
                [sys.executable, str(MODULE_PATH), str(path)],
                capture_output=True,
                check=False,
                env={**os.environ, "PYTHONIOENCODING": "cp950"},
            )
            self.assertTrue(path.with_suffix(".html").is_file())
        self.assertEqual(script.returncode, 0, script.stderr.decode("cp950", "replace"))
        self.assertNotIn(b"Traceback", script.stderr)
        self.assertIn("demo-", script.stdout.decode("cp950"))

    def test_old_python_gets_a_friendly_message(self) -> None:
        self.assertIn("3.12", rp.unsupported_python_message((3, 10, 2)))
        self.assertIn("3.10", rp.unsupported_python_message((3, 10, 2)))
        self.assertIsNone(rp.unsupported_python_message((3, 12, 0)))
        self.assertIsNone(rp.unsupported_python_message((3, 14, 0)))
        with RepoSandbox() as sandbox:
            path = sandbox.write_record("demo", build_record())
            with patch.object(rp.sys, "version_info", (3, 10, 2)):
                code, stdout, stderr = run_main([str(path)])
            self.assertFalse(path.with_suffix(".html").exists())
        self.assertEqual(code, 2)
        self.assertEqual(stdout, "")
        self.assertIn("3.12", stderr)


# ── 只寫進度資料夾、不覆寫別人的檔案 ─────────────────────────────


class LocationAndOwnershipTests(TestCase):
    def test_pages_carry_generator_marker(self) -> None:
        with RepoSandbox() as sandbox:
            page = sandbox.render(build_record())
            index = (sandbox.progress / "index.html").read_text(encoding="utf-8")
        marker = page.find("meta", attrs={"name": "generator"})
        self.assertEqual(marker.attrs["content"], "toukadev-progress")
        self.assertEqual(rp.GENERATOR_MARKER.count('"'), 4)
        self.assertLess(page.source.index(rp.GENERATOR_MARKER), 512)
        self.assertIn(rp.GENERATOR_MARKER, index[:512])

    def test_paths_outside_toukadev_progress_are_refused(self) -> None:
        with RepoSandbox() as sandbox:
            places = {
                "docs": sandbox.root / "docs",
                "root": sandbox.root,
                "data": sandbox.root / "data",
                "tmp": sandbox.root / ".toukadev" / "tmp" / "demo",
                "other-progress": sandbox.root / "notes" / "progress",
            }
            for name, folder in places.items():
                folder.mkdir(parents=True, exist_ok=True)
                record = folder / "guide.md"
                record.write_text(build_record(stem="guide"), encoding="utf-8")
                human_page = folder / "guide.html"
                human_page.write_text("HUMAN PAGE", encoding="utf-8")
                for target in (folder, record):
                    with self.subTest(place=name, target=target.name):
                        code, stdout, stderr = run_main([str(target)])
                        self.assertEqual(code, 2)
                        self.assertEqual(stdout, "")
                        self.assertIn(".toukadev/progress", stderr)
                        self.assertEqual(human_page.read_text("utf-8"), "HUMAN PAGE")
                        self.assertFalse((folder / "index.html").exists())
                with self.assertRaises(rp.LocationError):
                    rp.render_folder(folder)
                with self.assertRaises(rp.LocationError):
                    rp.render_file(record)

    def test_page_without_marker_is_not_overwritten(self) -> None:
        with RepoSandbox() as sandbox:
            path = sandbox.write_record("demo", build_record())
            human_page = path.with_suffix(".html")
            human_page.write_text("<html>人類自己寫的</html>", encoding="utf-8")
            code, stdout, stderr = run_main([str(path)])
            self.assertEqual(
                human_page.read_text(encoding="utf-8"), "<html>人類自己寫的</html>"
            )
        self.assertEqual(code, 1)
        self.assertEqual(stdout, "")
        self.assertIn("demo.html", stderr)
        self.assertIn("產生器標記", stderr)

    def test_index_without_marker_is_not_overwritten(self) -> None:
        with RepoSandbox() as sandbox:
            sandbox.write_record("alpha", build_record(stem="alpha"))
            human_index = sandbox.progress / "index.html"
            human_index.write_text("HUMAN INDEX", encoding="utf-8")
            code, stdout, stderr = run_main([str(sandbox.progress)])
            self.assertEqual(human_index.read_text(encoding="utf-8"), "HUMAN INDEX")
            self.assertTrue((sandbox.progress / "alpha.html").is_file())
        self.assertEqual(code, 1)
        self.assertIn(str(sandbox.progress / "alpha.html"), stdout.splitlines())
        self.assertIn("index.html", stderr)

    def test_folder_named_like_the_page_is_not_replaced(self) -> None:
        with RepoSandbox() as sandbox:
            path = sandbox.write_record("demo", build_record())
            folder = path.with_suffix(".html")
            folder.mkdir()
            (folder / "keep.txt").write_text(rp.GENERATOR_MARKER, encoding="utf-8")
            code, stdout, stderr = run_main([str(path)])
            self.assertTrue((folder / "keep.txt").is_file())
        self.assertEqual(code, 1)
        self.assertEqual(stdout, "")
        self.assertIn("不是一般檔案", stderr)

    def test_linked_page_is_not_followed(self) -> None:
        with RepoSandbox() as sandbox:
            path = sandbox.write_record("demo", build_record())
            outside = sandbox.base / "outside.html"
            outside.write_text(rp.GENERATOR_MARKER + "OUTSIDE", encoding="utf-8")
            make_symlink_or_skip(path.with_suffix(".html"), outside)
            code, _, stderr = run_main([str(path)])
            self.assertEqual(
                outside.read_text(encoding="utf-8"), rp.GENERATOR_MARKER + "OUTSIDE"
            )
        self.assertEqual(code, 1)
        self.assertIn("不是一般檔案", stderr)

    @skipUnless(IS_WINDOWS, JUNCTION_SKIP_REASON)
    def test_junction_named_like_the_page_is_not_followed(self) -> None:
        with RepoSandbox() as sandbox:
            path = sandbox.write_record("demo", build_record())
            outside = sandbox.base / "outside"
            outside.mkdir()
            make_junction(path.with_suffix(".html"), outside)
            code, _, stderr = run_main([str(path)])
            self.assertEqual(list(outside.iterdir()), [])
        self.assertEqual(code, 1)
        self.assertIn("不是一般檔案", stderr)

    def test_reparse_point_attribute_counts_as_link(self) -> None:
        reparse = stat.FILE_ATTRIBUTE_REPARSE_POINT
        self.assertTrue(
            rp.is_link_stat(
                SimpleNamespace(st_mode=stat.S_IFDIR, st_file_attributes=reparse)
            )
        )
        self.assertFalse(
            rp.is_link_stat(SimpleNamespace(st_mode=stat.S_IFDIR, st_file_attributes=0))
        )
        self.assertTrue(rp.is_link_stat(SimpleNamespace(st_mode=stat.S_IFLNK)))
        self.assertFalse(rp.is_link_stat(SimpleNamespace(st_mode=stat.S_IFREG)))

    def test_own_page_can_be_rewritten(self) -> None:
        with RepoSandbox() as sandbox:
            path = sandbox.write_record("demo", build_record())
            rp.render_file(path)
            sandbox.write_record("demo", build_record(state="已結束"))
            code, _, stderr = run_main([str(path)])
            page = Page(path.with_suffix(".html").read_text(encoding="utf-8"))
        self.assertEqual(code, 0, stderr)
        self.assertIn("已結束", page.find("header").text())


# ── 太長與格式（ADR-046 D8）：非編號待決、長格子、舊審核紀錄收合、總覽件數 ──

DELIVERY_DOC = ROOT / "dev-workflow" / "references" / "delivery.md"
UNNUMBERED_WARNING = (
    "「需要你決定的事」有 {count} 項不是編號項目：只放編號項目，回覆過的整項移走；"
    "總覽照樣列成可能待決。"
)


def long_cell_warning(table: str, numbers: str) -> str:
    return (
        f"{table}第 {numbers} 列有格子超過約 200 字（人類原話不算）："
        "每列寫一兩句，細節放 PR 說明或 ADR。"
    )


def review_rows(count: int, note: str = "—") -> str:
    rows = [
        f"| 10/11 {9 + number // 60:02d}:{number % 60:02d} | 關卡 {number} | 對象 | 主代理 "
        f"| reviewer | 通過 | {note} |"
        for number in range(1, count + 1)
    ]
    return "\n".join([*REVIEW_TABLE.splitlines()[:2], *rows])


def review_note_warnings(note: str, state: str | None = "進行中") -> list[str]:
    with RepoSandbox() as sandbox:
        record = build_record(state=state, sections={"審核紀錄": review_rows(1, note)})
        return sandbox.render(record).warnings()


class UnnumberedDecisionTests(TestCase):
    """「需要你決定的事」只放編號項目；其他寫法照樣算待決，並標出來要修。"""

    def test_paragraphs_and_plain_bullets_are_flagged_and_still_counted(self) -> None:
        cases = {
            "請決定要不要加 X。": 1,
            "- 要不要加 X？\n- 要不要加 Y？": 2,
            "1. 要不要加 X？\n\n補充：這也要你看。": 1,
        }
        for body, flagged in cases.items():
            with self.subTest(body=body), RepoSandbox() as sandbox:
                page = sandbox.render(build_record(sections={"需要你決定的事": body}))
                self.assertIn(UNNUMBERED_WARNING.format(count=flagged), page.warnings())
                index = Page((sandbox.progress / "index.html").read_text("utf-8"))
                flags = index.find_all("span", cls="decision-flag")
                self.assertEqual(len(flags), flagged)
                for flag in flags:
                    self.assertEqual(flag.text(), "⚠ 格式待修，可能是待決")

    def test_numbered_items_and_nothing_pending_are_not_flagged(self) -> None:
        for body in ("1. 要不要加 X？\n   - 甲\n   - 乙", "目前沒有。", "- 目前沒有。"):
            with self.subTest(body=body), RepoSandbox() as sandbox:
                page = sandbox.render(build_record(sections={"需要你決定的事": body}))
                self.assertEqual(page.warnings(), [])
                index = Page((sandbox.progress / "index.html").read_text("utf-8"))
                self.assertEqual(index.find_all("span", cls="decision-flag"), [])


class DuplicateSectionTests(TestCase):
    """必要區段寫了兩次：要警告；第二段「需要你決定的事」的待決照樣算（寧可多算）。"""

    def test_second_decision_section_still_counts(self) -> None:
        record = build_record(extra="## 需要你決定的事\n\n1. 第二段裡的事？")
        with RepoSandbox() as sandbox:
            page = sandbox.render(record)
            index = Page((sandbox.progress / "index.html").read_text("utf-8"))
        (section,) = page.find_all("section", attrs={"data-section": "需要你決定的事"})
        self.assertEqual(section.attrs["data-count"], "1")
        self.assertIn("第二段裡的事？", section.text())
        self.assertIn(
            "「需要你決定的事」寫了不只一段：合併成一段顯示，每段的待決都照算；請合併成一段。",
            page.warnings(),
        )
        items = [item.text() for item in index.find_all("li", cls="decision-item")]
        self.assertEqual(items, ["測試任務：1. 第二段裡的事？"])

    def test_each_repeated_part_starts_at_the_top_level(self) -> None:
        # 第二段開頭縮排或是一般段落，都不能被當成上一段最後一項的子項目或接續行。
        cases = {
            "  - 要不要 Y？": ["測試任務：1. A？", "測試任務：要不要 Y？⚠ 格式待修，可能是待決"],
            "\t\t- 要不要 Y？": ["測試任務：1. A？", "測試任務：要不要 Y？⚠ 格式待修，可能是待決"],
            "　　- 要不要 Y？": ["測試任務：1. A？", "測試任務：要不要 Y？⚠ 格式待修，可能是待決"],
            "請決定 Z。": ["測試任務：1. A？", "測試任務：請決定 Z。⚠ 格式待修，可能是待決"],
        }
        for second, expected in cases.items():
            record = build_record(
                sections={"需要你決定的事": "1. A？"},
                extra=f"## 需要你決定的事\n\n{second}",
            )
            with self.subTest(second=second), RepoSandbox() as sandbox:
                page = sandbox.render(record)
                index = Page((sandbox.progress / "index.html").read_text("utf-8"))
                section = page.section("需要你決定的事")
                self.assertEqual(section.attrs["data-count"], "2")
                items = [item.text() for item in index.find_all("li", cls="decision-item")]
                self.assertEqual(items, expected)

    def test_parts_without_blank_lines_stay_apart(self) -> None:
        # 兩段之間一個空行都沒有時，後一段的段落也不能變成前一段最後一項的接續行。
        decisions = "1. A？\n## 需要你決定的事\n請決定 C。"
        with RepoSandbox() as sandbox:
            page = sandbox.render(build_record(sections={"需要你決定的事": decisions}))
            index = Page((sandbox.progress / "index.html").read_text("utf-8"))
        self.assertEqual(page.section("需要你決定的事").attrs["data-count"], "2")
        items = [item.text() for item in index.find_all("li", cls="decision-item")]
        self.assertEqual(
            items, ["測試任務：1. A？", "測試任務：請決定 C。⚠ 格式待修，可能是待決"]
        )

    def test_other_repeated_sections_are_shown_and_warned(self) -> None:
        record = build_record(extra="## 工作清單\n\n第二段的內容")
        with RepoSandbox() as sandbox:
            page = sandbox.render(record)
        self.assertIn(
            "「工作清單」寫了不只一段：後面那段照原樣顯示在最下面；請合併成一段。",
            page.warnings(),
        )
        self.assertEqual(
            len(page.find_all("section", attrs={"data-section": "工作清單"})), 2
        )
        self.assertIn("第二段的內容", page.text())


class LongCellTests(TestCase):
    """進行中的紀錄裡，一格超過約 200 字就警告；「原話：「…」」裡的字不算。"""

    def test_threshold_is_200_characters(self) -> None:
        self.assertEqual(rp.LONG_CELL_CHARS, 200)
        self.assertEqual(review_note_warnings("字" * 200), [])
        self.assertEqual(
            review_note_warnings("字" * 201), [long_cell_warning("審核紀錄", "1")]
        )

    def test_every_table_is_checked_and_rows_are_listed_once(self) -> None:
        long_note = "字" * 201
        work = work_table(("A", "執行中", long_note), ("B", "待辦", "—"), ("C", "待辦", long_note))
        temp = TEMP_TABLE + f"\n| 筆記 | 其他 | .toukadev/tmp/demo/x | 主代理 | 使用中 | {long_note} |"
        with RepoSandbox() as sandbox:
            record = build_record(sections={"工作清單": work, "暫存項目": temp})
            warnings = sandbox.render(record).warnings()
        self.assertEqual(
            warnings,
            [long_cell_warning("工作清單", "1、3"), long_cell_warning("暫存項目", "3")],
        )

    def test_human_quotes_do_not_count(self) -> None:
        quote = "原話：「" + "話" * 300 + "」"
        nested = "原話:「先「引一句」" + "話" * 300 + "」"
        self.assertEqual(review_note_warnings(quote + "說明" * 90), [])
        self.assertEqual(review_note_warnings(nested + "說明" * 90), [])
        # 引號外的字照算；沒有「原話」開頭的引號也照算。
        self.assertEqual(
            review_note_warnings(quote + "說明" * 101), [long_cell_warning("審核紀錄", "1")]
        )
        self.assertEqual(
            review_note_warnings("「" + "話" * 201 + "」"), [long_cell_warning("審核紀錄", "1")]
        )
        # 沒收尾的原話一直算到格子結尾：引號後的字都不算，引號前的字照算。
        self.assertEqual(review_note_warnings("原話：「" + "話" * 300), [])
        self.assertEqual(
            review_note_warnings("說明" * 101 + "原話：「" + "話" * 300),
            [long_cell_warning("審核紀錄", "1")],
        )

    def test_only_running_records_are_checked(self) -> None:
        for state in ("已結束", None):
            with self.subTest(state=state):
                self.assertEqual(review_note_warnings("字" * 300, state=state), [])


class OlderReviewRowsTests(TestCase):
    """審核紀錄超過 10 列時，最近 10 列照常顯示，較早的收合；重新整理時保留展開狀態。"""

    def render_reviews(self, count: int) -> Page:
        with RepoSandbox() as sandbox:
            return sandbox.render(build_record(sections={"審核紀錄": review_rows(count)}))

    def test_ten_rows_stay_open(self) -> None:
        self.assertEqual(rp.REVIEW_OPEN_ROWS, 10)
        page = self.render_reviews(10)
        self.assertEqual(page.find_all("details"), [])
        self.assertEqual(len(page.find_all("tr", cls="review-row")), 10)

    def test_older_rows_collapse_in_order(self) -> None:
        page = self.render_reviews(12)
        section = page.section("審核紀錄")
        (older,) = page.find_all("details", cls="older-rows", within=section)
        self.assertNotIn("open", older.attrs)
        self.assertEqual(
            page.find("summary", within=older).text(), "較早的 2 列（按一下展開／收合）"
        )
        def gates(region: Node) -> list[str]:
            return [
                page.find("td", cls="col-關卡", within=row).text()
                for row in page.find_all("tr", cls="review-row", within=region)
            ]

        self.assertEqual(gates(older), ["關卡 1", "關卡 2"])
        # 收合的表格排在最近 10 列前面；整區照紀錄的順序，一列都不少。
        self.assertEqual(gates(section), [f"關卡 {number}" for number in range(1, 13)])
        self.assertLess(page.source.index("<details"), page.source.index(">關卡 3<"))
        self.assertEqual(len(page.find_all("thead", within=section)), 2)

    def test_text_outside_the_table_is_shown_once_after_the_rows(self) -> None:
        reviews = review_rows(12) + "\n\n表格外的說明"
        with RepoSandbox() as sandbox:
            page = sandbox.render(build_record(sections={"審核紀錄": reviews}))
        section = page.section("審核紀錄")
        older = page.find("details", cls="older-rows", within=section)
        self.assertNotIn("表格外的說明", older.text())
        self.assertEqual(section.text().count("表格外的說明"), 1)
        self.assertLess(page.source.index(">關卡 12<"), page.source.index("表格外的說明"))

    def test_open_state_is_kept_per_page_across_reloads(self) -> None:
        script = rp.SCRIPT
        self.assertIn('document.querySelectorAll("details.older-rows")', script)
        # 存的值和讀回來比對的值是同一個；讀到就照著打開，沒讀到就收合。
        self.assertIn(
            "if (event.target.open) {\n"
            '        window.sessionStorage.setItem(olderKey(), "open");',
            script,
        )
        self.assertIn('window.sessionStorage.getItem(olderKey()) === "open";', script)
        self.assertIn("window.sessionStorage.removeItem(olderKey());", script)
        self.assertIn("nodes[index].open = open;", script)
        self.assertIn("return OLDER_KEY + window.location.pathname;", script)
        self.assertIn('addEventListener("toggle", saveOlder)', script)
        statements = [
            line.strip()
            for line in script.splitlines()
            if re.match(r"  [^ }]", line)
            and not line.startswith(("  var ", "  function ", '  "use strict"'))
        ]
        self.assertIn("restoreOlder();", statements)


class FormatWarningSummaryTests(TestCase):
    """總覽最上方列出每個任務的格式警告件數（含其他專案），連到任務頁。"""

    def test_overview_lists_warning_counts(self) -> None:
        with TemporaryDirectory() as raw:
            base = Path(raw).resolve()
            home = progress_folder(base / "home")
            far = progress_folder(base / "far")
            put(home, "index.md", listing_board(far))
            put(home, "clean.md", build_record(stem="clean", title="乾淨"))
            put(
                home,
                "messy.md",
                build_record(
                    stem="messy", title="待修", sections={"需要你決定的事": "請決定 X。"}
                ),
            )
            # 少兩個必要區段：2 項警告。
            missing = {"暫存項目": None, "尚未驗證與已知問題": None}
            put(far, "away.md", build_record(stem="away", title="對方", sections=missing))
            page = overview_page(home)
        section = page.section("格式警告")
        self.assertIn("format-summary", section.classes())
        self.assertEqual(page.find("h2", within=section).text(), "格式警告（3 項）")
        items = [
            (item.attrs["data-record"], item.attrs.get("data-project", ""), item.text())
            for item in page.find_all("li", cls="format-item", within=section)
        ]
        self.assertEqual(
            items,
            [("messy", "", "待修：1 項"), ("away", "far", "far對方：2 項")],
        )
        self.assertEqual(hrefs(page, section), ["messy.html"])

    def test_overview_without_warnings_has_no_summary(self) -> None:
        with TemporaryDirectory() as raw:
            folder = progress_folder(Path(raw))
            put(folder, "clean.md", build_record(stem="clean"))
            page = overview_page(folder)
        self.assertEqual(page.find_all("section", cls="format-summary"), [])


class TrimRulesDocTests(TestCase):
    """正本寫的門檻與程式一樣；步驟 10 與 13 各重產一次網頁。"""

    def test_progress_record_doc_matches_the_new_limits(self) -> None:
        text = PROGRESS_RECORD_DOC.read_text(encoding="utf-8")
        self.assertIn(f"約 {rp.LONG_CELL_CHARS} 字", text)
        self.assertIn(f"最近 {rp.REVIEW_OPEN_ROWS} 列", text)
        self.assertIn(rp.UNNUMBERED_FLAG, text)
        self.assertIn("`.toukadev/progress/archive/`", text)
        self.assertIn("不得為 `index` 或 `archive`", text)

    def test_delivery_steps_10_and_13_rerender_once_each(self) -> None:
        text = DELIVERY_DOC.read_text(encoding="utf-8")
        step10 = text[text.index("## 步驟10") : text.index("## 步驟12")]
        step13 = text[text.index("## 步驟13") :]
        for step in (step10, step13):
            with self.subTest(step=step[:8]):
                self.assertEqual(step.count("重產一次進度網頁"), 1)

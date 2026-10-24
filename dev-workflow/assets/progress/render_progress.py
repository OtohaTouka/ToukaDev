"""把 ToukaDev 的進度紀錄（Markdown）轉成本機網頁。

用法：
    python render_progress.py <進度紀錄.md 或 .toukadev/progress 資料夾>

- 給一份紀錄：在旁邊產生同名 .html，並重產同資料夾的總覽 index.html
  （總覽讀資料夾內全部紀錄，但不重產其他紀錄的 .html）。
- 給總覽板 index.md：只重產總覽 index.html。
- 給資料夾：每份紀錄各產生一個 .html，另外產生總覽 index.html。
- 總覽最上面是自動彙總（要你決定、現在／下一步），下面接總覽板 index.md 的內容。
- 過期提示與總覽排序都看紀錄檔（.md）本身的修改時間；總覽板比已結束的紀錄舊時，
  提示「總覽板可能過期」（近似判斷）。
- 只處理「上一層是 .toukadev 的 progress 資料夾」；網頁帶產生器標記，
  已存在但沒有標記的 .html 一律不覆寫。
- 總覽板的「## 其他專案」每行是另一個專案 .toukadev/progress 的絕對路徑：只讀那裡直接
  底下的任務紀錄（不讀它的 index.md、不遞迴、不跟連結），一起放進自動彙總；不寫任何東西。
- 連結只有三種：總覽的任務名稱連到「<任務代號>.html」、任務頁上方「回總覽」連到
  index.html、其他專案的任務連到對方已有的「<任務代號>.html」（file: 網址）；都只由
  檔名（已驗證的任務代號）產生，紀錄內文一律不產生連結。

只用 Python 3.12 標準函式庫。網頁完全自含（不連網、不載入外部資源），
用一般瀏覽器開啟時每 5 秒自動重新整理。紀錄（.md）才是正本；網頁只是同一份資料的另一種呈現。
格式正本見 dev-workflow/references/progress-record.md。

- 角落顯示「畫面更新於 HH:MM:SS」；只把本機檔案顯示成快照的工具（網址不是
  file:、http:、https:）或網頁程式沒有執行時，改顯示不會自動更新的提醒，
  也不排自動重新整理（是否即時只看 head 腳本依協定白名單設定的 class）。
- 選取文字時暫停重新整理，並在固定位置說明原因。
- 淺色／深色切換只記在這個瀏覽器（localStorage），只接受 light、dark。
- 審核紀錄超過 10 列時，較早的列收合；展開狀態只記在這個分頁（sessionStorage），
  重新整理後照舊（ADR-046 D8）。
- 總覽最上方另列各任務的格式警告件數；「需要你決定的事」裡不是編號項目的照樣列為待決並標出來。
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import html
import io
import json
import os
import re
import stat
import sys
import tempfile
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from itertools import groupby
from pathlib import Path

# ── 格式正本（progress-record.md）───────────────────────────────

DECISIONS = "需要你決定的事"
WORK = "工作清單"
REVIEWS = "審核紀錄"
TEMP = "暫存項目"
ISSUES = "尚未驗證與已知問題"
REQUIRED_SECTIONS = (DECISIONS, WORK, REVIEWS, TEMP, ISSUES)

WORK_STATUSES = (
    "待辦",
    "執行中",
    "待審",
    "審核中",
    "退回修正",
    "已驗收",
    "已合併",
    "已完成",
)
CHECKED_STATUSES = frozenset({"已驗收", "已合併"})
NEUTRAL_DONE_STATUSES = frozenset({"已完成"})
TASK_STATES = ("進行中", "已結束")
RUNNING_STATE = "進行中"
FINISHED_STATE = "已結束"
TEMP_STATES = ("使用中", "已清理", "保留")
CLEANED_STATE = "已清理"
KEPT_STATE = "保留"
NOTE_COLUMN = "備註"
# 「保留」的備註空白或只有破折號類符號（-、—、－）時，不算寫了理由。
NO_REASON_PATTERN = re.compile(r"[\s\-—－]*")
# 暫存項目的收尾分類：只有已結束任務裡有寫理由的保留算 kept，其他沒清理的都算 open。
TEMP_CLEANED, TEMP_KEPT, TEMP_OPEN = "cleaned", "kept", "open"
STATUS_COLUMN = "狀態"
# 「保留」的備註（去掉前後空白）以這幾個字開頭：等人類回覆的收尾清理項目，任務結束後照樣算未清理。
WAITING_PREFIX = "等你決定"
# 現在／下一步：這四種狀態的項目，再加上第一個待辦。
ACTIVE_STATUSES = ("執行中", "待審", "審核中", "退回修正")
TODO_STATUS = "待辦"
BOARD_STEM = "index"
BOARD_FILENAME = "index.md"
BOARD_TITLE = "總覽板"
SUMMARY_DECISIONS = "要你決定"
NOW_NEXT = "現在／下一步"
OTHER_PROJECTS = "其他專案"
LINK_TEXT = "是連結（symlink、junction 或 reparse point）"
INDEX_FILENAME = "index.html"
TASK_CODE_PATTERN = re.compile(r"^[a-z0-9-]+$")
PROGRESS_FOLDER = "progress"
TOUKADEV_FOLDER = ".toukadev"
MINIMUM_PYTHON = (3, 12)
REVIEW_TIME_COLUMN = "時間"
# 審核紀錄的時間只認這兩種寫法（前面可以有「約」）；其他寫法看不懂就跳過，不警告。
SHORT_TIME_PATTERN = re.compile(r"(?:約\s*)?(\d{1,2})/(\d{1,2})\s+(\d{1,2}):(\d{2})")
FULL_TIME_PATTERN = re.compile(
    r"(?:約\s*)?(\d{4})-(\d{1,2})-(\d{1,2})\s+(\d{1,2}):(\d{2})"
)
# 只晚 1 分鐘可能是分鐘進位；差 1 小時以上可能只是本機與 UTC 的時區差。兩者都不警告。
FUTURE_MIN_SECONDS = 60
FUTURE_MAX_SECONDS = 59 * 60
# 只寫月日時取存檔那年；算出來比存檔時間晚超過這麼久，才當成前一年（跨年）。
YEAR_BACK_SECONDS = 30 * 24 * 60 * 60
# 進行中的紀錄裡，一格超過這麼多字就警告（ADR-046 D8）。
LONG_CELL_CHARS = 200
# 「原話：「…」」引號裡的字不算：人類原話照留在紀錄，不改短。引號可以巢狀。
QUOTE_LEAD_PATTERN = re.compile(r"原話\s*[：:]\s*「")
QUOTE_OPEN, QUOTE_CLOSE = "「", "」"
# 「需要你決定的事」裡不是編號項目的待決照樣算，總覽另標這句。
UNNUMBERED_FLAG = "格式待修，可能是待決"

# ── 不覆寫別人的檔案 ─────────────────────────────────────────────

GENERATOR_MARKER = '<meta name="generator" content="toukadev-progress">'
MARKER_SCAN_BYTES = 4096

# ── 網頁行為 ─────────────────────────────────────────────────────

REFRESH_SECONDS = 5
STALE_WARN_SECONDS = 30 * 60
STALE_ALERT_SECONDS = 120 * 60
STALE_TEXT = "分鐘沒更新：可能還在做，也可能忘了更新"
MISSING_CELL = "—"
EXTRA_CELLS_COLUMN = "（多出的格子）"
# 只有這些網址協定才會真的重新讀檔；其他（例如 data:）都當成快照。
LIVE_PROTOCOLS = ("file:", "http:", "https:")
LOADED_TEXT = "畫面更新於 "
SNAPSHOT_TEXT = "此畫面不會自動更新：請用一般瀏覽器開啟 index.html"
PAUSED_TEXT = "已暫停自動更新：你選取了文字（取消選取即恢復）"
THEME_STORAGE_KEY = "toukadev-progress-theme"
THEME_TITLE = "切換顯示：跟隨系統 → 淺色 → 深色"
# 審核紀錄超過這麼多列時，只展開最近的這幾列，較早的收合；展開狀態只記在這個分頁（sessionStorage）。
REVIEW_OPEN_ROWS = 10
OLDER_STORAGE_KEY = "toukadev-progress-older:"
FORMAT_SUMMARY = "格式警告"

TITLE_PATTERN = re.compile(r"^#\s+(?P<title>.+?)\s*$")
SECTION_PATTERN = re.compile(r"^##\s+(?P<title>.+?)\s*#*\s*$")
FENCE_PATTERN = re.compile(r"^\s{0,3}(```|~~~)")
# 舊紀錄的「更新時間：」照樣認得，但只為了略過它；排序與過期提示都看 .md 的修改時間。
META_PATTERN = re.compile(r"^(?P<key>更新時間|任務狀態)\s*[：:]\s*(?P<value>.*?)\s*$")
NOTE_PATTERN = re.compile(r"^(?P<base>.*?)\s*(?:[（(](?P<note>.*)[）)])?$")
BULLET_PATTERN = re.compile(
    r"^(?P<indent>\s*)(?:[-*+]|(?P<number>\d+)[.)])\s+(?P<text>.*)$"
)
# 最上層項目最多縮排 3 格；比上一個條列項目多縮排 2 格以上的條列是它的子項目（只有一層）。
TOP_ITEM_MAX_INDENT = 3
SUB_ITEM_EXTRA_INDENT = 2
# 括號說明只能和「目前沒有」在同一行；換行後的內容一律照實算成待決。
NOTHING_PENDING_PATTERN = re.compile(
    r"目前沒有[。.]?[ \t　]*(?:[（(][^）)\n]*[）)][ \t　]*[。.]?)?"
)
ROW_SPLIT_PATTERN = re.compile(r"(?<!\\)\|")
SEPARATOR_CELL_PATTERN = re.compile(r"^:?-+:?$")
CODE_SPAN_PATTERN = re.compile(r"`([^`\n]+)`")
BOLD_PATTERN = re.compile(r"\*\*(.+?)\*\*")


# ── 資料結構 ─────────────────────────────────────────────────────


@dataclass
class Section:
    title: str
    lines: list[str] = field(default_factory=list)


@dataclass
class Record:
    stem: str
    title: str
    task_state: str | None = None
    preamble_extra: list[str] = field(default_factory=list)
    sections: dict[str, Section] = field(default_factory=dict)
    other_sections: list[Section] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class TableSpec:
    """通用表格：依表頭顯示所有欄位；有規定狀態的表格替「狀態」欄上色。

    open_rows 有值時，列數超過就只展開最近的這幾列，較早的收合。
    """

    label: str
    css: str
    row_css: str
    statuses: tuple[str, ...]
    classes: Mapping[str, str]
    marks: bool
    open_rows: int | None = None


@dataclass(frozen=True)
class StatusView:
    raw: str | None
    base: str
    mark: str


@dataclass
class TableView:
    spec: TableSpec
    columns: list[str] = field(default_factory=list)
    rows: list[dict[str, str]] = field(default_factory=list)
    statuses: list[StatusView] = field(default_factory=list)
    extra_lines: list[str] = field(default_factory=list)
    found: bool = False


@dataclass
class ListItem:
    bullet: bool
    lines: list[str]
    number: str | None = None
    children: list[ListItem] = field(default_factory=list)

    @property
    def text(self) -> str:
        return "\n".join(self.lines)


@dataclass(frozen=True)
class DecisionView:
    present: bool
    count: int | None
    lines: tuple[str, ...]
    items: tuple[ListItem, ...] = ()


@dataclass
class RecordView:
    record: Record
    source_name: str
    decisions: DecisionView
    work: TableView | None
    reviews: TableView | None
    temp: TableView | None
    issues: Section | None
    modified_epoch: int

    @property
    def warnings(self) -> list[str]:
        return self.record.warnings

    @property
    def statuses(self) -> list[StatusView]:
        return self.work.statuses if self.work is not None else []

    @property
    def checked_count(self) -> int:
        return sum(1 for status in self.statuses if status.mark == "check")

    @property
    def complete_count(self) -> int:
        return sum(1 for status in self.statuses if status.mark == "complete")

    @property
    def done_count(self) -> int:
        """完成＝打 ✔ 的已驗收、已合併，加上中性「完成」的已完成。"""
        return self.checked_count + self.complete_count

    @property
    def temp_kinds(self) -> list[str]:
        if self.temp is None:
            return []
        finished = self.record.task_state == FINISHED_STATE
        return [
            temp_kind(status, row, finished)
            for status, row in zip(self.temp.statuses, self.temp.rows, strict=True)
        ]

    @property
    def open_temp_count(self) -> int:
        """沒清理的都算（包含沒寫或看不懂的狀態）；已結束任務裡有寫理由的保留除外。"""
        return self.temp_kinds.count(TEMP_OPEN)

    @property
    def kept_temp_count(self) -> int:
        """任務已結束時，「保留」而且備註有寫理由的項目；不算未清理，另外列件數。"""
        return self.temp_kinds.count(TEMP_KEPT)

    @property
    def stale_mode(self) -> str:
        if self.record.task_state != RUNNING_STATE:
            return "off"
        return "waiting" if (self.decisions.count or 0) > 0 else "running"


@dataclass(frozen=True)
class Board:
    """總覽板 index.md：第一行 # 標題，其餘 ## 區段原樣顯示，不檢查格式。"""

    name: str
    title: str
    preamble: tuple[str, ...]
    sections: tuple[Section, ...]
    modified_epoch: int


@dataclass(frozen=True)
class SummaryEntry:
    """自動彙總裡的一個任務；title_html 是已跳脫、可能帶連結的任務名稱。

    project 是其他專案的名稱；本專案是空字串。
    """

    view: RecordView
    title_html: str
    project: str = ""


@dataclass(frozen=True)
class RenderOutcome:
    output: Path
    warnings: tuple[str, ...]
    index: Path | None
    failures: tuple[str, ...]
    skipped: tuple[str, ...]


@dataclass
class FolderResult:
    outputs: list[Path] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    warning_counts: dict[str, int] = field(default_factory=dict)


class RenderError(Exception):
    """讀不到紀錄，或寫不進網頁。"""


class UsageError(RenderError):
    """給錯了位置或檔名；指令列以 exit 2 結束。"""


class LocationError(UsageError):
    """不在 .toukadev/progress 資料夾裡，不處理，避免覆寫其他檔案。"""


class ForeignFileError(RenderError):
    """要寫的 .html 已存在，但不是這支程式產生的。"""


STATUS_CLASSES = {
    "待辦": "st-todo",
    "執行中": "st-doing",
    "待審": "st-review",
    "審核中": "st-review",
    "退回修正": "st-rework",
    "已驗收": "st-check",
    "已合併": "st-check",
    "已完成": "st-complete",
}
TEMP_STATE_CLASSES = {"使用中": "t-active", "已清理": "t-cleaned", "保留": "t-kept"}
TASK_STATE_CLASSES = {"進行中": "st-doing", "已結束": "st-complete"}

WORK_TABLE = TableSpec(
    WORK, "work-table", "work-row", WORK_STATUSES, STATUS_CLASSES, True
)
REVIEW_TABLE = TableSpec(
    REVIEWS, "review-table", "review-row", (), {}, False, REVIEW_OPEN_ROWS
)
TEMP_TABLE = TableSpec(
    TEMP, "temp-table", "temp-row", TEMP_STATES, TEMP_STATE_CLASSES, False
)


# ── 解析：標題、開頭欄位與區段 ───────────────────────────────────


def parse_record(text: str, stem: str) -> Record:
    lines = text.splitlines()
    title, body_start = parse_title(lines)
    record = Record(stem=stem, title=title or stem)
    preamble, sections = split_sections(lines[body_start:])
    parse_preamble(preamble, record)
    assign_sections(sections, record)
    report_missing_sections(record)
    return record


def parse_board(text: str, name: str, modified_epoch: int) -> Board:
    """沒有 # 標題時顯示「總覽板」；區段不分必要與否，全部照順序原樣顯示。"""
    lines = text.splitlines()
    title, start = parse_title(lines)
    preamble, sections = split_sections(lines[start:])
    title = title or BOARD_TITLE
    return Board(name, title, tuple(preamble), tuple(sections), modified_epoch)


def is_linkable_task_code(stem: str) -> bool:
    """只有完全符合「小寫英數與 -」且不是 index 的檔名，才拿來產生連結。"""
    return TASK_CODE_PATTERN.fullmatch(stem) is not None and stem != BOARD_STEM


def is_board(path: Path) -> bool:
    """index.md（不分大小寫）是總覽板，不是任務紀錄。"""
    return path.name.casefold() == BOARD_FILENAME


def parse_title(lines: Sequence[str]) -> tuple[str | None, int]:
    """第一個非空行是「# 名稱」就回傳名稱與下一行的位置；不是的話回傳 None 與那一行的位置。"""
    for index, line in enumerate(lines):
        if not line.strip():
            continue
        match = TITLE_PATTERN.match(line)
        if match:
            return match["title"], index + 1
        return None, index
    return None, len(lines)


def split_sections(lines: Sequence[str]) -> tuple[list[str], list[Section]]:
    preamble: list[str] = []
    sections: list[Section] = []
    in_fence = False
    for line in lines:
        if FENCE_PATTERN.match(line):
            in_fence = not in_fence
        match = None if in_fence else SECTION_PATTERN.match(line)
        if match:
            sections.append(Section(match["title"]))
        elif sections:
            sections[-1].lines.append(line)
        else:
            preamble.append(line)
    return preamble, sections


def top_level_lines(lines: Sequence[str]) -> list[str]:
    """讓這一段的第一行從最上層開始：每行去掉和第一個非空行一樣多的開頭空白（不夠就去掉現有的）。

    重複的「需要你決定的事」併進第一段時用，免得開頭縮排的項目被當成上一段最後一項的子項目。
    空白的定義和清單解析的 `\\s` 一樣（含 tab、全形空白）。
    """
    first = next((line for line in lines if line.strip()), "")
    indent = len(first) - len(first.lstrip())
    return [line[min(indent, len(line) - len(line.lstrip())) :] for line in lines]


def parse_preamble(lines: Sequence[str], record: Record) -> None:
    """只讀「任務狀態：」；舊紀錄的「更新時間：」略過，其他文字照原樣顯示在最上面。"""
    seen: set[str] = set()
    for line in lines:
        match = META_PATTERN.match(line)
        if match is None:
            if line.strip():
                record.preamble_extra.append(line)
            continue
        if match["key"] in seen or match["key"] == "更新時間":
            continue
        seen.add(match["key"])
        parse_task_state(match["value"], record)


def parse_task_state(value: str, record: Record) -> None:
    base, _ = split_note(value)
    if base in TASK_STATES:
        record.task_state = base
        return
    record.warnings.append(
        f"任務狀態「{value}」看不懂（只能是進行中或已結束），所以不顯示過期提示。"
    )


def assign_sections(sections: Sequence[Section], record: Record) -> None:
    """同名的必要區段寫了不只一段時警告。

    「需要你決定的事」的後面幾段併進第一段，每段的待決都照算（寧可多算）；
    其他必要區段的後面幾段照原樣顯示在最下面。
    """
    repeated: list[str] = []
    for section in sections:
        title = section.title
        if title not in REQUIRED_SECTIONS:
            record.other_sections.append(section)
            continue
        if title not in record.sections:
            record.sections[title] = section
            continue
        if title not in repeated:
            repeated.append(title)
        if title == DECISIONS:
            record.sections[title].lines.extend(["", *top_level_lines(section.lines)])
        else:
            record.other_sections.append(section)
    for title in repeated:
        handling = (
            "合併成一段顯示，每段的待決都照算"
            if title == DECISIONS
            else "後面那段照原樣顯示在最下面"
        )
        record.warnings.append(f"「{title}」寫了不只一段：{handling}；請合併成一段。")


def report_missing_sections(record: Record) -> None:
    for title in REQUIRED_SECTIONS:
        if title in record.sections:
            continue
        record.warnings.append(
            f"缺少「{title}」區段：這不是「目前沒有」，是紀錄裡沒有寫這一段。"
        )


def split_note(value: str) -> tuple[str, str]:
    """把「執行中（04:17 開始）」拆成狀態與括號說明。"""
    match = NOTE_PATTERN.match(value.strip())
    if match is None:
        return value.strip(), ""
    return match["base"].strip(), (match["note"] or "").strip()


# ── 解析：通用表格（依表頭顯示所有欄位）─────────────────────────


def build_table_view(
    section: Section, spec: TableSpec, warnings: list[str]
) -> TableView:
    """第一個表格依表頭顯示；第二個表格與表格外的文字照原樣顯示在表格下方。"""
    blocks, extra = collect_table_blocks(section.lines)
    view = TableView(spec, extra_lines=extra, found=bool(blocks))
    if not blocks:
        return view
    for block in blocks[1:]:
        view.extra_lines.extend(block)
    header, rows = split_table_block(blocks[0])
    view.columns = header_names(header)
    view.rows = build_rows(rows, view)
    if spec.statuses:
        view.statuses = [
            classify_status(row.get(STATUS_COLUMN), number, spec, warnings)
            for number, row in enumerate(view.rows, start=1)
        ]
    return view


def collect_table_blocks(lines: Sequence[str]) -> tuple[list[list[str]], list[str]]:
    blocks: list[list[str]] = []
    extra: list[str] = []
    in_table = False
    for line in lines:
        is_row = line.strip().startswith("|")
        if is_row and not in_table:
            blocks.append([])
        if is_row:
            blocks[-1].append(line)
        elif line.strip():
            extra.append(line)
        in_table = is_row
    return blocks, extra


def split_row(line: str) -> list[str]:
    body = line.strip()
    if body.startswith("|"):
        body = body[1:]
    if body.endswith("|") and not body.endswith("\\|"):
        body = body[:-1]
    return [cell.replace("\\|", "|").strip() for cell in ROW_SPLIT_PATTERN.split(body)]


def is_separator_row(cells: Sequence[str]) -> bool:
    return bool(cells) and all(
        SEPARATOR_CELL_PATTERN.match(cell.replace(" ", "")) for cell in cells
    )


def split_table_block(block: Sequence[str]) -> tuple[list[str], list[list[str]]]:
    """第二行不是分隔線（|---|）時，把它當成資料列，不丟掉。"""
    cells = [split_row(line) for line in block]
    header, body = cells[0], cells[1:]
    if body and is_separator_row(body[0]):
        return header, body[1:]
    return header, body


def header_names(header: Sequence[str]) -> list[str]:
    names: list[str] = []
    for raw in header:
        names.append(unique_name(raw or "（空白欄名）", names))
    return names


def unique_name(name: str, taken: Sequence[str]) -> str:
    candidate, counter = name, 2
    while candidate in taken:
        candidate = f"{name}（{counter}）"
        counter += 1
    return candidate


def build_rows(rows: Sequence[Sequence[str]], view: TableView) -> list[dict[str, str]]:
    """少的格子顯示「—」；多的格子照原樣放進最右邊的「（多出的格子）」。"""
    keys = list(view.columns)
    built: list[dict[str, str]] = []
    for cells in rows:
        row = dict(zip(keys, cells))
        if len(cells) > len(keys):
            row[EXTRA_CELLS_COLUMN] = " | ".join(cells[len(keys) :])
            add_extra_column(view)
        built.append(row)
    return built


def add_extra_column(view: TableView) -> None:
    if EXTRA_CELLS_COLUMN not in view.columns:
        view.columns.append(EXTRA_CELLS_COLUMN)


def classify_status(
    raw: str | None, number: int, spec: TableSpec, warnings: list[str]
) -> StatusView:
    if raw is None:
        return StatusView(None, "", "missing")
    base, _ = split_note(raw)
    if base not in spec.statuses:
        warnings.append(f"{spec.label}第 {number} 列的狀態「{raw}」不是規定的狀態。")
        return StatusView(raw, base, "unknown")
    if base in CHECKED_STATUSES:
        return StatusView(raw, base, "check")
    if base in NEUTRAL_DONE_STATUSES:
        return StatusView(raw, base, "complete")
    return StatusView(raw, base, "none")


def temp_kind(status: StatusView, row: Mapping[str, str], finished: bool) -> str:
    """收尾時每項都要是「已清理」或「保留」（備註寫理由）。

    任務進行中、任務狀態缺漏或看不懂時，保留可能只是暫時的，照舊算未清理；
    等你決定的保留在任務結束後也照舊算未清理。
    """
    if status.base == CLEANED_STATE:
        return TEMP_CLEANED
    note = row.get(NOTE_COLUMN, "")
    if (
        finished
        and status.base == KEPT_STATE
        and not waits_for_you(status, row)
        and not NO_REASON_PATTERN.fullmatch(note)
    ):
        return TEMP_KEPT
    return TEMP_OPEN


def waits_for_you(status: StatusView, row: Mapping[str, str]) -> bool:
    """「保留」而且備註去掉前後空白後以「等你決定」開頭。"""
    note = row.get(NOTE_COLUMN, "").strip()
    return status.base == KEPT_STATE and note.startswith(WAITING_PREFIX)


def group_list_items(lines: Sequence[str]) -> list[ListItem]:
    """回傳最上層項目；子項目掛在上一個條列項目底下，接續行併進正在寫的那一項。"""
    items: list[ListItem] = []
    current: ListItem | None = None
    parent: ListItem | None = None
    parent_indent = 0
    for line in lines:
        if not line.strip():
            current = None
            continue
        match = BULLET_PATTERN.match(line)
        indent = len(match["indent"]) if match else 0
        if match and parent and indent >= parent_indent + SUB_ITEM_EXTRA_INDENT:
            current = ListItem(True, [match["text"]], list_number(match))
            parent.children.append(current)
            continue
        if indent > TOP_ITEM_MAX_INDENT:
            match = None
        if match is None and current is not None:
            current.lines.append(line.strip())
            continue
        text = match["text"] if match else line.strip()
        current = ListItem(match is not None, [text], list_number(match))
        items.append(current)
        parent, parent_indent = (current, indent) if match else (None, 0)
    return items


def list_number(match: re.Match[str] | None) -> str | None:
    """編號清單的原號（去掉開頭的 0）；不是編號就回傳 None。"""
    if match is None or match["number"] is None:
        return None
    return match["number"].lstrip("0") or "0"


# ── 分析 ─────────────────────────────────────────────────────────


def analyze_record(record: Record, source_name: str, modified_epoch: int) -> RecordView:
    work = table_or_none(record, WORK_TABLE)
    reviews = table_or_none(record, REVIEW_TABLE)
    running = record.task_state == RUNNING_STATE
    if running and reviews is not None:
        check_review_times(reviews.rows, modified_epoch, record.warnings)
    temp = table_or_none(record, TEMP_TABLE)
    if running:
        for table in (work, reviews, temp):
            check_long_cells(table, record.warnings)
    decisions = analyze_decisions(record.sections.get(DECISIONS))
    check_unnumbered_decisions(decisions, record.warnings)
    view = RecordView(
        record,
        source_name,
        decisions,
        work,
        reviews,
        temp,
        record.sections.get(ISSUES),
        modified_epoch,
    )
    check_waiting_holds(view)
    return view


def check_long_cells(table: TableView | None, warnings: list[str]) -> None:
    """一格超過約 200 字就警告，同一張表的列號合成一則；「原話：「…」」裡的字不算。"""
    if table is None:
        return
    numbers = [
        str(number)
        for number, row in enumerate(table.rows, start=1)
        if any(counted_length(cell) > LONG_CELL_CHARS for cell in row.values())
    ]
    if numbers:
        warnings.append(
            f"{table.spec.label}第 {'、'.join(numbers)} 列有格子超過約 {LONG_CELL_CHARS} 字"
            "（人類原話不算）：每列寫一兩句，細節放 PR 說明或 ADR。"
        )


def counted_length(cell: str) -> int:
    """格子的字數，不算「原話：「…」」引號裡的字；沒收尾的原話一直算到格子結尾。"""
    counted, position = 0, 0
    for match in QUOTE_LEAD_PATTERN.finditer(cell):
        if match.start() < position:
            continue
        counted += match.end() - position
        position = quote_end(cell, match.end())
    return counted + len(cell) - position


def quote_end(text: str, start: int) -> int:
    """從開引號後面找對應的收引號（可巢狀），回傳收引號後面的位置；沒收尾就回傳結尾。"""
    depth = 1
    for index in range(start, len(text)):
        if text[index] == QUOTE_OPEN:
            depth += 1
        elif text[index] == QUOTE_CLOSE:
            depth -= 1
            if depth == 0:
                return index + 1
    return len(text)


def check_unnumbered_decisions(decisions: DecisionView, warnings: list[str]) -> None:
    """不是編號項目的待決（段落或 - 清單）照樣算待決，另外警告要修。"""
    count = sum(1 for item in decisions.items if item.number is None)
    if count:
        warnings.append(
            f"「{DECISIONS}」有 {count} 項不是編號項目：只放編號項目，回覆過的整項移走；"
            "總覽照樣列成可能待決。"
        )


def check_waiting_holds(view: RecordView) -> None:
    """已結束的紀錄有等你決定的保留，「需要你決定的事」卻是「目前沒有」或沒有項目時警告。"""
    if view.record.task_state != FINISHED_STATE or view.temp is None:
        return
    if view.decisions.count:
        return
    pairs = zip(view.temp.statuses, view.temp.rows, strict=True)
    numbers = [
        str(number)
        for number, (status, row) in enumerate(pairs, start=1)
        if waits_for_you(status, row)
    ]
    if numbers:
        view.record.warnings.append(
            f"{TEMP}第 {'、'.join(numbers)} 列是「{KEPT_STATE}」且備註寫「{WAITING_PREFIX}」，"
            f"但「{DECISIONS}」沒有任何項目：收尾清理清單要寫成「{DECISIONS}」的一項。"
        )


def now_and_next(view: RecordView) -> list[tuple[StatusView, Mapping[str, str]]]:
    """執行中、待審、審核中、退回修正的項目照工作清單的順序，再加上第一個待辦。"""
    if view.work is None:
        return []
    pairs = list(zip(view.work.statuses, view.work.rows, strict=True))
    active = [pair for pair in pairs if pair[0].base in ACTIVE_STATUSES]
    todo = [pair for pair in pairs if pair[0].base == TODO_STATUS]
    return active + todo[:1]


def table_or_none(record: Record, spec: TableSpec) -> TableView | None:
    section = record.sections.get(spec.label)
    if section is None:
        return None
    return build_table_view(section, spec, record.warnings)


def check_review_times(
    rows: Sequence[Mapping[str, str]], modified_epoch: int, warnings: list[str]
) -> None:
    """只看「時間」欄：比上一列早，或比紀錄存檔時間晚 2～59 分鐘，就警告。"""
    previous: float | None = None
    for number, row in enumerate(rows, start=1):
        raw = row.get(REVIEW_TIME_COLUMN, "")
        moment = parse_review_time(raw, modified_epoch)
        if moment is None:
            continue
        if previous is not None and moment < previous:
            warnings.append(f"{REVIEWS}第 {number} 列的時間「{raw}」比上一列早。")
        if FUTURE_MIN_SECONDS < moment - modified_epoch <= FUTURE_MAX_SECONDS:
            warnings.append(
                f"{REVIEWS}第 {number} 列的時間「{raw}」晚於紀錄存檔時間（多半是估的）。"
            )
        previous = moment


def parse_review_time(raw: str, modified_epoch: int) -> float | None:
    """換成本機時間的 epoch（取該分鐘的起點）；看不懂或日期不存在時回傳 None。"""
    full = FULL_TIME_PATTERN.fullmatch(raw)
    short = SHORT_TIME_PATTERN.fullmatch(raw)
    try:
        if full is not None:
            return datetime(*map(int, full.groups())).timestamp()
        if short is None:
            return None
        year = time.localtime(modified_epoch).tm_year
        moment = datetime(year, *map(int, short.groups())).timestamp()
        if moment - modified_epoch > YEAR_BACK_SECONDS:
            moment = datetime(year - 1, *map(int, short.groups())).timestamp()
        return moment
    except (ValueError, OverflowError, OSError):
        return None


def analyze_decisions(section: Section | None) -> DecisionView:
    """只有每一項都是「目前沒有。」（可附括號說明）才算 0；其他寫法照實計數。

    只算最上層項目：縮排的子項目（選項）不另算一件。
    """
    if section is None:
        return DecisionView(False, None, ())
    items = group_list_items(section.lines)
    if not items:
        return DecisionView(True, None, tuple(section.lines))
    pending = tuple(item for item in items if not is_nothing_pending(item))
    return DecisionView(True, len(pending), tuple(section.lines), pending)


def is_nothing_pending(item: ListItem) -> bool:
    """底下還有子項目時不算「目前沒有」。"""
    if item.children:
        return False
    return NOTHING_PENDING_PATTERN.fullmatch(item.text.strip()) is not None


def is_link_stat(entry_stat: object) -> bool:
    """symlink，或 Windows 上帶 reparse point 屬性（junction 等）。"""
    mode = getattr(entry_stat, "st_mode", 0)
    attributes = getattr(entry_stat, "st_file_attributes", 0)
    return stat.S_ISLNK(mode) or bool(attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT)


# ── HTML：共用 ───────────────────────────────────────────────────

LIGHT_COLORS = """
  --bg: #f5f6f8; --card: #ffffff; --fg: #1d232b; --muted: #5b6573; --border: #d5dae1;
  --ok-bg: #e2f4e6; --ok-fg: #1c6a34; --info-bg: #e3edfc; --info-fg: #1f4f99;
  --review-bg: #eee6fb; --review-fg: #5a2d9b; --warn-bg: #fff2d4; --warn-fg: #7f5200;
  --alert-bg: #fde3e3; --alert-fg: #9f1c1c; --neutral-bg: #eaedf1; --neutral-fg: #45505c;
"""
DARK_COLORS = """
  --bg: #13171c; --card: #1c2229; --fg: #e5e9ee; --muted: #9aa4b0; --border: #333c47;
  --ok-bg: #163824; --ok-fg: #8fdea7; --info-bg: #172b48; --info-fg: #9dc2ff;
  --review-bg: #2b2041; --review-fg: #ccb1f4; --warn-bg: #3b2e0e; --warn-fg: #f3cb68;
  --alert-bg: #441a1a; --alert-fg: #ff9e9e; --neutral-bg: #29313b; --neutral-fg: #c2cbd5;
"""
# 沒選或選「跟隨系統」時依系統；選了淺色或深色就固定配色與 color-scheme。
THEME_STYLE = (
    "\n:root {\n  color-scheme: light dark;" + LIGHT_COLORS + "}\n"
    ':root[data-theme="light"] { color-scheme: light; }\n'
    ':root[data-theme="dark"] {\n  color-scheme: dark;' + DARK_COLORS + "}\n"
    "@media (prefers-color-scheme: dark) {\n"
    '  :root:not([data-theme="light"]) {' + DARK_COLORS + "  }\n}\n"
)
# 畫面更新時間、快照提醒、主題切換與暫停提示；顯示哪一個由 <html> 的 class 決定。
TOOLS_STYLE = """
.page-tools {
  display: flex; flex-wrap: wrap; justify-content: flex-end; align-items: center;
  gap: 6px 10px; margin: 0 0 8px; font-size: 0.85rem; color: var(--muted);
}
.refresh-snapshot {
  padding: 1px 8px; border-radius: 8px; border: 1px solid var(--warn-fg);
  background: var(--warn-bg); color: var(--warn-fg); font-weight: 600;
}
.loaded-at { display: inline-block; min-width: 8ch; font-variant-numeric: tabular-nums; }
.refresh-live, .theme-toggle, .theme-light, .theme-dark { display: none; }
html.live .refresh-live { display: inline; }
html.live .refresh-snapshot { display: none; }
html.js .theme-toggle { display: inline-block; }
html[data-theme="light"] .theme-system, html[data-theme="dark"] .theme-system {
  display: none;
}
html[data-theme="light"] .theme-light, html[data-theme="dark"] .theme-dark {
  display: inline;
}
.theme-toggle {
  font: inherit; color: var(--fg); background: var(--card); cursor: pointer;
  border: 1px solid var(--border); border-radius: 8px; padding: 1px 10px;
}
.pause-notice {
  position: fixed; left: 50%; bottom: 16px; transform: translateX(-50%); z-index: 1;
  max-width: calc(100% - 32px); margin: 0; padding: 6px 14px; border-radius: 8px;
  border: 2px solid var(--warn-fg); background: var(--warn-bg); color: var(--warn-fg);
  font-weight: 600;
}
html:not(.live) .pause-notice { display: none; }
"""
STYLE = THEME_STYLE + (
    """* { box-sizing: border-box; }
[hidden] { display: none !important; }
body {
  margin: 0; padding: 24px 16px 72px; background: var(--bg); color: var(--fg);
  font: 15px/1.6 system-ui, -apple-system, "Segoe UI", "Microsoft JhengHei",
    "PingFang TC", "Noto Sans TC", sans-serif;
}
main { max-width: 1120px; margin: 0 auto; }
h1 { font-size: 1.5rem; margin: 0 0 4px; }
h2 { font-size: 1.15rem; margin: 0 0 12px; }
p { margin: 0 0 8px; }
.meta { color: var(--muted); }
.section, .notice {
  background: var(--card); border: 1px solid var(--border); border-radius: 10px;
  padding: 16px 18px; margin: 16px 0;
}
.table-wrap { overflow-x: auto; }
table { border-collapse: collapse; width: 100%; min-width: 640px; font-size: 0.92rem; }
.status-note { margin-left: 4px; font-size: 0.85rem; }
th, td {
  text-align: left; vertical-align: top; padding: 6px 8px;
  border-bottom: 1px solid var(--border); white-space: pre-wrap;
}
th { color: var(--muted); font-weight: 600; }
td.missing { color: var(--muted); }
.mark {
  width: 4.5em; text-align: center; font-weight: 700; color: var(--ok-fg);
  white-space: nowrap;
}
.chip, .badge, .stale {
  display: inline-block; padding: 1px 8px; border-radius: 8px; font-size: 0.85rem;
  font-weight: 600; background: var(--neutral-bg); color: var(--neutral-fg);
}
th, .chip, .badge, .stale { white-space: nowrap; }
.badge, .stale { margin-left: 6px; }
.mark .badge { margin-left: 0; }
.st-doing, .t-active { background: var(--info-bg); color: var(--info-fg); }
.st-review, .t-kept { background: var(--review-bg); color: var(--review-fg); }
.st-rework { background: var(--alert-bg); color: var(--alert-fg); }
.st-check, .t-cleaned { background: var(--ok-bg); color: var(--ok-fg); }
.st-unknown, .badge-unknown, .stale-warn {
  background: var(--warn-bg); color: var(--warn-fg);
}
.st-unknown, .badge-unknown { outline: 2px dashed var(--warn-fg); }
.stale-alert, .badge-pending { background: var(--alert-bg); color: var(--alert-fg); }
.badge-waiting { background: var(--review-bg); color: var(--review-fg); }
.flag { display: block; font-size: 0.75rem; font-weight: 400; }
.decisions.pending { border: 2px solid var(--alert-fg); background: var(--alert-bg); }
.decisions.pending h2 { color: var(--alert-fg); }
.warnings { border: 2px solid var(--warn-fg); background: var(--warn-bg); color: var(--warn-fg); }
.missing-section {
  border: 2px dashed var(--alert-fg); background: var(--alert-bg); color: var(--alert-fg);
}
.temp-summary.open, td.temp.open { font-weight: 700; color: var(--warn-fg); }
.temp-summary.open { font-size: 1.1rem; }
.file { display: block; font-size: 0.8rem; font-weight: 400; color: var(--muted); }
ul { margin: 0; padding-left: 1.4em; }
li, .text p { white-space: pre-wrap; }
pre.raw {
  white-space: pre-wrap; margin: 8px 0 0; padding: 8px 10px; border-radius: 6px;
  background: var(--neutral-bg); color: var(--fg); font-size: 0.88rem;
}
code {
  font-family: ui-monospace, Consolas, "Cascadia Mono", monospace; font-size: 0.9em;
  background: var(--neutral-bg); padding: 0 4px; border-radius: 4px;
}
.older-rows { margin: 0 0 8px; }
.older-rows > summary { cursor: pointer; color: var(--muted); font-size: 0.9rem; }
.decision-flag { margin-left: 6px; }
.format-summary { border: 2px solid var(--warn-fg); }
footer { color: var(--muted); font-size: 0.85rem; margin-top: 24px; }
a { color: var(--info-fg); }
.nav { margin: 0 0 8px; font-size: 0.9rem; }
"""
    + TOOLS_STYLE
)

# 在 <head> 裡、畫面畫出來之前執行：決定顯示更新時間或快照提醒，並套用記住的主題。
HEAD_SCRIPT = """
(function () {
  "use strict";
  var root = document.documentElement;
  var live = %(live_protocols)s.indexOf(window.location.protocol) !== -1;
  root.setAttribute("class", live ? "js live" : "js");
  try {
    var theme = window.localStorage.getItem(%(theme_key)s);
    if (theme === "light" || theme === "dark") {
      root.setAttribute("data-theme", theme);
    }
  } catch (error) {
    return;
  }
})();
""" % {
    "live_protocols": json.dumps(list(LIVE_PROTOCOLS)),
    "theme_key": json.dumps(THEME_STORAGE_KEY),
}

# 重新整理後的捲動位置由瀏覽器自己保留（Edge 以 file:// 實測），不另寫還原程式。
SCRIPT = """
(function () {
  "use strict";
  var REFRESH_MS = %(refresh_ms)d;
  var STALE_TEXT = "%(stale_text)s";
  var THEME_KEY = %(theme_key)s;
  var OLDER_KEY = %(older_key)s;
  var NEXT_THEME = { system: "light", light: "dark", dark: "system" };
  var LIVE = document.documentElement.classList.contains("live");
  function staleLevel(node, elapsed) {
    if (elapsed > Number(node.getAttribute("data-alert-after"))) { return "alert"; }
    if (elapsed > Number(node.getAttribute("data-warn-after"))) { return "warn"; }
    return "";
  }
  function updateNode(node, now) {
    var elapsed = now - Number(node.getAttribute("data-epoch"));
    var minutes = Math.max(0, Math.floor(elapsed / 60));
    var age = node.querySelector(".age");
    if (age) { age.textContent = "（" + minutes + " 分鐘前）"; }
    var badge = node.querySelector(".stale");
    if (!badge || node.getAttribute("data-stale-mode") !== "running") { return; }
    var level = staleLevel(node, elapsed);
    badge.hidden = level === "";
    badge.className = level ? "stale stale-" + level : "stale";
    badge.textContent = level ? minutes + " " + STALE_TEXT : "";
  }
  function updateAll() {
    var now = Date.now() / 1000;
    var nodes = document.querySelectorAll("[data-epoch]");
    for (var index = 0; index < nodes.length; index += 1) {
      updateNode(nodes[index], now);
    }
  }
  function selectedText() {
    return window.getSelection ? String(window.getSelection()) : "";
  }
  function showPause(paused) {
    var notice = document.querySelector(".pause-notice");
    if (notice) { notice.hidden = !paused; }
  }
  function scheduleReload() {
    window.setTimeout(function () {
      if (selectedText()) { showPause(true); scheduleReload(); return; }
      window.location.reload();
    }, REFRESH_MS);
  }
  function twoDigits(value) {
    return (value < 10 ? "0" : "") + value;
  }
  function showLoadedAt() {
    var node = document.querySelector(".loaded-at");
    if (!node) { return; }
    var now = new Date();
    node.textContent = twoDigits(now.getHours()) + ":" +
      twoDigits(now.getMinutes()) + ":" + twoDigits(now.getSeconds());
  }
  function currentTheme() {
    var theme = document.documentElement.getAttribute("data-theme");
    return theme === "light" || theme === "dark" ? theme : "system";
  }
  function saveTheme(theme) {
    try {
      if (theme === "system") {
        window.localStorage.removeItem(THEME_KEY);
      } else {
        window.localStorage.setItem(THEME_KEY, theme);
      }
    } catch (error) { return; }
  }
  function toggleTheme() {
    var theme = NEXT_THEME[currentTheme()];
    document.documentElement.setAttribute("data-theme", theme);
    saveTheme(theme);
  }
  function watchControls() {
    var toggle = document.querySelector(".theme-toggle");
    if (toggle) { toggle.addEventListener("click", toggleTheme); }
    document.addEventListener("selectionchange", function () {
      showPause(selectedText() !== "");
    });
  }
  function olderKey() {
    return OLDER_KEY + window.location.pathname;
  }
  function saveOlder(event) {
    try {
      if (event.target.open) {
        window.sessionStorage.setItem(olderKey(), "open");
      } else {
        window.sessionStorage.removeItem(olderKey());
      }
    } catch (error) { return; }
  }
  function restoreOlder() {
    var open = false;
    try {
      open = window.sessionStorage.getItem(olderKey()) === "open";
    } catch (error) { open = false; }
    var nodes = document.querySelectorAll("details.older-rows");
    for (var index = 0; index < nodes.length; index += 1) {
      nodes[index].open = open;
      nodes[index].addEventListener("toggle", saveOlder);
    }
  }
  if (LIVE) { scheduleReload(); }
  updateAll();
  showLoadedAt();
  restoreOlder();
  watchControls();
})();
""" % {
    "refresh_ms": REFRESH_SECONDS * 1000,
    "stale_text": STALE_TEXT,
    "theme_key": json.dumps(THEME_STORAGE_KEY),
    "older_key": json.dumps(OLDER_STORAGE_KEY),
}


def csp_hash(source: str) -> str:
    digest = hashlib.sha256(source.encode("utf-8")).digest()
    return "'sha256-" + base64.b64encode(digest).decode("ascii") + "'"


CONTENT_SECURITY_POLICY = (
    f"default-src 'none'; style-src {csp_hash(STYLE)}; "
    f"script-src {csp_hash(HEAD_SCRIPT)} {csp_hash(SCRIPT)}; "
    "base-uri 'none'; form-action 'none'"
)


def esc(text: str) -> str:
    return html.escape(text, quote=True)


# 固定文字，不含紀錄內容。
PAGE_TOOLS = (
    '<div class="page-tools">'
    f'<span class="refresh-live">{esc(LOADED_TEXT)}<span class="loaded-at"></span></span>'
    f'<span class="refresh-snapshot">⚠ {esc(SNAPSHOT_TEXT)}</span>'
    f'<button type="button" class="theme-toggle" title="{esc(THEME_TITLE)}">'
    '<span class="theme-system">主題：跟隨系統</span>'
    '<span class="theme-light">主題：淺色</span>'
    '<span class="theme-dark">主題：深色</span></button>'
    "</div>\n"
)
PAUSE_NOTICE = f'<p class="pause-notice" role="status" hidden>{esc(PAUSED_TEXT)}</p>\n'


def inline(text: str) -> str:
    """跳脫後只認 `code` 與 **粗體**；不產生連結。"""
    pieces = CODE_SPAN_PATTERN.split(text)
    rendered: list[str] = []
    for index, piece in enumerate(pieces):
        if index % 2:
            rendered.append(f"<code>{esc(piece)}</code>")
        else:
            rendered.append(BOLD_PATTERN.sub(r"<strong>\1</strong>", esc(piece)))
    return "".join(rendered)


def render_document(title: str, body: str) -> str:
    return (
        "<!doctype html>\n"
        '<html lang="zh-Hant-TW">\n<head>\n<meta charset="utf-8">\n'
        f"{GENERATOR_MARKER}\n"
        '<meta http-equiv="Content-Security-Policy" '
        f'content="{CONTENT_SECURITY_POLICY}">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        '<meta name="color-scheme" content="light dark">\n'
        f"<title>{esc(title)}</title>\n"
        f"<script>{HEAD_SCRIPT}</script>\n"
        f"<style>{STYLE}</style>\n</head>\n<body>\n<main>\n{PAGE_TOOLS}{body}</main>\n"
        f"{PAUSE_NOTICE}<script>{SCRIPT}</script>\n</body>\n</html>\n"
    )


def clock_text(epoch: int) -> str:
    return time.strftime("%H:%M", time.localtime(epoch))


def render_age_stamp(epoch: int, mode: str, label: str) -> str:
    """顯示「label HH:MM（N 分鐘前）」；mode 為 running 時由腳本加上過期提示。"""
    waiting = (
        '<span class="badge badge-waiting">等你決定</span>' if mode == "waiting" else ""
    )
    return (
        f'<span class="age-stamp" data-epoch="{epoch}" '
        f'data-stale-mode="{mode}" data-warn-after="{STALE_WARN_SECONDS}" '
        f'data-alert-after="{STALE_ALERT_SECONDS}">{esc(label)}{clock_text(epoch)}'
        f'<span class="age"></span>{waiting}<span class="stale" hidden></span></span>'
    )


def render_text_block(lines: Sequence[str]) -> str:
    return f'<div class="text">{render_items(group_list_items(lines))}</div>'


def render_items(items: Sequence[ListItem]) -> str:
    """連續同一種的項目放進同一個清單：- 用 <ul>、編號用 <ol>，其他是段落。"""
    parts: list[str] = []
    for kind, run in groupby(items, key=list_kind):
        if kind == "p":
            parts.extend(f"<p>{inline(item.text)}</p>" for item in run)
        else:
            parts.append(f"<{kind}>{''.join(map(render_list_item, run))}</{kind}>")
    return "".join(parts)


def list_kind(item: ListItem) -> str:
    if not item.bullet:
        return "p"
    return "ul" if item.number is None else "ol"


def render_list_item(item: ListItem) -> str:
    """每一項都帶原號（value），跳號也照原號顯示；子項目是裡面的一層清單。"""
    value = "" if item.number is None else f' value="{item.number}"'
    return f"<li{value}>{inline(item.text)}{render_items(item.children)}</li>"


def render_raw(lines: Sequence[str]) -> str:
    text = "\n".join(lines).strip("\n")
    return f'<pre class="raw">{esc(text)}</pre>' if text else ""


def open_section(title: str, extra_class: str = "", attributes: str = "") -> str:
    classes = f"section {extra_class}".strip()
    return f'<section class="{classes}" data-section="{esc(title)}"{attributes}>'


def render_missing_section(title: str) -> str:
    opening = open_section(title, "missing-section", ' role="alert"')
    return (
        f"{opening}<h2>{esc(title)}</h2>"
        "<p>⚠ 紀錄缺少這一區。這不代表「目前沒有」，請 AI 補上。</p></section>\n"
    )


def css_token(name: str) -> str:
    return re.sub(r"\s+", "-", name)


def value_cell(row: Mapping[str, str], column: str) -> str:
    css = esc(f"col-{css_token(column)}")
    if column not in row:
        return f'<td class="{css} missing">{MISSING_CELL}</td>'
    return f'<td class="{css}">{inline(row[column])}</td>'


def table_open(view: TableView, leading: Sequence[str]) -> str:
    headers = [f"<th>{esc(name)}</th>" for name in (*leading, *view.columns)]
    return (
        f'<div class="table-wrap"><table class="{view.spec.css}"><thead><tr>'
        f"{''.join(headers)}</tr></thead><tbody>"
    )


TABLE_END = "</tbody></table></div>"


def table_close(view: TableView) -> str:
    return TABLE_END + render_raw(view.extra_lines)


def render_table_section(view: TableView | None, title: str, summary: str = "") -> str:
    if view is None:
        return render_missing_section(title)
    heading = f"{open_section(title)}<h2>{esc(title)}</h2>"
    if not view.found:
        return f"{heading}{render_raw(view.extra_lines)}</section>\n"
    return f"{heading}{summary}{render_table(view)}</section>\n"


def render_table(view: TableView) -> str:
    """列數超過 open_rows 時，較早的列放進收合的表格，排在最近幾列前面（順序照紀錄）。"""
    leading = ["進度"] if view.spec.marks else []
    total, keep = len(view.rows), view.spec.open_rows
    cut = total - keep if keep is not None and total > keep else 0
    older = ""
    if cut:
        older = (
            f'<details class="older-rows"><summary>較早的 {cut} 列（按一下展開／收合）</summary>'
            f"{table_open(view, leading)}{render_rows(view, range(cut))}{TABLE_END}"
            "</details>"
        )
    recent = render_rows(view, range(cut, total))
    return older + table_open(view, leading) + recent + table_close(view)


def render_rows(view: TableView, indexes: range) -> str:
    return "".join(render_row(view, index) for index in indexes)


def render_row(view: TableView, index: int) -> str:
    """有規定狀態的表格：「狀態」欄上色；工作清單另在最左邊標 ✔／完成／？。"""
    row = view.rows[index]
    status = view.statuses[index] if view.statuses else None
    cells = [mark_cell(status)] if view.spec.marks and status is not None else []
    for column in view.columns:
        if column == STATUS_COLUMN and status is not None:
            cells.append(status_cell(status, view.spec.classes))
        else:
            cells.append(value_cell(row, column))
    data = ""
    if status is not None:
        data = f' data-status="{esc(status.base)}" data-mark="{status.mark}"'
    return f'<tr class="{view.spec.row_css}"{data}>{"".join(cells)}</tr>'


def mark_cell(status: StatusView) -> str:
    """✔ 只給已驗收、已合併；已完成是中性的「完成」。"""
    if status.mark == "check":
        return '<td class="mark" title="已驗收或已合併">✔</td>'
    if status.mark == "complete":
        return '<td class="mark"><span class="badge">完成</span></td>'
    if status.mark == "unknown":
        return '<td class="mark"><span class="badge badge-unknown">？</span></td>'
    return '<td class="mark"></td>'


def label_with_note(css: str, raw: str, base: str, prefix: str = "") -> str:
    """狀態字放在不折行的標籤裡；括號說明放旁邊，照一般文字折行。"""
    note = raw.strip().removeprefix(base).strip() if base else ""
    label = inline(base) if note else inline(raw)
    note_html = f'<span class="status-note">{inline(note)}</span>' if note else ""
    return f'<span class="chip {css}">{prefix}{label}</span>{note_html}'


def status_cell(status: StatusView, classes: Mapping[str, str]) -> str:
    if status.raw is None:
        return f'<td class="col-狀態 missing">{MISSING_CELL}</td>'
    css = classes.get(status.base, "st-unknown")
    if status.mark != "unknown":
        return (
            f'<td class="col-狀態">{label_with_note(css, status.raw, status.base)}</td>'
        )
    return (
        f'<td class="col-狀態">{label_with_note(css, status.raw, status.base, "⚠ ")}'
        '<span class="flag">不是規定的狀態</span></td>'
    )


# ── HTML：紀錄頁 ─────────────────────────────────────────────────


def render_record_page(view: RecordView) -> str:
    body = "".join(
        [
            render_record_header(view),
            render_notices(view),
            render_now_next(view),
            render_decisions(view.decisions),
            render_table_section(view.work, WORK, work_summary(view)),
            render_table_section(view.reviews, REVIEWS),
            render_table_section(view.temp, TEMP, temp_summary(view)),
            render_issues(view.issues),
            render_other_sections(view.record.other_sections),
            render_footer(f"由 {view.source_name} 產生"),
        ]
    )
    return render_document(f"進度｜{view.record.title}", body)


def render_record_header(view: RecordView) -> str:
    record = view.record
    stamp = render_age_stamp(view.modified_epoch, view.stale_mode, "紀錄最後更新：")
    return (
        f'<header><p class="nav"><a href="{INDEX_FILENAME}">← 回總覽</a></p>'
        f"<h1>{esc(record.title)}</h1>"
        f'<p class="meta">任務狀態：{task_state_chip(record.task_state)}　{stamp}</p>'
        f"{render_raw(record.preamble_extra)}</header>\n"
    )


def task_state_chip(state: str | None) -> str:
    if state is None:
        return '<span class="chip st-unknown">⚠ 缺少或看不懂</span>'
    return f'<span class="chip {TASK_STATE_CLASSES[state]}">{esc(state)}</span>'


def render_notices(view: RecordView) -> str:
    if not view.warnings:
        return ""
    items = "".join(f"<li>{esc(warning)}</li>" for warning in view.warnings)
    return (
        '<div class="notice warnings" role="alert">'
        f"<h2>⚠ 格式警告（{len(view.warnings)}）</h2><ul>{items}</ul></div>\n"
    )


def render_now_next(view: RecordView) -> str:
    """進行中的任務頁上方：現在在做什麼、下一步；沒有這些項目就不顯示。"""
    items = render_now_items(view)
    if not items:
        return ""
    heading = f'{open_section(NOW_NEXT, "now-next")}<h2>{esc(NOW_NEXT)}</h2>'
    return f"{heading}<ul>{items}</ul></section>\n"


def render_now_items(view: RecordView) -> str:
    """只有進行中的紀錄才列；總覽與任務頁共用同一份判斷。"""
    if view.record.task_state != RUNNING_STATE:
        return ""
    return "".join(render_now_item(status, row) for status, row in now_and_next(view))


def render_now_item(status: StatusView, row: Mapping[str, str]) -> str:
    """狀態（含括號說明）、項目名稱（工作清單第一欄），備註有寫才附上。"""
    name = inline(next(iter(row.values()), ""))
    note = row.get(NOTE_COLUMN, "")
    if not NO_REASON_PATTERN.fullmatch(note):
        name += f'<span class="item-note"> — {inline(note)}</span>'
    data = f' data-status="{esc(status.base)}"'
    if status.base == TODO_STATUS:
        chip = '<span class="chip st-todo">下一步</span>'
        return f'<li class="next-item"{data}>{chip} {name}</li>'
    chip = label_with_note(STATUS_CLASSES[status.base], status.raw or "", status.base)
    return f'<li class="now-item"{data}>{chip} {name}</li>'


def render_decisions(decisions: DecisionView) -> str:
    if not decisions.present:
        return render_missing_section(DECISIONS)
    count = decisions.count
    pending = count is not None and count > 0
    heading = f"{DECISIONS}（{count} 項）" if pending else DECISIONS
    data_count = "unknown" if count is None else str(count)
    css = "decisions pending" if pending else "decisions"
    opening = open_section(DECISIONS, css, f' data-count="{data_count}"')
    return (
        f"{opening}<h2>{esc(heading)}</h2>"
        f"{render_text_block(decisions.lines)}</section>\n"
    )


def work_summary(view: RecordView) -> str:
    text = f"完成 {view.done_count}／{len(view.statuses)} 項"
    if view.done_count:
        text += f"・其中 {view.checked_count} 項經驗收或合併"
    return f'<p class="meta work-summary">{esc(text)}</p>'


def temp_summary(view: RecordView) -> str:
    count, kept = view.open_temp_count, view.kept_temp_count
    css = "temp-summary open" if count else "temp-summary"
    text = temp_summary_text(view, count, kept)
    return f'<p class="{css}" data-open="{count}" data-kept="{kept}">{esc(text)}</p>'


def temp_summary_text(view: RecordView, count: int, kept: int) -> str:
    if count:
        return f"未清理 {count} 項" + (f"；另保留 {kept} 項（有寫理由）" if kept else "")
    if kept:
        return f"沒有未清理的項目；保留 {kept} 項（有寫理由）。"
    rows = view.temp.rows if view.temp is not None else []
    return "全部已清理。" if rows else "還沒有登記任何暫存項目。"


def render_issues(section: Section | None) -> str:
    if section is None:
        return render_missing_section(ISSUES)
    return (
        f"{open_section(ISSUES)}<h2>{esc(ISSUES)}</h2>"
        f"{render_text_block(section.lines)}</section>\n"
    )


def render_other_sections(
    sections: Sequence[Section], css: str = "other-section"
) -> str:
    return "".join(
        f"{open_section(section.title, css)}<h2>{esc(section.title)}</h2>"
        f"{render_raw(section.lines)}</section>\n"
        for section in sections
    )


def render_footer(source: str) -> str:
    return (
        f"<footer><p>這個網頁{esc(source)}，用一般瀏覽器開啟時每 {REFRESH_SECONDS} 秒"
        "自動重新整理。"
        "紀錄（.md）才是正本，網頁只是方便看。</p></footer>\n"
    )


# ── HTML：總覽頁 ─────────────────────────────────────────────────

OVERVIEW_HEADERS = (
    "任務",
    "任務狀態",
    "紀錄最後更新",
    "需要你決定",
    "進度（完成／全部）",
    "未清暫存",
)


def render_index_page(
    views: Sequence[RecordView],
    result: FolderResult,
    board: Board | None,
    others: Sequence[SummaryEntry],
) -> str:
    """自動彙總先列本專案，再照總覽板的順序列其他專案。"""
    ordered = sort_views(views)
    entries = [
        SummaryEntry(view, overview_title(view.record.stem, view.record.title))
        for view in ordered
    ]
    entries.extend(others)
    body = "".join(
        [
            "<header><h1>進度總覽</h1></header>\n",
            render_folder_notices(result),
            render_decision_summary(entries),
            render_format_summary(entries),
            render_now_next_summary(entries),
            render_board(board, ordered),
            render_overview_table(ordered),
            render_footer(
                "由這個資料夾裡的進度紀錄產生；每個任務的詳細網頁是同名的 .html"
            ),
        ]
    )
    return render_document("進度總覽", body)


def render_decision_summary(entries: Sequence[SummaryEntry]) -> str:
    """每份紀錄「需要你決定的事」的最上層待決項目；已結束的任務照列，直到項目移除。"""
    items = [
        render_decision_entry(entry, item)
        for entry in entries
        for item in entry.view.decisions.items
    ]
    count = len(items)
    heading = f"{SUMMARY_DECISIONS}（{count} 項）" if count else SUMMARY_DECISIONS
    css = "decisions pending" if count else "decisions"
    opening = open_section(SUMMARY_DECISIONS, css, f' data-count="{count}"')
    return f"{opening}<h2>{esc(heading)}</h2>{summary_list(items)}</section>\n"


def render_decision_entry(entry: SummaryEntry, item: ListItem) -> str:
    record = entry.view.record
    state = record.task_state or ""
    finished = ""
    if state == FINISHED_STATE:
        finished = f'<span class="chip st-complete">{esc(FINISHED_STATE)}</span>'
    number = f"{item.number}. " if item.number is not None else ""
    flag = ""
    if item.number is None:
        flag = f'<span class="chip st-unknown decision-flag">⚠ {esc(UNNUMBERED_FLAG)}</span>'
    return (
        f'<li class="decision-item" data-record="{esc(record.stem)}"'
        f'{project_attribute(entry)} data-state="{esc(state)}">'
        f"{entry.title_html}{finished}：{esc(number)}{inline(item.text)}{flag}</li>"
    )


def render_format_summary(entries: Sequence[SummaryEntry]) -> str:
    """有格式警告的任務各列一項與件數（含其他專案）；都沒有就不顯示。"""
    flagged = [entry for entry in entries if entry.view.warnings]
    if not flagged:
        return ""
    total = sum(len(entry.view.warnings) for entry in flagged)
    items = "".join(
        f'<li class="format-item" data-record="{esc(entry.view.record.stem)}"'
        f"{project_attribute(entry)}>{entry.title_html}：{len(entry.view.warnings)} 項</li>"
        for entry in flagged
    )
    opening = open_section(FORMAT_SUMMARY, "format-summary", f' data-count="{total}"')
    return (
        f"{opening}<h2>{esc(FORMAT_SUMMARY)}（{total} 項）</h2>"
        "<p>內容在各任務頁上方；看到就修正紀錄（.md）。</p>"
        f'<ul class="summary-list">{items}</ul></section>\n'
    )


def project_attribute(entry: SummaryEntry) -> str:
    return f' data-project="{esc(entry.project)}"' if entry.project else ""


def render_now_next_summary(entries: Sequence[SummaryEntry]) -> str:
    """進行中的任務各列一項，底下是它現在在做的事與下一步。"""
    tasks: list[str] = []
    for entry in entries:
        items = render_now_items(entry.view)
        if items:
            tasks.append(
                f'<li class="now-task" data-record="{esc(entry.view.record.stem)}"'
                f"{project_attribute(entry)}>{entry.title_html}<ul>{items}</ul></li>"
            )
    heading = f"{open_section(NOW_NEXT)}<h2>{esc(NOW_NEXT)}</h2>"
    return f"{heading}{summary_list(tasks)}</section>\n"


def summary_list(items: Sequence[str]) -> str:
    if not items:
        return "<p>目前沒有。</p>"
    return f'<ul class="summary-list">{"".join(items)}</ul>'


def render_board(board: Board | None, views: Sequence[RecordView]) -> str:
    """總覽板接在自動彙總下面：標題一張卡，其餘 ## 區段原樣顯示。

    有已結束的紀錄比總覽板新時提示可能過期；這是近似判斷，更新總覽板後提示就消失。
    """
    if board is None:
        return ""
    stamp = render_age_stamp(board.modified_epoch, "off", "最後更新：")
    stale = any(
        view.record.task_state == FINISHED_STATE
        and view.modified_epoch > board.modified_epoch
        for view in views
    )
    hint = (
        '<span class="badge badge-unknown board-stale">'
        "⚠ 總覽板可能過期：有已結束的任務紀錄比它新</span>"
    )
    head = (
        f'{open_section(BOARD_TITLE, "board")}<h2>{esc(board.title)}</h2>'
        f'<p class="meta">{esc(BOARD_TITLE)}：{esc(board.name)}　{stamp}'
        f"{hint if stale else ''}</p>{render_raw(board.preamble)}</section>\n"
    )
    return head + render_other_sections(board.sections, "other-section board-section")


def sort_views(views: Sequence[RecordView]) -> list[RecordView]:
    """依紀錄檔（.md）的修改時間由新到舊；同一時間依檔名。"""
    by_name = sorted(views, key=lambda view: view.record.stem)
    return sorted(by_name, key=lambda view: view.modified_epoch, reverse=True)


def render_folder_notices(result: FolderResult) -> str:
    messages = [*result.skipped, *result.failures]
    if not messages:
        return ""
    items = "".join(f"<li>{esc(message)}</li>" for message in messages)
    return (
        '<div class="notice warnings" role="alert">'
        f"<h2>⚠ 有紀錄沒有顯示在總覽（{len(messages)}）</h2><ul>{items}</ul></div>\n"
    )


def render_overview_table(views: Sequence[RecordView]) -> str:
    if not views:
        return '<section class="section"><p>這個資料夾還沒有進度紀錄。</p></section>\n'
    headers = "".join(f"<th>{esc(name)}</th>" for name in OVERVIEW_HEADERS)
    rows = "".join(render_overview_row(view) for view in views)
    return (
        '<section class="section" data-section="總覽"><div class="table-wrap">'
        f'<table class="overview-table"><thead><tr>{headers}</tr></thead>'
        f"<tbody>{rows}</tbody></table></div></section>\n"
    )


def render_overview_row(view: RecordView) -> str:
    """每列的過期判斷用各自 .md 的修改時間，不受其他任務重產影響。"""
    record = view.record
    stamp = render_age_stamp(view.modified_epoch, view.stale_mode, "")
    cells = [
        overview_name_cell(view),
        f'<td class="state" data-state="{esc(record.task_state or "")}">'
        f"{task_state_chip(record.task_state)}</td>",
        f'<td class="updated-cell">{stamp}</td>',
        overview_pending_cell(view.decisions),
        overview_progress_cell(view),
        overview_temp_cell(view),
    ]
    return (
        f'<tr class="overview-row" data-record="{esc(record.stem)}">'
        f"{''.join(cells)}</tr>"
    )


def overview_name_cell(view: RecordView) -> str:
    record = view.record
    badges = ""
    if view.warnings:
        badges = (
            f'<span class="badge badge-unknown">⚠ 格式警告 {len(view.warnings)}</span>'
        )
    return (
        f'<td class="name"><strong>{overview_title(record.stem, record.title)}</strong>'
        f'{badges}<span class="file">網頁：{esc(record.stem)}.html</span></td>'
    )


def overview_title(stem: str, title: str) -> str:
    """連結網址只用已驗證的任務代號；紀錄裡的文字只當顯示用的連結文字（已跳脫）。"""
    if not is_linkable_task_code(stem):
        return esc(title)
    return f'<a class="task-link" href="{stem}.html">{esc(title)}</a>'


def overview_pending_cell(decisions: DecisionView) -> str:
    if decisions.count is None:
        return (
            '<td class="pending" data-count="unknown">'
            '<span class="badge badge-unknown">? 缺少或空白</span></td>'
        )
    if decisions.count:
        return (
            f'<td class="pending" data-count="{decisions.count}">'
            f'<span class="badge badge-pending">{decisions.count} 項</span></td>'
        )
    return '<td class="pending" data-count="0">0</td>'


def overview_progress_cell(view: RecordView) -> str:
    if view.work is None or not view.work.found:
        return (
            '<td class="progress" data-checked="unknown" data-total="unknown" '
            'data-complete="unknown">— 缺少工作清單</td>'
        )
    total = len(view.statuses)
    extra = f'<span class="file">其中 {view.checked_count} 項經驗收或合併</span>'
    return (
        f'<td class="progress" data-checked="{view.checked_count}" data-total="{total}" '
        f'data-complete="{view.complete_count}">完成 {view.done_count}／{total}'
        f"{extra if view.done_count else ''}</td>"
    )


def overview_temp_cell(view: RecordView) -> str:
    if view.temp is None or not view.temp.found:
        return '<td class="temp" data-open="unknown">— 缺少暫存項目</td>'
    count, kept = view.open_temp_count, view.kept_temp_count
    css = "temp open" if count else "temp"
    extra = f'<span class="file">另保留 {kept} 項</span>' if kept else ""
    return (
        f'<td class="{css}" data-open="{count}" data-kept="{kept}">{count} 項{extra}</td>'
    )


# ── 讀寫 ─────────────────────────────────────────────────────────


def write_atomic(path: Path, text: str) -> None:
    """先寫同資料夾的暫存檔，再用 os.replace 換上；失敗時舊檔不動。"""
    descriptor, temp_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temp_path = Path(temp_name)
    try:
        write_descriptor(descriptor, text)
        os.chmod(temp_path, 0o644)
        os.replace(temp_path, path)
    except BaseException:
        temp_path.unlink(missing_ok=True)
        raise


def write_descriptor(descriptor: int, text: str) -> None:
    with open(descriptor, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
        handle.flush()
        os.fsync(handle.fileno())


def read_record(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError) as error:
        raise RenderError(f"讀不到 {path}：{error}") from error


def record_modified_epoch(path: Path) -> int:
    """紀錄檔本身的修改時間；過期提示與總覽排序都以它為準，不受網頁何時重產影響。"""
    try:
        return int(path.stat().st_mtime)
    except OSError as error:
        raise RenderError(f"讀不到 {path} 的修改時間：{error}") from error


def load_view(path: Path) -> RecordView:
    modified = record_modified_epoch(path)
    record = parse_record(read_record(path), path.stem)
    return analyze_record(record, path.name, modified)


def write_record_page(view: RecordView, path: Path) -> Path:
    output = path.with_suffix(".html")
    write_page(output, render_record_page(view))
    return output


def write_page(output: Path, text: str) -> None:
    """寫網頁前先確認：已存在的同名檔必須是這支程式產生的，才換掉。"""
    ensure_replaceable(output)
    try:
        write_atomic(output, text)
    except OSError as error:
        raise RenderError(f"寫不進 {output}：{error}") from error


def ensure_replaceable(path: Path) -> None:
    try:
        info = os.lstat(path)
    except FileNotFoundError:
        return
    except OSError as error:
        raise ForeignFileError(
            f"不覆寫 {path}：讀不到它目前的狀態（{error}）。"
        ) from error
    if not stat.S_ISREG(info.st_mode) or is_link_stat(info):
        raise ForeignFileError(f"不覆寫 {path}：它不是一般檔案，請人類確認後處理。")
    if not has_generator_marker(path):
        raise ForeignFileError(
            f"不覆寫 {path}：這個檔案不是進度網頁產生程式寫的（沒有產生器標記），"
            "請人類確認後處理。"
        )


def has_generator_marker(path: Path) -> bool:
    try:
        with path.open("rb") as handle:
            head = handle.read(MARKER_SCAN_BYTES)
    except OSError:
        return False
    return GENERATOR_MARKER.encode("utf-8") in head


def ensure_progress_folder(folder: Path) -> None:
    """只處理「上一層是 .toukadev 的 progress 資料夾」，避免覆寫其他地方的檔案。"""
    resolved = folder.resolve()
    if resolved.name == PROGRESS_FOLDER and resolved.parent.name == TOUKADEV_FOLDER:
        return
    raise LocationError(
        f"不處理 {folder}：只產生 .toukadev/progress 資料夾裡的進度紀錄，"
        "避免覆寫其他地方的檔案。"
    )


def render_file(path: Path) -> RenderOutcome:
    """產生這份紀錄的網頁，並重產同資料夾的 index.html。"""
    ensure_progress_folder(path.parent)
    view = load_view(path)
    output = write_record_page(view, path)
    result = refresh_index(path, view)
    index = path.parent / INDEX_FILENAME
    return RenderOutcome(
        output,
        tuple(view.warnings),
        index if index in result.outputs else None,
        tuple(result.failures),
        tuple(result.skipped),
    )


def refresh_index(path: Path, view: RecordView) -> FolderResult:
    """總覽讀資料夾內全部紀錄，但只讀不寫：其他紀錄的 .html 不重產。"""
    result = FolderResult()
    try:
        siblings, board = split_board(list_records(path.parent))
    except RenderError as error:
        result.failures.append(str(error))
        return result
    views = [view]
    for sibling in siblings:
        if is_same_file(sibling, path):
            continue
        sibling_view = load_member(sibling, result)
        if sibling_view is not None:
            views.append(sibling_view)
    write_index(path.parent, views, board, result)
    return result


def render_board_file(path: Path) -> FolderResult:
    """只給總覽板 index.md 時：只重產總覽 index.html，任務的網頁都不重產。"""
    ensure_progress_folder(path.parent)
    result = FolderResult()
    tasks, _ = split_board(list_records(path.parent))
    views = [load_member(task, result) for task in tasks]
    write_index(path.parent, [view for view in views if view is not None], path, result)
    return result


def split_board(paths: Sequence[Path]) -> tuple[list[Path], Path | None]:
    """分成任務紀錄與總覽板；大小寫有分的檔案系統上有多份 index.md 時，只讀排序第一份。"""
    boards = [path for path in paths if is_board(path)]
    tasks = [path for path in paths if not is_board(path)]
    return tasks, (boards[0] if boards else None)


def is_same_file(first: Path, second: Path) -> bool:
    try:
        return first.samefile(second)
    except OSError:
        return first.name == second.name


def list_records(folder: Path) -> list[Path]:
    try:
        entries = sorted(folder.iterdir())
    except OSError as error:
        raise RenderError(f"讀不到資料夾 {folder}：{error}") from error
    return [
        path
        for path in entries
        if path.suffix.casefold() == ".md"
        and not path.name.startswith(".")
        and path.is_file()
    ]


def render_folder(folder: Path) -> FolderResult:
    ensure_progress_folder(folder)
    result = FolderResult()
    views: list[RecordView] = []
    tasks, board = split_board(list_records(folder))
    for path in tasks:
        view = render_member(path, result)
        if view is not None:
            views.append(view)
    write_index(folder, views, board, result)
    return result


def render_member(path: Path, result: FolderResult) -> RecordView | None:
    view = load_member(path, result)
    if view is None:
        return None
    try:
        result.outputs.append(write_record_page(view, path))
    except RenderError as error:
        result.failures.append(str(error))
    if view.warnings:
        result.warning_counts[str(path)] = len(view.warnings)
    return view


def load_member(path: Path, result: FolderResult) -> RecordView | None:
    try:
        return load_view(path)
    except RenderError as error:
        result.failures.append(str(error))
        return None


def load_board(path: Path | None, result: FolderResult) -> Board | None:
    if path is None:
        return None
    try:
        modified = record_modified_epoch(path)
        return parse_board(read_record(path), path.name, modified)
    except RenderError as error:
        result.failures.append(str(error))
        return None


def write_index(
    folder: Path,
    views: Sequence[RecordView],
    board_path: Path | None,
    result: FolderResult,
) -> None:
    output = folder / INDEX_FILENAME
    board = load_board(board_path, result)
    others = read_other_projects(board, folder, result)
    try:
        write_page(output, render_index_page(views, result, board, others))
    except RenderError as error:
        result.failures.append(str(error))
    else:
        result.outputs.append(output)


# ── 其他專案（只讀）─────────────────────────────────────────────


def read_other_projects(
    board: Board | None, own_folder: Path, result: FolderResult
) -> list[SummaryEntry]:
    """總覽板「其他專案」的每一行；同一個資料夾只讀一次，讀不到的原因列在總覽上方。"""
    seen = {folder_identity(own_folder)}
    entries: list[SummaryEntry] = []
    for line in other_project_lines(board):
        folder = Path(line)
        problem = other_folder_problem(folder)
        if problem is None and folder_identity(folder) in seen:
            problem = "和這個專案或前面列過的資料夾相同"
        if problem is not None:
            result.skipped.append(f"其他專案 {line}：{problem}，不讀。")
            continue
        seen.add(folder_identity(folder))
        entries.extend(read_other_folder(folder, result))
    return entries


def other_project_lines(board: Board | None) -> list[str]:
    if board is None:
        return []
    for section in board.sections:
        if section.title == OTHER_PROJECTS:
            return [line.strip() for line in section.lines if line.strip()]
    return []


def folder_identity(folder: Path) -> str:
    return os.path.normcase(str(folder.resolve()))


def other_folder_problem(folder: Path) -> str | None:
    """只接受絕對路徑、最後兩段是 .toukadev/progress，而且兩段都是真的資料夾（不是連結）。"""
    if not folder.is_absolute():
        return "不是絕對路徑"
    if folder.name != PROGRESS_FOLDER or folder.parent.name != TOUKADEV_FOLDER:
        return f"最後兩段不是 {TOUKADEV_FOLDER}/{PROGRESS_FOLDER}"
    return entry_problem(folder.parent, True) or entry_problem(folder, True)


def entry_problem(path: Path, want_folder: bool) -> str | None:
    """用 lstat 看路徑本身，連結一律不跟；讀不到或種類不對時回傳原因。"""
    try:
        info = os.lstat(path)
    except OSError as error:
        return f"讀不到 {path.name}（{error}）"
    if is_link_stat(info):
        return f"{path.name} {LINK_TEXT}"
    if want_folder and not stat.S_ISDIR(info.st_mode):
        return f"{path.name} 不是資料夾"
    if not want_folder and not stat.S_ISREG(info.st_mode):
        return f"{path.name} 不是一般檔案"
    return None


def read_other_folder(folder: Path, result: FolderResult) -> list[SummaryEntry]:
    """只讀直接底下的任務紀錄 .md：不遞迴、不讀總覽板 index.md、不替對方重產網頁。"""
    project = folder.parent.parent.name or str(folder.parent.parent)
    try:
        names = sorted(os.listdir(folder))
    except OSError as error:
        result.skipped.append(f"其他專案 {folder}：讀不到資料夾（{error}），不讀。")
        return []
    views: list[RecordView] = []
    for name in names:
        path = folder / name
        if path.suffix.casefold() != ".md" or name.startswith(".") or is_board(path):
            continue
        problem = entry_problem(path, False)
        if problem is None:
            try:
                views.append(load_view(path))
            except RenderError as error:
                problem = str(error)
        if problem is not None:
            result.skipped.append(f"其他專案 {project}：{problem}，不讀。")
    return [
        SummaryEntry(view, other_title(folder, view, project), project)
        for view in sort_views(views)
    ]


def other_title(folder: Path, view: RecordView, project: str) -> str:
    """標出專案；對方已有同名 .html 才用 file: 網址連過去，否則只顯示文字。"""
    title = esc(view.record.title)
    page = folder / f"{view.record.stem}.html"
    if is_linkable_task_code(view.record.stem) and entry_problem(page, False) is None:
        title = f'<a class="task-link" href="{esc(page.as_uri())}">{title}</a>'
    return f'<span class="chip project">{esc(project)}</span>{title}'


# ── 指令列 ───────────────────────────────────────────────────────


def configure_streams() -> None:
    for stream in (sys.stdout, sys.stderr):
        if isinstance(stream, io.TextIOWrapper):
            stream.reconfigure(errors="backslashreplace")


def print_error(message: str) -> None:
    print(message, file=sys.stderr)


def parse_arguments(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="把 ToukaDev 進度紀錄轉成本機網頁。")
    parser.add_argument("path", help="一份進度紀錄 .md，或 .toukadev/progress 資料夾")
    return parser.parse_args(argv)


def report_file(outcome: RenderOutcome) -> int:
    print(outcome.output)
    if outcome.index is not None:
        print(outcome.index)
    if outcome.warnings:
        print_error(
            f"格式警告 {len(outcome.warnings)} 項（詳見網頁上方）：{outcome.output}"
        )
    for message in (*outcome.skipped, *outcome.failures):
        print_error(message)
    return 1 if outcome.failures else 0


def report_folder(result: FolderResult) -> int:
    for output in result.outputs:
        print(output)
    for message in result.skipped:
        print_error(message)
    for name, count in result.warning_counts.items():
        print_error(f"格式警告 {count} 項（詳見網頁上方）：{name}")
    for message in result.failures:
        print_error(message)
    return 1 if result.failures else 0


def unsupported_python_message(version: Sequence[int]) -> str | None:
    if tuple(version[:2]) >= MINIMUM_PYTHON:
        return None
    return (
        f"這支程式需要 Python 3.12 以上，目前是 {version[0]}.{version[1]}。"
        "請改用 3.12 以上的 Python 執行；進度紀錄 .md 照樣可以直接打開閱讀。"
    )


def main(argv: Sequence[str] | None = None) -> int:
    configure_streams()
    too_old = unsupported_python_message(sys.version_info)
    if too_old is not None:
        print_error(too_old)
        return 2
    target = Path(parse_arguments(argv).path)
    try:
        if target.is_dir():
            return report_folder(render_folder(target))
        if target.is_file() and target.suffix.casefold() == ".md":
            if is_board(target):
                return report_folder(render_board_file(target))
            return report_file(render_file(target))
    except UsageError as error:
        print_error(str(error))
        return 2
    except RenderError as error:
        print_error(str(error))
        return 1
    print_error(
        f"找不到進度紀錄：{target}（請給一份 .md 紀錄或 .toukadev/progress 資料夾）"
    )
    return 2


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""
guard_security.py｜安全性靜態檢查（S1–S9）
執行方式：uv run python scripts/guard_security.py
所有檢查通過才輸出 SUCCESS，任一 ERROR 立即阻擋 commit（回傳非零退出碼）。

設計原則：
- 純標準函式庫（不需安裝 gitleaks / bandit / semgrep）。
- 安全檢查「預設全開」——安全不該是 opt-in。誤報用「白名單 + 行尾豁免註解」控制。
- 行尾豁免：在該行尾加 `# guard: <規則>-ok`（前端用 `// guard: <規則>-ok`）即略過，
  且會被計入「已豁免」數字（保持可見、不靜默）。規則代號見各檢查說明。
"""

import ast
import math
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

# ── Windows 主控台編碼修正 ──────────────────────────────────────
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

# ── 專案路徑設定（由 project-init 自動填入 / 各專案調整）──────────────
ROOT = Path(__file__).parent.parent
SRC = ROOT / "src"  # 後端主要程式碼目錄
FRONTEND_SRC = None  # 前端目錄，例：ROOT / "frontend/src"；無前端則 None
ENV_EXAMPLE = ROOT / ".env.example"  # 環境變數範本
GITIGNORE = ROOT / ".gitignore"

# 公開（免認證）的寫入端點白名單。路徑用 {param} 佔位，例："/webhook"、"/todos/{id}"。
# S5 會強制：未認證的寫入端點「必須」明列於此（逼你有意識地宣告公開，而非默默不設防）。
PUBLIC_ROUTES: set[str] = {"/todos", "/todos/{id}", "/todos/{id}/complete"}

# ── 嚴重性等級 ──────────────────────────────────────────────────
# ERROR 🔴 必須修復，阻擋 commit（exit 1）／WARNING 🟡 建議修復／INFO ℹ️ 提示
error_findings: list[str] = []
warning_findings: list[str] = []
info_findings: list[str] = []
suppressed_count = 0

# ── 共用字典 ────────────────────────────────────────────────────
_SENSITIVE_WORDS = (
    "token",
    "jwt",
    "auth",
    "password",
    "passwd",
    "secret",
    "session",
    "credential",
    "api_key",
    "apikey",
    "apikey",
    "email",
    "phone",
    "otp",
    "nonce",
    "csrf",
    "private",
    "access_token",
)
_PLACEHOLDER_WORDS = (
    "example",
    "dummy",
    "placeholder",
    "changeme",
    "your",
    "xxx",
    "fake",
    "test",
    "sample",
    "<",
    ">",
    "...",
    "redacted",
)
_KNOWN_KEY_PATTERNS = [
    r"AKIA[0-9A-Z]{16}",  # AWS access key id
    r"ghp_[A-Za-z0-9]{30,}",  # GitHub personal token
    r"gho_[A-Za-z0-9]{30,}",  # GitHub oauth token
    r"github_pat_[A-Za-z0-9_]{30,}",  # GitHub fine-grained PAT
    r"sk-[A-Za-z0-9]{20,}",  # OpenAI-style secret key
    r"xox[baprs]-[A-Za-z0-9-]{10,}",  # Slack token
    r"AIza[0-9A-Za-z_\-]{35}",  # Google API key
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----",  # PEM private key
]
# 祕密字串的可能字元集（base64/hex 風格）；刻意排除冒號與空白，避免誤判 URL、中文。
_SECRET_CHARSET = re.compile(r"[A-Za-z0-9_\-+/=.]{20,}")
_ENTROPY_BITS_THRESHOLD = 4.0

_line_cache: dict[Path, list[str]] = {}


# ═══════════════════════════════════════════════════════════════
# 共用工具
# ═══════════════════════════════════════════════════════════════


def _rel(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def _lines(path: Path) -> list[str]:
    if path not in _line_cache:
        try:
            _line_cache[path] = path.read_text(encoding="utf-8").splitlines()
        except OSError:
            _line_cache[path] = []
    return _line_cache[path]


def _suppressed(path: Path, lineno: int, rule: str) -> bool:
    if not lineno:
        return False
    rows = _lines(path)
    if lineno > len(rows):
        return False
    line = rows[lineno - 1]
    return f"guard: {rule}-ok" in line or "guard: off" in line


def _emit(level: str, rule: str, path: Path, lineno: int, msg: str) -> None:
    global suppressed_count
    if _suppressed(path, lineno, rule):
        suppressed_count += 1
        return
    loc = f"{_rel(path)}:{lineno}" if lineno else _rel(path)
    finding = f"{rule}｜{loc}｜{msg}"
    {"ERROR": error_findings, "WARNING": warning_findings, "INFO": info_findings}[level].append(
        finding
    )


def _py_files() -> list[Path]:
    return list(SRC.rglob("*.py")) if SRC.exists() else []


def _shannon_bits(text: str) -> float:
    if not text:
        return 0.0
    counts = Counter(text)
    n = len(text)
    return -sum((c / n) * math.log2(c / n) for c in counts.values())


def _looks_placeholder(value: str) -> bool:
    low = value.lower()
    return any(word in low for word in _PLACEHOLDER_WORDS)


def _looks_secret_value(value: str) -> bool:
    """已知金鑰格式，或高熵且非佔位字串。"""
    if any(re.search(p, value) for p in _KNOWN_KEY_PATTERNS):
        return True
    return bool(
        _SECRET_CHARSET.fullmatch(value)
        and _shannon_bits(value) >= _ENTROPY_BITS_THRESHOLD
        and not _looks_placeholder(value)
    )


def _docstring_ids(tree: ast.AST) -> set[int]:
    """收集 module/class/function 的 docstring 節點 id（掃描祕密時略過）。"""
    ids: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = getattr(node, "body", [])
            if (
                body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)
            ):
                ids.add(id(body[0].value))
    return ids


def _git_tracked(rel: str) -> bool | None:
    """回傳 .env 是否被 git 追蹤；非 git 環境 / git 不可用回傳 None。"""
    try:
        out = subprocess.run(
            ["git", "ls-files", rel],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if out.returncode != 0:
        return None
    return bool(out.stdout.strip())


# ═══════════════════════════════════════════════════════════════
# S1：金鑰/密碼進 code 或 git ＋ .env 衛生
# 規則代號：secret
# ═══════════════════════════════════════════════════════════════


def check_secrets_and_env_hygiene() -> None:
    for f in _py_files():
        text = f.read_text(encoding="utf-8")
        for pat in _KNOWN_KEY_PATTERNS:
            for m in re.finditer(pat, text):
                lineno = text.count("\n", 0, m.start()) + 1
                _emit("ERROR", "secret", f, lineno, "疑似硬編碼金鑰（符合已知金鑰格式）")
        try:
            tree = ast.parse(text)
        except SyntaxError:
            continue
        skip = _docstring_ids(tree)
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Constant)
                and isinstance(node.value, str)
                and id(node) not in skip
                and _SECRET_CHARSET.fullmatch(node.value)
                and _shannon_bits(node.value) >= _ENTROPY_BITS_THRESHOLD
                and not _looks_placeholder(node.value)
            ):
                _emit(
                    "ERROR",
                    "secret",
                    f,
                    getattr(node, "lineno", 0),
                    f"疑似高熵祕密字串（長度 {len(node.value)}），請改放 .env",
                )

    # .gitignore 必含 .env
    if GITIGNORE.exists():
        entries = {ln.strip() for ln in GITIGNORE.read_text(encoding="utf-8").splitlines()}
        if not ({".env", ".env*", "*.env", ".env.*"} & entries):
            _emit("ERROR", "secret", GITIGNORE, 0, ".gitignore 未包含 .env（敏感檔可能被提交）")
    else:
        _emit("ERROR", "secret", ROOT / ".gitignore", 0, "缺少 .gitignore")

    # .env 不可被 git 追蹤
    tracked = _git_tracked(".env")
    if tracked is True:
        _emit("ERROR", "secret", ROOT / ".env", 0, ".env 已被 git 追蹤，請 `git rm --cached .env`")
    elif tracked is None:
        info_findings.append("secret｜（略過 .env 追蹤檢查：非 git 環境或 git 不可用）")


# ═══════════════════════════════════════════════════════════════
# S2：.env.example 與設定層同步
# 規則代號：envsync
# ═══════════════════════════════════════════════════════════════


def _is_settings_class(node: ast.ClassDef) -> bool:
    for base in node.bases:
        name = base.attr if isinstance(base, ast.Attribute) else getattr(base, "id", "")
        if name.endswith("Settings"):
            return True
    return False


def _is_os_env_call(node: ast.Call) -> bool:
    fn = node.func
    if isinstance(fn, ast.Attribute):
        if fn.attr == "getenv" and isinstance(fn.value, ast.Name) and fn.value.id == "os":
            return True
        if fn.attr == "get" and isinstance(fn.value, ast.Attribute) and fn.value.attr == "environ":
            return True
    return False


def _collect_env_keys_from_src() -> set[str]:
    keys: set[str] = set()
    for f in _py_files():
        try:
            tree = ast.parse(f.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and _is_os_env_call(node) and node.args:
                arg = node.args[0]
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    keys.add(arg.value.upper())
            elif (
                isinstance(node, ast.Subscript)
                and isinstance(node.value, ast.Attribute)
                and node.value.attr == "environ"
                and isinstance(node.slice, ast.Constant)
                and isinstance(node.slice.value, str)
            ):
                keys.add(node.slice.value.upper())
            elif isinstance(node, ast.ClassDef) and _is_settings_class(node):
                for stmt in node.body:
                    if (
                        isinstance(stmt, ast.AnnAssign)
                        and isinstance(stmt.target, ast.Name)
                        and stmt.target.id != "model_config"
                        and not stmt.target.id.startswith("_")
                    ):
                        keys.add(stmt.target.id.upper())
    return keys


def _parse_env_example() -> dict[str, str] | None:
    if not ENV_EXAMPLE.exists():
        return None
    out: dict[str, str] = {}
    for raw in ENV_EXAMPLE.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        out[key.strip().upper()] = value.split("#", 1)[0].strip()
    return out


def check_env_example_sync() -> None:
    src_keys = _collect_env_keys_from_src()
    example = _parse_env_example()
    if example is None:
        if src_keys:
            _emit(
                "ERROR",
                "envsync",
                ROOT / ".env.example",
                0,
                "程式有讀環境變數，但缺少 .env.example",
            )
        return
    for key in sorted(src_keys - set(example)):
        _emit("ERROR", "envsync", ENV_EXAMPLE, 0, f"環境變數 {key} 未同步到 .env.example")
    for key, value in example.items():
        if value and _looks_secret_value(value):
            _emit(
                "ERROR",
                "envsync",
                ENV_EXAMPLE,
                0,
                f"{key} 的範本值疑似真實祕密（.env.example 應只放假值）",
            )


# ═══════════════════════════════════════════════════════════════
# S3：字串拼接 SQL（規則代號：sql）── 於後續任務實作
# ═══════════════════════════════════════════════════════════════


def _func_ranges(tree: ast.AST) -> list[tuple[str, int, int]]:
    return [
        (n.name, n.lineno, getattr(n, "end_lineno", n.lineno))
        for n in ast.walk(tree)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]


def _enclosing_func(funcs: list[tuple[str, int, int]], lineno: int) -> str:
    best, best_start = "", -1
    for name, start, end in funcs:
        if start <= lineno <= end and start > best_start:
            best, best_start = name, start
    return best


def _context_has(words: tuple[str, ...], func_name: str, line: str) -> bool:
    ctx = f"{func_name} {line}".lower()
    return any(w in ctx for w in words)


_SQL_EXEC_METHODS = {"execute", "executemany", "executescript", "exec_driver_sql"}


def _is_dynamic_sql(arg: ast.expr) -> bool:
    if isinstance(arg, ast.JoinedStr):  # f-string
        return True
    if isinstance(arg, ast.BinOp) and isinstance(arg.op, (ast.Add, ast.Mod)):  # + / %
        return True
    return bool(
        isinstance(arg, ast.Call)
        and isinstance(arg.func, ast.Attribute)
        and arg.func.attr == "format"
    )


def check_sql_string_concat() -> None:
    for f in _py_files():
        try:
            tree = ast.parse(f.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr in _SQL_EXEC_METHODS
                and node.args
                and _is_dynamic_sql(node.args[0])
            ):
                _emit(
                    "ERROR",
                    "sql",
                    f,
                    node.lineno,
                    "SQL 以字串拼接組成（f-string／+／%／.format），請改用參數化查詢或 ORM",
                )


# ═══════════════════════════════════════════════════════════════
# S4：敏感資料進 localStorage（規則代號：localstorage）── 後續實作
# ═══════════════════════════════════════════════════════════════

_LS_SENSITIVE = re.compile(
    r"(token|jwt|auth|password|passwd|secret|session|api[_-]?key|credential|email|phone)",
    re.IGNORECASE,
)
_LS_SETITEM = re.compile(r"""localStorage\.setItem\(\s*['"`]([^'"`]+)['"`]""")
_FRONTEND_GLOBS = ("*.ts", "*.tsx", "*.js", "*.jsx")


def check_localstorage_sensitive() -> None:
    if not FRONTEND_SRC or not FRONTEND_SRC.exists():
        return  # 無前端目錄：此檢查不適用
    files: list[Path] = []
    for glob in _FRONTEND_GLOBS:
        files += list(FRONTEND_SRC.rglob(glob))
    for f in files:
        for i, line in enumerate(_lines(f), 1):
            for m in _LS_SETITEM.finditer(line):
                key = m.group(1)
                if _LS_SENSITIVE.search(key):
                    _emit(
                        "ERROR",
                        "localstorage",
                        f,
                        i,
                        f"敏感資料 '{key}' 寫入 localStorage；token 應放 httpOnly cookie、勿存敏感資料",
                    )
                else:
                    _emit(
                        "WARNING",
                        "localstorage",
                        f,
                        i,
                        "直接使用 localStorage；建議集中封裝且只存非敏感 UI 偏好",
                    )


# ═══════════════════════════════════════════════════════════════
# S5：寫入端點缺認證（規則代號：endpoint）── 後續實作
# ═══════════════════════════════════════════════════════════════

_WRITE_METHODS = {"post", "put", "delete", "patch"}
_AUTH_DEP_WORDS = (
    "auth",
    "identity",
    "current_user",
    "verify",
    "login",
    "jwt",
    "principal",
    "require",
    "token",
)


def _router_prefixes(tree: ast.AST) -> dict[str, str]:
    """router/app 變數名 → 路徑前綴（APIRouter(prefix=...)；FastAPI()=""）。"""
    prefixes: dict[str, str] = {}
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Assign) and isinstance(node.value, ast.Call)):
            continue
        callee = node.value.func
        name = callee.attr if isinstance(callee, ast.Attribute) else getattr(callee, "id", "")
        if name not in {"APIRouter", "FastAPI"}:
            continue
        prefix = ""
        for kw in node.value.keywords:
            if kw.arg == "prefix" and isinstance(kw.value, ast.Constant):
                prefix = str(kw.value.value)
        for tgt in node.targets:
            if isinstance(tgt, ast.Name):
                prefixes[tgt.id] = prefix
    return prefixes


def _norm_route(path: str) -> str:
    return re.sub(r"\{[^}]+\}", "{}", path.rstrip("/")) or "/"


def _has_auth_dep(func: ast.AST) -> bool:
    for node in ast.walk(func.args):
        is_depends = isinstance(node, ast.Call) and (
            (isinstance(node.func, ast.Name) and node.func.id == "Depends")
            or (isinstance(node.func, ast.Attribute) and node.func.attr == "Depends")
        )
        if is_depends and node.args:
            inner = node.args[0]
            inner_name = (
                inner.attr if isinstance(inner, ast.Attribute) else getattr(inner, "id", "")
            )
            if any(w in inner_name.lower() for w in _AUTH_DEP_WORDS):
                return True
    return False


def check_endpoint_auth() -> None:
    public = {_norm_route(p) for p in PUBLIC_ROUTES}
    for f in _py_files():
        try:
            tree = ast.parse(f.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        prefixes = _router_prefixes(tree)
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for deco in node.decorator_list:
                if not (isinstance(deco, ast.Call) and isinstance(deco.func, ast.Attribute)):
                    continue
                if deco.func.attr not in _WRITE_METHODS:
                    continue
                router_name = getattr(deco.func.value, "id", "")
                if router_name not in prefixes:
                    continue
                subpath = (
                    str(deco.args[0].value)
                    if (deco.args and isinstance(deco.args[0], ast.Constant))
                    else ""
                )
                raw = prefixes[router_name] + subpath
                if not _has_auth_dep(node) and _norm_route(raw) not in public:
                    _emit(
                        "ERROR",
                        "endpoint",
                        f,
                        node.lineno,
                        f"寫入端點 {raw} 無認證依賴；若確定公開請列入 PUBLIC_ROUTES",
                    )


# ═══════════════════════════════════════════════════════════════
# S6：錯誤訊息洩漏（規則代號：errleak）── 後續實作
# ═══════════════════════════════════════════════════════════════

_EXC_VARS = {"e", "ex", "err", "exc", "error", "exception"}


def _detail_leaks_exception(value: ast.expr) -> bool:
    if (
        isinstance(value, ast.Call)
        and isinstance(value.func, ast.Name)
        and value.func.id == "str"
        and value.args
        and isinstance(value.args[0], ast.Name)
        and value.args[0].id in _EXC_VARS
    ):
        return True
    if isinstance(value, ast.JoinedStr):
        return any(
            isinstance(v, ast.FormattedValue)
            and isinstance(v.value, ast.Name)
            and v.value.id in _EXC_VARS
            for v in value.values
        )
    return False


def check_error_leak() -> None:
    for f in _py_files():
        try:
            tree = ast.parse(f.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        uses_traceback = False
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                for kw in node.keywords:
                    if (
                        kw.arg == "debug"
                        and isinstance(kw.value, ast.Constant)
                        and kw.value.value is True
                    ):
                        _emit(
                            "ERROR",
                            "errleak",
                            f,
                            node.lineno,
                            "debug=True 會把系統細節暴露給使用者，正式環境必須關閉",
                        )
                fn = node.func
                is_http_exc = (isinstance(fn, ast.Name) and fn.id == "HTTPException") or (
                    isinstance(fn, ast.Attribute) and fn.attr == "HTTPException"
                )
                if is_http_exc:
                    for kw in node.keywords:
                        if kw.arg == "detail" and _detail_leaks_exception(kw.value):
                            _emit(
                                "ERROR",
                                "errleak",
                                f,
                                node.lineno,
                                "錯誤回應夾帶原始例外（str(e)/f-string）；請回傳通用訊息、細節只進 log",
                            )
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "format_exc"
            ):
                uses_traceback = True
        if uses_traceback:
            _emit(
                "WARNING",
                "errleak",
                f,
                0,
                "檔案使用 traceback.format_exc()；切勿把其內容回傳給使用者",
            )


# ═══════════════════════════════════════════════════════════════
# S7：弱雜湊（規則代號：hash）── 後續實作
# ═══════════════════════════════════════════════════════════════

_PASSWORD_WORDS = ("pass", "pwd", "password", "passwd", "secret", "credential")


def _weak_hash_algo(node: ast.AST) -> str | None:
    if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
        return None
    fn = node.func
    if isinstance(fn.value, ast.Name) and fn.value.id == "hashlib":
        if fn.attr in {"md5", "sha1"}:
            return fn.attr
        if fn.attr == "new" and node.args and isinstance(node.args[0], ast.Constant):
            algo = str(node.args[0].value).lower()
            if algo in {"md5", "sha1"}:
                return algo
    return None


def check_weak_hash() -> None:
    for f in _py_files():
        rows = _lines(f)
        try:
            tree = ast.parse(f.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        funcs = _func_ranges(tree)
        for node in ast.walk(tree):
            algo = _weak_hash_algo(node)
            if not algo:
                continue
            line = rows[node.lineno - 1] if node.lineno <= len(rows) else ""
            if _context_has(_PASSWORD_WORDS, _enclosing_func(funcs, node.lineno), line):
                _emit(
                    "ERROR",
                    "hash",
                    f,
                    node.lineno,
                    f"密碼/祕密使用弱雜湊 {algo}，請改用 bcrypt/argon2/scrypt",
                )
            else:
                _emit(
                    "WARNING",
                    "hash",
                    f,
                    node.lineno,
                    f"使用弱雜湊 {algo}；若非安全用途請加 `# guard: hash-ok`（或 usedforsecurity=False）",
                )


# ═══════════════════════════════════════════════════════════════
# S8：非密碼學 RNG 生 token（規則代號：rng）── 後續實作
# ═══════════════════════════════════════════════════════════════

_RNG_WORDS = (
    "token",
    "secret",
    "session",
    "otp",
    "nonce",
    "csrf",
    "password",
    "passwd",
    "credential",
)
_RNG_FILE_HINTS = ("auth", "token", "session", "secret", "security", "login")


def _is_random_call(node: ast.AST) -> bool:
    return bool(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "random"
    )


def check_weak_rng_tokens() -> None:
    for f in _py_files():
        rows = _lines(f)
        try:
            tree = ast.parse(f.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        funcs = _func_ranges(tree)
        for node in ast.walk(tree):
            if not _is_random_call(node):
                continue
            line = rows[node.lineno - 1] if node.lineno <= len(rows) else ""
            if _context_has(_RNG_WORDS, _enclosing_func(funcs, node.lineno), line):
                _emit(
                    "ERROR",
                    "rng",
                    f,
                    node.lineno,
                    "用非密碼學 random 生成 token/secret，請改用 secrets.token_urlsafe / uuid4",
                )
        imports_random = any(
            isinstance(n, ast.Import) and any(a.name == "random" for a in n.names)
            for n in ast.walk(tree)
        )
        if imports_random and any(h in f.stem.lower() for h in _RNG_FILE_HINTS):
            _emit(
                "WARNING",
                "rng",
                f,
                0,
                "認證/安全相關檔案 import random；token/secret 請改用 secrets 模組",
            )


# ═══════════════════════════════════════════════════════════════
# S9：無 schema 的請求輸入（規則代號：rawbody）── 後續實作
# ═══════════════════════════════════════════════════════════════


def check_schemaless_request() -> None:
    for f in _py_files():
        try:
            tree = ast.parse(f.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr in {"json", "get_json"}
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id in {"request", "req"}
            ):
                _emit(
                    "ERROR",
                    "rawbody",
                    f,
                    node.lineno,
                    "直接讀原始請求 body（request.json）；請改用 Pydantic/typed schema 驗證",
                )


# ═══════════════════════════════════════════════════════════════
# 執行器
# ═══════════════════════════════════════════════════════════════


def main() -> int:
    print("🔒 執行安全性靜態檢查（S1–S9）...")

    check_secrets_and_env_hygiene()  # S1 → ERROR
    check_env_example_sync()  # S2 → ERROR
    check_sql_string_concat()  # S3 → ERROR
    check_localstorage_sensitive()  # S4 → ERROR/WARNING
    check_endpoint_auth()  # S5 → ERROR
    check_error_leak()  # S6 → ERROR/WARNING
    check_weak_hash()  # S7 → ERROR/WARNING
    check_weak_rng_tokens()  # S8 → ERROR/WARNING
    check_schemaless_request()  # S9 → ERROR

    if error_findings:
        print(f"\n🔴 ERROR（必須修復，阻擋 commit）：共 {len(error_findings)} 個")
        for i, e in enumerate(error_findings, 1):
            print(f"  {i}. {e}")
    if warning_findings:
        print(f"\n🟡 WARNING（建議修復）：共 {len(warning_findings)} 個")
        for i, e in enumerate(warning_findings, 1):
            print(f"  {i}. {e}")
    if info_findings:
        print(f"\nℹ️  INFO：共 {len(info_findings)} 個")
        for i, e in enumerate(info_findings, 1):
            print(f"  {i}. {e}")

    print("\n--- 安全檢查結果 ---")
    print(f"🔴 ERROR  ：{len(error_findings)} 個")
    print(f"🟡 WARNING：{len(warning_findings)} 個")
    print(f"ℹ️  INFO   ：{len(info_findings)} 個")
    print(f"🙈 已豁免  ：{suppressed_count} 個（# guard: <規則>-ok）")

    if error_findings:
        print("\n❌ 有安全性 ERROR，請修復後再 commit。")
        return 1
    print("\n✅ 無安全性 ERROR，可以繼續。")
    return 0


if __name__ == "__main__":
    sys.exit(main())

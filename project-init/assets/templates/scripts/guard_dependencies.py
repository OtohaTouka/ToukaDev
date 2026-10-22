#!/usr/bin/env python3
"""
guard_dependencies.py｜Docker 依賴性與 Import 靜態檢查
執行方式：uv run python scripts/guard_dependencies.py

檢查兩件事：
1. docker-compose.yml 的服務依賴關係是否有循環依賴或缺少定義
2. 專案 Python import 是否對應到已安裝的套件（避免無限重啟）
"""

import ast
import re
import sys
from pathlib import Path

# Windows cp950 終端機無法輸出 emoji，會 UnicodeEncodeError；強制改用 UTF-8。
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

try:
    import yaml
except ImportError:
    print("❌ 缺少 pyyaml，請執行：uv add --dev pyyaml")
    sys.exit(1)

ROOT = Path(__file__).parent.parent
DOCKER_COMPOSE = ROOT / "docker-compose.yml"
SRC = ROOT / "src"
REQUIREMENTS = ROOT / "pyproject.toml"

errors: list[str] = []

# ── 1. Docker Compose 依賴性檢查 ─────────────────────────────────────


def check_docker_compose_dependencies() -> None:
    """
    檢查 docker-compose.yml：
    - 所有 depends_on 引用的服務必須存在
    - 不得有循環依賴（A depends_on B，B depends_on A）
    """
    if not DOCKER_COMPOSE.exists():
        return  # 無 docker-compose.yml 則跳過

    try:
        with open(DOCKER_COMPOSE, encoding="utf-8") as f:
            compose = yaml.safe_load(f)
    except yaml.YAMLError as e:
        errors.append(f"Docker Compose｜YAML 解析錯誤：{e}")
        return

    services = compose.get("services", {})
    defined = set(services.keys())

    # 檢查 depends_on 引用是否存在
    for service, config in services.items():
        depends = config.get("depends_on", [])
        if isinstance(depends, dict):
            depends = list(depends.keys())
        for dep in depends:
            if dep not in defined:
                errors.append(
                    f"Docker 依賴｜服務 {service} 的 depends_on 引用了"
                    f"不存在的服務：{dep}"
                )

    # 檢查循環依賴（DFS）
    def has_cycle(service: str, visited: set, stack: set) -> bool:
        visited.add(service)
        stack.add(service)
        config = services.get(service, {})
        deps = config.get("depends_on", [])
        if isinstance(deps, dict):
            deps = list(deps.keys())
        for dep in deps:
            if dep not in visited:
                if has_cycle(dep, visited, stack):
                    return True
            elif dep in stack:
                return True
        stack.discard(service)
        return False

    visited: set = set()
    for service in defined:
        if service not in visited:
            if has_cycle(service, visited, set()):
                errors.append(f"Docker 依賴｜偵測到循環依賴，涉及服務：{service}")


# ── 2. Python Import 可解析性檢查 ───────────────────────────────────


def check_python_imports() -> None:
    """
    掃描 src/ 下所有 .py 檔案的頂層 import，
    確認第三方套件已在 pyproject.toml 或 requirements.txt 中定義。
    標準函式庫自動排除。
    """
    stdlib_modules = (
        set(sys.stdlib_module_names) if hasattr(sys, "stdlib_module_names") else set()
    )

    # 從 pyproject.toml 讀取已宣告的依賴
    declared: set[str] = set()
    if REQUIREMENTS.exists():
        content = REQUIREMENTS.read_text(encoding="utf-8")
        # 簡單掃描 [project.dependencies] 和 [tool.uv.dev-dependencies]
        pkgs = re.findall(r'^\s+"?([a-zA-Z0-9_\-]+)', content, re.MULTILINE)
        declared = {p.lower().replace("-", "_") for p in pkgs}

    # 也接受 requirements.txt
    req_txt = ROOT / "requirements.txt"
    if req_txt.exists():
        for line in req_txt.read_text(encoding="utf-8").splitlines():
            line = line.strip().split("==")[0].split(">=")[0].split("[")[0]
            if line and not line.startswith("#"):
                declared.add(line.lower().replace("-", "_"))

    py_files = list(SRC.rglob("*.py")) if SRC.exists() else []
    for f in py_files:
        try:
            tree = ast.parse(f.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    pkg = alias.name.split(".")[0].lower().replace("-", "_")
                    _check_pkg(pkg, f, stdlib_modules, declared)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    pkg = node.module.split(".")[0].lower().replace("-", "_")
                    _check_pkg(pkg, f, stdlib_modules, declared)


def _check_pkg(
    pkg: str,
    f: Path,
    stdlib: set,
    declared: set,
) -> None:
    """判斷套件是否為標準函式庫或已宣告依賴，否則回報錯誤。"""
    if not pkg or pkg in stdlib or pkg == "src":
        return
    # 相對 import 或本地模組
    if (SRC / pkg).exists() or (SRC / f"{pkg}.py").exists():
        return
    if pkg not in declared:
        errors.append(
            f"Import 未宣告｜{f.relative_to(ROOT)}｜"
            f"套件 {pkg!r} 未在 pyproject.toml 或 requirements.txt 中定義"
        )


# ── 執行器 ───────────────────────────────────────────────────────────


def main() -> int:
    print("🔍 執行依賴性檢查...")

    check_docker_compose_dependencies()
    check_python_imports()

    if errors:
        print(f"\n❌ 發現 {len(errors)} 個依賴問題：\n")
        for i, e in enumerate(errors, 1):
            print(f"  {i}. {e}")
        print("\n請修復以上問題後重新執行。")
        return 1

    print("✅ 依賴性檢查通過，零問題。")
    return 0


if __name__ == "__main__":
    sys.exit(main())

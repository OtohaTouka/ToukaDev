import tomllib
from pathlib import Path
from unittest import TestCase


ROOT = Path(__file__).resolve().parents[1]


class RootToolchainContractTests(TestCase):
    def test_root_uv_project_contract_is_declared(self) -> None:
        pyproject_path = ROOT / "pyproject.toml"
        python_version_path = ROOT / ".python-version"

        self.assertTrue(pyproject_path.is_file(), "root pyproject.toml is required")
        self.assertTrue(
            python_version_path.is_file(), "root .python-version is required"
        )

        pyproject = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
        self.assertEqual(pyproject["project"]["requires-python"], ">=3.12,<3.13")
        self.assertEqual(
            pyproject["dependency-groups"]["dev"],
            ["pytest==9.1.1", "ruff==0.16.0"],
        )
        self.assertFalse(pyproject["tool"]["uv"]["package"])
        self.assertEqual(pyproject["tool"]["uv"]["cache-dir"], ".uv-cache")
        self.assertEqual(pyproject["tool"]["uv"]["required-version"], "==0.12.1")
        self.assertEqual(
            pyproject["tool"]["pytest"]["ini_options"]["cache_dir"],
            ".uv-cache/pytest",
        )
        self.assertEqual(
            pyproject["tool"]["pytest"]["ini_options"]["pythonpath"], ["."]
        )
        self.assertEqual(
            python_version_path.read_text(encoding="utf-8").strip(), "3.12"
        )

    def test_root_uv_runtime_artifacts_are_ignored(self) -> None:
        ignore_entries = {
            line.strip()
            for line in (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        }

        self.assertIn(".venv/", ignore_entries)
        self.assertIn(".uv-cache/", ignore_entries)

    def test_framework_quick_profile_uses_locked_uv_environment(self) -> None:
        agents_lines = (ROOT / "AGENTS.md").read_text(encoding="utf-8").splitlines()

        self.assertEqual(
            1,
            agents_lines.count("- `uv run --locked python scripts/guard_framework.py`"),
        )

    def test_ci_uses_the_locked_root_environment(self) -> None:
        workflow_text = (
            ROOT / ".github" / "workflows" / "framework-guard.yml"
        ).read_text(encoding="utf-8")

        self.assertIn(
            "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1",
            workflow_text,
        )
        self.assertIn(
            "astral-sh/setup-uv@c771a70e6277c0a99b617c7a806ffedaca235ff9",
            workflow_text,
        )
        self.assertIn('version-file: "pyproject.toml"', workflow_text)
        for command in (
            "uv sync --locked",
            "uv run --locked pytest tests",
            "uv run --locked ruff check",
            "uv run --locked python scripts/guard_framework.py",
        ):
            with self.subTest(command=command):
                self.assertIn(command, workflow_text)

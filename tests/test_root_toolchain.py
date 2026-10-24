import re
import tomllib
from pathlib import Path
from unittest import TestCase


ROOT = Path(__file__).resolve().parents[1]
# CI installs one exact uv version; local runs accept it or newer (ADR-048).
CI_UV_VERSION = "0.12.1"
PINNED_ACTION = re.compile(r"uses: ([\w.-]+/[\w.-]+)@([0-9a-f]{40}) # v\d+(\.\d+)*$")


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
        # Exact pins, not fixed versions, so a dependency update PR can stay green.
        dev_group = pyproject["dependency-groups"]["dev"]
        self.assertEqual(
            [entry.split("==")[0] for entry in dev_group], ["pytest", "ruff"]
        )
        for entry in dev_group:
            with self.subTest(entry=entry):
                self.assertRegex(entry, r"^[a-z]+==\d+\.\d+\.\d+$")
        self.assertFalse(pyproject["tool"]["uv"]["package"])
        self.assertEqual(pyproject["tool"]["uv"]["cache-dir"], ".uv-cache")
        self.assertEqual(
            pyproject["tool"]["uv"]["required-version"], f">={CI_UV_VERSION}"
        )
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

        # Every action is pinned to a commit SHA with its version as a comment;
        # the SHA itself may change in an update PR.
        uses_lines = [
            line.strip().removeprefix("- ")
            for line in workflow_text.splitlines()
            if line.strip().removeprefix("- ").startswith("uses:")
        ]
        matches = [PINNED_ACTION.match(line) for line in uses_lines]
        for line, match in zip(uses_lines, matches):
            with self.subTest(uses=line):
                self.assertIsNotNone(match, "actions must be pinned to a commit SHA")
        self.assertEqual(
            [match.group(1) for match in matches if match],
            ["actions/checkout", "astral-sh/setup-uv"],
        )
        self.assertIn(f'version: "{CI_UV_VERSION}"', workflow_text)
        self.assertNotIn("version-file:", workflow_text)
        for command in (
            "uv sync --locked",
            "uv run --locked pytest tests",
            "uv run --locked ruff check",
            "uv run --locked python scripts/guard_framework.py",
        ):
            with self.subTest(command=command):
                self.assertIn(command, workflow_text)

    def test_dependabot_version_updates_target_dev(self) -> None:
        # Update PRs follow CONTRIBUTING's branch flow: into dev, never straight
        # into main. No YAML parser in the dev tools, so check the exact lines.
        config = ROOT / ".github" / "dependabot.yml"
        lines = config.read_text(encoding="utf-8").splitlines()
        # Every item of `updates` starts a section, whatever key it begins with,
        # so an extra entry cannot hide inside the previous one.
        sections: list[list[str]] = []
        for line in lines:
            if line.startswith("  -"):
                sections.append([line])
            elif sections:
                sections[-1].append(line)
        for section in sections:
            with self.subTest(entry=section[0]):
                self.assertTrue(section[0].startswith("  - package-ecosystem:"))
        self.assertEqual(
            [section[0].split(":", 1)[1].strip().strip('"') for section in sections],
            ["github-actions", "uv"],
        )
        for section in sections:
            with self.subTest(ecosystem=section[0]):
                # Same indent as `directory:`, exactly once, nowhere else in the
                # entry (not nested under schedule or cooldown, not commented out).
                self.assertIn('    directory: "/"', section)
                mentions = [line for line in section if "target-branch" in line]
                self.assertEqual(mentions, ['    target-branch: "dev"'])

"""What project-init copies to other people's projects stays neutral and pinned (ADR-048)."""

import re
from pathlib import Path
from unittest import TestCase

from scripts import guard_framework


ROOT = Path(__file__).resolve().parents[1]
CI_TEMPLATES = ROOT / "project-init" / "assets" / "templates" / "ci"
DOCKERFILE_TEMPLATE = ROOT / "project-init" / "assets" / "templates" / "docker" / "Dockerfile"
# Personal preferences of the ToukaDev maintainers; they live outside the shared block.
PERSONAL_PREFERENCES = ("繁體中文", "隨性", "言簡意賅", "客套開場", "安全性僅在")
MAINTAINER_PREFERENCE_LINE = "- 一律使用繁體中文；語氣隨性、言簡意賅，直接給重點，不用客套開場。"
PINNED_ACTION = re.compile(r"uses: ([\w.-]+/[\w.-]+)@[0-9a-f]{40} # v\d+(\.\d+)*$")
# Templates outside GitHub Actions run in uv's official image, pinned to a uv and Python version.
UV_IMAGE = re.compile(r"image: ghcr\.io/astral-sh/uv:\d+\.\d+\.\d+-python\d+\.\d+-[a-z]+-slim$")
IMAGE_TEMPLATES = ("bitbucket-pipelines.yml", "circleci-config.yml", "gitlab-ci.yml")
BARE_TOOL = re.compile(r"(^|[-:|]\s*)(pytest|ruff|mkdocs|python)\s")
PIP_INSTALL = re.compile(r"\bpip[\d.]*\s+install\b")
UNLOCKED_UV = re.compile(r"\buv (run|sync)\b(?! --locked)")


def _active_lines(path: Path) -> list[str]:
    """Lines that run, without YAML comments."""
    lines = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            lines.append(stripped)
    return lines


class SharedBlockNeutralTests(TestCase):
    def test_shared_block_has_no_personal_communication_preferences(self) -> None:
        shared = guard_framework.extract_shared_rules(ROOT / "AGENTS.md")
        self.assertIsNotNone(shared)
        for preference in PERSONAL_PREFERENCES:
            with self.subTest(preference=preference):
                self.assertNotIn(preference, shared)

    def test_maintainer_preferences_stay_in_the_framework_section(self) -> None:
        text = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
        outside = text.replace(guard_framework.extract_shared_rules(ROOT / "AGENTS.md"), "")
        self.assertEqual(1, outside.splitlines().count(MAINTAINER_PREFERENCE_LINE))


class CiTemplateTests(TestCase):
    def test_ci_templates_install_with_uv_only(self) -> None:
        for path in sorted(CI_TEMPLATES.iterdir()):
            for line in _active_lines(path):
                with self.subTest(template=path.name, line=line):
                    self.assertIsNone(PIP_INSTALL.search(line), "install with uv")
                    self.assertIsNone(
                        BARE_TOOL.search(line), "run tools through `uv run --locked`"
                    )
                    self.assertIsNone(UNLOCKED_UV.search(line), "add `--locked`")

    def test_ci_templates_run_in_a_pinned_uv_image(self) -> None:
        for name in IMAGE_TEMPLATES:
            images = [
                line.removeprefix("- ")
                for line in _active_lines(CI_TEMPLATES / name)
                if line.removeprefix("- ").startswith("image:")
            ]
            with self.subTest(template=name):
                self.assertEqual(1, len(images))
                self.assertRegex(images[0], UV_IMAGE)

    def test_github_actions_template_pins_actions_and_reads_only(self) -> None:
        lines = _active_lines(CI_TEMPLATES / "github-actions-ci.yml")
        uses = [line.removeprefix("- ") for line in lines if "uses:" in line]
        self.assertTrue(uses)
        for line in uses:
            with self.subTest(uses=line):
                self.assertRegex(line, PINNED_ACTION)
        self.assertIn("permissions:", lines)
        self.assertIn("contents: read", lines)
        self.assertIn("persist-credentials: false", lines)
        self.assertIn("run: uv sync --locked", lines)

    def test_dockerfile_template_pins_uv(self) -> None:
        lines = _active_lines(DOCKERFILE_TEMPLATE)
        copies = [line for line in lines if "ghcr.io/astral-sh/uv" in line]
        self.assertEqual(1, len(copies))
        self.assertRegex(copies[0], r"ghcr\.io/astral-sh/uv:\d+\.\d+\.\d+ ")

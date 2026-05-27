"""Tests for mini_agent.agent_core.skills.eligibility module."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from mini_agent.agent_core.skills.eligibility import (
    SkillEligibilityChecker,
    SkillEligibilityResult,
    SkillRequirements,
    parse_skill_requirements,
)


class TestSkillRequirements:
    def test_defaults(self) -> None:
        req = SkillRequirements()
        assert req.os_names == ()
        assert req.bins == ()
        assert req.env_vars == ()
        assert req.python_packages == ()

    def test_custom_values(self) -> None:
        req = SkillRequirements(
            os_names=("linux",),
            bins=("ffmpeg",),
            env_vars=("API_KEY",),
            python_packages=("pillow",),
        )
        assert req.os_names == ("linux",)
        assert req.bins == ("ffmpeg",)
        assert req.env_vars == ("API_KEY",)
        assert req.python_packages == ("pillow",)


class TestSkillEligibilityResult:
    def test_eligible_no_reason(self) -> None:
        result = SkillEligibilityResult(eligible=True)
        assert result.eligible is True
        assert result.blocked_reason() is None

    def test_blocked_by_os(self) -> None:
        result = SkillEligibilityResult(eligible=False, os_mismatch=True, current_os="windows")
        reason = result.blocked_reason()
        assert reason is not None
        assert "os_mismatch" in reason
        assert "windows" in reason

    def test_blocked_by_missing_bins(self) -> None:
        result = SkillEligibilityResult(eligible=False, missing_bins=("ffmpeg", "jq"))
        reason = result.blocked_reason()
        assert reason is not None
        assert "missing_bins" in reason
        assert "ffmpeg" in reason
        assert "jq" in reason

    def test_blocked_by_missing_env(self) -> None:
        result = SkillEligibilityResult(eligible=False, missing_env_vars=("API_KEY",))
        reason = result.blocked_reason()
        assert reason is not None
        assert "missing_env" in reason

    def test_blocked_by_missing_packages(self) -> None:
        result = SkillEligibilityResult(eligible=False, missing_packages=("pillow", "numpy"))
        reason = result.blocked_reason()
        assert reason is not None
        assert "missing_packages" in reason
        assert "pillow" in reason

    def test_multiple_reasons_combined(self) -> None:
        result = SkillEligibilityResult(
            eligible=False,
            os_mismatch=True,
            current_os="darwin",
            missing_bins=("ffmpeg",),
            missing_packages=("pillow",),
        )
        reason = result.blocked_reason()
        assert reason is not None
        assert "os_mismatch" in reason
        assert "missing_bins" in reason
        assert "missing_packages" in reason


class TestParseSkillRequirements:
    def test_none_frontmatter(self) -> None:
        req = parse_skill_requirements(None)
        assert req == SkillRequirements()

    def test_empty_frontmatter(self) -> None:
        req = parse_skill_requirements({})
        assert req == SkillRequirements()

    def test_no_requires_key(self) -> None:
        req = parse_skill_requirements({"name": "test"})
        assert req == SkillRequirements()

    def test_requires_not_dict(self) -> None:
        req = parse_skill_requirements({"requires": "invalid"})
        assert req == SkillRequirements()

    def test_full_requires(self) -> None:
        req = parse_skill_requirements({
            "requires": {
                "os": ["linux", "darwin"],
                "bins": "ffmpeg, jq",
                "env": ["API_KEY", "SECRET"],
                "python_packages": ["pillow", "numpy"],
            }
        })
        assert req.os_names == ("linux", "darwin")
        assert req.bins == ("ffmpeg", "jq")
        assert req.env_vars == ("API_KEY", "SECRET")
        assert req.python_packages == ("pillow", "numpy")

    def test_os_names_lowercased(self) -> None:
        req = parse_skill_requirements({"requires": {"os": ["Linux", "DARWIN"]}})
        assert req.os_names == ("linux", "darwin")

    def test_bins_as_comma_string(self) -> None:
        req = parse_skill_requirements({"requires": {"bins": "git, docker"}})
        assert req.bins == ("git", "docker")

    def test_empty_values_ignored(self) -> None:
        req = parse_skill_requirements({"requires": {"bins": ", ,", "env": []}})
        assert req.bins == ()
        assert req.env_vars == ()


class TestSkillEligibilityChecker:
    def test_empty_requirements_always_eligible(self) -> None:
        checker = SkillEligibilityChecker()
        result = checker.check(SkillRequirements())
        assert result.eligible is True
        assert result.blocked_reason() is None

    def test_os_match(self) -> None:
        checker = SkillEligibilityChecker()
        with patch("mini_agent.agent_core.skills.eligibility.platform") as mock_platform:
            mock_platform.system.return_value = "Linux"
            result = checker.check(SkillRequirements(os_names=("linux", "darwin")))
        assert result.eligible is True

    def test_os_mismatch(self) -> None:
        checker = SkillEligibilityChecker()
        with patch("mini_agent.agent_core.skills.eligibility.platform") as mock_platform:
            mock_platform.system.return_value = "Windows"
            result = checker.check(SkillRequirements(os_names=("linux",)))
        assert result.eligible is False
        assert result.os_mismatch is True

    def test_missing_bins_detected(self) -> None:
        checker = SkillEligibilityChecker()
        with patch("mini_agent.agent_core.skills.eligibility.shutil") as mock_shutil:
            mock_shutil.which.return_value = None
            result = checker.check(SkillRequirements(bins=("nonexistent_tool",)))
        assert result.eligible is False
        assert "nonexistent_tool" in result.missing_bins

    def test_existing_bins_pass(self) -> None:
        checker = SkillEligibilityChecker()
        with patch("mini_agent.agent_core.skills.eligibility.shutil") as mock_shutil:
            mock_shutil.which.return_value = "/usr/bin/python"
            result = checker.check(SkillRequirements(bins=("python",)))
        assert result.eligible is True
        assert result.missing_bins == ()

    def test_missing_env_vars(self) -> None:
        checker = SkillEligibilityChecker(environment={"EXISTING": "1"})
        result = checker.check(SkillRequirements(env_vars=("MISSING_VAR",)))
        assert result.eligible is False
        assert "MISSING_VAR" in result.missing_env_vars

    def test_existing_env_vars_pass(self) -> None:
        checker = SkillEligibilityChecker(environment={"MY_KEY": "secret"})
        result = checker.check(SkillRequirements(env_vars=("MY_KEY",)))
        assert result.eligible is True

    def test_missing_python_packages(self) -> None:
        checker = SkillEligibilityChecker()
        result = checker.check(SkillRequirements(python_packages=("nonexistent_package_xyz",)))
        assert result.eligible is False
        assert "nonexistent_package_xyz" in result.missing_packages

    def test_existing_python_packages_pass(self) -> None:
        checker = SkillEligibilityChecker()
        result = checker.check(SkillRequirements(python_packages=("os", "sys")))
        assert result.eligible is True

    def test_combined_check_all_pass(self) -> None:
        checker = SkillEligibilityChecker(environment={"KEY": "val"})
        with patch("mini_agent.agent_core.skills.eligibility.platform") as mock_platform, \
             patch("mini_agent.agent_core.skills.eligibility.shutil") as mock_shutil:
            mock_platform.system.return_value = "Linux"
            mock_shutil.which.return_value = "/usr/bin/git"
            result = checker.check(SkillRequirements(
                os_names=("linux",),
                bins=("git",),
                env_vars=("KEY",),
                python_packages=("os",),
            ))
        assert result.eligible is True

    def test_combined_check_partial_failure(self) -> None:
        checker = SkillEligibilityChecker(environment={})
        with patch("mini_agent.agent_core.skills.eligibility.platform") as mock_platform, \
             patch("mini_agent.agent_core.skills.eligibility.shutil") as mock_shutil:
            mock_platform.system.return_value = "Linux"
            mock_shutil.which.return_value = "/usr/bin/git"
            result = checker.check(SkillRequirements(
                os_names=("linux",),
                bins=("git",),
                env_vars=("MISSING_KEY",),
            ))
        assert result.eligible is False
        assert result.missing_env_vars == ("MISSING_KEY",)
        assert result.missing_bins == ()

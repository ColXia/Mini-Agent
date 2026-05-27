"""Tests for mini_agent.utils.text module."""

from __future__ import annotations

from mini_agent.utils.text import safe_text


class TestSafeText:
    def test_none_returns_empty(self) -> None:
        assert safe_text(None) == ""

    def test_empty_string(self) -> None:
        assert safe_text("") == ""

    def test_simple_string(self) -> None:
        assert safe_text("hello") == "hello"

    def test_strips_whitespace(self) -> None:
        assert safe_text("  hello  ") == "hello"

    def test_collapses_internal_whitespace(self) -> None:
        assert safe_text("hello   world") == "hello world"

    def test_collapses_tabs_and_newlines(self) -> None:
        assert safe_text("hello\t\n  world") == "hello world"

    def test_integer_conversion(self) -> None:
        assert safe_text(42) == "42"

    def test_float_conversion(self) -> None:
        assert safe_text(3.14) == "3.14"

    def test_boolean_conversion(self) -> None:
        assert safe_text(True) == "True"

    def test_list_conversion(self) -> None:
        result = safe_text([1, 2, 3])
        assert "1" in result
        assert "2" in result
        assert "3" in result

    def test_dict_conversion(self) -> None:
        result = safe_text({"key": "value"})
        assert "key" in result
        assert "value" in result

    def test_zero_treated_as_empty(self) -> None:
        assert safe_text(0) == ""

    def test_false_treated_as_empty(self) -> None:
        assert safe_text(False) == ""

    def test_empty_list_becomes_empty(self) -> None:
        assert safe_text([]) == ""

    def test_chinese_text(self) -> None:
        assert safe_text("  你好  世界  ") == "你好 世界"

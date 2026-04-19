"""Tests for preprocess.icons — icon shortcode stripping/mapping."""

from __future__ import annotations

import pytest

from mkdocs_to_confluence.preprocess.icons import strip_icon_shortcodes


class TestKnownMappings:
    def test_check_maps_to_checkmark(self) -> None:
        assert strip_icon_shortcodes(":material-check:") == "✅"

    def test_check_circle_maps_to_checkmark(self) -> None:
        assert strip_icon_shortcodes(":material-check-circle:") == "✅"

    def test_alert_maps_to_warning(self) -> None:
        assert strip_icon_shortcodes(":material-alert:") == "⚠️"

    def test_alert_circle_maps_to_warning(self) -> None:
        assert strip_icon_shortcodes(":material-alert-circle:") == "⚠️"

    def test_information_maps_to_info(self) -> None:
        assert strip_icon_shortcodes(":material-information:") == "ℹ️"

    def test_close_maps_to_cross(self) -> None:
        assert strip_icon_shortcodes(":material-close:") == "❌"

    def test_lock_maps_to_lock(self) -> None:
        assert strip_icon_shortcodes(":material-lock:") == "🔒"

    def test_shield_maps_to_lock(self) -> None:
        assert strip_icon_shortcodes(":material-shield:") == "🔒"

    def test_rocket_maps_to_rocket(self) -> None:
        assert strip_icon_shortcodes(":material-rocket-launch:") == "🚀"

    def test_settings_maps_to_gear(self) -> None:
        assert strip_icon_shortcodes(":material-cog:") == "⚙️"

    def test_search_maps_to_magnifier(self) -> None:
        assert strip_icon_shortcodes(":material-magnify:") == "🔍"


class TestArrowMappings:
    def test_arrow_right(self) -> None:
        assert strip_icon_shortcodes(":material-arrow-right:") == "→"

    def test_arrow_left(self) -> None:
        assert strip_icon_shortcodes(":material-arrow-left:") == "←"

    def test_arrow_up(self) -> None:
        assert strip_icon_shortcodes(":material-arrow-up:") == "↑"

    def test_arrow_down(self) -> None:
        assert strip_icon_shortcodes(":material-arrow-down:") == "↓"

    def test_chevron_right(self) -> None:
        assert strip_icon_shortcodes(":material-chevron-right:") == "→"


class TestFamilies:
    def test_fontawesome_mapped(self) -> None:
        assert strip_icon_shortcodes(":fontawesome-solid-check:") == "✅"

    def test_octicons_mapped(self) -> None:
        assert strip_icon_shortcodes(":octicons-check-16:") == "✅"

    def test_simple_icons_unknown_stripped(self) -> None:
        # :simple-github: has no meaningful emoji mapping
        assert strip_icon_shortcodes(":simple-github:") == ""


class TestUnknownIcons:
    def test_unknown_icon_stripped(self) -> None:
        assert strip_icon_shortcodes(":material-quadcopter:") == ""

    def test_unknown_fontawesome_stripped(self) -> None:
        assert strip_icon_shortcodes(":fontawesome-brands-github:") == ""


class TestInlineReplacement:
    def test_icon_in_sentence(self) -> None:
        result = strip_icon_shortcodes("Status: :material-check: complete")
        assert result == "Status: ✅ complete"

    def test_multiple_icons_in_text(self) -> None:
        result = strip_icon_shortcodes(":material-check: done :material-close: failed")
        assert result == "✅ done ❌ failed"

    def test_unknown_stripped_inline(self) -> None:
        result = strip_icon_shortcodes("See :material-quadcopter: for details")
        assert result == "See  for details"

    def test_no_icons_unchanged(self) -> None:
        text = "No icons here, just plain text."
        assert strip_icon_shortcodes(text) == text

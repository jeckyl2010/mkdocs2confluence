"""Tests for preprocess.icons — icon shortcode stripping/mapping.

Confluence Cloud uses utf8mb4 and supports full Unicode including
supplementary-plane emoji (U+10000+).  Shortcodes with no clear emoji
equivalent are stripped silently.
"""

from __future__ import annotations

from mkdocs_to_confluence.preprocess.icons import strip_icon_shortcodes


class TestKnownMappings:
    def test_check_maps_to_checkmark(self) -> None:
        assert strip_icon_shortcodes(":material-check:") == "✓"

    def test_check_circle_maps_to_checkmark(self) -> None:
        assert strip_icon_shortcodes(":material-check-circle:") == "✓"

    def test_alert_maps_to_warning(self) -> None:
        assert strip_icon_shortcodes(":material-alert:") == "⚠"

    def test_alert_circle_maps_to_warning(self) -> None:
        assert strip_icon_shortcodes(":material-alert-circle:") == "⚠"

    def test_information_maps_to_info(self) -> None:
        assert strip_icon_shortcodes(":material-information:") == "ℹ"

    def test_close_maps_to_cross(self) -> None:
        assert strip_icon_shortcodes(":material-close:") == "✗"

    def test_lock_maps_to_emoji(self) -> None:
        assert strip_icon_shortcodes(":material-lock:") == "🔒"

    def test_shield_maps_to_emoji(self) -> None:
        assert strip_icon_shortcodes(":material-shield:") == "🛡️"

    def test_rocket_maps_to_emoji(self) -> None:
        assert strip_icon_shortcodes(":material-rocket-launch:") == "🚀"

    def test_settings_maps_to_gear(self) -> None:
        assert strip_icon_shortcodes(":material-cog:") == "⚙"

    def test_search_maps_to_emoji(self) -> None:
        assert strip_icon_shortcodes(":material-magnify:") == "🔍"

    def test_refresh_maps_to_arrow(self) -> None:
        assert strip_icon_shortcodes(":material-refresh:") == "↻"

    def test_email_maps_to_envelope(self) -> None:
        assert strip_icon_shortcodes(":material-email:") == "✉"

    def test_phone_maps_to_telephone(self) -> None:
        assert strip_icon_shortcodes(":material-phone:") == "☎"

    def test_star_maps_to_star(self) -> None:
        assert strip_icon_shortcodes(":material-star:") == "★"

    def test_heart_maps_to_heart(self) -> None:
        assert strip_icon_shortcodes(":material-heart:") == "♥"

    def test_music_maps_to_note(self) -> None:
        assert strip_icon_shortcodes(":material-music:") == "♪"


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


class TestBuggedIcons:
    """Regression tests for icons that should not produce wrong output."""

    def test_link_variant_maps_to_emoji(self) -> None:
        assert strip_icon_shortcodes(":material-link-variant:") == "🔗"

    def test_grid_view_outline_stripped(self) -> None:
        # grid/view have no meaningful emoji analogue
        assert strip_icon_shortcodes(":material-grid-view-outline:") == ""

    def test_link_maps_to_emoji(self) -> None:
        assert strip_icon_shortcodes(":material-link:") == "🔗"

    def test_view_stripped(self) -> None:
        assert strip_icon_shortcodes(":material-view-dashboard:") == ""

    def test_grid_stripped(self) -> None:
        assert strip_icon_shortcodes(":material-grid:") == ""


class TestFamilies:
    def test_fontawesome_mapped(self) -> None:
        assert strip_icon_shortcodes(":fontawesome-solid-check:") == "✓"

    def test_octicons_mapped(self) -> None:
        assert strip_icon_shortcodes(":octicons-check-16:") == "✓"

    def test_simple_icons_unknown_stripped(self) -> None:
        # :simple-github: has no meaningful symbol mapping
        assert strip_icon_shortcodes(":simple-github:") == ""


class TestUnknownIcons:
    def test_unknown_icon_stripped(self) -> None:
        assert strip_icon_shortcodes(":material-quadcopter:") == ""

    def test_unknown_fontawesome_stripped(self) -> None:
        assert strip_icon_shortcodes(":fontawesome-brands-github:") == ""


class TestEmojiMappings:
    """Supplementary-plane emoji now map to real emoji (Cloud utf8mb4 support)."""

    def test_fire_maps_to_emoji(self) -> None:
        assert strip_icon_shortcodes(":material-fire:") == "🔥"

    def test_lightbulb_maps_to_emoji(self) -> None:
        assert strip_icon_shortcodes(":material-lightbulb:") == "💡"

    def test_bug_maps_to_emoji(self) -> None:
        assert strip_icon_shortcodes(":material-bug:") == "🐛"

    def test_package_maps_to_emoji(self) -> None:
        assert strip_icon_shortcodes(":material-package:") == "📦"

    def test_account_maps_to_emoji(self) -> None:
        assert strip_icon_shortcodes(":material-account:") == "👤"

    def test_robot_maps_to_emoji(self) -> None:
        assert strip_icon_shortcodes(":material-robot:") == "🤖"


class TestInlineReplacement:
    def test_icon_in_sentence(self) -> None:
        result = strip_icon_shortcodes("Status: :material-check: complete")
        assert result == "Status: ✓ complete"

    def test_multiple_icons_in_text(self) -> None:
        result = strip_icon_shortcodes(":material-check: done :material-close: failed")
        assert result == "✓ done ✗ failed"

    def test_unknown_stripped_inline(self) -> None:
        result = strip_icon_shortcodes("See :material-quadcopter: for details")
        assert result == "See  for details"

    def test_no_icons_unchanged(self) -> None:
        text = "No icons here, just plain text."
        assert strip_icon_shortcodes(text) == text


class TestStandardEmoji:
    """Tests for bare emoji shortcodes like :rotating_light:."""

    def test_rotating_light_maps_to_siren(self) -> None:
        assert strip_icon_shortcodes(":rotating_light:") == "🚨"

    def test_octagonal_sign_maps_to_no_entry(self) -> None:
        assert strip_icon_shortcodes(":octagonal_sign:") == "⛔"

    def test_wrench_maps_to_wrench_emoji(self) -> None:
        assert strip_icon_shortcodes(":wrench:") == "🔧"

    def test_information_source_maps_to_info(self) -> None:
        assert strip_icon_shortcodes(":information_source:") == "ℹ"

    def test_white_check_mark_maps_to_check(self) -> None:
        assert strip_icon_shortcodes(":white_check_mark:") == "✓"

    def test_x_maps_to_cross(self) -> None:
        assert strip_icon_shortcodes(":x:") == "✗"

    def test_briefcase_maps_to_emoji(self) -> None:
        assert strip_icon_shortcodes(":briefcase:") == "💼"

    def test_unknown_shortcode_unchanged(self) -> None:
        assert strip_icon_shortcodes(":unknown_emoji_xyz:") == ":unknown_emoji_xyz:"

    def test_emoji_in_sentence(self) -> None:
        result = strip_icon_shortcodes("Status: :white_check_mark: Done")
        assert result == "Status: ✓ Done"

    def test_material_icon_not_double_processed(self) -> None:
        # :material-check-circle: should still go through the prefixed path
        result = strip_icon_shortcodes(":material-check-circle:")
        assert result == "✓"

    def test_all_standard_emoji_values_are_strings(self) -> None:
        from mkdocs_to_confluence.preprocess.icons import _STANDARD_EMOJI_MAP
        for name, symbol in _STANDARD_EMOJI_MAP.items():
            assert isinstance(symbol, str), f"_STANDARD_EMOJI_MAP[{name!r}] is not a string"

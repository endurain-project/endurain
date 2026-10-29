"""Tests for the token-rotation policy enum."""

from modules.auth.identity_providers.token_policy import TokenAction


class TestTokenActionEnum:
    """TokenAction enum values used by token-rotation policy."""

    def test_enum_values(self):
        assert TokenAction.SKIP.value == "skip"
        assert TokenAction.REFRESH.value == "refresh"
        assert TokenAction.CLEAR.value == "clear"

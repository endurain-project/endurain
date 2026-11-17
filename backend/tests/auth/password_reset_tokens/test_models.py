"""Tests for the password reset token model."""

import modules.auth.password_reset_tokens.models as password_reset_models


def test_token_hash_has_a_unique_index():
    table = password_reset_models.PasswordResetToken.__table__

    indexes = {index.name: index for index in table.indexes}

    index = indexes["ix_password_reset_tokens_token_hash"]
    assert index.unique is True
    assert [column.name for column in index.columns] == ["token_hash"]

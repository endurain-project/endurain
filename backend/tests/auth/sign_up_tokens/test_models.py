"""Tests for the sign-up token model."""

import modules.auth.sign_up_tokens.models as sign_up_models


def test_token_hash_has_a_unique_index():
    table = sign_up_models.SignUpToken.__table__

    indexes = {index.name: index for index in table.indexes}

    index = indexes["ix_sign_up_tokens_token_hash"]
    assert index.unique is True
    assert [column.name for column in index.columns] == ["token_hash"]

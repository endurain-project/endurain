"""The sign-up schemas state which of their sets are open."""

import modules.auth.sign_up_tokens.schema as sign_up_schema


def test_the_next_step_description_says_the_set_is_open():
    description = sign_up_schema.SignUpRead.model_fields["next_step"].description

    assert "set is open" in description
    assert "unsupported step" in description

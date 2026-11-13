"""Tests that the sign-up publishers stage their events in the caller's transaction."""

import uuid
from unittest.mock import MagicMock, patch

import pytest

import modules.auth.sign_up_tokens.event_publishers as sign_up_publishers

_USER_3 = uuid.UUID("00000000-0000-4000-8000-000000000003")
_USER_9 = uuid.UUID("00000000-0000-4000-8000-000000000009")

_PLATFORM = "modules.auth.sign_up_tokens.event_publishers.platform_publisher"


@pytest.mark.parametrize(
    ("publisher", "args", "event_type"),
    [
        (sign_up_publishers.publish_sign_up_verification_requested, (_USER_3,), "auth.sign_up_verification_requested"),
        (sign_up_publishers.publish_sign_up_approval_requested, (_USER_3, _USER_9), "auth.sign_up_approval_requested"),
        (sign_up_publishers.publish_sign_up_existing_account, (_USER_3,), "auth.sign_up_existing_account"),
    ],
)
def test_publisher_stages_on_commit_and_leaves_the_commit_to_the_caller(publisher, args, event_type):
    db = MagicMock()
    with patch(f"{_PLATFORM}.publish_on_commit") as staged, patch(f"{_PLATFORM}.publish") as bare:
        publisher(*args, db)

    bare.assert_not_called()
    staged.assert_called_once()
    assert staged.call_args.args[0] == event_type
    assert staged.call_args.kwargs["db"] is db
    db.commit.assert_not_called()

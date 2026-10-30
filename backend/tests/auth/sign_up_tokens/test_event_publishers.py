"""Tests that the sign-up publishers stage their events in the caller's transaction."""

from unittest.mock import MagicMock, patch

import pytest

import modules.auth.sign_up_tokens.event_publishers as sign_up_publishers

_PLATFORM = "modules.auth.sign_up_tokens.event_publishers.platform_publisher"


@pytest.mark.parametrize(
    ("publisher", "args", "event_type"),
    [
        (sign_up_publishers.publish_sign_up_verification_requested, (3,), "auth.sign_up_verification_requested"),
        (sign_up_publishers.publish_sign_up_approval_requested, (3, 9), "auth.sign_up_approval_requested"),
        (sign_up_publishers.publish_sign_up_existing_account, (3,), "auth.sign_up_existing_account"),
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

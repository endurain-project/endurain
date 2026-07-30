import pytest
from fastapi import HTTPException


class TestValidateNotificationId:
    def test_valid(self):
        from modules.notifications.dependencies import validate_notification_id

        validate_notification_id(1)
        validate_notification_id(100)

    def test_invalid(self):
        from modules.notifications.dependencies import validate_notification_id

        with pytest.raises(HTTPException):
            validate_notification_id(0)

    def test_negative(self):
        from modules.notifications.dependencies import validate_notification_id

        with pytest.raises(HTTPException):
            validate_notification_id(-1)

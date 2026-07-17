from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException


class TestCreateAndNotify:
    @pytest.mark.asyncio
    async def test_success(self):
        import modules.notifications.models as m
        import modules.notifications.schema as s
        from modules.notifications.utils import _create_and_notify

        mock_notification = MagicMock(spec=m.Notification, id=1)
        mock_ws_manager = MagicMock()
        mock_db = MagicMock()

        with (
            patch(
                "modules.notifications.utils.notifications_crud.create_notification", return_value=mock_notification
            ) as mock_create,
            patch("modules.notifications.utils.websocket_utils.notify_frontend", new_callable=AsyncMock) as mock_notify,
        ):
            result = await _create_and_notify(
                notification_data=MagicMock(spec=s.NotificationCreate),
                ws_message="TEST_MESSAGE",
                notify_user_id=42,
                ws_manager=mock_ws_manager,
                db=mock_db,
            )

        assert result is mock_notification
        mock_create.assert_called_once()
        mock_notify.assert_awaited_once_with(
            42,
            mock_ws_manager,
            {
                "message": "TEST_MESSAGE",
                "notification_id": 1,
            },
        )


class TestCreateActivityCreatedNotification:
    """The synchronous helper used by the activity.created subscriber."""

    def test_new_activity_variant(self):
        import modules.notifications.constants as c
        from modules.notifications.utils import create_activity_created_notification

        mock_db = MagicMock()
        with patch(
            "modules.notifications.utils.notifications_crud.create_notification",
            return_value=MagicMock(id=1),
        ) as mock_create:
            notification, ws_message = create_activity_created_notification(42, 7, False, mock_db)

        assert notification.id == 1
        assert ws_message == "NEW_ACTIVITY_NOTIFICATION"
        created = mock_create.call_args.args[0]
        assert created.user_id == 42
        assert created.type == c.NotificationType.NEW_ACTIVITY
        assert created.options == {"activity_id": 7}

    def test_duplicate_variant(self):
        import modules.notifications.constants as c
        from modules.notifications.utils import create_activity_created_notification

        mock_db = MagicMock()
        with patch(
            "modules.notifications.utils.notifications_crud.create_notification",
            return_value=MagicMock(id=2),
        ) as mock_create:
            _, ws_message = create_activity_created_notification(1, 3, True, mock_db)

        assert ws_message == "NEW_DUPLICATE_ACTIVITY_START_TIME_NOTIFICATION"
        assert mock_create.call_args.args[0].type == c.NotificationType.DUPLICATE_ACTIVITY


class TestCreateNewActivityNotification:
    @pytest.mark.asyncio
    async def test_success(self):
        import modules.notifications.constants as c
        import modules.notifications.models as m
        from modules.notifications.utils import create_new_activity_notification

        mock_notification = MagicMock(spec=m.Notification, id=1)
        mock_ws_manager = MagicMock()

        mock_session = MagicMock()
        mock_session.__enter__.return_value = MagicMock()
        mock_session.__exit__.return_value = None
        mock_session_local = MagicMock(return_value=mock_session)

        with (
            patch("modules.notifications.utils.SessionLocal", mock_session_local),
            patch(
                "modules.notifications.utils.notifications_crud.create_notification", return_value=mock_notification
            ) as mock_create,
            patch("modules.notifications.utils.websocket_utils.notify_frontend", new_callable=AsyncMock) as mock_notify,
        ):
            result = await create_new_activity_notification(
                user_id=1,
                activity_id=10,
                websocket_manager=mock_ws_manager,
            )

        assert result is mock_notification
        assert mock_create.call_args[0][0].type == c.NotificationType.NEW_ACTIVITY
        assert mock_create.call_args[0][0].options == {"activity_id": 10}
        mock_notify.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_http_exception_propagates(self):
        from modules.notifications.utils import create_new_activity_notification

        mock_ws_manager = MagicMock()

        with (
            patch("modules.notifications.utils.SessionLocal"),
            patch(
                "modules.notifications.utils.notifications_crud.create_notification",
                side_effect=HTTPException(status_code=404, detail="Not found"),
            ),
        ):
            with pytest.raises(HTTPException) as e:
                await create_new_activity_notification(
                    user_id=1,
                    activity_id=10,
                    websocket_manager=mock_ws_manager,
                )
            assert e.value.status_code == 404

    @pytest.mark.asyncio
    async def test_generic_exception_raises_500(self):
        from modules.notifications.utils import create_new_activity_notification

        mock_ws_manager = MagicMock()

        with (
            patch("modules.notifications.utils.SessionLocal"),
            patch("modules.notifications.utils.notifications_crud.create_notification", side_effect=ValueError("boom")),
        ):
            with pytest.raises(HTTPException) as e:
                await create_new_activity_notification(
                    user_id=1,
                    activity_id=10,
                    websocket_manager=mock_ws_manager,
                )
            assert e.value.status_code == 500


class TestCreateNewDuplicateStartTimeActivityNotification:
    @pytest.mark.asyncio
    async def test_success(self):
        import modules.notifications.constants as c
        import modules.notifications.models as m
        from modules.notifications.utils import create_new_duplicate_start_time_activity_notification

        mock_notification = MagicMock(spec=m.Notification, id=1)
        mock_ws_manager = MagicMock()

        mock_session = MagicMock()
        mock_session.__enter__.return_value = MagicMock()
        mock_session.__exit__.return_value = None
        mock_session_local = MagicMock(return_value=mock_session)

        with (
            patch("modules.notifications.utils.SessionLocal", mock_session_local),
            patch(
                "modules.notifications.utils.notifications_crud.create_notification", return_value=mock_notification
            ) as mock_create,
            patch("modules.notifications.utils.websocket_utils.notify_frontend", new_callable=AsyncMock) as mock_notify,
        ):
            result = await create_new_duplicate_start_time_activity_notification(
                user_id=1,
                activity_id=10,
                websocket_manager=mock_ws_manager,
            )

        assert result is mock_notification
        assert mock_create.call_args[0][0].type == c.NotificationType.DUPLICATE_ACTIVITY
        assert mock_create.call_args[0][0].options == {"activity_id": 10}
        mock_notify.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_http_exception_propagates(self):
        from modules.notifications.utils import create_new_duplicate_start_time_activity_notification

        mock_ws_manager = MagicMock()

        mock_session = MagicMock()
        mock_session.__enter__.return_value = MagicMock()
        mock_session.__exit__.return_value = None
        mock_session_local = MagicMock(return_value=mock_session)

        with (
            patch("modules.notifications.utils.SessionLocal", mock_session_local),
            patch(
                "modules.notifications.utils.notifications_crud.create_notification",
                side_effect=HTTPException(status_code=400, detail="Bad"),
            ),
        ):
            with pytest.raises(HTTPException) as e:
                await create_new_duplicate_start_time_activity_notification(
                    user_id=1,
                    activity_id=10,
                    websocket_manager=mock_ws_manager,
                )
            assert e.value.status_code == 400

    @pytest.mark.asyncio
    async def test_generic_exception_raises_500(self):
        from modules.notifications.utils import create_new_duplicate_start_time_activity_notification

        mock_ws_manager = MagicMock()

        mock_session = MagicMock()
        mock_session.__enter__.return_value = MagicMock()
        mock_session.__exit__.return_value = None
        mock_session_local = MagicMock(return_value=mock_session)

        with (
            patch("modules.notifications.utils.SessionLocal", mock_session_local),
            patch(
                "modules.notifications.utils.notifications_crud.create_notification", side_effect=RuntimeError("fail")
            ),
        ):
            with pytest.raises(HTTPException) as e:
                await create_new_duplicate_start_time_activity_notification(
                    user_id=1,
                    activity_id=10,
                    websocket_manager=mock_ws_manager,
                )
            assert e.value.status_code == 500


class TestCreateNewFollowerRequestNotification:
    @pytest.mark.asyncio
    async def test_success(self):
        import modules.notifications.constants as c
        import modules.notifications.models as m
        import modules.users.users.models as u_models
        from modules.notifications.utils import create_new_follower_request_notification

        mock_user = MagicMock(spec=u_models.Users, id=5, username="follower_user")
        mock_user.name = "Follower"
        mock_notification = MagicMock(spec=m.Notification, id=1)
        mock_ws_manager = MagicMock()
        mock_db = MagicMock()

        with (
            patch("modules.notifications.utils.users_crud.get_user_by_id", return_value=mock_user),
            patch(
                "modules.notifications.utils.notifications_crud.create_notification", return_value=mock_notification
            ) as mock_create,
            patch("modules.notifications.utils.websocket_utils.notify_frontend", new_callable=AsyncMock) as mock_notify,
        ):
            result = await create_new_follower_request_notification(
                user_id=5,
                target_user_id=10,
                websocket_manager=mock_ws_manager,
                db=mock_db,
            )

        assert result is mock_notification
        mock_notify.assert_awaited_once()
        created = mock_create.call_args[0][0]
        assert created.user_id == 10
        assert created.type == c.NotificationType.NEW_FOLLOWER_REQUEST
        assert created.options == {
            "user_id": 5,
            "user_name": "Follower",
            "user_username": "follower_user",
        }

    @pytest.mark.asyncio
    async def test_user_not_found_raises_404(self):
        from modules.notifications.utils import create_new_follower_request_notification

        mock_ws_manager = MagicMock()
        mock_db = MagicMock()

        with patch("modules.notifications.utils.users_crud.get_user_by_id", return_value=None):
            with pytest.raises(HTTPException) as e:
                await create_new_follower_request_notification(
                    user_id=999,
                    target_user_id=10,
                    websocket_manager=mock_ws_manager,
                    db=mock_db,
                )
            assert e.value.status_code == 404

    @pytest.mark.asyncio
    async def test_http_exception_propagates(self):
        import modules.users.users.models as u_models
        from modules.notifications.utils import create_new_follower_request_notification

        mock_user = MagicMock(spec=u_models.Users, id=5, username="follower_user")
        mock_user.name = "Follower"
        mock_ws_manager = MagicMock()
        mock_db = MagicMock()

        with (
            patch("modules.notifications.utils.users_crud.get_user_by_id", return_value=mock_user),
            patch(
                "modules.notifications.utils.notifications_crud.create_notification",
                side_effect=HTTPException(status_code=409, detail="Conflict"),
            ),
        ):
            with pytest.raises(HTTPException) as e:
                await create_new_follower_request_notification(
                    user_id=5,
                    target_user_id=10,
                    websocket_manager=mock_ws_manager,
                    db=mock_db,
                )
            assert e.value.status_code == 409

    @pytest.mark.asyncio
    async def test_generic_exception_raises_500(self):
        import modules.users.users.models as u_models
        from modules.notifications.utils import create_new_follower_request_notification

        mock_user = MagicMock(spec=u_models.Users, id=5, username="follower_user")
        mock_user.name = "Follower"
        mock_ws_manager = MagicMock()
        mock_db = MagicMock()

        with (
            patch("modules.notifications.utils.users_crud.get_user_by_id", return_value=mock_user),
            patch(
                "modules.notifications.utils.notifications_crud.create_notification", side_effect=KeyError("missing")
            ),
        ):
            with pytest.raises(HTTPException) as e:
                await create_new_follower_request_notification(
                    user_id=5,
                    target_user_id=10,
                    websocket_manager=mock_ws_manager,
                    db=mock_db,
                )
            assert e.value.status_code == 500


class TestCreateAcceptedFollowerRequestNotification:
    @pytest.mark.asyncio
    async def test_success(self):
        import modules.notifications.constants as c
        import modules.notifications.models as m
        import modules.users.users.models as u_models
        from modules.notifications.utils import create_accepted_follower_request_notification

        mock_user = MagicMock(spec=u_models.Users, id=5, username="accepter_user")
        mock_user.name = "Accepter"
        mock_notification = MagicMock(spec=m.Notification, id=1)
        mock_ws_manager = MagicMock()
        mock_db = MagicMock()

        with (
            patch("modules.notifications.utils.users_crud.get_user_by_id", return_value=mock_user),
            patch(
                "modules.notifications.utils.notifications_crud.create_notification", return_value=mock_notification
            ) as mock_create,
            patch("modules.notifications.utils.websocket_utils.notify_frontend", new_callable=AsyncMock) as mock_notify,
        ):
            result = await create_accepted_follower_request_notification(
                user_id=5,
                target_user_id=10,
                websocket_manager=mock_ws_manager,
                db=mock_db,
            )

        assert result is mock_notification
        mock_notify.assert_awaited_once()
        created = mock_create.call_args[0][0]
        assert created.user_id == 10
        assert created.type == c.NotificationType.NEW_FOLLOWER_REQUEST_ACCEPTED
        assert created.options == {
            "user_id": 5,
            "user_name": "Accepter",
            "user_username": "accepter_user",
        }

    @pytest.mark.asyncio
    async def test_user_not_found_raises_404(self):
        from modules.notifications.utils import create_accepted_follower_request_notification

        mock_ws_manager = MagicMock()
        mock_db = MagicMock()

        with patch("modules.notifications.utils.users_crud.get_user_by_id", return_value=None):
            with pytest.raises(HTTPException) as e:
                await create_accepted_follower_request_notification(
                    user_id=999,
                    target_user_id=10,
                    websocket_manager=mock_ws_manager,
                    db=mock_db,
                )
            assert e.value.status_code == 404

    @pytest.mark.asyncio
    async def test_http_exception_propagates(self):
        import modules.users.users.models as u_models
        from modules.notifications.utils import create_accepted_follower_request_notification

        mock_user = MagicMock(spec=u_models.Users, id=5, username="accepter_user")
        mock_user.name = "Accepter"
        mock_ws_manager = MagicMock()
        mock_db = MagicMock()

        with (
            patch("modules.notifications.utils.users_crud.get_user_by_id", return_value=mock_user),
            patch(
                "modules.notifications.utils.notifications_crud.create_notification",
                side_effect=HTTPException(status_code=403, detail="Forbidden"),
            ),
        ):
            with pytest.raises(HTTPException) as e:
                await create_accepted_follower_request_notification(
                    user_id=5,
                    target_user_id=10,
                    websocket_manager=mock_ws_manager,
                    db=mock_db,
                )
            assert e.value.status_code == 403

    @pytest.mark.asyncio
    async def test_generic_exception_raises_500(self):
        import modules.users.users.models as u_models
        from modules.notifications.utils import create_accepted_follower_request_notification

        mock_user = MagicMock(spec=u_models.Users, id=5, username="accepter_user")
        mock_user.name = "Accepter"
        mock_ws_manager = MagicMock()
        mock_db = MagicMock()

        with (
            patch("modules.notifications.utils.users_crud.get_user_by_id", return_value=mock_user),
            patch("modules.notifications.utils.notifications_crud.create_notification", side_effect=ValueError("bad")),
        ):
            with pytest.raises(HTTPException) as e:
                await create_accepted_follower_request_notification(
                    user_id=5,
                    target_user_id=10,
                    websocket_manager=mock_ws_manager,
                    db=mock_db,
                )
            assert e.value.status_code == 500


class TestCreateAdminNewSignUpApprovalRequestNotification:
    @pytest.mark.asyncio
    async def test_success(self):
        import modules.notifications.constants as c
        import modules.notifications.models as m
        import modules.users.users.models as u_models
        from modules.notifications.utils import create_admin_new_sign_up_approval_request_notification

        mock_user = MagicMock(spec=u_models.Users, id=1, username="newbie")
        mock_user.name = "New User"
        mock_admin1 = MagicMock(spec=u_models.Users, id=10, username="admin1")
        mock_admin1.name = "Admin One"
        mock_admin2 = MagicMock(spec=u_models.Users, id=20, username="admin2")
        mock_admin2.name = "Admin Two"
        mock_ws_manager = MagicMock()
        mock_db = MagicMock()

        mock_notification = MagicMock(spec=m.Notification, id=1)

        with (
            patch(
                "modules.notifications.utils.users_utils.get_admin_users_or_404",
                return_value=[mock_admin1, mock_admin2],
            ),
            patch(
                "modules.notifications.utils.notifications_crud.create_notification", return_value=mock_notification
            ) as mock_create,
            patch("modules.notifications.utils.websocket_utils.notify_frontend", new_callable=AsyncMock) as mock_notify,
        ):
            await create_admin_new_sign_up_approval_request_notification(
                user=mock_user,
                websocket_manager=mock_ws_manager,
                db=mock_db,
            )

        assert mock_create.call_count == 2
        assert mock_notify.await_count == 2

        first = mock_create.call_args_list[0][0][0]
        second = mock_create.call_args_list[1][0][0]
        assert first.user_id == 10
        assert first.type == c.NotificationType.ADMIN_NEW_SIGN_UP_APPROVAL_REQUEST
        assert first.options == {"user_id": 1, "user_name": "New User", "user_username": "newbie"}
        assert second.user_id == 20
        assert second.type == c.NotificationType.ADMIN_NEW_SIGN_UP_APPROVAL_REQUEST
        assert second.options == {"user_id": 1, "user_name": "New User", "user_username": "newbie"}

    @pytest.mark.asyncio
    async def test_http_exception_propagates(self):
        import modules.users.users.models as u_models
        from modules.notifications.utils import create_admin_new_sign_up_approval_request_notification

        mock_user = MagicMock(spec=u_models.Users, id=1, username="newbie")
        mock_user.name = "New User"
        mock_ws_manager = MagicMock()
        mock_db = MagicMock()

        with (
            patch(
                "modules.notifications.utils.users_utils.get_admin_users_or_404",
                side_effect=HTTPException(status_code=404, detail="No admins"),
            ),
        ):
            with pytest.raises(HTTPException) as e:
                await create_admin_new_sign_up_approval_request_notification(
                    user=mock_user,
                    websocket_manager=mock_ws_manager,
                    db=mock_db,
                )
            assert e.value.status_code == 404

    @pytest.mark.asyncio
    async def test_generic_exception_raises_500(self):
        import modules.users.users.models as u_models
        from modules.notifications.utils import create_admin_new_sign_up_approval_request_notification

        mock_user = MagicMock(spec=u_models.Users, id=1, username="newbie")
        mock_user.name = "New User"
        mock_ws_manager = MagicMock()
        mock_db = MagicMock()

        with (
            patch(
                "modules.notifications.utils.users_utils.get_admin_users_or_404", side_effect=RuntimeError("unexpected")
            ),
        ):
            with pytest.raises(HTTPException) as e:
                await create_admin_new_sign_up_approval_request_notification(
                    user=mock_user,
                    websocket_manager=mock_ws_manager,
                    db=mock_db,
                )
            assert e.value.status_code == 500


class TestCreateGarminTokenExpiredNotification:
    @pytest.mark.asyncio
    async def test_success(self):
        import modules.notifications.constants as c
        import modules.notifications.models as m
        from modules.notifications.utils import create_garmin_token_expired_notification

        mock_notification = MagicMock(spec=m.Notification, id=1)
        mock_ws_manager = MagicMock()

        with (
            patch("modules.notifications.utils.SessionLocal"),
            patch(
                "modules.notifications.utils.notifications_crud.create_notification", return_value=mock_notification
            ) as mock_create,
            patch("modules.notifications.utils.websocket_utils.notify_frontend", new_callable=AsyncMock) as mock_notify,
        ):
            await create_garmin_token_expired_notification(
                user_id=42,
                websocket_manager=mock_ws_manager,
            )

        mock_notify.assert_awaited_once()
        created = mock_create.call_args[0][0]
        assert created.user_id == 42
        assert created.type == c.NotificationType.GARMIN_TOKEN_EXPIRED
        assert created.options == {}

    @pytest.mark.asyncio
    async def test_http_exception_propagates(self):
        from modules.notifications.utils import create_garmin_token_expired_notification

        mock_ws_manager = MagicMock()

        mock_session = MagicMock()
        mock_session.__enter__.return_value = MagicMock()
        mock_session.__exit__.return_value = False
        mock_session_local = MagicMock(return_value=mock_session)

        with (
            patch("modules.notifications.utils.SessionLocal", mock_session_local),
            patch(
                "modules.notifications.utils.notifications_crud.create_notification",
                side_effect=HTTPException(status_code=500, detail="err"),
            ),
        ):
            with pytest.raises(HTTPException) as e:
                await create_garmin_token_expired_notification(
                    user_id=42,
                    websocket_manager=mock_ws_manager,
                )
            assert e.value.status_code == 500

    @pytest.mark.asyncio
    async def test_generic_exception_raises_500(self):
        from modules.notifications.utils import create_garmin_token_expired_notification

        mock_ws_manager = MagicMock()

        mock_session = MagicMock()
        mock_session.__enter__.return_value = MagicMock()
        mock_session.__exit__.return_value = False
        mock_session_local = MagicMock(return_value=mock_session)

        with (
            patch("modules.notifications.utils.SessionLocal", mock_session_local),
            patch("modules.notifications.utils.notifications_crud.create_notification", side_effect=ValueError("oops")),
        ):
            with pytest.raises(HTTPException) as e:
                await create_garmin_token_expired_notification(
                    user_id=42,
                    websocket_manager=mock_ws_manager,
                )
            assert e.value.status_code == 500

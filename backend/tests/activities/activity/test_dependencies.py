import pytest
from fastapi import HTTPException


class TestValidateWeekNumber:
    def test_validate_week_number_valid(self):
        from modules.activities.activity.dependencies import validate_week_number

        validate_week_number(0)
        validate_week_number(52)

    def test_validate_week_number_invalid(self):
        from modules.activities.activity.dependencies import validate_week_number

        with pytest.raises(HTTPException):
            validate_week_number(-1)


class TestValidateActivityType:
    def test_validate_valid_type(self):
        from modules.activities.activity.dependencies import validate_activity_type

        validate_activity_type(1)
        validate_activity_type(None)

    def test_validate_invalid_type(self):
        from modules.activities.activity.dependencies import validate_activity_type

        with pytest.raises(HTTPException) as exc:
            validate_activity_type(9999)
        assert exc.value.status_code == 422


class TestValidateSortBy:
    def test_validate_valid_sort_by(self):
        from modules.activities.activity.dependencies import validate_sort_by

        validate_sort_by("name")
        validate_sort_by("distance")
        validate_sort_by("average_hr")
        validate_sort_by(None)

    def test_validate_invalid_sort_by(self):
        from modules.activities.activity.dependencies import validate_sort_by

        with pytest.raises(HTTPException) as exc:
            validate_sort_by("invalid_field")
        assert exc.value.status_code == 422


class TestValidateSortOrder:
    def test_validate_valid_sort_order(self):
        from modules.activities.activity.dependencies import validate_sort_order

        validate_sort_order("asc")
        validate_sort_order("desc")
        validate_sort_order(None)

    def test_validate_invalid_sort_order(self):
        from modules.activities.activity.dependencies import validate_sort_order

        with pytest.raises(HTTPException) as exc:
            validate_sort_order("invalid")
        assert exc.value.status_code == 422


class TestValidateVisibility:
    def test_validate_valid_visibility(self):
        from modules.activities.activity.dependencies import validate_visibility

        validate_visibility(0)
        validate_visibility(1)
        validate_visibility(2)

    def test_validate_invalid_visibility(self):
        from modules.activities.activity.dependencies import validate_visibility

        with pytest.raises(HTTPException):
            validate_visibility(5)


class TestValidateActivityID:
    def test_validate_valid_activity_id(self):
        import modules.activities.activity.dependencies as deps

        deps.validate_activity_id(1)
        deps.validate_activity_id(100)

    def test_validate_invalid_activity_id(self):
        import modules.activities.activity.dependencies as deps

        with pytest.raises(HTTPException):
            deps.validate_activity_id(-1)

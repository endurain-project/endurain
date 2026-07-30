from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException


class TestValidateGearComponentId:
    def test_valid(self):
        from modules.gears.gear_components.dependencies import validate_gear_component_id

        validate_gear_component_id(1)
        validate_gear_component_id(100)

    def test_invalid(self):
        from modules.gears.gear_components.dependencies import validate_gear_component_id

        with pytest.raises(HTTPException):
            validate_gear_component_id(0)

    def test_negative(self):
        from modules.gears.gear_components.dependencies import validate_gear_component_id

        with pytest.raises(HTTPException):
            validate_gear_component_id(-1)


class TestValidateGearComponentType:
    def test_valid_bike_component(self, mock_db):
        from modules.gears.gear_components.dependencies import validate_gear_component_type

        gear = MagicMock()
        gear.gear_type = 1
        gear.user_id = 1

        with patch("modules.gears.gear_components.dependencies.gears_crud.get_gear_user_by_id") as mock_get_gear:
            mock_get_gear.return_value = gear
            from modules.gears.gear_components.schema import GearComponentCreate

            component = GearComponentCreate(type="chain", brand="Shimano", model="Ultegra", gear_id=1)
            validate_gear_component_type(component, 1, mock_db)

    def test_gear_not_found(self, mock_db):
        from modules.gears.gear_components.dependencies import validate_gear_component_type

        with patch("modules.gears.gear_components.dependencies.gears_crud.get_gear_user_by_id") as mock_get_gear:
            mock_get_gear.return_value = None
            from modules.gears.gear_components.schema import GearComponentCreate

            component = GearComponentCreate(type="chain", brand="Shimano", model="Ultegra", gear_id=999)
            with pytest.raises(HTTPException) as exc:
                validate_gear_component_type(component, 1, mock_db)
            assert exc.value.status_code == 404

    def test_invalid_component_type(self, mock_db):
        from modules.gears.gear_components.dependencies import validate_gear_component_type

        gear = MagicMock()
        gear.gear_type = 1  # bike
        gear.user_id = 1

        with patch("modules.gears.gear_components.dependencies.gears_crud.get_gear_user_by_id") as mock_get_gear:
            mock_get_gear.return_value = gear
            from modules.gears.gear_components.schema import GearComponentCreate

            component = GearComponentCreate(type="invalid_type", brand="Shimano", model="Ultegra", gear_id=1)
            with pytest.raises(HTTPException) as exc:
                validate_gear_component_type(component, 1, mock_db)
            assert exc.value.status_code == 422

    def test_gear_type_without_components(self, mock_db):
        from modules.gears.gear_components.dependencies import validate_gear_component_type

        gear = MagicMock()
        gear.gear_type = 3  # Not in the supported types mapping
        gear.user_id = 1

        with patch("modules.gears.gear_components.dependencies.gears_crud.get_gear_user_by_id") as mock_get_gear:
            mock_get_gear.return_value = gear
            from modules.gears.gear_components.schema import GearComponentCreate

            component = GearComponentCreate(type="chain", brand="Shimano", model="Ultegra", gear_id=1)
            validate_gear_component_type(component, 1, mock_db)

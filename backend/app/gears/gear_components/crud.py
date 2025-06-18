from fastapi import HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from urllib.parse import unquote

import gears.gear_components.schema as gear_components_schema
import gears.gear_components.utils as gear_components_utils
import gears.gear_components.models as gear_components_models

import core.logger as core_logger


def get_gear_component_by_id(
    gear_component_id: int, db: Session
) -> gear_components_schema.GearComponents | None:
    try:
        gear_component = (
            db.query(gear_components_models.GearComponents)
            .filter(gear_components_models.GearComponents.id == gear_component_id)
            .first()
        )

        # Check if gear component is None and return None if it is
        if gear_component is None:
            return None

        gear_component = gear_components_utils.serialize_gear_component(gear_component)

        # Return the gear component
        return gear_component
    except Exception as err:
        # Log the exception
        core_logger.print_to_log(
            f"Error in get_gear_component_by_id: {err}", "error", exc=err
        )
        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def get_gear_components_user(
    user_id: int, db: Session
) -> list[gear_components_schema.GearComponents] | None:
    try:
        # Get the gear components by user ID from the database
        gear_components = (
            db.query(gear_components_models.GearComponents)
            .filter(gear_components_models.GearComponents.user_id == user_id)
            .all()
        )

        # Check if gear components is None and return None if it is
        if gear_components is None:
            return None

        # Serialize the gear components
        for g in gear_components:
            g = gear_components_utils.serialize_gear_component(g)

        # Return the gear components
        return gear_components
    except Exception as err:
        # Log the exception
        core_logger.print_to_log(
            f"Error in get_gear_components_user: {err}", "error", exc=err
        )
        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def get_gear_components_user_by_gear_id(
    user_id: int, gear_id: int, db: Session
) -> list[gear_components_schema.GearComponents] | None:
    try:
        gear_components = (
            db.query(gear_components_models.GearComponents)
            .filter(
                gear_components_models.GearComponents.user_id == user_id,
                gear_components_models.GearComponents.gear_id == gear_id,
            )
            .all()
        )

        # Check if gear components is None and return None if it is
        if gear_components is None:
            return None

        # Serialize the gear components
        for g in gear_components:
            g = gear_components_utils.serialize_gear_component(g)

        # Return the gear components
        return gear_components
    except Exception as err:
        # Log the exception
        core_logger.print_to_log(
            f"Error in get_gear_components_user_by_gear_id: {err}", "error", exc=err
        )
        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def create_gear_component(
    gear_component: gear_components_schema.GearComponents, user_id: int, db: Session
):
    try:
        new_gear_component = gear_components_models.GearComponents(
            user_id=gear_component.user_id,
            gear_id=gear_component.gear_id,
            type=gear_component.type,
            brand=gear_component.brand,
            model=gear_component.model,
            purchase_date=gear_component.purchase_date,
            is_active=True,
            expected_kms=gear_component.expected_kms,
            purchase_value=gear_component.purchase_value,
        )

        # Add the gear component to the database
        db.add(new_gear_component)
        db.commit()
        db.refresh(new_gear_component)

        gear_component_serialized = gear_components_utils.serialize_gear_component(
            new_gear_component
        )

        # Return the gear component
        return gear_component_serialized
    except Exception as err:
        # Rollback the transaction
        db.rollback()

        # Log the exception
        core_logger.print_to_log(
            f"Error in create_gear_component: {err}", "error", exc=err
        )

        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def delete_gear_component(user_id: int, gear_component_id: int, db: Session):
    try:
        # Delete the gear component
        num_deleted = (
            db.query(gear_components_models.GearComponents)
            .filter(
                gear_components_models.GearComponents.user_id == user_id,
                gear_components_models.GearComponents.id == gear_component_id,
            )
            .delete()
        )

        # Check if the gear component was found and deleted
        if num_deleted == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Gear component with ID {gear_component_id} not found",
            )

        # Commit the transaction
        db.commit()
    except HTTPException as http_err:
        raise http_err
    except Exception as err:
        # Rollback the transaction
        db.rollback()

        # Log the exception
        core_logger.print_to_log(
            f"Error in delete_gear_component: {err}", "error", exc=err
        )

        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err

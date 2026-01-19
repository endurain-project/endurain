from fastapi import HTTPException, status
from sqlalchemy.orm import Session

import computer_models.schema as computer_models_schema
import computer_models.models as computer_models_models


import core.logger as core_logger


def get_computer_model_by_id(
    computer_model_id: int, db: Session
) -> computer_models_schema.ComputerModelRead | None:
    try:
        computer_model = (
            db.query(computer_models_models.ComputerModel)
            .filter(computer_models_models.ComputerModel.id == computer_model_id)
            .first()
        )

        if computer_model is None:
            return None

        return computer_models_schema.ComputerModelRead.model_validate(computer_model)
    except Exception as err:
        core_logger.print_to_log(
            f"Error in get_computer_model_by_id: {err}", "error", exc=err
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def get_computer_model_by_manufacturer_and_product_code(
    manufacturer: str, product_code: str, db: Session
) -> computer_models_schema.ComputerModelRead | None:
    """Find a computer model by manufacturer and product code (e.g., 'garmin' + 'fenix7x')"""
    try:
        computer_model = (
            db.query(computer_models_models.ComputerModel)
            .filter(
                computer_models_models.ComputerModel.manufacturer == manufacturer.lower(),
                computer_models_models.ComputerModel.product_code == product_code.lower(),
            )
            .first()
        )

        if computer_model is None:
            return None

        return computer_models_schema.ComputerModelRead.model_validate(computer_model)
    except Exception as err:
        core_logger.print_to_log(
            f"Error in get_computer_model_by_manufacturer_and_product_code: {err}",
            "error",
            exc=err,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def get_computer_model_by_manufacturer_and_product_id(
    manufacturer: str, product_id: int, db: Session
) -> computer_models_schema.ComputerModelRead | None:
    """Find a computer model by manufacturer and numeric product ID"""
    try:
        computer_model = (
            db.query(computer_models_models.ComputerModel)
            .filter(
                computer_models_models.ComputerModel.manufacturer == manufacturer.lower(),
                computer_models_models.ComputerModel.product_id == product_id,
            )
            .first()
        )

        if computer_model is None:
            return None

        return computer_models_schema.ComputerModelRead.model_validate(computer_model)
    except Exception as err:
        core_logger.print_to_log(
            f"Error in get_computer_model_by_manufacturer_and_product_id: {err}",
            "error",
            exc=err,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def get_all_computer_models(
    db: Session,
) -> list[computer_models_schema.ComputerModelRead]:
    """Get all computer models"""
    try:
        computer_models = (
            db.query(computer_models_models.ComputerModel)
            .order_by(
                computer_models_models.ComputerModel.manufacturer,
                computer_models_models.ComputerModel.model_name,
            )
            .all()
        )

        return [
            computer_models_schema.ComputerModelRead.model_validate(cm)
            for cm in computer_models
        ]
    except Exception as err:
        core_logger.print_to_log(
            f"Error in get_all_computer_models: {err}", "error", exc=err
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def get_computer_models_by_manufacturer(
    manufacturer: str, db: Session
) -> list[computer_models_schema.ComputerModelRead]:
    """Get all computer models for a specific manufacturer"""
    try:
        computer_models = (
            db.query(computer_models_models.ComputerModel)
            .filter(
                computer_models_models.ComputerModel.manufacturer == manufacturer.lower()
            )
            .order_by(computer_models_models.ComputerModel.model_name)
            .all()
        )

        return [
            computer_models_schema.ComputerModelRead.model_validate(cm)
            for cm in computer_models
        ]
    except Exception as err:
        core_logger.print_to_log(
            f"Error in get_computer_models_by_manufacturer: {err}", "error", exc=err
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def create_computer_model(
    computer_model: computer_models_schema.ComputerModelCreate, db: Session
) -> computer_models_schema.ComputerModelRead:
    """Create a new computer model"""
    try:
        new_computer_model = computer_models_models.ComputerModel(
            manufacturer=computer_model.manufacturer.lower(),
            product_code=computer_model.product_code.lower()
            if computer_model.product_code
            else None,
            product_id=computer_model.product_id,
            model_name=computer_model.model_name,
            region=computer_model.region,
        )

        db.add(new_computer_model)
        db.commit()
        db.refresh(new_computer_model)

        return computer_models_schema.ComputerModelRead.model_validate(new_computer_model)
    except Exception as err:
        db.rollback()
        core_logger.print_to_log(
            f"Error in create_computer_model: {err}", "error", exc=err
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def get_or_create_computer_model_from_fit_data(
    manufacturer: str,
    product_code: str | None,
    product_id: int | None,
    product_name: str | None,
    db: Session,
) -> computer_models_schema.ComputerModelRead | None:
    """
    Find or create a computer model from FIT file data.

    For Garmin: Uses product_code to look up in computer_models table
    For Suunto: Uses product_name directly (no lookup needed)
    For others: Creates entry with available info
    """
    try:
        manufacturer_lower = manufacturer.lower() if manufacturer else None

        if not manufacturer_lower:
            return None

        # Try to find by product_code first (Garmin)
        if product_code:
            existing = get_computer_model_by_manufacturer_and_product_code(
                manufacturer_lower, product_code, db
            )
            if existing:
                return existing

        # Try to find by product_id
        if product_id:
            existing = get_computer_model_by_manufacturer_and_product_id(
                manufacturer_lower, product_id, db
            )
            if existing:
                return existing

        # For Suunto or unknown, create a new entry if we have a name
        if product_name:
            new_computer_model = computer_models_models.ComputerModel(
                manufacturer=manufacturer_lower,
                product_code=product_code.lower() if product_code else None,
                product_id=product_id,
                model_name=product_name,
            )
            db.add(new_computer_model)
            db.commit()
            db.refresh(new_computer_model)
            return computer_models_schema.ComputerModelRead.model_validate(new_computer_model)

        return None
    except Exception as err:
        db.rollback()
        core_logger.print_to_log(
            f"Error in get_or_create_computer_model_from_fit_data: {err}",
            "error",
            exc=err,
        )
        return None

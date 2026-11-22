"""Body Mass Index arithmetic."""

import modules.health.health_weight.schema as health_weight_schema


def calculate_bmi(weight_kg: float | None, height_cm: float | None) -> float | None:
    """Return the BMI for a weight and height, or ``None`` when it is unusable.

    Args:
        weight_kg: Weight in kilograms.
        height_cm: Height in centimeters.

    Returns:
        ``weight / (height in metres) ** 2``, or ``None`` without a positive weight and height or
        when the result falls outside ``0`` to ``MAX_BMI``, which a stored BMI cannot be.
    """
    if weight_kg is None or not height_cm or height_cm <= 0:
        return None
    bmi = float(weight_kg) / ((height_cm / 100) ** 2)
    return bmi if 0 <= bmi <= health_weight_schema.MAX_BMI else None

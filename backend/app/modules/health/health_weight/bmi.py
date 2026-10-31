"""Body Mass Index arithmetic."""


def calculate_bmi(weight_kg: float | None, height_cm: float | None) -> float | None:
    """Return the BMI for a weight and height, or ``None`` when either is unusable.

    Args:
        weight_kg: Weight in kilograms.
        height_cm: Height in centimeters.

    Returns:
        ``weight / (height in metres) ** 2``, or ``None`` without a positive weight and height.
    """
    if weight_kg is None or not height_cm or height_cm <= 0:
        return None
    return float(weight_kg) / ((height_cm / 100) ** 2)

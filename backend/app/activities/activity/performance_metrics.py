"""
Performance Metrics Module

This module contains functions to calculate advanced performance metrics for cycling and running activities,
including power-based metrics, heart rate efficiency, climbing metrics, and advanced mathematical derivations.

Metrics include:
- Normalized Power (NP)
- Intensity Factor (IF)
- Training Stress Score (TSS)
- Variability Index (VI)
- Efficiency Factor (EF)
- Aerobic Decoupling (Pw:HR)
- VAM (Velocità Ascensionale Media)
- Climbing Efficiency
- Gradient Distribution
- W' Balance (W-Prime)
- Quadrant Analysis
- Power Duration Curve
"""

from typing import List, Dict, Optional, Tuple
from statistics import mean
import math
import core.logger as core_logger


def calculate_normalized_power(power_waypoints: List[Dict]) -> Optional[float]:
    """
    Calculate Normalized Power (NP).
    
    Normalized Power is a better measure of the physiological cost of a ride than average power.
    Algorithm:
    1. Take a 30-second rolling average of the power stream
    2. Raise each value to the 4th power
    3. Average those results
    4. Take the 4th root
    
    Args:
        power_waypoints: List of dictionaries with 'power' and 'time' keys
        
    Returns:
        Normalized power in watts, or None if insufficient data
    """
    try:
        power_values = [
            float(wp.get("power"))
            for wp in power_waypoints
            if wp.get("power") is not None
        ]
    except (ValueError, TypeError):
        return None
    
    if not power_values or len(power_values) < 2:
        return None
    
    # Rolling 30-second average (assuming waypoints are 1 second apart)
    window_size = min(30, len(power_values))
    rolling_avg = []
    
    for i in range(len(power_values) - window_size + 1):
        window = power_values[i : i + window_size]
        rolling_avg.append(mean(window))
    
    if not rolling_avg:
        return None
    
    # Raise to 4th power
    fourth_powers = [p ** 4 for p in rolling_avg]
    
    # Average the fourth powers
    avg_fourth_power = mean(fourth_powers)
    
    # Take the 4th root
    normalized_power = avg_fourth_power ** (1 / 4)
    
    return normalized_power


def calculate_intensity_factor(
    normalized_power: Optional[float],
    ftp: Optional[float]
) -> Optional[float]:
    """
    Calculate Intensity Factor (IF).
    
    Measures how hard a ride was relative to the user's fitness.
    Formula: IF = NP / FTP
    
    Args:
        normalized_power: Normalized power in watts
        ftp: Functional Threshold Power in watts
        
    Returns:
        Intensity factor, or None if insufficient data
    """
    if normalized_power is None or ftp is None or ftp == 0:
        return None
    
    return normalized_power / ftp


def calculate_training_stress_score(
    duration_seconds: float,
    normalized_power: Optional[float],
    intensity_factor: Optional[float],
    ftp: Optional[float]
) -> Optional[float]:
    """
    Calculate Training Stress Score (TSS).
    
    A numerical value for the total "load" of a workout.
    Formula: (Duration in sec × NP × IF) / (FTP × 3600) × 100
    
    Args:
        duration_seconds: Duration of activity in seconds
        normalized_power: Normalized power in watts
        intensity_factor: Intensity factor (IF)
        ftp: Functional Threshold Power in watts
        
    Returns:
        Training stress score, or None if insufficient data
    """
    if (normalized_power is None or intensity_factor is None or 
        ftp is None or ftp == 0 or duration_seconds <= 0):
        return None
    
    tss = (duration_seconds * normalized_power * intensity_factor) / (ftp * 3600) * 100
    return tss


def calculate_variability_index(
    normalized_power: Optional[float],
    average_power: Optional[float]
) -> Optional[float]:
    """
    Calculate Variability Index (VI).
    
    Indicates how "steady" or "punchy" the ride was.
    Formula: VI = NP / Average Power
    
    Interpretation:
    - Steady time trial: ~1.05
    - Criterium race: ~1.30+
    
    Args:
        normalized_power: Normalized power in watts
        average_power: Average power in watts
        
    Returns:
        Variability index, or None if insufficient data
    """
    if (normalized_power is None or average_power is None or 
        average_power == 0):
        return None
    
    return normalized_power / average_power


def calculate_efficiency_factor(
    normalized_power: Optional[float],
    average_heart_rate: Optional[float]
) -> Optional[float]:
    """
    Calculate Efficiency Factor (EF).
    
    Measures how much "output" (Power) you get for a specific "input" (Heart Rate).
    Formula: EF = NP / Average Heart Rate
    
    Args:
        normalized_power: Normalized power in watts
        average_heart_rate: Average heart rate in bpm
        
    Returns:
        Efficiency factor, or None if insufficient data
    """
    if (normalized_power is None or average_heart_rate is None or 
        average_heart_rate == 0):
        return None
    
    return normalized_power / average_heart_rate


def calculate_aerobic_decoupling(
    hr_waypoints: List[Dict],
    power_waypoints: List[Dict]
) -> Optional[float]:
    """
    Calculate Aerobic Decoupling (Pw:HR).
    
    Measures "cardiac drift" or how much heart rate rises as you fatigue over a steady ride.
    Algorithm:
    1. Split the ride into two halves
    2. Calculate EF (NP / Avg HR) for each half
    3. Return the percentage difference
    
    Value > 5% suggests lack of aerobic endurance for that duration.
    
    Args:
        hr_waypoints: List of dictionaries with 'heartrate' and 'time' keys
        power_waypoints: List of dictionaries with 'power' and 'time' keys
        
    Returns:
        Aerobic decoupling percentage, or None if insufficient data
    """
    if not hr_waypoints or not power_waypoints or len(hr_waypoints) < 4:
        return None
    
    try:
        hr_values = [
            float(wp.get("heartrate"))
            for wp in hr_waypoints
            if wp.get("heartrate") is not None
        ]
        power_values = [
            float(wp.get("power"))
            for wp in power_waypoints
            if wp.get("power") is not None
        ]
    except (ValueError, TypeError):
        return None
    
    if not hr_values or not power_values:
        return None
    
    # Split into two halves
    mid_point_hr = len(hr_values) // 2
    mid_point_power = len(power_values) // 2
    
    # First half
    first_half_hr = mean(hr_values[:mid_point_hr])
    first_half_power_avg = mean(power_values[:mid_point_power])
    
    # Second half
    second_half_hr = mean(hr_values[mid_point_hr:])
    second_half_power_avg = mean(power_values[mid_point_power:])
    
    # Calculate EF for each half
    ef_first = first_half_power_avg / first_half_hr if first_half_hr > 0 else None
    ef_second = second_half_power_avg / second_half_hr if second_half_hr > 0 else None
    
    if ef_first is None or ef_second is None:
        return None
    
    # Calculate percentage difference
    decoupling = ((ef_first - ef_second) / ef_first * 100) if ef_first > 0 else None
    
    return decoupling


def calculate_vam(
    elevation_waypoints: List[Dict],
    total_time_seconds: float
) -> Optional[float]:
    """
    Calculate VAM (Velocità Ascensionale Media).
    
    Average vertical ascent speed.
    Formula: (Vertical meters climbed × 60) / Time in minutes
    
    Args:
        elevation_waypoints: List of dictionaries with 'altitude' key
        total_time_seconds: Total time in seconds
        
    Returns:
        VAM in meters per hour, or None if insufficient data
    """
    if not elevation_waypoints or total_time_seconds <= 0:
        return None
    
    try:
        elevations = [
            float(wp.get("altitude"))
            for wp in elevation_waypoints
            if wp.get("altitude") is not None
        ]
    except (ValueError, TypeError):
        return None
    
    if not elevations or len(elevations) < 2:
        return None
    
    # Calculate total vertical gain
    total_vertical_gain = 0
    for i in range(1, len(elevations)):
        elevation_diff = elevations[i] - elevations[i - 1]
        if elevation_diff > 0:
            total_vertical_gain += elevation_diff
    
    if total_vertical_gain <= 0:
        return None
    
    # Convert to minutes and calculate VAM
    time_minutes = total_time_seconds / 60
    vam = (total_vertical_gain * 60) / time_minutes
    
    return vam


def calculate_climbing_efficiency(
    vam: Optional[float],
    average_power: Optional[float],
    athlete_weight_kg: Optional[float]
) -> Optional[float]:
    """
    Calculate Climbing Efficiency.
    
    VAM relative to power-to-weight ratio (W/kg).
    Formula: VAM / Power-to-weight ratio
    
    Args:
        vam: VAM in meters per hour
        average_power: Average power in watts
        athlete_weight_kg: Athlete weight in kilograms
        
    Returns:
        Climbing efficiency ratio, or None if insufficient data
    """
    if (vam is None or average_power is None or average_power == 0 or
        athlete_weight_kg is None or athlete_weight_kg == 0):
        return None
    
    power_to_weight = average_power / athlete_weight_kg
    
    if power_to_weight == 0:
        return None
    
    return vam / power_to_weight


def calculate_gradient_distribution(
    elevation_waypoints: List[Dict],
    distance_waypoints: List[Dict]
) -> Optional[Dict[str, float]]:
    """
    Calculate Gradient Distribution.
    
    Creates a histogram showing what percentage of the ride was spent at specific grades.
    
    Args:
        elevation_waypoints: List of dictionaries with 'altitude' key
        distance_waypoints: List of dictionaries with 'distance' key
        
    Returns:
        Dictionary with gradient ranges and percentage of time spent, or None if insufficient data
        Example: {">10%": 15.5, "7-10%": 22.3, "4-7%": 30.2, "<4%": 32.0}
    """
    if not elevation_waypoints or not distance_waypoints:
        return None
    
    try:
        elevations = [
            float(wp.get("altitude"))
            for wp in elevation_waypoints
            if wp.get("altitude") is not None
        ]
        distances = [
            float(wp.get("distance"))
            for wp in distance_waypoints
            if wp.get("distance") is not None
        ]
    except (ValueError, TypeError):
        return None
    
    if not elevations or not distances or len(elevations) < 2 or len(distances) < 2:
        return None
    
    # Calculate gradients for each segment
    min_segment_length = 100  # Minimum 100m segments for gradient calculation
    gradients = []
    
    for i in range(1, min(len(elevations), len(distances))):
        if distances[i] != distances[i - 1]:
            distance_diff = distances[i] - distances[i - 1]
            if distance_diff >= min_segment_length:
                elevation_diff = elevations[i] - elevations[i - 1]
                gradient = (elevation_diff / distance_diff) * 100
                gradients.append(gradient)
    
    if not gradients:
        return None
    
    # Categorize gradients
    categories = {
        ">10%": 0,
        "7-10%": 0,
        "4-7%": 0,
        "0-4%": 0,
        "<0% (descent)": 0
    }
    
    for gradient in gradients:
        if gradient > 10:
            categories[">10%"] += 1
        elif gradient >= 7:
            categories["7-10%"] += 1
        elif gradient >= 4:
            categories["4-7%"] += 1
        elif gradient >= 0:
            categories["0-4%"] += 1
        else:
            categories["<0% (descent)"] += 1
    
    # Convert to percentages
    total = sum(categories.values())
    if total == 0:
        return None
    
    distribution = {k: (v / total * 100) for k, v in categories.items()}
    
    return distribution


def calculate_w_prime_balance(
    power_waypoints: List[Dict],
    critical_power: Optional[float],
    w_prime_capacity: Optional[float]
) -> Optional[Dict]:
    """
    Calculate W' Balance (W-Prime).
    
    If you know a user's Critical Power, you can calculate their "anaerobic battery" 
    depletion in real-time throughout the ride to see exactly where they "blew up."
    
    Args:
        power_waypoints: List of dictionaries with 'power' and 'time' keys
        critical_power: Critical power threshold in watts
        w_prime_capacity: W' capacity in joules
        
    Returns:
        Dictionary with min W' balance and percent depleted, or None if insufficient data
    """
    if (not power_waypoints or critical_power is None or w_prime_capacity is None or
        critical_power == 0 or w_prime_capacity == 0):
        return None
    
    try:
        power_values = [
            float(wp.get("power"))
            for wp in power_waypoints
            if wp.get("power") is not None
        ]
    except (ValueError, TypeError):
        return None
    
    if not power_values:
        return None
    
    w_prime_balance = w_prime_capacity
    min_w_prime = w_prime_capacity
    
    for power in power_values:
        if power > critical_power:
            # Using simplified exponential decay model
            excess_power = power - critical_power
            tau = 546  # Time constant for recovery (seconds)
            # Approximate depletion: excess_power * time_step
            w_prime_balance -= excess_power  # Simplified (would need proper integration)
            min_w_prime = min(min_w_prime, w_prime_balance)
        elif power < critical_power:
            # Recovery
            recovery_rate = 0.01  # Recovery rate constant
            w_prime_balance = min(
                w_prime_capacity,
                w_prime_balance + recovery_rate * (w_prime_capacity - w_prime_balance)
            )
    
    percent_depleted = (
        max(0, (w_prime_capacity - min_w_prime) / w_prime_capacity * 100)
    )
    
    return {
        "min_w_prime": max(0, min_w_prime),
        "percent_depleted": percent_depleted
    }


def calculate_quadrant_analysis(
    power_waypoints: List[Dict],
    cadence_waypoints: List[Dict]
) -> Optional[Dict[str, float]]:
    """
    Calculate Quadrant Analysis.
    
    Plotting pedaling force vs. pedal speed to see if a ride was:
    - High-torque/low-cadence (grinding)
    - Low-torque/high-cadence (spinning)
    
    Args:
        power_waypoints: List of dictionaries with 'power' key
        cadence_waypoints: List of dictionaries with 'cadence' key
        
    Returns:
        Dictionary with quadrant distribution percentages, or None if insufficient data
    """
    if not power_waypoints or not cadence_waypoints:
        return None
    
    try:
        powers = [
            float(wp.get("power"))
            for wp in power_waypoints
            if wp.get("power") is not None
        ]
        cadences = [
            float(wp.get("cadence"))
            for wp in cadence_waypoints
            if wp.get("cadence") is not None
        ]
    except (ValueError, TypeError):
        return None
    
    if not powers or not cadences or len(powers) < 10 or len(cadences) < 10:
        return None
    
    # Use median values as dividers
    median_power = sorted(powers)[len(powers) // 2]
    median_cadence = sorted(cadences)[len(cadences) // 2]
    
    # Calculate force (proxy: power / cadence)
    forces = []
    for i in range(min(len(powers), len(cadences))):
        if cadences[i] > 0:
            forces.append(powers[i] / cadences[i])
    
    if not forces:
        return None
    
    median_force = sorted(forces)[len(forces) // 2]
    
    # Categorize into quadrants
    quadrants = {
        "high_force_low_cadence": 0,  # Grinding
        "high_force_high_cadence": 0,  # Powerful
        "low_force_low_cadence": 0,    # Coasting
        "low_force_high_cadence": 0    # Spinning
    }
    
    for i in range(len(forces)):
        if forces[i] >= median_force:
            if i < len(cadences) and cadences[i] >= median_cadence:
                quadrants["high_force_high_cadence"] += 1
            else:
                quadrants["high_force_low_cadence"] += 1
        else:
            if i < len(cadences) and cadences[i] >= median_cadence:
                quadrants["low_force_high_cadence"] += 1
            else:
                quadrants["low_force_low_cadence"] += 1
    
    # Convert to percentages
    total = sum(quadrants.values())
    if total == 0:
        return None
    
    distribution = {k: (v / total * 100) for k, v in quadrants.items()}
    
    return distribution


def calculate_power_duration_curve(
    power_waypoints: List[Dict]
) -> Optional[Dict[str, float]]:
    """
    Calculate Power Duration Curve.
    
    Scans the power stream for max power achieved over various windows:
    1s, 5s, 1m, 5m, 20m
    
    Args:
        power_waypoints: List of dictionaries with 'power' key
        
    Returns:
        Dictionary with time windows and corresponding max power, or None if insufficient data
    """
    if not power_waypoints:
        return None
    
    try:
        powers = [
            float(wp.get("power"))
            for wp in power_waypoints
            if wp.get("power") is not None
        ]
    except (ValueError, TypeError):
        return None
    
    if not powers or len(powers) < 60:
        return None
    
    # Define windows in number of points (assuming 1 second intervals)
    windows = {
        "1s": 1,
        "5s": 5,
        "1m": 60,
        "5m": 300,
        "20m": 1200,
        "1h" : 3600
    }
    
    curve = {}
    
    for label, window_size in windows.items():
        if window_size > len(powers):
            # Use all available data if window is larger
            curve[f"{len(powers) // 60}m"] = mean(powers)
            break
        else:
            max_power = 0
            for i in range(len(powers) - window_size + 1):
                window_avg = mean(powers[i : i + window_size])
                max_power = max(max_power, window_avg)
            curve[label] = max_power
    
    return curve


def calculate_all_performance_metrics(
    power_waypoints: Optional[List[Dict]],
    hr_waypoints: Optional[List[Dict]],
    elevation_waypoints: Optional[List[Dict]],
    distance_waypoints: Optional[List[Dict]],
    cadence_waypoints: Optional[List[Dict]],
    duration_seconds: float,
    average_power: Optional[float],
    average_heart_rate: Optional[float],
    ftp: Optional[float],
    critical_power: Optional[float] = None,
    w_prime_capacity: Optional[float] = None,
    athlete_weight_kg: Optional[float] = None
) -> Dict[str, Optional[float]]:
    """
    Calculate all available performance metrics for an activity.
    
    Args:
        power_waypoints: Power stream data
        hr_waypoints: Heart rate stream data
        elevation_waypoints: Elevation stream data
        distance_waypoints: Distance stream data
        cadence_waypoints: Cadence stream data
        duration_seconds: Total activity duration in seconds
        average_power: Average power in watts
        average_heart_rate: Average heart rate in bpm
        ftp: Functional Threshold Power in watts
        critical_power: Critical power in watts
        w_prime_capacity: W' capacity in joules
        athlete_weight_kg: Athlete weight in kg
        
    Returns:
        Dictionary containing all calculated metrics
    """
    # Log input parameters
    core_logger.print_to_log(
        f"[Performance Metrics] Calculating metrics with inputs: "
        f"duration={duration_seconds}s, avg_power={average_power}W, avg_hr={average_heart_rate}bpm, "
        f"ftp={ftp}W, power_waypoints={len(power_waypoints) if power_waypoints else 0}, "
        f"hr_waypoints={len(hr_waypoints) if hr_waypoints else 0}, "
        f"elevation_waypoints={len(elevation_waypoints) if elevation_waypoints else 0}, "
        f"distance_waypoints={len(distance_waypoints) if distance_waypoints else 0}, "
        f"cadence_waypoints={len(cadence_waypoints) if cadence_waypoints else 0}",
        "info"
    )
    
    # Calculate Normalized Power first as it's used by multiple metrics
    np_value = calculate_normalized_power(power_waypoints) if power_waypoints else None
    core_logger.print_to_log(f"[Performance Metrics] Normalized Power (NP): {np_value}W", "info")
    
    # Calculate primary metrics
    if_value = calculate_intensity_factor(np_value, ftp)
    core_logger.print_to_log(f"[Performance Metrics] Intensity Factor (IF): {if_value}", "info")
    
    tss_value = calculate_training_stress_score(duration_seconds, np_value, if_value, ftp)
    core_logger.print_to_log(f"[Performance Metrics] Training Stress Score (TSS): {tss_value}", "info")
    
    vi_value = calculate_variability_index(np_value, average_power)
    core_logger.print_to_log(f"[Performance Metrics] Variability Index (VI): {vi_value}", "info")
    
    ef_value = calculate_efficiency_factor(np_value, average_heart_rate)
    core_logger.print_to_log(f"[Performance Metrics] Efficiency Factor (EF): {ef_value}", "info")
    
    ad_value = calculate_aerobic_decoupling(hr_waypoints, power_waypoints) if (hr_waypoints and power_waypoints) else None
    core_logger.print_to_log(f"[Performance Metrics] Aerobic Decoupling: {ad_value}", "info")
    
    vam_value = calculate_vam(elevation_waypoints, duration_seconds) if elevation_waypoints else None
    core_logger.print_to_log(f"[Performance Metrics] VAM: {vam_value}m/h", "info")
    
    ce_value = calculate_climbing_efficiency(vam_value, average_power, athlete_weight_kg) if vam_value else None
    core_logger.print_to_log(f"[Performance Metrics] Climbing Efficiency: {ce_value}", "info")
    
    gd_value = calculate_gradient_distribution(elevation_waypoints, distance_waypoints) if (elevation_waypoints and distance_waypoints) else None
    core_logger.print_to_log(f"[Performance Metrics] Gradient Distribution: {gd_value}", "info")
    
    wpb_value = calculate_w_prime_balance(power_waypoints, critical_power, w_prime_capacity) if power_waypoints else None
    core_logger.print_to_log(f"[Performance Metrics] W' Balance: {wpb_value}", "info")
    
    qa_value = calculate_quadrant_analysis(power_waypoints, cadence_waypoints) if (power_waypoints and cadence_waypoints) else None
    core_logger.print_to_log(f"[Performance Metrics] Quadrant Analysis: {qa_value}", "info")
    
    pdc_value = calculate_power_duration_curve(power_waypoints) if power_waypoints else None
    core_logger.print_to_log(f"[Performance Metrics] Power Duration Curve: {pdc_value}", "info")
    
    return {
        "normalized_power": np_value,
        "intensity_factor": if_value,
        "training_stress_score": tss_value,
        "variability_index": vi_value,
        "efficiency_factor": ef_value,
        "aerobic_decoupling": ad_value,
        "vam": vam_value,
        "climbing_efficiency": ce_value,
        "gradient_distribution": gd_value,
        "w_prime_balance": wpb_value,
        "quadrant_analysis": qa_value,
        "power_duration_curve": pdc_value
    }

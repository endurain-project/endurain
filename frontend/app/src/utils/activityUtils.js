import { metersToKm } from "@/utils/unitsUtils"; // Import unit utils
import {
    formatDateMed,
    formatTime,
    formatSecondsToMinutes,
  } from "@/utils/dateTimeUtils"; // Import date/time utils

/**
 * Formats a given pace in meters per minute to a string representation in minutes per kilometer.
 *
 * @param {number} pace - The pace in meters per minute.
 * @param {boolean} units - Whether to include the units in the output string.
 * @returns {string} The formatted pace as a string in the format "MM:SS min/km".
 */
export function formatPaceMetric(pace, units = true) {
    // Convert pace to seconds per kilometer
    const pacePerKm = pace * 1000 / 60;
    // Calculate minutes and seconds
    const minutes = Math.floor(pacePerKm);
    const seconds = Math.round((pacePerKm - minutes) * 60);

    // Format the seconds
    const formattedSeconds = seconds < 10 ? `0${seconds}` : seconds;

    // Return the formatted pace
    if (units) {
        return `${minutes}:${formattedSeconds} min/km`;
    }
    return `${minutes}:${formattedSeconds}`;
}

/**
 * Converts a pace in meters per minute to a pace in minutes per mile.
 *
 * @param {number} pace - The pace in meters per minute.
 * @param {boolean} units - Whether to include the units in the output string.
 * @returns {string} The formatted pace in minutes per mile (min/mi).
 */
export function formatPaceImperial(pace, units = true) {
    // Convert pace to seconds per mile (1 mile = 1609.34 meters)
    const pacePerMile = (pace * 1609.34) / 60;
    // Calculate minutes and seconds
    const minutes = Math.floor(pacePerMile);
    const seconds = Math.round((pacePerMile - minutes) * 60);

    // Format the seconds
    const formattedSeconds = seconds < 10 ? `0${seconds}` : seconds;

    // Return the formatted pace
    if (units) {
        return `${minutes}:${formattedSeconds} min/mi`;
    }
    return `${minutes}:${formattedSeconds}`;
}

/**
 * Formats the swimming pace from minutes per kilometer to minutes per 100 meters.
 *
 * @param {number} pace - The swimming pace in minutes per kilometer.
 * @param {boolean} units - Whether to include the units in the output string.
 * @returns {string} The formatted pace as a string in the format "MM:SS min/100m".
 */
export function formatPaceSwimMetric(pace, units = true) {
    // Convert pace to seconds per 100 meters
    const pacePerKm = pace * 100 / 60;
    // Calculate minutes and seconds
    const minutes = Math.floor(pacePerKm);
    const seconds = Math.round((pacePerKm - minutes) * 60);

    // Format the seconds
    const formattedSeconds = seconds < 10 ? `0${seconds}` : seconds;

    // Return the formatted pace
    if (units) {
        return `${minutes}:${formattedSeconds} min/100m`;
    }
    return `${minutes}:${formattedSeconds}`;
}

/**
 * Converts a swimming pace from meters per second to minutes per 100 yards.
 *
 * @param {number} pace - The swimming pace in meters per second.
 * @param {boolean} units - Whether to include the units in the output string.
 * @returns {string} The formatted pace in minutes per 100 yards (min/100yd).
 */
export function formatPaceSwimImperial(pace, units = true) {
    // Convert pace to seconds per 100 yards (1 yard = 0.9144 meters)
    const pacePer100Yards = (pace * 100 * 0.9144) / 60;
    // Calculate minutes and seconds
    const minutes = Math.floor(pacePer100Yards);
    const seconds = Math.round((pacePer100Yards - minutes) * 60);

    // Format the seconds
    const formattedSeconds = seconds < 10 ? `0${seconds}` : seconds;

    // Return the formatted pace
    if (units) {
        return `${minutes}:${formattedSeconds} min/100yd`;
    }
    return `${minutes}:${formattedSeconds}`;
}

/**
 * Converts a speed from meters per second (m/s) to kilometers per hour (km/h) and formats it to a whole number.
 *
 * @param {number} speed - The speed in meters per second (m/s).
 * @returns {string} The speed converted to kilometers per hour (km/h) and rounded to the nearest whole number.
 */
export function formatAverageSpeedMetric(speed) {
    return (speed * 3.6).toFixed(0);
}

/**
 * Converts a speed from meters per second to miles per hour and formats it to a whole number.
 *
 * @param {number} speed - The speed in meters per second.
 * @returns {string} The speed in miles per hour, rounded to the nearest whole number.
 */
export function formatAverageSpeedImperial(speed) {
    return (speed * 2.23694).toFixed(0);
}

/**
 * Formats the pace for an activity based on its type and the desired unit system,
 * utilizing the existing specific formatting functions.
 * Input speed is expected in seconds per meter (s/m).
 *
 * @param {object} activity - The activity object, containing average_speed (s/m) and activity_type.
 * @param {int} unitSystem - 1 = 'metric' or 'imperial'.
 * @param {boolean} [units=true] - Whether to include the unit string (e.g., "min/km").
 * @returns {string} The formatted pace string (e.g., "MM:SS min/km", "MM:SS min/100m").
 */
export function formatPace(activity, unitSystem, units = true) {

    const isSwim = activity.activity_type === 8 || activity.activity_type === 9;

    if (isSwim) {
        if (unitSystem === 1) {
            // formatPaceSwimMetric expects pace in minutes per kilometer
            return formatPaceSwimMetric(activity.pace, units);
        } else { // imperial
            // formatPaceSwimImperial expects pace in meters per second
            return formatPaceSwimImperial(activity.pace, units);
        }
    } else { // Non-swim activities
        if (unitSystem === 1) {
            // formatPaceMetric expects pace in meters per minute
            return formatPaceMetric(activity.pace, units);
        } else { // imperial
            // formatPaceImperial expects pace in meters per minute
            return formatPaceImperial(activity.pace, units);
        }
    }
}

/**
 * Formats the average speed for an activity based on the desired unit system,
 * utilizing the existing specific formatting functions.
 * Input speed is expected in seconds per meter (s/m).
 *
 * @param {object} activity - The activity object, containing average_speed (s/m).
 * @param {int} unitSystem - 1 = 'metric' or 'imperial'.
 * @returns {string} The formatted speed string (km/h or mph, rounded to whole number).
 */
export function formatAverageSpeed(activity, unitSystem) {
    const avgSpeed_spm = activity?.average_speed; // seconds per meter

    if (!avgSpeed_spm || avgSpeed_spm <= 0) {
        return '--'; // Return placeholder if speed is invalid
    }

    const speed_ms = 1 / avgSpeed_spm; // meters per second

    if (unitSystem === 1) {
        return formatAverageSpeedMetric(speed_ms);
    } else { // imperial
        return formatAverageSpeedImperial(speed_ms);
    }
}

// Refactored to use dateTimeUtils
export function formatDateTime(dateTimeString) {
  if (!dateTimeString) return t("generalItems.labelNotApplicable");
  try {
    // Combine localized date and time from utils
    return `${formatDateMed(dateTimeString)}, ${formatTime(dateTimeString)}`;
  } catch (e) {
    console.error("Error formatting date/time:", e);
    return dateTimeString; // Fallback
  }
}

export function formatDuration(seconds) {
    if (seconds === null || seconds === undefined || seconds < 0)
      return t("generalItems.labelNotApplicable");
    try {
      return formatSecondsToMinutes(seconds);
    } catch (e) {
      console.error("Error formatting duration:", e);
      return seconds; // Fallback
    }
  }

// Refactored to use unitsUtils
export function formatDistance(meters) {
  if (meters === null || meters === undefined || meters < 0)
    return t("generalItems.labelNotApplicable");
  try {
    return `${metersToKm(meters)} km`; // Use util, keep unit consistent
  } catch (e) {
    console.error("Error formatting distance:", e);
    return meters; // Fallback
  }
}

export function formatAvgHr(avgHr) {
	if (avgHr === null || avgHr === undefined || avgHr <= 0)
		return t("generalItems.labelNotApplicable");
return `${Math.round(avgHr)} bpm`; // Assuming 'bpm' unit doesn't need translation for US
}

export function formatElevation(meters) {
	if (meters === null || meters === undefined)
		return t("generalItems.labelNotApplicable");
	return `${meters.toLocaleString()} m`; // Assuming 'm' unit doesn't need translation for US
}

export function formatCalories(calories) {
	if (calories === null || calories === undefined)
		return t("generalItems.labelNotApplicable");
	return `${calories.toLocaleString()} kcal`; // Assuming 'm' unit doesn't need translation for US
}

export function getIcon(typeId) {
  const iconMap = {
    1: ["fas", "person-running"],
    2: ["fas", "person-running"],
    3: ["fas", "person-running"], // Consider a different icon for virtual?
    4: ["fas", "person-biking"],
    5: ["fas", "person-biking"],
    6: ["fas", "person-biking"],
    7: ["fas", "person-biking"], // Consider a different icon for virtual?
    8: ["fas", "person-swimming"],
    9: ["fas", "person-swimming"],
    11: ["fas", "person-walking"],
    12: ["fas", "person-hiking"],
    13: ["fas", "sailboat"], // Rowing icon might be better if available
    14: ["fas", "hands-praying"], // Yoga icon might be better if available
    15: ["fas", "person-skiing"],
    16: ["fas", "person-skiing-nordic"],
    17: ["fas", "person-snowboarding"],
    18: ["fas", "repeat"], // Transition icon
    21: ["fas", "table-tennis-paddle-ball"], // Racquet sports
    22: ["fas", "table-tennis-paddle-ball"],
    23: ["fas", "table-tennis-paddle-ball"],
    24: ["fas", "table-tennis-paddle-ball"],
    25: ["fas", "table-tennis-paddle-ball"],
    26: ["fas", "table-tennis-paddle-ball"],
    27: ["fas", "person-biking"],
  };

  return iconMap[typeId] || ["fas", "dumbbell"]; // Default for Workout, Strength, Crossfit, etc.
}

/**
 * Formats the location of an activity based on available town, city, and country data.
 *
 * @param {object} activity - The activity object containing location fields (town, city, country).
 * @param {string} notApplicableLabel - The label to return if no location data is available.
 * @returns {string} The formatted location string (e.g., "Town, Country", "City", "N/A").
 */
export function formatLocation(activity) {
  const { town, city, country } = activity;

  if (!town && !city && !country) {
    return t("generalItems.labelNotApplicable");
  }

  let locationParts = [];
  if (town) {
    locationParts.push(town);
  } else if (city) {
    locationParts.push(city);
  }

  if (country) {
    // Add country, adding a comma only if town/city was already added
    if (locationParts.length > 0) {
      locationParts.push(`, ${country}`);
    } else {
      locationParts.push(country);
    }
  }

  return locationParts.join(''); // Join without extra spaces, comma is handled above
}

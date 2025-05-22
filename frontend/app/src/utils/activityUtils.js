import i18n from "@/i18n";
import {
	metersToKm,
	metersToMiles,
	metersToFeet,
	metersToYards,
} from "@/utils/unitsUtils";
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
	const pacePerKm = (pace * 1000) / 60;
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
	const pacePerKm = (pace * 100) / 60;
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
 * Checks if the activity type is a swimming activity.
 *
 * @param {object} activity - The activity object.
 * @returns {boolean} True if the type of the activity is swimming (Indoor or Outdoor), false otherwise.
 */
export function activityTypeIsSwimming(activity) {
    return activity.activity_type === 8 || activity.activity_type === 9;
}

/**
 * Formats the pace of an activity based on its type and the specified unit system.
 *
 * @param {Object} activity - The activity object containing pace and activity_type.
 * @param {number|string} unitSystem - The unit system to use (1 for metric, otherwise imperial).
 * @param {Object|null} [lap=null] - Optional lap object to use its enhanced_avg_pace instead of activity pace.
 * @param {boolean} [units=true] - Whether to include units in the formatted output.
 * @param {boolean} [isRest=false] - Whether the lap is a rest lap.
 * @returns {string} The formatted pace string.
 */
export function formatPace(activity, unitSystem, lap = null, units = true, isRest = false) {
	let pace = activity.pace;
	if (lap) {
		pace = lap.enhanced_avg_pace;
	}
    if (isRest) {
        return i18n.global.t("generalItems.labelRest");
    }
	if (
		activityTypeIsSwimming(activity) ||
		activity.activity_type === 13
	) {
		if (Number(unitSystem) === 1) {
			return formatPaceSwimMetric(pace, units);
		}
		return formatPaceSwimImperial(pace, units);
	}
	if (Number(unitSystem) === 1) {
		return formatPaceMetric(pace, units);
	}
	return formatPaceImperial(pace, units);
}


/**
 * Formats the average speed of an activity based on the unit system and activity type.
 *
 * @param {Object} activity - The activity object containing speed and type information.
 * @param {number|string} unitSystem - The unit system to use (1 for imperial, otherwise metric).
 * @param {Object|null} [lap=null] - Optional lap object to use for speed calculation.
 * @param {boolean} [units=true] - Whether to include units in the formatted string.
 * @returns {string} The formatted average speed, including units if specified, or a "No Data" label if unavailable.
 */
export function formatAverageSpeed(
	activity,
	unitSystem,
	lap = null,
	units = true,
) {
	let speed = activity.average_speed;
	if (lap) {
		speed = lap.enhanced_avg_speed;
	}
	if (
		activity.average_speed === null ||
		activity.average_speed === undefined ||
		activity.average_speed < 0
	)
		return i18n.global.t("generalItems.labelNoData");
	if (Number(unitSystem) === 1) {
		if (
			activity.activity_type === 4 ||
			activity.activity_type === 5 ||
			activity.activity_type === 6 ||
			activity.activity_type === 7 ||
			activity.activity_type === 27
		) {
			if (units) {
				return `${formatAverageSpeedImperial(speed)} ${i18n.global.t("generalItems.unitsKmH")}`;
			}
			return `${formatAverageSpeedMetric(speed)}`;
		}
		return i18n.global.t("generalItems.labelNoData");
	}
	if (
		activity.activity_type === 4 ||
		activity.activity_type === 5 ||
		activity.activity_type === 6 ||
		activity.activity_type === 7 ||
		activity.activity_type === 27
	) {
		if (units) {
			return `${formatAverageSpeedMetric(speed)} ${i18n.global.t("generalItems.unitsMph")}`;
		}
		return `${formatAverageSpeedImperial(speed)}`;
	}
	return i18n.global.t("generalItems.labelNoData");
}

/**
 * Formats a date-time string into a localized date and time string.
 *
 * @param {string} dateTimeString - The date-time string to format. If falsy, a "Not Applicable" label is returned.
 * @param {string} [separator=", "] - The separator to use between the date and time. Defaults to ", ".
 * @returns {string} The formatted date and time string, or a "Not Applicable" label if the input is invalid.
 */
export function formatDateTime(dateTimeString, separator = ", ") {
	if (!dateTimeString) return i18n.global.t("generalItems.labelNoData");
	return `${formatDateMed(dateTimeString)}${separator}${formatTime(dateTimeString)}`;
}

/**
 * Formats a duration given in seconds into a human-readable format.
 * If the input is null, undefined, or negative, it returns a localized "Not Applicable" label.
 *
 * @param {number|null|undefined} seconds - The duration in seconds to format.
 * @returns {string} The formatted duration or a "Not Applicable" label if the input is invalid.
 */
export function formatDuration(seconds) {
	if (seconds === null || seconds === undefined || seconds < 0)
		return i18n.global.t("generalItems.labelNoData");
	return formatSecondsToMinutes(seconds);
}

/**
 * Formats the distance of an activity or lap based on the unit system and activity type.
 *
 * @param {Object} activity - The activity object containing distance and activity_type.
 * @param {number|string} unitSystem - The unit system to use (1 for metric, otherwise imperial).
 * @param {Object|null} [lap=null] - Optional lap object containing total_distance.
 * @returns {string} The formatted distance string with appropriate units or a "No Data" label.
 */
export function formatDistance(activity, unitSystem, lap = null) {
	let distance = activity.distance;
	if (lap) {
		distance = lap.total_distance;
	}
	if (distance === null || distance === undefined || distance < 0)
		return i18n.global.t("generalItems.labelNoData");
	if (Number(unitSystem) === 1) {
		if (!activityTypeIsSwimming(activity)) {
			return `${metersToKm(distance)} ${i18n.global.t("generalItems.unitsKm")}`;
		}
		return `${distance} ${i18n.global.t("generalItems.unitsM")}`;
	}
	if (!activityTypeIsSwimming(activity)) {
		return `${metersToMiles(distance)} ${i18n.global.t("generalItems.unitsMiles")}`;
	}
	return `${metersToYards(distance)} ${i18n.global.t("generalItems.unitsYards")}`;
}

/**
 * Formats the heart rate (hr) into a user-friendly string.
 *
 * If the provided hr is null, undefined, or less than or equal to 0,
 * it returns a localized "Not Applicable" label. Otherwise, it rounds
 * the hr value and appends the localized "bpm" unit.
 *
 * @param {number|null|undefined} hr - The heart rate to format.
 * @returns {string} A formatted string representing the heart rate
 *                   or a "Not Applicable" label if the input is invalid.
 */
export function formatHr(hr) {
	if (hr === null || hr === undefined || hr <= 0)
		return i18n.global.t("generalItems.labelNoData");
	return `${Math.round(hr)} ${i18n.global.t("generalItems.unitsBpm")}`;
}

export function formatPower(power) {
	if (power === null || power === undefined || power <= 0)
		return i18n.global.t("generalItems.labelNoData");
	return `${Math.round(power)} ${i18n.global.t("generalItems.unitsWattsShort")}`;
}

/**
 * Formats an elevation value based on the provided unit system.
 *
 * @param {number|null|undefined} meters - The elevation value in meters. Can be null or undefined.
 * @param {number} unitSystem - The unit system to use. If `1`, the elevation is returned in meters; otherwise, it is converted to feet.
 * @returns {string} The formatted elevation string with the appropriate unit, or a "not applicable" label if the input is null or undefined.
 */
export function formatElevation(meters, unitSystem, units = true) {
  if (meters === null || meters === undefined) {
    return i18n.global.t("generalItems.labelNoData");
  }
  const numericValue = Number(unitSystem) === 1 ? parseFloat(meters) : parseFloat(metersToFeet(meters));
  const formattedValue = numericValue.toLocaleString(undefined, { maximumFractionDigits: 0 });

  if (!units) {
    return formattedValue;
  }

  const unitLabel = Number(unitSystem) === 1 ? i18n.global.t("generalItems.unitsM") : i18n.global.t("generalItems.unitsFeet");
  return `${formattedValue} ${unitLabel}`;
}

/**
 * Formats the given calorie value into a string with appropriate units.
 *
 * @param {number|null|undefined} calories - The calorie value to format. If null or undefined, a "not applicable" label is returned.
 * @returns {string} A formatted string representing the calorie value with units, or a "not applicable" label if the input is null or undefined.
 */
export function formatCalories(calories) {
  if (calories === null || calories === undefined) {
    return i18n.global.t("generalItems.labelNoData");
  }
  const numericValue = parseFloat(calories);
  const formattedValue = numericValue.toLocaleString(undefined, { maximumFractionDigits: 0 });
  return `${formattedValue} ${i18n.global.t("generalItems.unitsCalories")}`;
}

/**
 * Retrieves the corresponding Font Awesome icon class for a given activity type ID.
 *
 * @param {number} typeId - The ID representing the activity type.
 * @returns {string[]} An array containing the Font Awesome icon prefix and icon name.
 *                      Defaults to ["fas", "dumbbell"] if the typeId is not found.
 */
export function getIcon(typeId) {
	const iconMap = {
		1: ["fas", "person-running"],
		2: ["fas", "person-running"],
		3: ["fas", "person-running"],
		4: ["fas", "person-biking"],
		5: ["fas", "person-biking"],
		6: ["fas", "person-biking"],
		7: ["fas", "person-biking"],
		8: ["fas", "person-swimming"],
		9: ["fas", "person-swimming"],
		11: ["fas", "person-walking"],
		12: ["fas", "person-hiking"],
		13: ["fas", "sailboat"], // Rowing icon might be better if available
		14: ["fas", "hands-praying"], // Yoga icon might be better if available
		15: ["fas", "person-skiing"],
		16: ["fas", "person-skiing-nordic"],
		17: ["fas", "person-snowboarding"],
		18: ["fas", "repeat"],
		21: ["fas", "table-tennis-paddle-ball"], // Racquet sports
		22: ["fas", "table-tennis-paddle-ball"],
		23: ["fas", "table-tennis-paddle-ball"],
		24: ["fas", "table-tennis-paddle-ball"],
		25: ["fas", "table-tennis-paddle-ball"],
		26: ["fas", "table-tennis-paddle-ball"],
		27: ["fas", "person-biking"],
	};

	return iconMap[typeId] || ["fas", "dumbbell"];
}

/**
 * Formats the location of an activity into a readable string.
 *
 * @param {Object} activity - The activity object containing location details.
 * @returns {string} A formatted location string. If no location details are provided,
 * it returns a localized "Not Applicable" label.
 */
export function formatLocation(activity) {
	const { town, city, country } = activity;

	if (!town && !city && !country) {
		return i18n.global.t("generalItems.labelNoData");
	}

	const locationParts = [];
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

return locationParts.join(""); // Join without extra spaces, comma is handled above
}

/**
 * Formats a raw distance in meters based on the unit system.
 *
 * @param {number|null|undefined} meters - The distance in meters.
 * @param {number|string} unitSystem - The unit system to use (1 for metric, otherwise imperial).
 * @returns {string} The formatted distance string with appropriate units or a "No Data" label.
 */
export function formatRawDistance(meters, unitSystem) {
  if (meters === null || meters === undefined || meters < 0) {
    return i18n.global.t("generalItems.labelNoData");
  }
  const numericValue = Number(unitSystem) === 1 ? parseFloat(metersToKm(meters)) : parseFloat(metersToMiles(meters));
  // Assuming metersToKm and metersToMiles return numbers or strings that can be parsed to numbers
  // Use toLocaleString for formatting, allow for some decimal places for precision if needed
  const formattedValue = numericValue.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });

  const unitLabel = Number(unitSystem) === 1 ? i18n.global.t("generalItems.unitsKm") : i18n.global.t("generalItems.unitsMiles");
  return `${formattedValue} ${unitLabel}`;
}

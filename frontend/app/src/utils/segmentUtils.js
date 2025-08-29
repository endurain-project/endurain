import i18n from "@/i18n";
import Decimal from 'decimal.js';
import {
	formatAverageSpeedImperial,
	formatAverageSpeedMetric,
	formatPaceSwimImperial,
	formatPaceSwimMetric,
	formatPaceImperial,
	formatPaceMetric
 } from "./activityUtils";

export function activityTypeIsCycling(activity_type) {
	return activity_type === 4 || activity_type === 5 || activity_type === 6 || activity_type === 7 || activity_type === 27 || activity_type === 28 || activity_type === 29;
}

export function activityTypeIsSwimming(activity_type) {
	return activity_type === 8 || activity_type === 9;
}

export function activityTypeIsRowing(activity_type) {
	return activity_type === 13;
}

export function activityTypeIsWindsurf(activity_type) {
	return activity_type === 30;
}

/**
 * Formats the location of an activity into a readable string.
 *
 * @param {Object} activity - The activity object containing location details.
 * @returns {string} A formatted location string. If no location details are provided,
 * it returns a localized "Not Applicable" label.
 */
export function formatSegmentLocation(segment_location) {
	const { city, town, country } = segment_location;

	if (!city && !town && !country) {
		return i18n.global.t("generalItems.labelNoData");
	}

	const locationParts = [];
    // Want to support locality, city/town, country information
    if (town && city) {
        locationParts.push(`${town}, ${city}`);
    } else if (city) {
		locationParts.push(city);
	} else if (town) {
		locationParts.push(town);
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

export function formatSecondsToTime(seconds) {
	if (isNaN(seconds)) return '';
	const hours = Math.floor(seconds / 3600);
	const minutes = Math.floor((seconds % 3600) / 60);
	const secs = (seconds % 60).toFixed(1);
	if (hours > 0) {
		// If hours are present, show them
		return `${hours}h ${minutes.toString().padStart(2, '0')}m ${secs.toString().padStart(4, '0')}s`;
	} else {
		// If no hours, just show minutes and seconds
		return `${minutes}m ${secs.toString().padStart(4, '0')}s`;
	}
}

export function formatDistance(meters) {
	if (isNaN(meters)) return '';
	const kms = new Decimal(meters / 1000);
	if (kms > 1) {
		return `${kms.toDecimalPlaces(2)} km`;
	} else {
		return `${Math.round(meters)} m`;
	}
}

export function formatSpeed(
	pace,
	activity_type,
	unitSystem,
	units = true,
) {
	let speed = pace;
	if (
		pace === null ||
		pace === undefined ||
		pace < 0
	)
		return i18n.global.t("generalItems.labelNoData");

	if (
		activityTypeIsCycling(activity_type)
	) {
		if (Number(unitSystem) === 1) {
			if (units) {
				return `${formatAverageSpeedMetric(1/speed)} ${i18n.global.t("generalItems.unitsKmH")}`;
			}
			return `${formatAverageSpeedMetric(1/speed)}`;
		} else {
			if (units) {
				return `${formatAverageSpeedImperial(1/speed)} ${i18n.global.t("generalItems.unitsMph")}`;
			}
			return `${formatAverageSpeedImperial(1/speed)}`;
		}
	}
	else if(
		activityTypeIsSwimming(activity_type) ||
		activityTypeIsRowing(activity_type) ||
		activityTypeIsWindsurf(activity_type)
	)  {
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

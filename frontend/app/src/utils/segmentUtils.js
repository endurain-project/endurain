import i18n from "@/i18n";

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


import {
	getWeekStartDate,
	getWeekEndDate,
	getMonthStartDate,
	getMonthEndDate,
	formatDateISO,
} from "@/utils/dateTimeUtils";

/**
 * Builds parameters for summary API call
 * @param {string} viewType - The selected view type
 * @param {string} selectedDate - The selected date in ISO format
 * @param {number} selectedYear - The selected year
 * @returns {Object} - Parameters object for the API call
 */
export function buildSummaryParams(viewType, selectedDate, selectedYear) {
	const params = {};
	
	if (viewType === "year") {
		params.year = selectedYear;
	} else if (viewType === "week" || viewType === "month") {
		params.date = selectedDate;
	}
	// For 'lifetime', params remains empty
	
	return params;
}

/**
 * Builds filters for activities API call
 * @param {string} viewType - The selected view type
 * @param {string} selectedDate - The selected date in ISO format
 * @param {number} selectedYear - The selected year
 * @param {string} selectedActivityType - The selected activity type
 * @returns {Object} - Filters object for the API call
 */
export function buildActivityFilters(viewType, selectedDate, selectedYear, selectedActivityType) {
	const filters = {
		type: selectedActivityType || null,
	};
	
	if (viewType === "year") {
		// Note: Validation should be done before calling this function
		filters.start_date = `${selectedYear}-01-01`;
		filters.end_date = `${selectedYear + 1}-01-01`;
	} else if (viewType === "week" || viewType === "month") {
		const date = new Date(`${selectedDate}T00:00:00Z`);
		
		if (viewType === "week") {
			const weekStart = getWeekStartDate(date);
			const weekEnd = getWeekEndDate(date);
			filters.start_date = formatDateISO(weekStart);
			filters.end_date = formatDateISO(weekEnd);
		} else {
			// month
			const monthStart = getMonthStartDate(date);
			const monthEnd = getMonthEndDate(date);
			filters.start_date = formatDateISO(monthStart);
			filters.end_date = formatDateISO(monthEnd);
		}
	}
	// For 'lifetime', no date filters are added
	
	// Clean up null/empty values
	for (const key of Object.keys(filters)) {
		if (filters[key] == null || filters[key] === "") {
			delete filters[key];
		}
	}
	
	return filters;
}

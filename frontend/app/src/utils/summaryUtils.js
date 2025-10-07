import { DateTime } from 'luxon'
import {
  getWeekStartDate,
  getWeekEndDate,
  getMonthStartDate,
  getMonthEndDate,
  formatDateISO,
  formatUTCDateTimeISO,
  getYearStartDate,
  getYearEndDate
} from '@/utils/dateTimeUtils'

/**
 * Builds parameters for summary API call
 * @param {string} viewType - The selected view type
 * @param {string} selectedDate - The selected date in ISO format
 * @param {number} selectedYear - The selected year
 * @param {number} firstDayOfWeek - The first day of week preference (0 = Sunday, 1 = Monday, etc.)
 * @returns {Object} - Parameters object for the API call

export function buildSummaryParams(viewType, selectedDate, selectedYear, firstDayOfWeek = 0) {
    const params = {};
   
    if (viewType === "year") {
        params.year = selectedYear;
    } else if (viewType === "week" || viewType === "month") {
        params.date = selectedDate;
        // Include firstDayOfWeek for week view to ensure backend uses correct week boundaries
        if (viewType === "week") {
            params.firstDayOfWeek = firstDayOfWeek;
        }
    }
    // For 'lifetime', params remains empty
   
    return params;
} */
/**
 * @param {string} viewType - The selected view type
 * @param {string} selectedDate - The selected date in ISO format
 * @param {number} selectedYear - The selected year
 * @param {number} firstDayOfWeek - The first day of week preference (0 = Sunday, 1 = Monday, etc.)
 * @returns {Object} - Parameters object for the API call
 */
export function buildSummaryParams(viewType, selectedDate, selectedYear, firstDayOfWeek = 0) {
  const params = {}

  if (viewType === 'year') {
    params.year = selectedYear
  } else if (viewType === 'week' || viewType === 'month') {
    params.date = selectedDate
    // Include firstDayOfWeek for week view to ensure backend uses correct week boundaries
    if (viewType === 'week') {
      params.firstDayOfWeek = firstDayOfWeek
    }
  }
  // For 'lifetime', params remains empty

  return params
}

/**
 * Builds filters for activities API call
 * @param {string} viewType - The selected view type
 * @param {string} selectedDate - The selected date in ISO format
 * @param {number} selectedYear - The selected year
 * @param {string} selectedActivityType - The selected activity type
 * @param {number} firstDayOfWeek - The first day of week preference (0 = Sunday, 1 = Monday, etc.)
 * @returns {Object} - Filters object for the API call

export function buildActivityFilters(viewType, selectedDate, selectedYear, selectedActivityType, firstDayOfWeek = 0) {
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
            const weekStart = getWeekStartDate(date, firstDayOfWeek);
            const weekEnd = getWeekEndDate(date, firstDayOfWeek);
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
} */
/**
 * @param {string} selectedDate - The selected date in ISO format
 * @param {number} selectedYear - The selected year
 * @param {string} selectedActivityType - The selected activity type
 * @param {number} firstDayOfWeek - The first day of week preference (0 = Sunday, 1 = Monday, etc.)
 * @returns {Object} - Filters object for the API call
 */
export function buildActivityFilters(
  viewType,
  selectedDate,
  selectedYear,
  selectedActivityType,
  timezone,
  firstDayOfWeek = 0
) {
  const filters = {
    type: selectedActivityType || null
  }

  if (viewType === 'year') {
    // Note: Validation should be done before calling this function
    const datestr = `${selectedYear}-01-01T00:00:00`
    const date_tz_applied = DateTime.fromISO(datestr, {zone: timezone})
    const date = date_tz_applied.toUTC().toJSDate()
    const yearStart = getYearStartDate(date, timezone)
    const yearEnd = getYearEndDate(date, timezone)
    
    filters.start_date = formatUTCDateTimeISO(yearStart)
    filters.end_date = formatUTCDateTimeISO(yearEnd)

  } else if (viewType === 'month') {
    const date_tz_applied = DateTime.fromISO(selectedDate, { zone: timezone}).startOf("day")
    const date = date_tz_applied.toUTC().toJSDate()
    const monthStart = getMonthStartDate(date, timezone)
    const monthEnd = getMonthEndDate(date, timezone)

    filters.start_date = formatUTCDateTimeISO(monthStart)
    filters.end_date = formatUTCDateTimeISO(monthEnd)

  } else if (viewType === 'week') {
    const date_tz_applied = DateTime.fromISO(selectedDate, { zone: timezone}).startOf("day")
    const date = date_tz_applied.toUTC().toJSDate()
    const weekStart = getWeekStartDate(date, firstDayOfWeek)
    const weekEnd = getWeekEndDate(date, firstDayOfWeek)

    filters.start_date = formatUTCDateTimeISO(weekStart)
    filters.end_date = formatUTCDateTimeISO(weekEnd)
  }
  // For 'lifetime', no date filters are added

  // Clean up null/empty values
  for (const key of Object.keys(filters)) {
    if (filters[key] == null || filters[key] === '') {
      delete filters[key]
    }
  }

  return filters
}

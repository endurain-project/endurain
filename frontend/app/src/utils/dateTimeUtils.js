import { DateTime } from 'luxon'

/**
 * Formats a date string into a localized date format.
 *
 * @param {string} dateString - The date string to be formatted.
 * @returns {string} The formatted date string.
 */
export function formatDateShort(dateString) {
  // Create a DateTime object from the date string
  const date = DateTime.fromISO(dateString, { setZone: true })

  // Return the formatted date string respecting browser's locale
  return date.toLocaleString(DateTime.DATE_SHORT)
}

export function formatDateMed(dateString) {
  // Create a DateTime object from the date string
  const date = DateTime.fromISO(dateString, { setZone: true })

  // Return the formatted date string respecting browser's locale
  return date.toLocaleString(DateTime.DATE_MED)
}

/**
 * Formats a given date string into a time string.
 * @param {string} dateString - The date string to be formatted.
 * @returns {string} The formatted time string.
 */
export function formatTime(dateString) {
  // Create a DateTime object from the date string and preserve its time zone offset
  const date = DateTime.fromISO(dateString, { setZone: true })

  // Return the formatted time string, respecting the browser's locale
  return date.toLocaleString(DateTime.TIME_SIMPLE)
}

/**
 * Calculates the time difference between two given timestamps.
 *
 * @param {string} startTime - The start timestamp.
 * @param {string} endTime - The end timestamp.
 * @returns {string} The formatted time difference.
 */
export function calculateTimeDifference(startTime, endTime) {
  // Create new Date objects from the timestamps
  const startDateTime = new Date(startTime)
  const endDateTime = new Date(endTime)
  const interval = new Date(endDateTime - startDateTime)

  // Get the hours, minutes, and seconds from the interval
  const hours = interval.getUTCHours()
  const minutes = interval.getUTCMinutes()
  const seconds = interval.getUTCSeconds()

  // Return the formatted time difference
  if (hours < 1) {
    // If the difference is less than an hour, return the minutes and seconds
    return `${minutes}m ${seconds}s`
  }
  // If the difference is greater than an hour, return the hours and minutes
  return `${hours}h ${minutes}m`
}

/**
 * Converts a given number of seconds into a minutes:seconds format.
 *
 * @param {number} totalSeconds - The total number of seconds.
 * @returns {string} The formatted time string in minutes:seconds.
 */
export function formatSecondsToMinutes(totalSeconds) {
  const hours = Math.floor(totalSeconds / 3600)
  const minutes = Math.floor((totalSeconds % 3600) / 60)
  const seconds = Math.floor(totalSeconds % 60)

  const formattedSeconds = seconds < 10 ? `0${seconds}` : seconds
  const formattedMinutes = minutes < 10 && hours > 0 ? `0${minutes}` : minutes

  if (hours > 0) {
    return `${hours}h ${formattedMinutes}m ${formattedSeconds}s`
  }
  return `${minutes}m ${formattedSeconds}s`
}

/**
 * Converts a total number of seconds to the equivalent whole hours.
 *
 * @param {number} totalSeconds - The total number of seconds to convert.
 * @returns {number} The number of whole hours represented by the input seconds. Returns 0 if less than one hour.
 */
export function formatSecondsToOnlyHours(totalSeconds) {
  const hours = Math.floor(totalSeconds / 3600)

  if (hours > 0) {
    return `${hours}h`
  }
  return 0
}

/**
 * Gets the start date (Monday) of the week for a given date object, in UTC.
 * @param {Date} date - The input data object.
 * @returns {Date} - The data object for the Monday of that week (UTC).
 
export function getWeekStartDate(date) {
	return DateTime.fromJSDate(date, { zone: 'utc' }).startOf('week').toJSDate();
}*/

/**
 * Gets the start date of the week for a given date object, respecting the specified first day of week, in UTC.
 * @param {Date} date - The input date object.
 * @param {number} firstDayOfWeek - The first day of week (0 = Sunday, 1 = Monday, etc.).
 * @returns {Date} - The date object for the start of that week (UTC).
 */
export function getWeekStartDate(date, firstDayOfWeek = 0) {
  const dt = DateTime.fromJSDate(date, { zone: 'utc' })

  // Get the current day of the week (1 = Monday, 7 = Sunday in Luxon)
  const currentDayOfWeek = dt.weekday

  // Convert firstDayOfWeek parameter to Luxon format
  // 0 (Sunday) -> 7, 1 (Monday) -> 1, 2 (Tuesday) -> 2, etc.
  const luxonFirstDayOfWeek = firstDayOfWeek === 0 ? 7 : firstDayOfWeek

  // Calculate days to subtract to get to the start of the week
  let daysToSubtract = (currentDayOfWeek - luxonFirstDayOfWeek + 7) % 7

  return dt.minus({ days: daysToSubtract }).toJSDate()
}

/**
 * Gets the end date (start of next week) for a given JavaScript Date object's week, in UTC.
 * This means it's the first day of the next week, making the range exclusive for the end date.
 * @param {Date} jsDate - The input JavaScript Date object.
 * @returns {Date} - The JavaScript Date object for the start of the next week (UTC).
 
export function getWeekEndDate(jsDate) {
	return DateTime.fromJSDate(jsDate, { zone: 'utc' }).startOf('week').plus({ days: 7 }).toJSDate();
}*/
/**
 * Gets the end date (start of next week) for a given JavaScript Date object's week, in UTC.
 * This means it's the first day of the next week, making the range exclusive for the end date.
 * @param {Date} jsDate - The input JavaScript Date object.
 * @param {number} firstDayOfWeek - The first day of week (0 = Sunday, 1 = Monday, etc.).
 * @returns {Date} - The JavaScript Date object for the start of the next week (UTC).
 */
export function getWeekEndDate(jsDate, firstDayOfWeek = 0) {
  const weekStart = getWeekStartDate(jsDate, firstDayOfWeek)
  return DateTime.fromJSDate(weekStart, { zone: 'utc' }).plus({ days: 7 }).toJSDate()
}

/**
 * Navigates to the previous or next week based on the specified first day of week.
 * @param {Date} currentDate - The current date.
 * @param {number} direction - Direction to navigate (-1 for previous, 1 for next).
 * @param {number} firstDayOfWeek - The first day of week (0 = Sunday, 1 = Monday, etc.).
 * @returns {Date} - The new date after navigation.
 */
export function navigateWeek(currentDate, direction, firstDayOfWeek = 0) {
  return DateTime.fromJSDate(currentDate, { zone: 'utc' })
    .plus({ days: 7 * direction })
    .toJSDate()
}

/**
 * Gets the start date (1st) of the month for a given JavaScript Date object, in the specified timezone.
 * @param {Date} jsDate - The input JavaScript Date object.
 * @returns {Date} - The JavaScript Date object for the first day of that month (UTC).
 * @param {string} timezone - The local timezone.
 * @returns {Date} - The JavaScript Date object for the first day of that month in the specified timezone. */
export function getMonthStartDate(jsDate, timezone) {
  return DateTime.fromJSDate(jsDate, { zone: timezone }).startOf('month').toJSDate()
}

/**
 * Gets the end date (start of next month) for a given JavaScript Date object's month, in UTC.
 * This means it's the first day of the next month, making the range exclusive for the end date.
 * @param {Date} jsDate - The input JavaScript Date object.
 * @param {string} timezone - The timezone.
 * @returns {Date} - The JavaScript Date object for the start of the next month in the specified timezone.
 */
export function getMonthEndDate(jsDate, timezone) {
  return DateTime.fromJSDate(jsDate, { zone: timezone })
    .startOf('month')
    .plus({ months: 1 })
    .toJSDate()
}

/**
 * Gets the start date year for a given JavaScript Date object, in the specified time zone.
 * @param {Date} jsDate - The input JavaScript Date object.
 * @param {string} timezone - The timezone.
 * @returns {Date} - The JavaScript Date object for the first day of the year in the specified timezone.
 */

export function getYearStartDate(jsDate, timezone) {
  return DateTime.fromJSDate(jsDate, {zone: timezone}).startOf('year').toJSDate()
}

/**
 * Gets the start date of the next year for a given JavaScript Date object, in the specified time zone.
 * @param {Date} jsDate - The input JavaScript Date object.
 * @param {string} timezone - The timezone.
 * @returns {Date} - The JavaScript Date object for the first day of the next year in the specified timezone.
 */

export function getYearEndDate(jsDate, timezone) {
  return DateTime.fromJSDate(jsDate, {zone: timezone}).startOf('year').plus({years: 1}).toJSDate()
}

/**
 * Formats a Date object into a string with the format "YYYY-MM".
 *
 * @param {Date} date - The date to format.
 * @returns {string} The formatted date string in "YYYY-MM" format.
 */
export function formatDateToMonthString(date) {
  let year = date.getFullYear()
  let month = String(date.getMonth() + 1).padStart(2, '0')
  return `${year}-${month}`
}

/**
 * Formats a Date object into an ISO date string (YYYY-MM-DD).
 *
 * @param {Date} date - The date to format.
 * @returns {string} The formatted date string in ISO format.
 */
export function formatDateISO(date) {
  let year = date.getFullYear()
  let month = String(date.getMonth() + 1).padStart(2, '0')
  let day = String(date.getDate()).padStart(2, '0')

  return `${year}-${month}-${day}`
}

/**
 * Formats a Date object with time information into an ISO date string (YYYY-MM-DDTHH:MM:SS).
 *
 * @param {Date} datetime - The date with time information time to format.
 * @returns {string} The formatted date and time time string in ISO format.
 */
export function formatUTCDateTimeISO(datetime) {
  let year = datetime.getUTCFullYear()
  let month = String(datetime.getUTCMonth() + 1).padStart(2, '0')
  let day = String(datetime.getUTCDate()).padStart(2, '0')
  let hours = String(datetime.getUTCHours()).padStart(2, '0')
  let minutes = String(datetime.getUTCMinutes()).padStart(2, '0')
  let seconds = String(datetime.getUTCSeconds()).padStart(2, '0')
  return `${year}-${month}-${day}T${hours}:${minutes}:${seconds}`
}
import { DateTime } from 'luxon'

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

export function formatTime(dateString) {
  // Create a DateTime object from the date string and preserve its time zone offset
  const date = DateTime.fromISO(dateString, { setZone: true })

  // Return the formatted time string, respecting the browser's locale
  return date.toLocaleString(DateTime.TIME_SIMPLE)
}

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

export function formatSecondsToOnlyHours(totalSeconds) {
  const hours = Math.floor(totalSeconds / 3600)

  if (hours > 0) {
    return `${hours}h`
  }
  return 0
}

export function returnHoursMinutesFromSeconds(totalSeconds) {
  const hours = Math.floor(totalSeconds / 3600)
  const minutes = Math.floor((totalSeconds % 3600) / 60)

  return { hours, minutes }
}

export function returnSecondsFromHoursMinutes(hours, minutes) {
  return hours * 3600 + minutes * 60
}

/**
 * Formats seconds into a human-readable duration string without seconds.
 *
 * @param {number} seconds - The total number of seconds to format.
 * @returns {string} Formatted duration string (e.g., "2h 30m" or "45m").
 */
export function formatDuration(seconds) {
  const hours = Math.floor(seconds / 3600)
  const minutes = Math.floor((seconds % 3600) / 60)
  if (hours > 0) {
    return `${hours}h ${minutes}m`
  }
  return `${minutes}m`
}

/**
 * Formats a duration in seconds to a HH:mm string format.
 *
 * @param {number} seconds - The duration in seconds to format.
 * @returns {string} The formatted duration as a string in HH:mm format (e.g., "02:30").
 *
 * @example
 * formatDurationHHmm(9000) // Returns "02:30"
 * formatDurationHHmm(3661) // Returns "01:01"
 */
export function formatDurationHHmm(seconds) {
  const hours = Math.floor(seconds / 3600)
  const minutes = Math.floor((seconds % 3600) / 60)

  const formattedHours = String(hours).padStart(2, '0')
  const formattedMinutes = String(minutes).padStart(2, '0')

  return `${formattedHours}:${formattedMinutes}`
}

export function getWeekStartDate(date, firstDayOfWeek = 'monday') {
  const dt = DateTime.fromJSDate(date, { zone: 'utc' })

  // Get the current day of the week (1 = Monday, 7 = Sunday in Luxon)
  const currentDayOfWeek = dt.weekday

  // Map string day names to Luxon weekday numbers (1 = Monday, 7 = Sunday)
  const dayMap = {
    monday: 1,
    tuesday: 2,
    wednesday: 3,
    thursday: 4,
    friday: 5,
    saturday: 6,
    sunday: 7
  }

  // Convert firstDayOfWeek string to Luxon format
  const luxonFirstDayOfWeek = dayMap[firstDayOfWeek.toLowerCase()] || 1

  // Calculate days to subtract to get to the start of the week
  let daysToSubtract = (currentDayOfWeek - luxonFirstDayOfWeek + 7) % 7

  return dt.minus({ days: daysToSubtract }).toJSDate()
}

export function getWeekEndDate(jsDate, firstDayOfWeek = 'monday') {
  const weekStart = getWeekStartDate(jsDate, firstDayOfWeek)
  return DateTime.fromJSDate(weekStart, { zone: 'utc' }).plus({ days: 7 }).toJSDate()
}

export function navigateWeek(currentDate, direction, firstDayOfWeek = 'monday') {
  return DateTime.fromJSDate(currentDate, { zone: 'utc' })
    .plus({ days: 7 * direction })
    .toJSDate()
}

export function getMonthStartDate(jsDate) {
  return DateTime.fromJSDate(jsDate, { zone: 'utc' }).startOf('month').toJSDate()
}

/**
 * Gets the end date (start of next month) for a given JavaScript Date object's month, in UTC.
 * This means it's the first day of the next month, making the range exclusive for the end date.
 * @param {Date} jsDate - The input JavaScript Date object.
 * @returns {Date} - The JavaScript Date object for the start of the next month (UTC).
 */
export function getMonthEndDate(jsDate) {
  return DateTime.fromJSDate(jsDate, { zone: 'utc' })
    .startOf('month')
    .plus({ months: 1 })
    .toJSDate()
}

export function formatDateToMonthString(date) {
  let year = date.getFullYear()
  let month = String(date.getMonth() + 1).padStart(2, '0')
  return `${year}-${month}`
}

export function formatDateISO(date) {
  let year = date.getFullYear()
  let month = String(date.getMonth() + 1).padStart(2, '0')
  let day = String(date.getDate()).padStart(2, '0')

  return `${year}-${month}-${day}`
}

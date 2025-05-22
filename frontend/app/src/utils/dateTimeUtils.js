import { DateTime } from 'luxon';

/**
 * Formats a date string into a localized date format.
 *
 * @param {string} dateString - The date string to be formatted.
 * @returns {string} The formatted date string.
 */
export function formatDateShort(dateString) {
  // Create a DateTime object from the date string
  const date = DateTime.fromISO(dateString, { setZone: true });

  // Return the formatted date string respecting browser's locale
  return date.toLocaleString(DateTime.DATE_SHORT);
}

export function formatDateMed(dateString) {
  // Create a DateTime object from the date string
  const date = DateTime.fromISO(dateString, { setZone: true });

  // Return the formatted date string respecting browser's locale
  return date.toLocaleString(DateTime.DATE_MED);
}
  

/**
 * Formats a given date string into a time string.
 * @param {string} dateString - The date string to be formatted.
 * @returns {string} The formatted time string.
 */
export function formatTime(dateString) {
  // Create a DateTime object from the date string and preserve its time zone offset
  const date = DateTime.fromISO(dateString, { setZone: true });

  // Return the formatted time string, respecting the browser's locale
  return date.toLocaleString(DateTime.TIME_SIMPLE);
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
  const startDateTime = new Date(startTime);
  const endDateTime = new Date(endTime);
  const interval = new Date(endDateTime - startDateTime);

  // Get the hours, minutes, and seconds from the interval
  const hours = interval.getUTCHours();
  const minutes = interval.getUTCMinutes();
  const seconds = interval.getUTCSeconds();

  // Return the formatted time difference
  if (hours < 1) {
    // If the difference is less than an hour, return the minutes and seconds
    return `${minutes}m ${seconds}s`;
  }
  // If the difference is greater than an hour, return the hours and minutes
  return `${hours}h ${minutes}m`;
}

/**
 * Converts a given number of seconds into a minutes:seconds format.
 *
 * @param {number} totalSeconds - The total number of seconds.
 * @returns {string} The formatted time string in minutes:seconds.
 */
export function formatSecondsToMinutes(totalSeconds) {
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = Math.floor(totalSeconds % 60);

  const formattedSeconds = seconds < 10 ? `0${seconds}` : seconds;
  const formattedMinutes = minutes < 10 && hours > 0 ? `0${minutes}` : minutes;

  if (hours > 0) {
    return `${hours}:${formattedMinutes}:${formattedSeconds}`;
  }
  return `${minutes}:${formattedSeconds}`;
}

/**
 * Gets the start date (Monday) of the week for a given JavaScript Date object, in UTC.
 * @param {Date} jsDate - The input JavaScript Date object.
 * @returns {Date} - The JavaScript Date object for the Monday of that week (UTC).
 */
export function getWeekStartDate(jsDate) {
  return DateTime.fromJSDate(jsDate, { zone: 'utc' }).startOf('week').toJSDate();
}

/**
 * Gets the end date (start of next week) for a given JavaScript Date object's week, in UTC.
 * This means it's the first day of the next week, making the range exclusive for the end date.
 * @param {Date} jsDate - The input JavaScript Date object.
 * @returns {Date} - The JavaScript Date object for the start of the next week (UTC).
 */
export function getWeekEndDate(jsDate) {
  return DateTime.fromJSDate(jsDate, { zone: 'utc' }).startOf('week').plus({ days: 7 }).toJSDate();
}

/**
 * Gets the start date (1st) of the month for a given JavaScript Date object, in UTC.
 * @param {Date} jsDate - The input JavaScript Date object.
 * @returns {Date} - The JavaScript Date object for the first day of that month (UTC).
 */
export function getMonthStartDate(jsDate) {
  return DateTime.fromJSDate(jsDate, { zone: 'utc' }).startOf('month').toJSDate();
}

/**
 * Gets the end date (start of next month) for a given JavaScript Date object's month, in UTC.
 * This means it's the first day of the next month, making the range exclusive for the end date.
 * @param {Date} jsDate - The input JavaScript Date object.
 * @returns {Date} - The JavaScript Date object for the start of the next month (UTC).
 */
export function getMonthEndDate(jsDate) {
  return DateTime.fromJSDate(jsDate, { zone: 'utc' }).startOf('month').plus({ months: 1 }).toJSDate();
}

/**
 * Formats a JavaScript Date object into YYYY-MM-DD string (UTC).
 * Handles non-Date inputs by attempting to parse them.
 * @param {Date | string | number} jsDateInput - The input JavaScript Date object or a value parseable into a Date.
 * @returns {string} - The formatted date string (YYYY-MM-DD), or an empty string if input is invalid.
 */
export function formatDateToISOString(jsDateInput) {
  let dt;
  if (jsDateInput instanceof Date && !isNaN(jsDateInput.getTime())) {
    dt = DateTime.fromJSDate(jsDateInput, { zone: 'utc' });
  } else {
    // Attempt to parse if not a valid Date object (e.g., could be a date string)
    const parsedDate = new Date(jsDateInput);
    if (isNaN(parsedDate.getTime())) {
      console.error("formatDateToISOString received invalid date input:", jsDateInput);
      return "";
    }
    dt = DateTime.fromJSDate(parsedDate, { zone: 'utc' });
  }
  
  if (dt.isValid) {
    return dt.toISODate();
  }
  console.error("formatDateToISOString failed to create valid DateTime:", jsDateInput);
  return "";
}

/**
 * Parses a "YYYY-MM" string into the JavaScript Date object for the 1st of that month (UTC).
 * @param {string} monthString - The month string (e.g., "2023-10").
 * @returns {Date | null} - The JavaScript Date object for the start of the month (UTC), or null if invalid.
 */
export function parseMonthString(monthString) {
  if (typeof monthString !== 'string') {
    console.error("parseMonthString expects a string input. Received:", monthString);
    return null;
  }
  const dt = DateTime.fromFormat(monthString, 'yyyy-MM', { zone: 'utc' });
  if (dt.isValid) {
    return dt.startOf('month').toJSDate();
  }
  // Do not log error here if SummaryView handles it, to avoid console spam for tentative inputs
  // console.error(`Invalid month string format for : ${monthString}`); 
  return null;
}

/**
 * Formats a JavaScript Date object into a "YYYY-MM" string (UTC).
 * Handles non-Date inputs by attempting to parse them.
 * @param {Date | string | number} jsDateInput - The input JavaScript Date object or a value parseable into a Date.
 * @returns {string} - The formatted month string (YYYY-MM), or an empty string if input is invalid.
 */
export function formatDateToMonthString(jsDateInput) {
  let dt;
  if (jsDateInput instanceof Date && !isNaN(jsDateInput.getTime())) {
    dt = DateTime.fromJSDate(jsDateInput, { zone: 'utc' });
  } else {
    const parsedDate = new Date(jsDateInput);
    if (isNaN(parsedDate.getTime())) {
      console.error("formatDateToMonthString received invalid date input:", jsDateInput);
      return "";
    }
    dt = DateTime.fromJSDate(parsedDate, { zone: 'utc' });
  }

  if (dt.isValid) {
    return dt.toFormat('yyyy-MM');
  }
  console.error("formatDateToMonthString failed to create valid DateTime:", jsDateInput);
  return "";
}

/**
 * Formats a Date object into YYYY-MM-DD string.
 * @param {Date} date - The input date.
 * @returns {string} - The formatted date string.
 */
export function formatDateISO(date) {
    // Ensure input is a Date object
    if (!(date instanceof Date)) {
        console.error("formatDateISO received non-Date object:", date);
        // Attempt to parse if it's a valid date string, otherwise return empty or throw
        try {
            date = new Date(date);
            if (isNaN(date.getTime())) throw new Error("Invalid date input");
        } catch (e) {
            return ""; // Or handle error appropriately
        }
    }
    // Check for invalid date after potential parsing
    if (isNaN(date.getTime())) {
        console.error("formatDateISO received invalid Date object:", date);
        return "";
    }
    return date.toISOString().slice(0, 10);
}
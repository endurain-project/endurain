/**
 * Formats a date string into a localized date format.
 *
 * @param {string} dateString - The date string to be formatted.
 * @returns {string} The formatted date string.
 */
export function formatDate(dateString) {
  // Create a new Date object from the date string
  const date = new Date(dateString);

  // Return the formatted date string
  return date.toLocaleDateString(undefined, { day: '2-digit', month: '2-digit', year: '2-digit' });
}
  

/**
 * Formats a given date string into a time string.
 * @param {string} dateString - The date string to be formatted.
 * @returns {string} The formatted time string.
 */
export function formatTime(dateString) {
  // Create a new Date object from the date string
  const date = new Date(dateString);

  // Return the formatted time string
  return date.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' });
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
  } else {
    // If the difference is greater than an hour, return the hours and minutes
    return `${hours}h ${minutes}m`;
  }
}
/**
 * Formats the pace in minutes per kilometer.
 * 
 * @param {number} pace - The pace in minutes per kilometer.
 * @returns {string} The formatted pace in the format "minutes:seconds min/km".
 */
export function formatPace(pace) {
    // Convert pace to seconds per kilometer
    const pacePerKm = pace * 1000 / 60;
    // Calculate minutes and seconds
    const minutes = Math.floor(pacePerKm);
    const seconds = Math.round((pacePerKm - minutes) * 60);

    // Format the seconds
    const formattedSeconds = seconds < 10 ? `0${seconds}` : seconds;

    // Return the formatted pace
    return `${minutes}:${formattedSeconds} min/km`;
}

/**
 * Formats the pace for swimming activities.
 * @param {number} pace - The pace in minutes per 100 meters.
 * @returns {string} The formatted pace in the format "minutes:seconds min/km".
 */
export function formatPaceSwim(pace) {
    // Convert pace to seconds per 100 meters
    const pacePerKm = pace * 100 / 60;
    // Calculate minutes and seconds
    const minutes = Math.floor(pacePerKm);
    const seconds = Math.round((pacePerKm - minutes) * 60);

    // Format the seconds
    const formattedSeconds = seconds < 10 ? `0${seconds}` : seconds;

    // Return the formatted pace
    return `${minutes}:${formattedSeconds} min/100m`;
}
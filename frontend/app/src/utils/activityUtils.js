/**
 * Formats a given pace in meters per minute to a string representation in minutes per kilometer.
 *
 * @param {number} pace - The pace in meters per minute.
 * @param {boolean} units - Whether to include the units in the output string.
 * @returns {string} The formatted pace as a string in the format "MM:SS min/km".
 */
export function formatPaceMetric(pace, units = true) {
    // Convert pace to seconds per kilometer
    const pacePerKm = pace * 1000 / 60;
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
    const pacePerKm = pace * 100 / 60;
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
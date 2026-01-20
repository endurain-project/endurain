import { metersToKm, metersToMiles, metersToFeet, metersToYards } from '@/utils/unitsUtils'
import { formatDateMed, formatTime, formatSecondsToMinutes } from '@/utils/dateTimeUtils' // Import date/time utils

/**
 * An array of numeric identifiers representing different activity types.
 * Each number corresponds to a specific activity type used within the application.
 * @type {number[]}
 */
const ACTIVITY_TYPES = [
  1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27,
  28, 29, 30, 31, 32, 33, 34, 35, 36, 37, 38, 39, 40, 41, 42, 43, 44, 45, 46
]

/**
 * Maps activity type IDs to functions that return localized activity labels.
 *
 * @type {Object<number, function(function(string): string): string>}
 * Each key is an activity type ID (number).
 * Each value is a function that takes a translation function `t` and returns the localized label string.
 *
 * Example usage:
 *   const label = activityLabelMap[1](t); // Returns the localized label for "run"
 */
const activityLabelMap = {
  1: (t) => t('activityItems.run'),
  2: (t) => t('activityItems.trailRun'),
  3: (t) => t('activityItems.virtualRun'),
  4: (t) => t('activityItems.ride'),
  5: (t) => t('activityItems.gravelRide'),
  6: (t) => t('activityItems.mtbRide'),
  7: (t) => t('activityItems.virtualRide'),
  8: (t) => t('activityItems.lapSwimming'),
  9: (t) => t('activityItems.openWaterSwimming'),
  10: (t) => t('activityItems.workout'),
  11: (t) => t('activityItems.walk'),
  12: (t) => t('activityItems.hike'),
  13: (t) => t('activityItems.rowing'),
  14: (t) => t('activityItems.yoga'),
  15: (t) => t('activityItems.alpineSki'),
  16: (t) => t('activityItems.nordicSki'),
  17: (t) => t('activityItems.snowboard'),
  18: (t) => t('activityItems.transition'),
  19: (t) => t('activityItems.strengthTraining'),
  20: (t) => t('activityItems.crossfit'),
  21: (t) => t('activityItems.tennis'),
  22: (t) => t('activityItems.tableTennis'),
  23: (t) => t('activityItems.badminton'),
  24: (t) => t('activityItems.squash'),
  25: (t) => t('activityItems.racquetball'),
  26: (t) => t('activityItems.pickleball'),
  27: (t) => t('activityItems.commutingRide'),
  28: (t) => t('activityItems.indoorRide'),
  29: (t) => t('activityItems.mixedSurfaceRide'),
  30: (t) => t('activityItems.windsurf'),
  31: (t) => t('activityItems.indoorWalk'),
  32: (t) => t('activityItems.standUpPaddling'),
  33: (t) => t('activityItems.surf'),
  34: (t) => t('activityItems.trackRun'),
  35: (t) => t('activityItems.ebikeRide'),
  36: (t) => t('activityItems.ebikeMountainRide'),
  37: (t) => t('activityItems.iceSkate'),
  38: (t) => t('activityItems.soccer'),
  39: (t) => t('activityItems.padel'),
  40: (t) => t('activityItems.treadmillRun'),
  41: (t) => t('activityItems.cardioTraining'),
  42: (t) => t('activityItems.kayaking'),
  43: (t) => t('activityItems.sailing'),
  44: (t) => t('activityItems.snowShoeing'),
  45: (t) => t('activityItems.inlineSkating'),
  46: (t) => t('activityItems.hiit')
}

/**
 * Returns the localized label for a given activity type.
 *
 * If `activity_type` exists in the global ACTIVITY_TYPES array, the corresponding
 * formatter function from `activityLabelMap` is invoked with the translation
 * function `t` and its result is returned. Otherwise a default translated
 * label for the key "activityItems.workout" is returned.
 *
 * @param {string} activity_type - Identifier of the activity type to resolve.
 * @param {function(string, Object=): string} t - Translation function that accepts a translation key and optional options, returning the localized string.
 * @returns {string} Localized label for the specified activity type, or a default "workout" label when the type is unknown.
 *
 * @see ACTIVITY_TYPES
 * @see activityLabelMap
 */
export function activityTypeName(activity_type, t) {
  if (ACTIVITY_TYPES.includes(activity_type)) {
    return activityLabelMap[activity_type](t)
  }
  return t('activityItems.workout')
}

/**
 * Formats the name of an activity, optionally appending its location.
 *
 * @param {Object} activity - The activity object containing details about the activity.
 * @param {string} activity.activity_type - The type of the activity.
 * @param {string} [activity.town] - The town where the activity took place (optional).
 * @param {string} [activity.city] - The city where the activity took place (optional).
 * @param {Function} t - The translation function.
 * @returns {string} The formatted activity name, including location if available, or "Workout" as a default.
 */
export function formatName(activity, t) {
  if (ACTIVITY_TYPES.includes(activity.activity_type) && activity.activity_type !== 10) {
    const translation = activityLabelMap[activity.activity_type](t)
    if (activity.town || activity.city) {
      // If the activity has a town or city, append it to the label
      const location = activity.town || activity.city
      return `${translation}${t('activityItems.labelWorkout')} - ${location}`
    }
    return `${translation}${t('activityItems.labelWorkout')}`
  }
  return 'Workout' // Default label for activities not in the map
}

/**
 * Formats a given pace in meters per minute to a string representation in minutes per kilometer.
 *
 * @param {number} pace - The pace in meters per minute.
 * @param {boolean} units - Whether to include the units in the output string.
 * @returns {string} The formatted pace as a string in the format "MM:SS min/km".
 */
export function formatPaceMetric(pace, units = true) {
  // Convert pace to seconds per kilometer
  const pacePerKm = (pace * 1000) / 60
  // Calculate minutes and seconds
  let minutes = Math.floor(pacePerKm)
  let seconds = Math.round((pacePerKm - minutes) * 60)

  // If rounding pushed us up to 60 seconds, roll over
  if (seconds === 60) {
    minutes += 1
    seconds = 0
  }

  // Format the seconds
  const formattedSeconds = seconds < 10 ? `0${seconds}` : seconds

  // Return the formatted pace
  if (units) {
    return `${minutes}:${formattedSeconds} min/km`
  }
  return `${minutes}:${formattedSeconds}`
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
  const pacePerMile = (pace * 1609.34) / 60
  // Calculate minutes and seconds
  let minutes = Math.floor(pacePerMile)
  let seconds = Math.round((pacePerMile - minutes) * 60)

  // Format the seconds
  const formattedSeconds = seconds < 10 ? `0${seconds}` : seconds

  // Catch the rare “60 seconds” case and roll it into an extra minute
  if (seconds === 60) {
    minutes += 1
    seconds = 0
  }

  // Return the formatted pace
  if (units) {
    return `${minutes}:${formattedSeconds} min/mi`
  }
  return `${minutes}:${formattedSeconds}`
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
  const pacePerKm = (pace * 100) / 60
  // Calculate minutes and seconds
  let minutes = Math.floor(pacePerKm)
  let seconds = Math.round((pacePerKm - minutes) * 60)

  // Format the seconds
  const formattedSeconds = seconds < 10 ? `0${seconds}` : seconds

  // Catch the rare “60 seconds” case and roll it into an extra minute
  if (seconds === 60) {
    minutes += 1
    seconds = 0
  }

  // Return the formatted pace
  if (units) {
    return `${minutes}:${formattedSeconds} min/100m`
  }
  return `${minutes}:${formattedSeconds}`
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
  const pacePer100Yards = (pace * 100 * 0.9144) / 60
  // Calculate minutes and seconds
  let minutes = Math.floor(pacePer100Yards)
  let seconds = Math.round((pacePer100Yards - minutes) * 60)

  // Format the seconds
  const formattedSeconds = seconds < 10 ? `0${seconds}` : seconds

  // Catch the rare “60 seconds” case and roll it into an extra minute
  if (seconds === 60) {
    minutes += 1
    seconds = 0
  }

  // Return the formatted pace
  if (units) {
    return `${minutes}:${formattedSeconds} min/100yd`
  }
  return `${minutes}:${formattedSeconds}`
}

/**
 * Converts a speed from meters per second (m/s) to kilometers per hour (km/h) and formats it to two decimal places.
 *
 * @param {number} speed - The speed in meters per second (m/s).
 * @returns {string} The speed converted to kilometers per hour (km/h) and formatted to two decimal places.
 */
export function formatAverageSpeedMetric(speed) {
  return (speed * 3.6).toFixed(2)
}

/**
 * Converts a speed from meters per second to miles per hour and formats it to two decimal places.
 *
 * @param {number} speed - The speed in meters per second.
 * @returns {string} The speed in miles per hour, formatted to two decimal places.
 */
export function formatAverageSpeedImperial(speed) {
  return (speed * 2.23694).toFixed(2)
}

/**
 * Checks if the activity type is a swimming activity.
 *
 * @param {object} activity - The activity object.
 * @param {number} activity.activity_type - The type identifier of the activity.
 * @returns {boolean} True if the type of the activity is swimming (Indoor or Outdoor), false otherwise.
 */
export function activityTypeIsSwimming(activity) {
  return activity.activity_type === 8 || activity.activity_type === 9
}

/**
 * Checks if the activity type is not a swimming-related activity.
 *
 * @param {Object} activity - The activity object to check.
 * @param {number} activity.activity_type - The type identifier of the activity.
 * @returns {boolean} Returns true if the activity is not swimming-related (types 8, or 9), otherwise false.
 */
export function activityTypeNotSwimming(activity) {
  return activity.activity_type !== 8 && activity.activity_type !== 9
}

/**
 * Checks if the activity type is a running activity.
 *
 * @param {object} activity - The activity object.
 * @param {number} activity.activity_type - The type identifier of the activity.
 * @returns {boolean} True if the type of the activity is running, false otherwise.
 */
export function activityTypeIsRunning(activity) {
  return (
    activity.activity_type === 1 ||
    activity.activity_type === 2 ||
    activity.activity_type === 3 ||
    activity.activity_type === 34 ||
    activity.activity_type === 40
  )
}
/**
 * Checks if the activity type is not a running-related activity.
 *
 * @param {Object} activity - The activity object to check.
 * @param {number} activity.activity_type - The type identifier of the activity.
 * @returns {boolean} Returns true if the activity is not running-related (types 1,2,3,34 and 40), otherwise false.
 */
export function activityTypeNotRunning(activity) {
  return (
    activity.activity_type !== 1 &&
    activity.activity_type !== 2 &&
    activity.activity_type !== 3 &&
    activity.activity_type !== 34 &&
    activity.activity_type !== 40
  )
}

/**
 * Checks if the activity type is a running activity.
 *
 * @param {object} activity - The activity object.
 * @param {number} activity.activity_type - The type identifier of the activity.
 * @returns {boolean} True if the type of the activity is cycling, false otherwise.
 */
export function activityTypeIsCycling(activity) {
  return (
    activity.activity_type === 4 ||
    activity.activity_type === 5 ||
    activity.activity_type === 6 ||
    activity.activity_type === 7 ||
    activity.activity_type === 27 ||
    activity.activity_type === 28 ||
    activity.activity_type === 29 ||
    activity.activity_type === 35 ||
    activity.activity_type === 36
  )
}

/**
 * Determines if the given activity is not a cycling-related activity.
 *
 * @param {Object} activity - The activity object to check.
 * @param {number} activity.activity_type - The type identifier of the activity.
 * @returns {boolean} Returns true if the activity is not cycling-related (types 4, 5, 6, 7, 27, 28, or 29), otherwise false.
 */
export function activityTypeNotCycling(activity) {
  return (
    activity.activity_type !== 4 &&
    activity.activity_type !== 5 &&
    activity.activity_type !== 6 &&
    activity.activity_type !== 7 &&
    activity.activity_type !== 27 &&
    activity.activity_type !== 28 &&
    activity.activity_type !== 29 &&
    activity.activity_type !== 35 &&
    activity.activity_type !== 36
  )
}

/**
 * Checks if the activity type is a running activity.
 *
 * @param {object} activity - The activity object.
 * @param {number} activity.activity_type - The type identifier of the activity.
 * @returns {boolean} True if the type of the activity is walking, false otherwise.
 */
export function activityTypeIsWalking(activity) {
  return (
    activity.activity_type === 11 ||
    activity.activity_type === 12 ||
    activity.activity_type === 31 ||
    activity.activity_type === 44
  )
}

/**
 * Checks if the activity type is a racquet based activity.
 *
 * @param {object} activity - The activity object.
 * @param {number} activity.activity_type - The type identifier of the activity.
 * @returns {boolean} True if the type of the activity is racquet based, false otherwise.
 */
export function activityTypeIsRacquet(activity) {
  return (
    activity.activity_type === 21 ||
    activity.activity_type === 22 ||
    activity.activity_type === 23 ||
    activity.activity_type === 24 ||
    activity.activity_type === 25 ||
    activity.activity_type === 26 ||
    activity.activity_type === 39
  )
}

/**
 * Determines if the given activity is not a racquet-related activity.
 *
 * @param {Object} activity - The activity object to check.
 * @param {number} activity.activity_type - The type identifier of the activity.
 * @returns {boolean} Returns true if the activity is not racquet-related (types 21, 22, 23, 24, 25, 26, or 39), otherwise false.
 */
export function activityTypeNotRacquet(activity) {
  return (
    activity.activity_type !== 21 &&
    activity.activity_type !== 22 &&
    activity.activity_type !== 23 &&
    activity.activity_type !== 24 &&
    activity.activity_type !== 25 &&
    activity.activity_type !== 26 &&
    activity.activity_type !== 39
  )
}

/**
 * Checks if the given activity is of type Sailing.
 *
 * @param {Object} activity - The activity object to check.
 * @param {number} activity.activity_type - The type identifier of the activity.
 * @returns {boolean} Returns true if the activity type is Sailing (43), otherwise false.
 */
export function activityTypeIsSailing(activity) {
  return activity.activity_type === 43
}

/**
 * Checks if the activity type is not sailing (activity_type !== 43).
 *
 * @param {Object} activity - The activity object to check.
 * @param {number} activity.activity_type - The type of the activity.
 * @returns {boolean} Returns true if the activity type is not sailing, false otherwise.
 */
export function activityTypeNotSailing(activity) {
  return activity.activity_type !== 43
}

/**
 * Checks if the given activity is of type Windsurf.
 *
 * @param {Object} activity - The activity object to check.
 * @param {number} activity.activity_type - The type identifier of the activity.
 * @returns {boolean} Returns true if the activity type is Windsurf (30), otherwise false.
 */
export function activityTypeIsWindsurf(activity) {
  return activity.activity_type === 30
}

/**
 * Checks if the activity type is not windsurf (activity_type !== 30).
 *
 * @param {Object} activity - The activity object to check.
 * @param {number} activity.activity_type - The type of the activity.
 * @returns {boolean} Returns true if the activity type is not windsurf, false otherwise.
 */
export function activityTypeNotWindsurf(activity) {
  return activity.activity_type !== 30
}

/**
 * Checks if the given activity is of type Rowing.
 *
 * @param {Object} activity - The activity object to check.
 * @param {number} activity.activity_type - The type identifier of the activity.
 * @returns {boolean} Returns true if the activity type is rowing (13, 42), otherwise false.
 */
export function activityTypeIsRowing(activity) {
  return activity.activity_type === 13 || activity.activity_type === 42
}

/**
 * Checks if the activity type is not rowing (activity_type !== 13, 42).
 *
 * @param {Object} activity - The activity object to check.
 * @param {number} activity.activity_type - The type of the activity.
 * @returns {boolean} Returns true if the activity type is not rowing, false otherwise.
 */
export function activityTypeNotRowing(activity) {
  return activity.activity_type !== 13 && activity.activity_type !== 42
}

/**
 * Checks if the given activity is of type Rowing.
 *
 * @param {Object} activity - The activity object to check.
 * @param {number} activity.activity_type - The type identifier of the activity.
 * @returns {boolean} Returns true if the activity type is skating (45), otherwise false.
 */
export function activityTypeIsSkating(activity) {
  return activity.activity_type === 45
}

/**
 * Checks if the activity type is not skating (activity_type !== 45).
 *
 * @param {Object} activity - The activity object to check.
 * @param {number} activity.activity_type - The type of the activity.
 * @returns {boolean} Returns true if the activity type is not skating, false otherwise.
 */
export function activityTypeNotSkating(activity) {
  return activity.activity_type !== 45
}

/**
 * Checks if the activity type corresponds to a snow skiing activity.
 *
 * @param {Object} activity - The activity object to check
 * @param {number} activity.activity_type - The numeric type identifier of the activity
 * @returns {boolean} True if the activity type is snow skiing (types 15, 16, or 44), false otherwise
 */
export function activityTypeIsSnowSkiing(activity) {
  return (
    activity.activity_type === 15 || activity.activity_type === 16 || activity.activity_type === 44
  )
}

/**
 * Checks if an activity is of type snowboarding.
 * @param {Object} activity - The activity object to check.
 * @param {number} activity.activity_type - The type identifier of the activity.
 * @returns {boolean} True if the activity type is snowboarding (17), false otherwise.
 */
export function activityTypeIsSnowboarding(activity) {
  return activity.activity_type === 17
}

/**
 * Checks if an activity is stand-up paddleboarding.
 * @param {Object} activity - The activity object to check.
 * @param {number} activity.activity_type - The type identifier of the activity.
 * @returns {boolean} True if the activity is stand-up paddleboarding (type 32), false otherwise.
 */
export function activityTypeIsStandUpPaddling(activity) {
  return activity.activity_type === 32
}

/**
 * Checks if an activity is a surf activity.
 * @param {Object} activity - The activity object to check.
 * @param {number} activity.activity_type - The type identifier of the activity.
 * @returns {boolean} True if the activity type is 33 (surf), false otherwise.
 */
export function activityTypeIsSurf(activity) {
  return activity.activity_type === 33
}

/**
 * Formats the pace of an activity based on its type and the specified unit system.
 *
 * @param {Object} t - The translation function.
 * @param {Object} activity - The activity object containing pace and activity_type.
 * @param {string} unitSystem - The unit system to use ('metric' or 'imperial').
 * @param {Object|null} [lap=null] - Optional lap object to use its enhanced_avg_pace instead of activity pace.
 * @param {boolean} [units=true] - Whether to include units in the formatted output.
 * @param {boolean} [isRest=false] - Whether the lap is a rest lap.
 * @returns {string} The formatted pace string.
 */
export function formatPace(t, activity, unitSystem, lap = null, units = true, isRest = false) {
  let pace = activity.pace
  if (lap) {
    pace = lap.enhanced_avg_pace
  }
  if (isRest) {
    return t('generalItems.labelRest')
  }
  if (
    activityTypeIsSwimming(activity) ||
    activityTypeIsRowing(activity) ||
    activityTypeIsWindsurf(activity)
  ) {
    if (unitSystem === 'metric') {
      return formatPaceSwimMetric(pace, units)
    }
    return formatPaceSwimImperial(pace, units)
  }
  if (unitSystem === 'metric') {
    return formatPaceMetric(pace, units)
  }
  return formatPaceImperial(pace, units)
}

/**
 * Formats the average speed of an activity based on the unit system and activity type.
 *
 * @param {Object} t - The translation function.
 * @param {Object} activity - The activity object containing speed and type information.
 * @param {string} unitSystem - The unit system to use ('metric' or 'imperial').
 * @param {Object|null} [lap=null] - Optional lap object to use for speed calculation.
 * @param {boolean} [units=true] - Whether to include units in the formatted string.
 * @returns {string} The formatted average speed, including units if specified, or a "No Data" label if unavailable.
 */
export function formatAverageSpeed(t, activity, unitSystem, lap = null, units = true) {
  let speed = activity.average_speed
  if (lap) {
    speed = lap.enhanced_avg_speed
  }
  if (
    activity.average_speed === null ||
    activity.average_speed === undefined ||
    activity.average_speed < 0
  )
    return t('generalItems.labelNoData')

  if (
    activityTypeIsCycling(activity) ||
    activityTypeIsWindsurf(activity) ||
    activityTypeIsSailing(activity)
  ) {
    if (unitSystem === 'metric') {
      if (units) {
        return `${formatAverageSpeedMetric(speed)} ${t('generalItems.unitsKmH')}`
      }
      return `${formatAverageSpeedMetric(speed)}`
    } else {
      if (units) {
        return `${formatAverageSpeedImperial(speed)} ${t('generalItems.unitsMph')}`
      }
      return `${formatAverageSpeedImperial(speed)}`
    }
  }
  return t('generalItems.labelNoData')
}

/**
 * Formats a date-time string into a localized date and time string.
 *
 * @param {Object} t - The translation function.
 * @param {string} dateTimeString - The date-time string to format. If falsy, a "Not Applicable" label is returned.
 * @param {string} [separator=", "] - The separator to use between the date and time. Defaults to ", ".
 * @returns {string} The formatted date and time string, or a "Not Applicable" label if the input is invalid.
 */
export function formatDateTime(t, dateTimeString, separator = ', ') {
  if (!dateTimeString) return t('generalItems.labelNoData')
  return `${formatDateMed(dateTimeString)}${separator}${formatTime(dateTimeString)}`
}

/**
 * Formats a duration given in seconds into a human-readable format.
 * If the input is null, undefined, or negative, it returns a localized "Not Applicable" label.
 *
 * @param {Object} t - The translation function.
 * @param {number|null|undefined} seconds - The duration in seconds to format.
 * @returns {string} The formatted duration or a "Not Applicable" label if the input is invalid.
 */
export function formatDuration(t, seconds) {
  if (seconds === null || seconds === undefined || seconds < 0) return t('generalItems.labelNoData')
  return formatSecondsToMinutes(seconds)
}

/**
 * Formats the distance of an activity or lap based on the unit system and activity type.
 *
 * @param {Object} t - The translation function.
 * @param {Object} activity - The activity object containing distance and activity_type.
 * @param {string} unitSystem - The unit system to use ('metric' or 'imperial').
 * @param {Object|null} [lap=null] - Optional lap object containing total_distance.
 * @returns {string} The formatted distance string with appropriate units or a "No Data" label.
 */
export function formatDistance(t, activity, unitSystem, lap = null) {
  let distance = activity.distance
  if (lap) {
    distance = lap.total_distance
  }
  if (distance === null || distance === undefined || distance < 0)
    return t('generalItems.labelNoData')
  if (unitSystem === 'metric') {
    if (!activityTypeIsSwimming(activity)) {
      return `${metersToKm(distance)} ${t('generalItems.unitsKm')}`
    }
    return `${distance} ${t('generalItems.unitsM')}`
  }
  if (!activityTypeIsSwimming(activity)) {
    return `${metersToMiles(distance)} ${t('generalItems.unitsMiles')}`
  }
  return `${metersToYards(distance)} ${t('generalItems.unitsYards')}`
}

/**
 * Formats a distance value in meters to either kilometers or miles, based on the unit system.
 * The result is rounded (optionally) and formatted with spaces as thousands separators.
 *
 * @param {Object} t - The translation function.
 * @param {number} distance - The distance in meters to format.
 * @param {string} unitSystem - The unit system to use ('metric' or 'imperial').
 * @param {boolean} [round=true] - Whether to round the result to the nearest integer.
 * @returns {string} The formatted distance string with the appropriate unit.
 */
export function formatDistanceRaw(t, distance, unitSystem, round = true, units = true) {
  let value = unitSystem === 'metric' ? metersToKm(distance) : metersToMiles(distance)
  if (round) {
    value = Math.round(value)
  }
  // Format with space as thousands separator for better readability
  let formatted = value
    .toLocaleString('en-US', { useGrouping: true, maximumFractionDigits: 0 })
    .replace(/,/g, ' ')
  const unit = unitSystem === 'metric' ? t('generalItems.unitsKm') : t('generalItems.unitsMiles')
  if (units) {
    return `${formatted} ${unit}`
  }
  return formatted
}

/**
 * Formats the heart rate (hr) into a user-friendly string.
 *
 * If the provided hr is null, undefined, or less than or equal to 0,
 * it returns a localized "Not Applicable" label. Otherwise, it rounds
 * the hr value and appends the localized "bpm" unit.
 *
 * @param {Object} t - The translation function.
 * @param {number|null|undefined} hr - The heart rate to format.
 * @returns {string} A formatted string representing the heart rate
 *                   or a "Not Applicable" label if the input is invalid.
 */
export function formatHr(t, hr) {
  if (hr === null || hr === undefined || hr <= 0) return t('generalItems.labelNoData')
  return `${Math.round(hr)} ${t('generalItems.unitsBpm')}`
}

/**
 * Formats the power into a user-friendly string.
 *
 * If the provided power is null, undefined, or less than or equal to 0,
 * it returns a localized "Not Applicable" label. Otherwise, it rounds
 * the power value and appends the localized "W" unit.
 *
 * @param {Object} t - The translation function.
 * @param {number|null|undefined} power - The power to format.
 * @returns {string} A formatted string representing the power
 *                   or a "Not Applicable" label if the input is invalid.
 */
export function formatPower(t, power) {
  if (power === null || power === undefined || power <= 0) return t('generalItems.labelNoData')
  return `${Math.round(power)} ${t('generalItems.unitsWattsShort')}`
}

/**
 * Formats an elevation value based on the provided unit system.
 *
 * @param {Object} t - The translation function.
 * @param {number|null|undefined} meters - The elevation value in meters. Can be null or undefined.
 * @param {string} unitSystem - The unit system to use ('metric' or 'imperial').
 * @returns {string} The formatted elevation string with the appropriate unit, or a "not applicable" label if the input is null or undefined.
 */
export function formatElevation(t, meters, unitSystem, units = true) {
  if (meters === null || meters === undefined) {
    return t('generalItems.labelNoData')
  }
  const numericValue =
    unitSystem === 'metric' ? parseFloat(meters) : parseFloat(metersToFeet(meters))
  const formattedValue = numericValue.toLocaleString(undefined, { maximumFractionDigits: 0 })

  if (!units) {
    return formattedValue
  }

  const unitLabel = unitSystem === 'metric' ? t('generalItems.unitsM') : t('generalItems.unitsFeet')
  return `${formattedValue} ${unitLabel}`
}

/**
 * Formats the given calorie value into a string with appropriate units.
 *
 * @param {Object} t - The translation function.
 * @param {number|null|undefined} calories - The calorie value to format. If null or undefined, a "not applicable" label is returned.
 * @returns {string} A formatted string representing the calorie value with units, or a "not applicable" label if the input is null or undefined.
 */
export function formatCalories(t, calories) {
  if (calories === null || calories === undefined) {
    return t('generalItems.labelNoData')
  }
  const numericValue = parseFloat(calories)
  const formattedValue = numericValue.toLocaleString(undefined, { maximumFractionDigits: 0 })
  return `${formattedValue} ${t('generalItems.unitsCalories')}`
}

/**
 * Retrieves the corresponding Font Awesome icon class for a given activity type ID.
 *
 * @param {number} typeId - The ID representing the activity type.
 * @returns {string[]} An array containing the Font Awesome icon prefix and icon name.
 *                      Defaults to ["fas", "dumbbell"] if the typeId is not found.
 */
export function getIcon(typeId) {
  const iconMap = {
    1: ['fas', 'person-running'],
    2: ['fas', 'person-running'],
    3: ['fas', 'person-running'],
    4: ['fas', 'person-biking'],
    5: ['fas', 'person-biking'],
    6: ['fas', 'person-biking'],
    7: ['fas', 'person-biking'],
    8: ['fas', 'person-swimming'],
    9: ['fas', 'person-swimming'],
    11: ['fas', 'person-walking'],
    12: ['fas', 'person-hiking'],
    13: ['fas', 'sailboat'], // Rowing icon might be better if available
    14: ['fas', 'hands-praying'], // Yoga icon might be better if available
    15: ['fas', 'person-skiing'],
    16: ['fas', 'person-skiing-nordic'],
    17: ['fas', 'person-snowboarding'],
    18: ['fas', 'repeat'],
    21: ['fas', 'table-tennis-paddle-ball'],
    22: ['fas', 'table-tennis-paddle-ball'],
    23: ['fas', 'table-tennis-paddle-ball'],
    24: ['fas', 'table-tennis-paddle-ball'],
    25: ['fas', 'table-tennis-paddle-ball'],
    26: ['fas', 'table-tennis-paddle-ball'],
    27: ['fas', 'person-biking'],
    28: ['fas', 'person-biking'],
    29: ['fas', 'person-biking'],
    30: ['fas', 'wind'], // Windsurf icon might be better if available
    31: ['fas', 'person-walking'],
    32: ['fas', 'person-snowboarding'],
    33: ['fas', 'person-snowboarding'],
    34: ['fas', 'person-running'], // Track run icon might be better if available
    35: ['fas', 'person-biking'],
    36: ['fas', 'person-biking'],
    37: ['fas', 'person-skating'],
    38: ['fas', 'futbol'],
    39: ['fas', 'table-tennis-paddle-ball'],
    40: ['fas', 'person-running'], // Treadmill run icon might be better if available
    41: ['fas', 'heart-pulse'], // Cardio training icon might be better if available
    42: ['fas', 'sailboat'], // Kayaking icon might be better if available
    43: ['fas', 'wind'], // Sailing icon might be better if available
    44: ['fas', 'person-hiking'],
    45: ['fas', 'person-skating'],
    46: ['fas', 'heart-pulse'] // HIIT icon might be better if available
  }

  return iconMap[typeId] || ['fas', 'dumbbell']
}

/**
 * Formats the location of an activity into a readable string.
 *
 * @param {Object} t - The translation function.
 * @param {Object} activity - The activity object containing location details.
 * @returns {string} A formatted location string. If no location details are provided,
 * it returns a localized "Not Applicable" label.
 */
export function formatLocation(t, activity) {
  const { city, town, country } = activity

  if (!city && !town && !country) {
    return t('generalItems.labelNoData')
  }

  const locationParts = []
  if (city) {
    locationParts.push(city)
  } else if (town) {
    locationParts.push(town)
  }

  if (country) {
    // Add country, adding a comma only if town/city was already added
    if (locationParts.length > 0) {
      locationParts.push(`, ${country}`)
    } else {
      locationParts.push(country)
    }
  }

  return locationParts.join('') // Join without extra spaces, comma is handled above
}

/**
 * Formats a raw distance in meters based on the unit system.
 *
 * @param {Object} t - The translation function.
 * @param {number|null|undefined} meters - The distance in meters.
 * @param {string} unitSystem - The unit system to use ('metric' or 'imperial').
 * @returns {string} The formatted distance string with appropriate units or a "No Data" label.
 */
export function formatRawDistance(t, meters, unitSystem) {
  if (meters === null || meters === undefined || meters < 0) {
    return t('generalItems.labelNoData')
  }
  const numericValue =
    unitSystem === 'metric' ? parseFloat(metersToKm(meters)) : parseFloat(metersToMiles(meters))
  // Assuming metersToKm and metersToMiles return numbers or strings that can be parsed to numbers
  // Use toLocaleString for formatting, allow for some decimal places for precision if needed
  const formattedValue = numericValue.toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2
  })

  const unitLabel =
    unitSystem === 'metric' ? t('generalItems.unitsKm') : t('generalItems.unitsMiles')
  return `${formattedValue} ${unitLabel}`
}

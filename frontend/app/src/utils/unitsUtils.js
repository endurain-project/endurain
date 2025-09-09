// Metric to Imperial conversions
export function cmToFeetInches(cm) {
  const totalInches = cm / 2.54
  const feet = Math.floor(totalInches / 12)
  const inches = Math.round(totalInches % 12)

  return { feet, inches }
}

export function metersToMiles(meters) {
  return (meters / 1609.344).toFixed(2)
}

export function kmToMiles(km) {
  return (km / 1.60934).toFixed(2)
}

export function metersToFeet(meters) {
  return (meters * 3.28084).toFixed(0)
}

export function metersToYards(meters) {
  return (meters * 1.09361).toFixed(0)
}

export function kgToLbs(kg) {
  return (kg * 2.20462).toFixed(0)
}

// Imperial to Metric conversions
export function feetAndInchesToCm(feet, inches) {
  const totalInches = feet * 12 + inches
  return (totalInches * 2.54).toFixed(0)
}

export function feetToMeters(feet) {
  return (feet * 0.3048).toFixed(0)
}

export function milesToKm(miles) {
  return (miles * 1.60934).toFixed(0)
}

export function milesToMeters(miles) {
  return (miles * 1609.344).toFixed(0)
}

export function lbsToKg(lbs) {
  return (lbs / 2.20462).toFixed(1)
}

// Metric to Metric conversions
export function metersToKm(meters) {
  return (meters / 1000).toFixed(2)
}

export function kmToMeters(km) {
  return (km * 1000).toFixed(0)
}

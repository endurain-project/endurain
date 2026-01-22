// Metric to Imperial conversions
export function cmToFeetInches(cm) {
  const totalInches = cm / 2.54
  const feet = Math.floor(totalInches / 12)
  const inches = Math.round(totalInches % 12)

  return { feet, inches }
}

export function metersToMiles(meters) {
  return Number((meters / 1609.344).toFixed(2))
}

export function kmToMiles(km) {
  return Number((km / 1.60934).toFixed(2))
}

export function metersToFeet(meters) {
  return Number((meters * 3.28084).toFixed(0))
}

export function metersToYards(meters) {
  return Number((meters * 1.09361).toFixed(0))
}

export function kgToLbs(kg) {
  return Number((kg * 2.20462).toFixed(0))
}

// Imperial to Metric conversions
export function feetAndInchesToCm(feet, inches) {
  const totalInches = feet * 12 + inches
  return Number((totalInches * 2.54).toFixed(0))
}

export function feetToMeters(feet) {
  return Number((feet * 0.3048).toFixed(0))
}

export function milesToKm(miles) {
  return Number((miles * 1.60934).toFixed(0))
}

export function milesToMeters(miles) {
  return Number((miles * 1609.344).toFixed(0))
}

export function lbsToKg(lbs) {
  return Number((lbs / 2.20462).toFixed(1))
}

// Metric to Metric conversions
export function metersToKm(meters) {
  return Number((meters / 1000).toFixed(2))
}

export function kmToMeters(km) {
  return Number((km * 1000).toFixed(0))
}

export function cmToFeetInches(cm) {
    const totalInches = cm / 2.54;
    const feet = Math.floor(totalInches / 12);
    const inches = Math.round(totalInches % 12);

    return { feet, inches };
}

export function feetAndInchesToCm(feet, inches) {
    const totalInches = (feet * 12) + inches;
    return (totalInches * 2.54).toFixed(0);
}

export function metersToMiles(meters) {
	return (meters / 1609.344).toFixed(2);
}
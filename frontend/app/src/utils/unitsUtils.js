export function cmToFeetInches(cm) {
    const inches = cm / 2.54;
    const feet = Math.floor(inches / 12);
    const remainingInches = (inches % 12).toFixed(0);

    return `${feet}’${remainingInches}’’`;
}

export function metersToMiles(meters) {
    return (meters / 1609.344).toFixed(2);
}
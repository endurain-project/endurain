export function cmToFeetInches(cm) {
    const inches = cm / 2.54;
    const feet = Math.floor(inches / 12);
    const remainingInches = (inches % 12).toFixed(0);

    return `${feet}’${remainingInches}’’`;
}
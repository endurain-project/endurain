// Function to calculate and format the pace (minutes per kilometer) from activity pace
export const formatPace = (pace) => {
    const pacePerKm = pace * 1000 / 60;
    const minutes = Math.floor(pacePerKm);
    const seconds = Math.round((pacePerKm - minutes) * 60);

    // Format seconds to always be two digits
    const formattedSeconds = seconds < 10 ? `0${seconds}` : seconds;

    return `${minutes}:${formattedSeconds} min/km`;
};
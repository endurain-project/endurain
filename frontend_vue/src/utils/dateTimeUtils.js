// Helper function to format date
export const formatDate = (dateString) => {
    const date = new Date(dateString);
    return date.toLocaleDateString(undefined, { day: '2-digit', month: '2-digit', year: '2-digit' });
};
  
  // Helper function to format time
  export const formatTime = (dateString) => {
    const date = new Date(dateString);
    return date.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' });
};
  
  // Function to calculate time difference and format it
  export const calculateTimeDifference = (startTime, endTime) => {
    const startDateTime = new Date(startTime);
    const endDateTime = new Date(endTime);
    const interval = new Date(endDateTime - startDateTime);
  
    const hours = interval.getUTCHours();
    const minutes = interval.getUTCMinutes();
    const seconds = interval.getUTCSeconds();
  
    if (hours < 1) {
      return `${minutes}m ${seconds}s`;
    } else {
      return `${hours}h ${minutes}m`;
    }
};
  
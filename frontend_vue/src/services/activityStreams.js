//const API_URL = process.env.VUE_APP_API_URL || 'http://localhost:98/';
const API_URL = 'http://localhost:98/';

export const activityStreams = {
    async getActivitySteamByStreamTypeByActivityId(activityId, streamType) {
        const response = await fetch(`${API_URL}activities/streams/activity_id/${activityId}/stream_type/${streamType}`, {
            method: 'GET',
            headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${localStorage.getItem('accessToken')}`
            },
        });
        if (!response.ok) {
            throw new Error('' + response.status);
        }
        return response.json();
    }
};
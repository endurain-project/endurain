//const API_URL = process.env.VUE_APP_API_URL || 'http://localhost:98/';
const API_URL = 'http://localhost:98/';

export const activities = {
    async getUserThisWeekStats(id) {
        const response = await fetch(`${API_URL}activities/user/${id}/thisweek/distances`, {
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
    },
    async getUserThisMonthStats(id) {
        const response = await fetch(`${API_URL}activities/user/${id}/thismonth/distances`, {
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
    },
    async getUserNumberOfActivities(id) {
        const response = await fetch(`${API_URL}activities/user/${id}/number`, {
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
    },
    async getUserActivitiesWithPagination(id, pageNumber, numRecords) {
        const response = await fetch(`${API_URL}activities/user/${id}/page_number/${pageNumber}/num_records/${numRecords}`, {
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
    },
    async getUserFollowersActivitiesWithPagination(id, pageNumber, numRecords) {
        const response = await fetch(`${API_URL}activities/user/${id}/followed/page_number/${pageNumber}/num_records/${numRecords}`, {
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
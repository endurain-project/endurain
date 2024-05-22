import { fetchGetRequest, fetchPostRequest, fetchPutRequest, fetchDeleteRequest } from '@/utils/serviceUtils';

export const strava = {
    setUniqueUserStateStravaLink(state) {
        return fetchPutRequest(`strava/set-user-unique-state/${state}`)
    },
    unsetUniqueUserStateStravaLink() {
        return fetchPutRequest(`strava/unset-user-unique-state`)
    },
    linkStrava(state) {
        const stravaClientId = '115321';
        //const redirectUri = process.env.VUE_APP_API_URL || 'http://localhost:98';
        const redirectUri = 'http://localhost:98';
        redirectUri = encodeURIComponent(redirectUri);
        const scope = 'read,read_all,profile:read_all,activity:read,activity:read_all';

        const stravaAuthUrl = `http://www.strava.com/oauth/authorize?client_id=${stravaClientId}&response_type=code&redirect_uri=${redirectUri}/strava/link&approval_prompt=force&scope=${scope}&state=${state}`;

        // Redirect to the Strava authorization URL
        window.location.href = strava_auth_url;
    },
    getStravaActivitiesLastDays(days) {
        return fetchGetRequest(`strava/activities/days/${days}`);
    },
    getStravaGear() {
        return fetchGetRequest('strava/gear');
    }
};
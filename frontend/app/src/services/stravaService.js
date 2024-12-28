import { fetchGetRequest, fetchPutRequest, fetchDeleteRequest } from '@/utils/serviceUtils';

export const strava = {
    setUniqueUserStateStravaLink(state) {
        return fetchPutRequest(`strava/set-user-unique-state/${state}`)
    },
    unsetUniqueUserStateStravaLink() {
        return fetchPutRequest("strava/unset-user-unique-state")
    },
    linkStrava(state) {
        const stravaClientId = `${import.meta.env.VITE_STRAVA_CLIENT_ID}`;
        let redirectUri = `${import.meta.env.VITE_ENDURAIN_HOST}`;
        redirectUri = encodeURIComponent(redirectUri);
        const scope = 'read,read_all,profile:read_all,activity:read,activity:read_all';

        const stravaAuthUrl = `http://www.strava.com/oauth/authorize?client_id=${stravaClientId}&response_type=code&redirect_uri=${redirectUri}/strava/callback&approval_prompt=force&scope=${scope}&state=${state}`;

        // Redirect to the Strava authorization URL
        window.location.href = stravaAuthUrl;
    },
    linkStravaCallback(state, code, scope) {
        return fetchPutRequest(`strava/link?state=${state}&code=${code}&scope=${scope}`);
    },
    getStravaActivitiesLastDays(days) {
        return fetchGetRequest(`strava/activities/days/${days}`);
    },
    getStravaGear() {
        return fetchGetRequest('strava/gear');
    },
    unlinkStrava() {
        return fetchDeleteRequest('strava/unlink');
    }
};
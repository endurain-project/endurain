// Importing the router
import { useRouter } from 'vue-router';
// Importing the auth store
import { useAuthStore } from '@/stores/authStore';
// Importing the i18n
import { useI18n } from 'vue-i18n';
// Importing the services for the login
import { session } from '@/services/sessionService';

export const API_URL = `${import.meta.env.VITE_ENDURAIN_HOST}/api/v1/`;

async function fetchWithRetry(url, options) {
    try {
        return await attemptFetch(url, options);
    } catch (error) {
        if (error.message === '401 - Access token missing') {
            try {
                await refreshAccessToken();
                return await attemptFetch(url, options);
            } catch (refreshError) {
                const router = useRouter();
                const authStore = useAuthStore();
                const { locale } = useI18n();
                
                await session.logout();
                authStore.clearUser(locale);
                router.push('/')
                //throw new Error(`Failed to refresh access token: ${refreshError.message}`);
            }
        } else {
            throw error;
        }
    }
}

async function attemptFetch(url, options) {
    const fullUrl = `${API_URL}${url}`;
    const response = await fetch(fullUrl, options);
    if (!response.ok) {
        const errorBody = await response.json(); // Parse the response as JSON
        const errorMessage = errorBody.detail || 'Unknown error'; // Get the 'detail' field or a default message
        throw new Error(`${response.status} - ${errorMessage}`);
    }
    return response.json();
}

async function refreshAccessToken() {
    const refreshUrl = `${API_URL}refresh`;
    const response = await fetch(refreshUrl, {
        method: 'POST',
        credentials: 'include',
        headers: {
            'Content-Type': 'application/json',
            'X-Client-Type': 'web',
        },
    });
    if (!response.ok) {
        const errorBody = await response.json(); // Parse the response as JSON
        const errorMessage = errorBody.detail || 'Unknown error'; // Get the 'detail' field or a default message
        throw new Error(`${response.status} - ${errorMessage}`);
    }
}


export async function fetchGetRequest(url) {
    const options = {
        method: 'GET',
        credentials: 'include',
        headers: {
            'Content-Type': 'application/json',
            'X-Client-Type': 'web',
        },
    };
    return fetchWithRetry(url, options);
}


export async function fetchPostFileRequest(url, formData) {
    const options = {
        method: 'POST',
        body: formData,
        credentials: 'include',
        headers: {
            'X-Client-Type': 'web',
        },
    };
    return fetchWithRetry(url, options);
}


export async function fetchPostFormUrlEncoded(url, formData) {
    const urlEncodedData = new URLSearchParams(formData);
    const options = {
        method: 'POST',
        body: urlEncodedData,
        credentials: 'include',
        headers: {
            'Content-Type': 'application/x-www-form-urlencoded',
            'X-Client-Type': 'web',
        },
    };
    return attemptFetch(url, options);
    //return fetchWithRetry(url, options);
}


export async function fetchPostRequest(url, data) {
    const options = {
        method: 'POST',
        body: JSON.stringify(data),
        credentials: 'include',
        headers: {
            'Content-Type': 'application/json',
            'X-Client-Type': 'web',
        },
    };
    return fetchWithRetry(url, options);
}


export async function fetchPutRequest(url, data) {
    const options = {
        method: 'PUT',
        body: JSON.stringify(data),
        credentials: 'include',
        headers: {
            'Content-Type': 'application/json',
            'X-Client-Type': 'web',
        },
    };
    return fetchWithRetry(url, options);
}


export async function fetchDeleteRequest(url) {
    const options = {
        method: 'DELETE',
        credentials: 'include',
        headers: {
            'Content-Type': 'application/json',
            'X-Client-Type': 'web',
        },
    };
    return fetchWithRetry(url, options);
}
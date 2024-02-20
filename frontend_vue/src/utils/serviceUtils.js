//const API_URL = process.env.VUE_APP_API_URL || 'http://localhost:98/';
const API_URL = 'http://localhost:98/';

async function fetchGetRequest(url, headers = {}) {
    const fullUrl = `${API_URL}${url}`;
    const response = await fetch(fullUrl, {
        method: 'GET',
        headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${localStorage.getItem('accessToken')}`,
        },
    });
    if (!response.ok) {
        throw new Error('' + response.status);
    }
    return response.json();
}

async function fetchGetRequestTokenAsParameter(url, token, headers = {}) {
    const fullUrl = `${API_URL}${url}`;
    const response = await fetch(fullUrl, {
        method: 'GET',
        headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${token}`,
        },
    });
    if (!response.ok) {
        throw new Error('' + response.status);
    }
    return response.json();
}

async function fetchPostFileRequest(url, formData, headers = {}) {
    const fullUrl = `${API_URL}${url}`;
    const response = await fetch(fullUrl, {
        method: 'POST',
        body: formData,
        headers: {
            'Authorization': `Bearer ${localStorage.getItem('accessToken')}`
        },
    });
    if (!response.ok) {
        throw new Error('' + response.status);
    }
    return response.json();
}

async function fetchPostFormUrlEncoded(url, formData, headers = {}) {
    const fullUrl = `${API_URL}${url}`;
    const response = await fetch(fullUrl, {
        method: 'POST',
        body: formData,
        headers: {
            'Content-Type': 'application/x-www-form-urlencoded',
        },
    });
    if (!response.ok) {
        throw new Error('' + response.status);
    }
    return response.json();
}

export { fetchGetRequest, fetchGetRequestTokenAsParameter, fetchPostFileRequest, fetchPostFormUrlEncoded };
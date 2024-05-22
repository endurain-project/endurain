//const API_URL = process.env.VUE_APP_API_URL || 'http://localhost:98/';
const API_URL = 'http://localhost:98/';

/**
 * Makes a GET request to the specified URL with optional headers.
 * @param {string} url - The URL to send the GET request to.
 * @param {Object} headers - Optional headers to include in the request.
 * @returns {Promise<Object>} - A promise that resolves to the JSON response from the server.
 * @throws {Error} - If the response status is not ok.
 */
export async function fetchGetRequest(url) {
    // Create the full URL by combining the API URL with the provided URL
    const fullUrl = `${API_URL}${url}`;
    // Send the GET request
    const response = await fetch(fullUrl, {
        method: 'GET',
        headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${localStorage.getItem('accessToken')}`,
        },
    });
    // If the response status is not ok, throw an error
    if (!response.ok) {
        throw new Error('' + response.status);
    }
    // Return the JSON response
    return response.json();
}

/**
 * Fetches a GET request with a token as a parameter.
 *
 * @param {string} url - The URL to fetch.
 * @param {string} token - The token to include in the request headers.
 * @param {Object} headers - Additional headers to include in the request.
 * @returns {Promise<Object>} - A promise that resolves to the JSON response.
 * @throws {Error} - If the response status is not ok.
 */
export async function fetchGetRequestTokenAsParameter(url, token) {
    // Check if a token is provided
    if (!token) {
        throw new Error('No token provided');
    }
    // Create the full URL by combining the API URL with the provided URL
    const fullUrl = `${API_URL}${url}`;
    // Send the GET request
    const response = await fetch(fullUrl, {
        method: 'GET',
        headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${token}`,
        },
    });
    // If the response status is not ok, throw an error
    if (!response.ok) {
        throw new Error('' + response.status);
    }
    // Return the JSON response
    return response.json();
}

/**
 * Sends a POST request with a file using FormData.
 * @param {string} url - The URL to send the request to.
 * @param {FormData} formData - The FormData object containing the file data.
 * @param {Object} headers - Optional headers to include in the request.
 * @returns {Promise<Object>} - A promise that resolves to the JSON response from the server.
 * @throws {Error} - If the response status is not ok.
 */
export async function fetchPostFileRequest(url, formData) {
    // Create the full URL by combining the API URL with the provided URL
    const fullUrl = `${API_URL}${url}`;
    // Send the POST request
    const response = await fetch(fullUrl, {
        method: 'POST',
        body: formData,
        headers: {
            'Authorization': `Bearer ${localStorage.getItem('accessToken')}`
        },
    });
    // If the response status is not ok, throw an error
    if (!response.ok) {
        throw new Error('' + response.status);
    }
    // Return the JSON response
    return response.json();
}

/**
 * Fetches data from the specified URL using the POST method with form-urlencoded data.
 * @param {string} url - The URL to fetch data from.
 * @param {FormData} formData - The form data to send in the request body.
 * @param {Object} headers - Additional headers to include in the request.
 * @returns {Promise<Object>} - A promise that resolves to the JSON response from the server.
 * @throws {Error} - If the response status is not ok.
 */
export async function fetchPostFormUrlEncoded(url, formData) {
    // Create the full URL by combining the API URL with the provided URL
    const fullUrl = `${API_URL}${url}`;
    // Send the POST request
    const response = await fetch(fullUrl, {
        method: 'POST',
        body: formData,
        headers: {
            'Content-Type': 'application/x-www-form-urlencoded',
        },
    });
    // If the response status is not ok, throw an error
    if (!response.ok) {
        throw new Error('' + response.status);
    }
    // Return the JSON response
    return response.json();
}

/**
 * Sends a POST request to the specified URL with the provided data.
 * @param {string} url - The URL to send the request to.
 * @param {Object} data - The data to include in the request body.
 * @param {Object} headers - The optional headers to include in the request.
 * @returns {Promise<Object>} - A promise that resolves to the JSON response.
 * @throws {Error} - If the response status is not ok.
 */
export async function fetchPostRequest(url, data) {
    // Create the full URL by combining the API URL with the provided URL
    const fullUrl = `${API_URL}${url}`;
    // Send the POST request
    const response = await fetch(fullUrl, {
        method: 'POST',
        body: JSON.stringify(data),
        headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${localStorage.getItem('accessToken')}`,
        },
    });
    // If the response status is not ok, throw an error
    if (!response.ok) {
        throw new Error('' + response.status);
    }
    // Return the JSON response
    return response.json();
}

/**
 * Sends a PUT request to the specified URL with the provided data.
 * @param {string} url - The URL to send the request to.
 * @param {Object} data - The data to be sent in the request body.
 * @param {Object} headers - Optional headers to be included in the request.
 * @returns {Promise<Object>} - A promise that resolves to the JSON response from the server.
 * @throws {Error} - If the response status is not ok.
 */
export async function fetchPutRequest(url, data) {
    // Create the full URL by combining the API URL with the provided URL
    const fullUrl = `${API_URL}${url}`;
    // Send the PUT request
    const response = await fetch(fullUrl, {
        method: 'PUT',
        body: JSON.stringify(data),
        headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${localStorage.getItem('accessToken')}`,
        },
    });
    // If the response status is not ok, throw an error
    if (!response.ok) {
        throw new Error('' + response.status);
    }
    // Return the JSON response
    return response.json();
}

/**
 * Sends a DELETE request to the specified URL with optional headers.
 * @param {string} url - The URL to send the DELETE request to.
 * @param {Object} headers - Optional headers to include in the request.
 * @returns {Promise<Object>} - A promise that resolves to the JSON response from the server.
 * @throws {Error} - If the response status is not ok.
 */
export async function fetchDeleteRequest(url) {
    // Create the full URL by combining the API URL with the provided URL
    const fullUrl = `${API_URL}${url}`;
    // Send the DELETE request
    const response = await fetch(fullUrl, {
        method: 'DELETE',
        headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${localStorage.getItem('accessToken')}`,
        },
    });
    // If the response status is not ok, throw an error
    if (!response.ok) {
        throw new Error('' + response.status);
    }
    // Return the JSON response
    return response.json();
}
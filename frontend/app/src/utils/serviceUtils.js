// Importing the auth store
import { useAuthStore } from "@/stores/authStore";

let refreshTokenPromise = null;

export const API_URL = `${import.meta.env.VITE_ENDURAIN_HOST}/api/v1/`;
export const FRONTEND_URL = `${import.meta.env.VITE_ENDURAIN_HOST}/`;

async function fetchWithRetry(url, options) {
	// Define paths that don't need CSRF token
	const exemptPaths = ["/api/v1/token", "/api/v1/refresh"];

	// Check if the current URL path is exempt
	const isExempt = exemptPaths.some((path) => url.includes(path));

	// Add CSRF token to headers for state-changing requests
	if (
		["POST", "PUT", "DELETE", "PATCH"].includes(options.method) &&
		!isExempt
	) {
		const csrfToken = document.cookie
			.split("; ")
			.find((row) => row.startsWith("endurain_csrf_token="))
			?.split("=")[1];

		if (csrfToken) {
			options.headers = {
				...options.headers,
				"X-CSRF-Token": csrfToken,
			};
		}
	}

	try {
		return await attemptFetch(url, options);
	} catch (error) {
		if (error.message.startsWith("401") && isExempt) {
			try {
				await refreshAccessToken();
				return await attemptFetch(url, options);
			} catch {
				const authStore = useAuthStore();
				authStore.logoutUser();

				window.location.replace(`${FRONTEND_URL}login?sessionExpired=true`);
			}
		} else {
			throw error;
		}
	}
}

export async function attemptFetch(url, options) {
	const fullUrl = `${API_URL}${url}`;
	const response = await fetch(fullUrl, options);
	if (!response.ok) {
		const errorBody = await response.json(); // Parse the response as JSON
		const errorMessage = errorBody.detail || "Unknown error"; // Get the 'detail' field or a default message
		throw new Error(`${response.status} - ${errorMessage}`);
	}
	return response.json();
}

async function refreshAccessToken() {
	if (refreshTokenPromise) {
		return refreshTokenPromise;
	}

	const refreshUrl = `${API_URL}refresh`;
	refreshTokenPromise = fetch(refreshUrl, {
		method: "POST",
		credentials: "include",
		headers: {
			"Content-Type": "application/json",
			"X-Client-Type": "web",
		},
	})
		.then(async (response) => {
			if (!response.ok) {
				const errorBody = await response.json();
				const errorMessage = errorBody.detail || "Unknown error";
				throw new Error(`${response.status} - ${errorMessage}`);
			}
		})
		.finally(() => {
			refreshTokenPromise = null;
		});

	return refreshTokenPromise;
}

export async function fetchGetRequest(url) {
	const options = {
		method: "GET",
		credentials: "include",
		headers: {
			"Content-Type": "application/json",
			"X-Client-Type": "web",
		},
	};
	return fetchWithRetry(url, options);
}

export async function fetchPostFileRequest(url, formData) {
	const options = {
		method: "POST",
		body: formData,
		credentials: "include",
		headers: {
			"X-Client-Type": "web",
		},
	};
	return fetchWithRetry(url, options);
}

export async function fetchPostFormUrlEncoded(url, formData) {
	const urlEncodedData = new URLSearchParams(formData);
	const options = {
		method: "POST",
		body: urlEncodedData,
		credentials: "include",
		headers: {
			"Content-Type": "application/x-www-form-urlencoded",
			"X-Client-Type": "web",
		},
	};
	return fetchWithRetry(url, options);
}

export async function fetchPostRequest(url, data) {
	const options = {
		method: "POST",
		body: JSON.stringify(data),
		credentials: "include",
		headers: {
			"Content-Type": "application/json",
			"X-Client-Type": "web",
		},
	};
	return fetchWithRetry(url, options);
}

export async function fetchPutRequest(url, data) {
	const options = {
		method: "PUT",
		body: JSON.stringify(data),
		credentials: "include",
		headers: {
			"Content-Type": "application/json",
			"X-Client-Type": "web",
		},
	};
	return fetchWithRetry(url, options);
}

export async function fetchDeleteRequest(url) {
	const options = {
		method: "DELETE",
		credentials: "include",
		headers: {
			"Content-Type": "application/json",
			"X-Client-Type": "web",
		},
	};
	return fetchWithRetry(url, options);
}

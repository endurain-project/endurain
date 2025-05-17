import {
	fetchGetRequest,
	fetchPostFileRequest,
	fetchDeleteRequest,
	fetchPutRequest,
	fetchPostRequest,
} from "@/utils/serviceUtils";
import { fetchPublicGetRequest } from "@/utils/servicePublicUtils";

export const activities = {
	// Activities authenticated
	getUserWeekActivities(user_id, week_number) {
		return fetchGetRequest(`activities/user/${user_id}/week/${week_number}`);
	},
	getUserThisWeekStats(user_id) {
		return fetchGetRequest(`activities/user/${user_id}/thisweek/distances`);
	},
	getUserThisMonthStats(user_id) {
		return fetchGetRequest(`activities/user/${user_id}/thismonth/distances`);
	},
	getUserThisMonthActivitiesNumber(user_id) {
		return fetchGetRequest(`activities/user/${user_id}/thismonth/number`);
	},
	getUserActivitiesByGearId(gear_id) {
		return fetchGetRequest(`activities/user/gear/${gear_id}`);
	},
	getUserNumberOfActivities(filters = {}) {
		let baseUrl = "activities/number";
		const params = new URLSearchParams();

		// Add filters to query parameters if they exist
		if (filters.type) {
			params.append("type", filters.type);
		}
		if (filters.start_date) {
			params.append("start_date", filters.start_date);
		}
		if (filters.end_date) {
			params.append("end_date", filters.end_date);
		}
		if (filters.name_search) {
			params.append("name_search", filters.name_search);
		}

		const queryString = params.toString();
		if (queryString) {
			baseUrl += `?${queryString}`;
		}

		return fetchGetRequest(baseUrl);
	},
	// New function to get distinct activity types
	getActivityTypes() {
		return fetchGetRequest("activities/types");
	},
	// Modified function to accept filters and sorting
	getUserActivitiesWithPagination(
		user_id,
		pageNumber,
		numRecords,
		filters = {},
		sortBy = null,
		sortOrder = null,
	) {
		// Added sortBy and sortOrder
		let baseUrl = `activities/user/${user_id}/page_number/${pageNumber}/num_records/${numRecords}`;
		const params = new URLSearchParams();

		// Add filters to query parameters if they exist
		if (filters.type) {
			params.append("type", filters.type);
		}
		if (filters.start_date) {
			params.append("start_date", filters.start_date);
		}
		if (filters.end_date) {
			params.append("end_date", filters.end_date);
		}
		if (filters.name_search) {
			params.append("name_search", filters.name_search);
		}

		// Add sorting parameters if they exist
		if (sortBy) {
			params.append("sort_by", sortBy);
		}
		if (sortOrder) {
			params.append("sort_order", sortOrder);
		}

		const queryString = params.toString();
		if (queryString) {
			baseUrl += `?${queryString}`;
		}

		return fetchGetRequest(baseUrl);
	},
	getUserFollowersActivitiesWithPagination(user_id, pageNumber, numRecords) {
		// Note: This endpoint is not yet updated to handle filters
		return fetchGetRequest(
			`activities/user/${user_id}/followed/page_number/${pageNumber}/num_records/${numRecords}`,
		);
	},
	getActivityById(activityId) {
		return fetchGetRequest(`activities/${activityId}`);
	},
	getActivityByName(name) {
		return fetchGetRequest(`activities/name/contains/${name}`);
	},
	getActivityRefresh() {
		return fetchGetRequest("activities/refresh");
	},
	uploadActivityFile(formData) {
		return fetchPostFileRequest("activities/create/upload", formData);
	},
	bulkImportActivities() {
		return fetchPostRequest("activities/create/bulkimport");
	},
	editActivity(data) {
		return fetchPutRequest("activities/edit", data);
	},
	editUserActivitiesVisibility(visibility) {
		return fetchPutRequest(`activities/visibility/${visibility}`);
	},
	deleteActivity(activityId) {
		return fetchDeleteRequest(`activities/${activityId}/delete`);
	},
	// Activities public
	getPublicActivityById(activityId) {
		return fetchPublicGetRequest(`public/activities/${activityId}`);
	},
};

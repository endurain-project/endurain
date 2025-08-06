import {
	fetchGetRequest,
	fetchPostFileRequest,
	fetchDeleteRequest,
	fetchPutRequest,
	fetchPostRequest,
} from "@/utils/serviceUtils";
import { fetchPublicGetRequest } from "@/utils/servicePublicUtils";

export const segments = {
    // Get segments for a user with optional filters
 	getUserNumberOfSegments(user_id, filters = {}) {
		let baseUrl = `segments/number`;
		const params = new URLSearchParams();

		// Add filters to query parameters if they exist
		if (filters.type) {
			params.append("type", filters.type);
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
    // Get the activity types for which we have segments
    getActivityTypes() {
        return fetchGetRequest("segments/types");
    },
    // Get segments with pagination
    getSegmentsWithPagination(
        user_id, 
        pageNumber, 
        numRecords, 
        filters = {},
        sortBy = null,
        sortOrder = null
    ) {
        let baseUrl = `segments/user/${user_id}/page_number/${pageNumber}/num_records/${numRecords}`;
        const params = new URLSearchParams();

        // Add filters to query parameters if they exist
        if (filters.type) {
            params.append("type", filters.type);
        }
        if (filters.name_search) {
            params.append("name_search", filters.name_search);
        }

        // Add sorting to query parameters if it exists
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
    getActivitySegments(segmentId){
        return fetchGetRequest(`segments/${segmentId}/intersections`)
    },
    getSegmentById(segmentId) {
        return fetchGetRequest(`segments/${segmentId}`);
    },
    deleteSegment(segmentId) {
        return fetchDeleteRequest(`segments/${segmentId}/delete`);
    },
};
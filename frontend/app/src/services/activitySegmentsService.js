import { fetchGetRequest, fetchPostRequest, fetchPutRequest, fetchDeleteRequest } from '@/utils/serviceUtils';

export const activitySegments = {
    createSegment(data) {
        return fetchPostRequest('segments', data);
    },
    getActivitySegments(activityId) {
        return fetchGetRequest(`segments/activity_id/${activityId}/all`);
    },
    getActivitySegmentIntersections(activityId, segmentId) {
        return fetchGetRequest(`segments/activity_id/${activityId}/segment_id/${segmentId}/intersections`);
    }
};

import {
	fetchGetRequest,
	fetchPostRequest,
	fetchDeleteRequest,
} from "@/utils/serviceUtils";

export const garminConnect = {
	linkGarminConnect(data) {
		return fetchPostRequest("garminconnect/link", data);
	},
	mfaGarminConnect(data) {
return fetchPostRequest("garminconnect/mfa", data);
},
getGarminConnectActivitiesByDates(startDate, endDate) { // Renamed and params changed
return fetchGetRequest(`garminconnect/activities?start_date=${startDate}&end_date=${endDate}`); // Path and params updated
},
getGarminConnectGear() {
return fetchGetRequest("garminconnect/gear");
},
getGarminConnectHealthDataByDates(startDate, endDate) { // Renamed and params changed
return fetchGetRequest(`garminconnect/health?start_date=${startDate}&end_date=${endDate}`); // Path and params updated
},
unlinkGarminConnect() {
		return fetchDeleteRequest("garminconnect/unlink");
	},
};

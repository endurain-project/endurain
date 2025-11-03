import { fetchGetRequest } from '@/utils/serviceUtils'

export const summaryService = {
  getSummary(userId, viewType, params = {}, activityType = null) {
    // Added activityType parameter
    const url = `activities_summaries/${viewType}`
    const queryParams = new URLSearchParams(params) // Create params object

    // Add activity type filter if provided
    if (activityType) {
      queryParams.append('type', activityType)
    }

    const queryString = queryParams.toString()
    const fullUrl = queryString ? `${url}?${queryString}` : url
    return fetchGetRequest(fullUrl)
  }
}

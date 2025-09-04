import { fetchGetRequest } from '@/utils/serviceUtils'

export const summaryService = {
  /**
   * Fetches activity summary data for a user based on view type and period.
   * @param {number} userId - The ID of the user.
   * @param {string} viewType - The type of summary ('week', 'month', 'year').
   * @param {object} params - Query parameters (e.g., { date: 'YYYY-MM-DD' } or { year: YYYY }).
   * @param {string | null} activityType - Optional activity type name to filter by.
   * @returns {Promise<object>} - The summary data.
   */
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

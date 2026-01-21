import {
  fetchGetRequest,
  fetchPostRequest,
  fetchPutRequest,
  fetchDeleteRequest
} from '@/utils/serviceUtils'

export const userGoals = {
  getUserGoalResults() {
    return fetchGetRequest('profile/goals/results')
  },
  /**
   * Get user goals with optional filters.
   *
   * @param {Object} filters - Optional filters
   * @param {string} filters.interval - Filter by interval (daily, weekly, monthly, yearly)
   * @param {string} filters.activity_type - Filter by activity type (run, bike, swim, walk, strength, cardio)
   * @param {string} filters.goal_type - Filter by goal type (calories, activities, distance, elevation, duration)
   * @returns {Promise} API response with filtered goals
   */
  getUserGoals(filters = {}) {
    const params = new URLSearchParams()
    if (filters.interval) params.append('interval', filters.interval)
    if (filters.activity_type) params.append('activity_type', filters.activity_type)
    if (filters.goal_type) params.append('goal_type', filters.goal_type)

    const queryString = params.toString()
    const url = queryString ? `profile/goals?${queryString}` : 'profile/goals'
    return fetchGetRequest(url)
  },
  createGoal(data) {
    return fetchPostRequest('profile/goals', data)
  },
  editGoal(data) {
    return fetchPutRequest('profile/goals', data)
  },
  deleteGoal(goal_id) {
    return fetchDeleteRequest(`profile/goals/${goal_id}`)
  }
}

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
  getUserGoals() {
    return fetchGetRequest('profile/goals')
  },
  createGoal(data) {
    return fetchPostRequest('profile/goals', data)
  },
  editGoal(goal_id, data) {
    return fetchPutRequest(`profile/goals/${goal_id}`, data)
  },
  deleteGoal(goal_id) {
    return fetchDeleteRequest(`profile/goals/${goal_id}`)
  }
}

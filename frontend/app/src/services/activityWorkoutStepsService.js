import { fetchGetRequest } from '@/utils/serviceUtils'
import { fetchPublicGetRequest } from '@/utils/servicePublicUtils'

export const activityWorkoutSteps = {
  // Activity workout_steps authenticated
  async getActivityWorkoutStepsByActivityId(activityId) {
    return fetchGetRequest(`activities_workout_steps/activity_id/${activityId}/all`)
  },
  // Activity workout_steps public
  async getPublicActivityWorkoutStepsByActivityId(activityId) {
    return fetchPublicGetRequest(`public/activities_workout_steps/activity_id/${activityId}/all`)
  }
}

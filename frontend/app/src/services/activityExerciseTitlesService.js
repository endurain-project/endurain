import { fetchGetRequest } from '@/utils/serviceUtils'
import { fetchPublicGetRequest } from '@/utils/servicePublicUtils'

export const activityExerciseTitles = {
  // Activity exercise titles authenticated
  async getActivityExerciseTitlesAll() {
    return fetchGetRequest('activities_exercise_titles/all')
  },
  // Activity exercise titles public
  async getPublicActivityExerciseTitlesAll() {
    return fetchPublicGetRequest('public/activities_exercise_titles/all')
  }
}

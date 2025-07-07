import { fetchGetRequest, fetchPostRequest, fetchPutRequest, fetchDeleteRequest, fetchPostFileRequest } from '@/utils/serviceUtils';
import {getIcon, formatCalories, formatDuration, convertDistanceMetersToKmsOrMiles, convertDistanceMetersToYards} from '@/utils/activityUtils'
import { startCase } from '@/utils/genericUtils';
import {useAuthStore} from '@/stores/authStore';

const authStore = useAuthStore();

export const userGoals = {
    getUserGoals() {
        return fetchGetRequest('goals/results')
            .then(response => {
                return response.map(goal => ({
                    ...goal,
                    
                    icon: getIcon(goal.activity_type),
                    interval_intl_key: `summaryView.option${startCase(goal.interval)}`,
                    goal_distance: convertDistanceMetersToKmsOrMiles(goal.goal_distance, Number(authStore.user.units) === 1),
                    total_distance: convertDistanceMetersToKmsOrMiles(goal.total_distance, Number(authStore.user.units) === 1),

                    total_calories: formatCalories(goal.total_calories),
                    goal_calories: formatCalories(goal.goal_calories),

                    total_duration: formatDuration(goal.total_duration),
                    goal_duration: formatDuration(goal.goal_duration),
                }));
            })
    }
}
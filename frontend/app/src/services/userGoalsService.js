import { fetchGetRequest, fetchPostRequest, fetchPutRequest, fetchDeleteRequest, fetchPostFileRequest } from '@/utils/serviceUtils';
import { getIcon, formatCalories, formatDuration, convertDistanceMetersToKmsOrMiles, convertDistanceMetersToYards } from '@/utils/activityUtils'
import { startCase } from '@/utils/genericUtils';
import { useAuthStore } from '@/stores/authStore';
import { useI18n } from "vue-i18n";


const authStore = useAuthStore();
const { t } = useI18n();

export const userGoals = {
    getUserGoalResults() {
        return fetchGetRequest('profile/goals/results')
            .then(response => {
                console.log('User goal results:', response);
                if (!response || !Array.isArray(response)) {
                    return null;
                } 
                return response.map(goal => ({
                    ...goal,

                    icon: getIcon(goal.activity_type),
                    interval_intl_key: `summaryView.option${startCase(goal.interval)}`,
                    goal_distance: convertDistanceMetersToKmsOrMiles(goal.goal_distance, Number(authStore.user.units) === 1),
                    total_distance: convertDistanceMetersToKmsOrMiles(goal.total_distance, Number(authStore.user.units) === 1),

                    total_calories: formatCalories(t, goal.total_calories),
                    goal_calories: formatCalories(t, goal.goal_calories),

                    total_duration: formatDuration(t, goal.total_duration),
                    goal_duration: formatDuration(t, goal.goal_duration),
                }));
            })
    },
    getUserGoals() {
        return fetchGetRequest('profile/goals')
            .then(response => {
                if (!response || !Array.isArray(response)) {
                    return [];
                }
                return response.map(goal => ({
                    ...goal,
                    goal_duration: goal.goal_duration,
                }))
            });
    },
    createGoal(data) {
        return fetchPostRequest('profile/goals', data);
    },
	editGoal(goal_id, data) {
		return fetchPutRequest(`profile/goals/${goal_id}`, data)
	},
    deleteGoal(goal_id) {
        return fetchDeleteRequest(`profile/goals/${goal_id}`);
    }
}
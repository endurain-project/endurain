import { fetchGetRequest, fetchPostRequest, fetchPutRequest, fetchDeleteRequest, fetchPostFileRequest, API_URL } from '@/utils/serviceUtils';
import { fetchPublicGetRequest } from '@/utils/servicePublicUtils';

export const users = {
    // Users authenticated
    getUsersNumber() {
        return fetchGetRequest('users/number');
    },
    getUsersWithPagination(pageNumber, numRecords) {
        return fetchGetRequest(`users/page_number/${pageNumber}/num_records/${numRecords}`);
    },
    getUserContainsUsername(username){
        return fetchGetRequest(`users/username/contains/${username}`);
    },
    getUserByUsername(username){
        return fetchGetRequest(`users/username/${username}`);
    },
    getUserByEmail(email){
        return fetchGetRequest(`users/email/${email}`);
    },
    getUserById(user_id) {
        return fetchGetRequest(`users/id/${user_id}`);
    },
    createUser(data) {
        return fetchPostRequest('users', data)
    },
    uploadImage(file, user_id) {
        const formData = new FormData();
        formData.append('file', file);

        return fetchPostFileRequest(`users/${user_id}/image`, formData);
    },
    editUser(user_id, data) {
        return fetchPutRequest(`users/${user_id}`, data)
    },
    editUserPassword(user_id, data) {
        return fetchPutRequest(`users/${user_id}/password`, data)
    },
    deleteUserPhoto(user_id) {
        return fetchDeleteRequest(`users/${user_id}/photo`);
    },
    deleteUser(user_id) {
        return fetchDeleteRequest(`users/${user_id}`);
    },
    // Users public
    getPublicUserById(user_id) {
        return fetchPublicGetRequest(`public/users/id/${user_id}`);
    },
};

export const userFirstDayOfWeekService = {
  /**
   * Get user's first day of week preference
   * @param {number} userId - The user ID
   * @returns {Promise<Object>} User's first day of week preference
   */
  async getUserFirstDayOfWeek(userId) {
    try {
      const response = await fetch(
        `${API_URL}users/${userId}/first-day-of-week`,
        {
          method: "GET",
          credentials: "include",
          headers: {
            "Content-Type": "application/json",
          },
        }
      );

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || "Failed to fetch first day of week preference");
      }

      return await response.json();
    } catch (error) {
      console.error("Error fetching user first day of week:", error);
      throw error;
    }
  },

  /**
   * Update user's first day of week preference
   * @param {number} userId - The user ID
   * @param {number} firstDayOfWeek - The first day of week (0=Sunday, 1=Monday, etc.)
   * @returns {Promise<Object>} Updated first day of week preference
   */
  async updateUserFirstDayOfWeek(userId, firstDayOfWeek) {
    try {
      const response = await fetch(
        `${API_URL}users/${userId}/first-day-of-week`,
        {
          method: "PUT",
          credentials: "include",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            first_day_of_week: firstDayOfWeek,
          }),
        }
      );

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || "Failed to update first day of week preference");
      }

      return await response.json();
    } catch (error) {
      console.error("Error updating user first day of week:", error);
      throw error;
    }
  },

  /**
   * Create or update user's first day of week preference
   * @param {number} userId - The user ID
   * @param {number} firstDayOfWeek - The first day of week (0=Sunday, 1=Monday, etc.)
   * @returns {Promise<Object>} Created/updated first day of week preference
   */
  async createUserFirstDayOfWeek(userId, firstDayOfWeek) {
    try {
      const response = await fetch(
        `${API_URL}users/${userId}/first-day-of-week`,
        {
          method: "POST",
          credentials: "include",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            first_day_of_week: firstDayOfWeek,
          }),
        }
      );

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || "Failed to create first day of week preference");
      }

      return await response.json();
    } catch (error) {
      console.error("Error creating user first day of week:", error);
      throw error;
    }
  },
};
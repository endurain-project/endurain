<template>
    <li class="list-group-item bg-body-tertiary rounded px-0" :class="{ 'shadow my-1': userDetails }">
		<div class="d-flex justify-content-between">
			<div class="d-flex align-items-center">
				<UserAvatarComponent :user="user" :width=55 :height=55 />
				<div class="ms-3">
					<div class="fw-bold">
						{{ user.username }}
					</div>
					<b>{{ $t("usersListComponent.userListAccessTypeLabel") }}</b>
					<span v-if="user.access_type == 1">{{ $t("usersListComponent.userListAccessTypeOption1") }}</span>
					<span v-else>{{ $t("usersListComponent.userListAccessTypeOption2") }}</span>
				</div>
			</div>
			<div>
				<span class="badge bg-secondary-subtle border border-secondary-subtle text-secondary-emphasis align-middle me-2" v-if="user.id == authStore.user.id">{{ $t("usersListComponent.userListUserIsMeBadge") }}</span>
				<span class="badge bg-warning-subtle border border-warning-subtle text-warning-emphasis align-middle me-2" v-if="user.access_type == 2">{{ $t("usersListComponent.userListUserIsAdminBadge") }}</span>
				<span class="badge bg-success-subtle border border-success-subtle text-success-emphasis align-middle" v-if="user.is_active == 1">{{ $t("usersListComponent.userListUserIsActiveBadge") }}</span>
				<span class="badge bg-danger-subtle border border-danger-subtle text-danger-emphasis align-middle" v-else>{{ $t("usersListComponent.userListUserIsInactiveBadge") }}</span>

				<!-- change user password button -->
				<a class="btn btn-link btn-lg link-body-emphasis" href="#" role="button" data-bs-toggle="modal" :data-bs-target="`#editUserPasswordModal${user.id}`"><font-awesome-icon :icon="['fas', 'fa-key']" /></a>

				<!-- change user password Modal -->
				<UsersChangeUserPasswordModalComponent :user="user" />

				<!-- edit user button -->
				<a class="btn btn-link btn-lg link-body-emphasis" href="#" role="button" data-bs-toggle="modal" :data-bs-target="`#editUserModal${user.id}`"><font-awesome-icon :icon="['fas', 'fa-pen-to-square']" /></a>

				<UsersAddEditUserModalComponent :action="'edit'" :user="user" @editedUser="editUserList"/>

				<!-- delete user button -->
				<a class="btn btn-link btn-lg link-body-emphasis" href="#" role="button" data-bs-toggle="modal" :data-bs-target="`#deleteUserModal${user.id}`" v-if="authStore.user.id != user.id"><font-awesome-icon :icon="['fas', 'fa-trash-can']" /></a>

				<!-- delete user modal -->
				<ModalComponent :modalId="`deleteUserModal${user.id}`" :title="t('usersListComponent.modalDeleteUserTitle')" :body="`${t('usersListComponent.modalDeleteUserBody')}<b>${user.username}</b>?`" :actionButtonType="`danger`" :actionButtonText="t('usersListComponent.modalDeleteUserTitle')" @submitAction="submitDeleteUser"/>

				<!-- button toggle user details -->
				<a class="btn btn-link btn-lg link-body-emphasis" data-bs-toggle="collapse" :href="`#collapseUserDetails${user.id}`" role="button" aria-expanded="false" @click="showUserDetails()" aria-controls="`collapseUserDetails${user.id}`">
					<font-awesome-icon :icon="['fas', 'caret-down']" v-if="!userDetails"/>
					<font-awesome-icon :icon="['fas', 'caret-up']" v-else/>
				</a>
			</div>
		</div>
		<div class="collapse" :id="`collapseUserDetails${user.id}`">
			<br>
			<h6>{{ $t("usersListComponent.userListUserSessionsTitle") }}</h6>
			<div v-if="isLoading">
				<LoadingComponent />
			</div>
			<div v-else-if="userSessions && userSessions.length > 0">
				<UserSessionsListComponent v-for="session in userSessions" :key="session.id" :session="session" @sessionDeleted="updateSessionListDeleted"/>
			</div>
			<div v-else>
				<NoItemsFoundComponents />
			</div>
		</div>
    </li>
</template>

<script>
import { ref, onMounted } from "vue";
import { useI18n } from "vue-i18n";
// Importing the services
import { users } from "@/services/usersService";
// Import the stores
import { useAuthStore } from "@/stores/authStore";
// Import Notivue push
import { push } from "notivue";
// Import services
import { session } from "@/services/sessionService";
// Importing the components
import UserAvatarComponent from "@/components/Users/UserAvatarComponent.vue";
import UserSessionsListComponent from "@/components/Settings/SettingsUserSessionsZone/UserSessionsListComponent.vue";
import NoItemsFoundComponents from "@/components/GeneralComponents/NoItemsFoundComponents.vue";
import LoadingComponent from "@/components/GeneralComponents/LoadingComponent.vue";
import ModalComponent from "@/components/Modals/ModalComponent.vue";
import UsersChangeUserPasswordModalComponent from "@/components/Settings/SettingsUsersZone/UsersChangeUserPasswordModalComponent.vue";
import UsersAddEditUserModalComponent from "@/components/Settings/SettingsUsersZone/UsersAddEditUserModalComponent.vue";

export default {
	components: {
		UserAvatarComponent,
		LoadingComponent,
		NoItemsFoundComponents,
		UserSessionsListComponent,
		ModalComponent,
		UsersChangeUserPasswordModalComponent,
		UsersAddEditUserModalComponent,
	},
	props: {
		user: {
			type: Object,
			required: true,
		},
	},
	emits: ["userDeleted", "editedUser"],
	setup(props, { emit }) {
		const { t } = useI18n();
		const authStore = useAuthStore();
		const userProp = ref(props.user);
		const userDetails = ref(false);
		const userSessions = ref([]);
		const isLoading = ref(true);

		async function submitDeleteUser() {
			try {
				await users.deleteUser(props.user.id);

				emit("userDeleted", props.user.id);
			} catch (error) {
				// If there is an error, set the error message and show the error alert.
				push.error(
					`${t("usersListComponent.userDeleteErrorMessage")} - ${error}`,
				);
			}
		}

		function editUserList(editedUser) {
			emit("editedUser", editedUser);
		}

		async function submitDeleteUserPhoto() {
			try {
				await users.deleteUserPhoto(props.user.id);
				userProp.value.photo_path = null;

				// Set the success message and show the success alert.
				push.success(t("usersListComponent.userPhotoDeleteSuccessMessage"));
			} catch (error) {
				// Set the error message
				push.error(
					`${t("usersListComponent.userPhotoDeleteErrorMessage")} - ${error}`,
				);
			}
		}

		function showUserDetails() {
			userDetails.value = !userDetails.value;
		}

		async function updateSessionListDeleted(sessionDeletedId) {
			try {
				// Delete session in the DB
				await session.deleteSession(sessionDeletedId, props.user.id);

				// Remove the session from the userSessions
				userSessions.value = userSessions.value.filter(
					(session) => session.id !== sessionDeletedId,
				);

				// Show the success alert.
				push.success(
					t("usersListComponent.userSessionDeleteSuccessMessage"),
				);
			} catch (error) {
				// If there is an error, show the error alert.
				push.error(
					`${t("usersListComponent.userSessionDeleteErrorMessage")} - ${error}`,
				);
			}
		}

		onMounted(async () => {
			// Fetch the user sessions
			userSessions.value = await session.getUserSessions(props.user.id);

			// Set the isLoading to false
			isLoading.value = false;
		});

		return {
			t,
			authStore,
			submitDeleteUser,
			submitDeleteUserPhoto,
			showUserDetails,
			userDetails,
			userSessions,
			isLoading,
			updateSessionListDeleted,
			editUserList,
		};
	},
};
</script>
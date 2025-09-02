<template>
  <li class="list-group-item bg-body-tertiary rounded px-0">
    <div class="d-flex justify-content-between">
      <div class="d-flex align-items-center">
        <UserAvatarComponent :user="user" :width="55" :height="55" />
        <div class="ms-3">
          <div class="fw-bold">
            {{ user.username }}
          </div>
          <span v-if="user.access_type == 1">{{
            $t('usersListComponent.userListAccessTypeOption1')
          }}</span>
          <span v-else>{{ $t('usersListComponent.userListAccessTypeOption2') }}</span>
        </div>
      </div>
      <div>
        <span
          class="badge bg-secondary-subtle border border-secondary-subtle text-secondary-emphasis me-2 d-none d-sm-inline"
          v-if="user.id == authStore.user.id"
          >{{ $t('usersListComponent.userListUserIsMeBadge') }}</span
        >
        <span
          class="badge bg-warning-subtle border border-warning-subtle text-warning-emphasis me-2 d-none d-sm-inline"
          v-if="user.access_type == 2"
          >{{ $t('usersListComponent.userListUserIsAdminBadge') }}</span
        >
        <span
          class="badge bg-danger-subtle border border-danger-subtle text-danger-emphasis d-none d-sm-inline"
          v-if="user.is_active == 2"
          >{{ $t('usersListComponent.userListUserIsInactiveBadge') }}</span
        >

        <!-- button toggle user details -->
        <a
          class="btn btn-link btn-lg link-body-emphasis"
          data-bs-toggle="collapse"
          :href="`#collapseUserDetails${user.id}`"
          role="button"
          aria-expanded="false"
          @click="showUserDetails()"
          :aria-controls="`collapseUserDetails${user.id}`"
        >
          <font-awesome-icon :icon="['fas', 'caret-down']" v-if="!userDetails" />
          <font-awesome-icon :icon="['fas', 'caret-up']" v-else />
        </a>

        <!-- change user password button -->
        <a
          class="btn btn-link btn-lg link-body-emphasis"
          href="#"
          role="button"
          data-bs-toggle="modal"
          :data-bs-target="`#editUserPasswordModal${user.id}`"
          ><font-awesome-icon :icon="['fas', 'fa-key']"
        /></a>

        <!-- change user password Modal -->
        <UsersChangeUserPasswordModalComponent :user="user" />

        <!-- edit user button -->
        <a
          class="btn btn-link btn-lg link-body-emphasis"
          href="#"
          role="button"
          data-bs-toggle="modal"
          :data-bs-target="`#editUserModal${user.id}`"
          ><font-awesome-icon :icon="['fas', 'fa-pen-to-square']"
        /></a>

        <!-- edit user modal -->
        <UsersAddEditUserModalComponent :action="'edit'" :user="user" @editedUser="editUserList" />

        <!-- delete user button -->
        <a
          class="btn btn-link btn-lg link-body-emphasis"
          href="#"
          role="button"
          data-bs-toggle="modal"
          :data-bs-target="`#deleteUserModal${user.id}`"
          v-if="authStore.user.id != user.id"
          ><font-awesome-icon :icon="['fas', 'fa-trash-can']"
        /></a>

        <!-- delete user modal -->
        <ModalComponent
          :modalId="`deleteUserModal${user.id}`"
          :title="t('usersListComponent.modalDeleteUserTitle')"
          :body="`${t('usersListComponent.modalDeleteUserBody')}<b>${user.username}</b>?`"
          :actionButtonType="`danger`"
          :actionButtonText="t('usersListComponent.modalDeleteUserTitle')"
          @submitAction="submitDeleteUser"
        />
      </div>
    </div>
    <div class="collapse" :id="`collapseUserDetails${user.id}`">
      <br />
      <h6>{{ $t('usersListComponent.userListUserSessionsTitle') }}</h6>
      <div v-if="isLoading">
        <LoadingComponent />
      </div>
      <div v-else-if="userSessions && userSessions.length > 0">
        <UserSessionsListComponent
          v-for="session in userSessions"
          :key="session.id"
          :session="session"
          @sessionDeleted="updateSessionListDeleted"
        />
      </div>
      <div v-else>
        <NoItemsFoundComponents />
      </div>
    </div>
  </li>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { users } from '@/services/usersService'
import { useAuthStore } from '@/stores/authStore'
import { push } from 'notivue'
import { session } from '@/services/sessionService'
import UserAvatarComponent from '@/components/Users/UserAvatarComponent.vue'
import UserSessionsListComponent from '@/components/Settings/SettingsUserSessionsZone/UserSessionsListComponent.vue'
import NoItemsFoundComponents from '@/components/GeneralComponents/NoItemsFoundComponents.vue'
import LoadingComponent from '@/components/GeneralComponents/LoadingComponent.vue'
import ModalComponent from '@/components/Modals/ModalComponent.vue'
import UsersChangeUserPasswordModalComponent from '@/components/Settings/SettingsUsersZone/UsersChangeUserPasswordModalComponent.vue'
import UsersAddEditUserModalComponent from '@/components/Settings/SettingsUsersZone/UsersAddEditUserModalComponent.vue'

const props = defineProps({
  user: {
    type: Object,
    required: true
  }
})
const emit = defineEmits(['userDeleted', 'editedUser'])
const { t } = useI18n()
const authStore = useAuthStore()
const userDetails = ref(false)
const userSessions = ref([])
const isLoading = ref(true)

async function submitDeleteUser() {
  try {
    await users.deleteUser(props.user.id)
    emit('userDeleted', props.user.id)
  } catch (error) {
    push.error(`${t('usersListComponent.userDeleteErrorMessage')} - ${error}`)
  }
}

function editUserList(editedUser) {
  emit('editedUser', editedUser)
}

function showUserDetails() {
  userDetails.value = !userDetails.value
}

async function updateSessionListDeleted(sessionDeletedId) {
  try {
    await session.deleteSession(sessionDeletedId, props.user.id)
    userSessions.value = userSessions.value.filter((session) => session.id !== sessionDeletedId)
    push.success(t('usersListComponent.userSessionDeleteSuccessMessage'))
  } catch (error) {
    push.error(`${t('usersListComponent.userSessionDeleteErrorMessage')} - ${error}`)
  }
}

onMounted(async () => {
  userSessions.value = await session.getUserSessions(props.user.id)
  isLoading.value = false
})
</script>

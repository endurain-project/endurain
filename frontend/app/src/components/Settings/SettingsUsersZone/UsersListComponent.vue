<template>
  <li
    class="list-group-item bg-body-tertiary rounded px-0"
    :class="{ 'shadow rounded px-3 mb-3': userDetails }"
  >
    <div class="d-flex justify-content-between">
      <div class="d-flex align-items-center">
        <UserAvatarComponent :user="user" :width="55" :height="55" />
        <div class="ms-3">
          <div class="fw-bold">
            {{ user.username }}
          </div>
          <span v-if="user.access_type === 'regular'">{{
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
          v-if="user.access_type === 'admin'"
          >{{ $t('usersListComponent.userListUserIsAdminBadge') }}</span
        >
        <span
          class="badge bg-danger-subtle border border-danger-subtle text-danger-emphasis me-2 d-none d-sm-inline"
          v-if="user.active == false"
          >{{ $t('usersListComponent.userListUserIsInactiveBadge') }}</span
        >
        <span
          class="badge bg-danger-subtle border border-danger-subtle text-danger-emphasis me-2 d-none d-sm-inline"
          v-if="user.email_verified == false"
          >{{ $t('usersListComponent.userListUserHasUnverifiedEmailBadge') }}</span
        >
        <span
          class="badge bg-info-subtle border border-info-subtle text-info-emphasis d-none d-sm-inline"
          v-if="user.external_auth_count && user.external_auth_count > 0"
          :aria-label="$t('usersListComponent.userListUserHasExternalAuthBadge')"
          >{{ $t('usersListComponent.userListUserHasExternalAuthBadge') }}</span
        >

        <!-- button toggle user details -->
        <a
          class="btn btn-link btn-lg link-body-emphasis"
          data-bs-toggle="collapse"
          :href="`#collapseUserDetails${user.id}`"
          role="button"
          aria-expanded="false"
          :aria-controls="`collapseUserDetails${user.id}`"
        >
          <font-awesome-icon :icon="['fas', 'caret-down']" v-if="!userDetails" />
          <font-awesome-icon :icon="['fas', 'caret-up']" v-else />
        </a>

        <!-- approve sign-up button -->
        <a
          class="btn btn-link btn-lg link-body-emphasis"
          href="#"
          role="button"
          data-bs-toggle="modal"
          :data-bs-target="`#approveSignUpModal${user.id}`"
          v-if="user.pending_admin_approval && user.email_verified"
          ><font-awesome-icon :icon="['fas', 'fa-check']"
        /></a>

        <!-- approve sign up modal -->
        <ModalComponent
          :modalId="`approveSignUpModal${user.id}`"
          :title="t('usersListComponent.modalApproveSignUpTitle')"
          :body="`${t('usersListComponent.modalApproveSignUpBody')}<b>${user.username}</b>?`"
          :actionButtonType="`success`"
          :actionButtonText="t('usersListComponent.modalApproveSignUpTitle')"
          @submitAction="submitApproveSignUp"
          v-if="user.pending_admin_approval && user.email_verified"
        />

        <!-- reject sign-up button -->
        <a
          class="btn btn-link btn-lg link-body-emphasis"
          href="#"
          role="button"
          data-bs-toggle="modal"
          :data-bs-target="`#rejectSignUpModal${user.id}`"
          v-if="user.pending_admin_approval && user.email_verified"
          ><font-awesome-icon :icon="['fas', 'fa-xmark']"
        /></a>

        <!-- reject sign up modal -->
        <ModalComponent
          :modalId="`rejectSignUpModal${user.id}`"
          :title="t('usersListComponent.modalRejectSignUpTitle')"
          :body="`${t('usersListComponent.modalRejectSignUpBody1')}<b>${user.username}</b>? ${t('usersListComponent.modalRejectSignUpBody2')}`"
          :actionButtonType="`danger`"
          :actionButtonText="t('usersListComponent.modalRejectSignUpTitle')"
          @submitAction="submitDeleteUser"
          v-if="user.pending_admin_approval && user.email_verified"
        />

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
      <!-- Bootstrap Tabs Navigation -->
      <ul class="nav nav-tabs mt-3" role="tablist">
        <li class="nav-item" role="presentation">
          <button
            class="nav-link active link-body-emphasis link-underline-opacity-0 link-underline-opacity-100-hover"
            :id="`sessions-tab-${user.id}`"
            data-bs-toggle="tab"
            :data-bs-target="`#sessions-${user.id}`"
            type="button"
            role="tab"
            :aria-controls="`sessions-${user.id}`"
            aria-selected="true"
          >
            {{ $t('usersListComponent.tabSessions') }}
          </button>
        </li>
        <li class="nav-item" role="presentation">
          <button
            class="nav-link link-body-emphasis link-underline-opacity-0 link-underline-opacity-100-hover"
            :id="`idps-tab-${user.id}`"
            data-bs-toggle="tab"
            :data-bs-target="`#idps-${user.id}`"
            type="button"
            role="tab"
            :aria-controls="`idps-${user.id}`"
            aria-selected="false"
            @click="loadUserIdpsIfNeeded"
          >
            {{ $t('usersListComponent.tabIdentityProviders') }}
          </button>
        </li>
      </ul>

      <!-- Tab Content -->
      <div class="tab-content mt-3">
        <!-- Sessions Tab -->
        <div
          class="tab-pane fade show active"
          :id="`sessions-${user.id}`"
          role="tabpanel"
          :aria-labelledby="`sessions-tab-${user.id}`"
        >
          <div v-if="isLoadingSessions">
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
          <NoItemsFoundComponents :show-shadow="false" v-else />
        </div>

        <!-- Identity Providers Tab -->
        <div
          class="tab-pane fade"
          :id="`idps-${user.id}`"
          role="tabpanel"
          :aria-labelledby="`idps-tab-${user.id}`"
        >
          <div v-if="isLoadingIdps">
            <LoadingComponent />
          </div>
          <div v-else-if="userIdps && userIdps.length > 0">
            <UserIdentityProviderListComponent
              v-for="idp in userIdps"
              :key="idp.id"
              :idp="idp"
              :userId="user.id"
              @idpDeleted="updateIdpListDeleted"
            />
          </div>
          <NoItemsFoundComponents :show-shadow="false" v-else />
        </div>
      </div>
    </div>
  </li>
</template>

<script setup lang="ts">
import { ref, onMounted, type Ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { users } from '@/services/usersService'
import { useAuthStore } from '@/stores/authStore'
import { push } from 'notivue'
import { session } from '@/services/sessionService'
import { userIdentityProviders } from '@/services/userIdentityProvidersService'
import type { UserIdentityProviderEnriched } from '@/types'
import UserAvatarComponent from '@/components/Users/UserAvatarComponent.vue'
import UserSessionsListComponent from '@/components/Settings/SettingsUserSessionsZone/UserSessionsListComponent.vue'
import UserIdentityProviderListComponent from '@/components/Settings/SettingsUsersZone/UserIdentityProviderListComponent.vue'
import NoItemsFoundComponents from '@/components/GeneralComponents/NoItemsFoundComponents.vue'
import LoadingComponent from '@/components/GeneralComponents/LoadingComponent.vue'
import ModalComponent from '@/components/Modals/ModalComponent.vue'
import UsersChangeUserPasswordModalComponent from '@/components/Settings/SettingsUsersZone/UsersChangeUserPasswordModalComponent.vue'
import UsersAddEditUserModalComponent from '@/components/Settings/SettingsUsersZone/UsersAddEditUserModalComponent.vue'

const props = defineProps<{
  user: {
    id: number
    username: string
    access_type: string
    active: boolean
    email_verified: boolean
    pending_admin_approval?: boolean
    external_auth_count?: number
  }
}>()

const emit = defineEmits<{
  userDeleted: [userId: number]
  editedUser: [editedUser: any]
  approvedUser: [userId: number]
}>()

const { t } = useI18n()
const authStore = useAuthStore()
const userDetails = ref(false)
const userSessions: Ref<any[]> = ref([])
const userIdps: Ref<UserIdentityProviderEnriched[]> = ref([])
const isLoadingSessions = ref(true)
const isLoadingIdps = ref(false)
const idpsLoaded = ref(false)

async function submitDeleteUser() {
  try {
    await users.deleteUser(props.user.id)
    emit('userDeleted', props.user.id)
  } catch (error) {
    push.error(`${t('usersListComponent.userDeleteErrorMessage')} - ${error}`)
  }
}

function editUserList(editedUser: any) {
  emit('editedUser', editedUser)
}

async function updateSessionListDeleted(sessionDeletedId: string) {
  try {
    await session.deleteSession(sessionDeletedId, props.user.id)
    userSessions.value = userSessions.value.filter((session) => session.id !== sessionDeletedId)
    push.success(t('usersListComponent.userSessionDeleteSuccessMessage'))
  } catch (error) {
    push.error(`${t('usersListComponent.userSessionDeleteErrorMessage')} - ${error}`)
  }
}

async function loadUserIdpsIfNeeded() {
  if (idpsLoaded.value) {
    return
  }

  isLoadingIdps.value = true
  try {
    userIdps.value = await userIdentityProviders.getUserIdentityProviders(props.user.id)
    idpsLoaded.value = true
  } catch (error) {
    push.error(`${t('usersListComponent.userIdpsLoadErrorMessage')} - ${error}`)
  } finally {
    isLoadingIdps.value = false
  }
}

async function updateIdpListDeleted(idpId: number) {
  try {
    await userIdentityProviders.deleteUserIdentityProvider(props.user.id, idpId)

    // Remove from local list
    userIdps.value = userIdps.value.filter((idp) => idp.idp_id !== idpId)

    // Update the external_auth_count badge
    if (props.user.external_auth_count && props.user.external_auth_count > 0) {
      props.user.external_auth_count--
    }

    push.success(t('usersListComponent.userIdpDeleteSuccessMessage'))
  } catch (error) {
    push.error(`${t('usersListComponent.userIdpDeleteErrorMessage')} - ${error}`)
  }
}

async function submitApproveSignUp() {
  const notification = push.promise(t('usersListComponent.processingApproval'))
  try {
    await users.approveUser(props.user.id)
    notification.resolve(t('usersListComponent.userApproveSuccessMessage'))
    emit('approvedUser', props.user.id)
  } catch (error) {
    notification.reject(`${t('usersListComponent.userApproveErrorMessage')} - ${error}`)
  }
}

onMounted(async () => {
  userSessions.value = await session.getUserSessions(props.user.id)
  isLoadingSessions.value = false

  // Attach Bootstrap collapse event listeners to sync icon state
  const collapseElement = document.getElementById(`collapseUserDetails${props.user.id}`)
  if (collapseElement) {
    collapseElement.addEventListener('show.bs.collapse', () => {
      userDetails.value = true
    })
    collapseElement.addEventListener('hide.bs.collapse', () => {
      userDetails.value = false
    })
  }
})
</script>

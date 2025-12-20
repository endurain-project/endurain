<template>
  <div v-if="isLoading">
    <LoadingComponent />
  </div>
  <div class="d-flex align-items-center" v-if="!isLoading">
    <UserAvatarComponent :user="userFollower" :width="55" :height="55" />
    <div class="ms-3">
      <div class="fw-bold">
        <router-link
          :to="{ name: 'user', params: { id: userFollower.id } }"
          class="link-body-emphasis link-underline-opacity-0 link-underline-opacity-100-hover"
        >
          {{ userFollower.name }}
        </router-link>
        <!--<a :href="`/user/${userFollower.id}`" class="link-body-emphasis link-underline-opacity-0 link-underline-opacity-100-hover">
                    {{ userFollower.name }}
                </a>-->
      </div>
      {{ userFollower.username }}
    </div>
  </div>
  <div class="ms-3 align-middle" v-if="!isLoading">
    <!-- badge is accepted  -->
    <span
      class="badge bg-success-subtle border border-success-subtle text-success-emphasis rounded-pill align-middle"
      v-if="follower.is_accepted == 1"
      >{{ $t('followersListComponent.requestAccepted') }}</span
    >
    <!-- badge pending request  -->
    <span
      class="badge bg-danger-subtle border border-danger-subtle text-danger-emphasis rounded-pill align-middle"
      v-else
      >{{ $t('followersListComponent.requestPending') }}</span
    >

    <!-- delete following zone  -->
    <a
      class="ms-2 btn btn-link btn-lg link-body-emphasis"
      href="#"
      role="button"
      data-bs-toggle="modal"
      :data-bs-target="`#deleteFollowingModal${userFollower.id}`"
      v-if="type == 1 && authStore.user.id == idFromParam"
      ><font-awesome-icon :icon="['fas', 'fa-trash']"
    /></a>

    <!-- delete following modal -->
    <ModalComponent
      v-if="type == 1 && authStore.user.id == idFromParam"
      :modalId="`deleteFollowingModal${userFollower.id}`"
      :title="t('followersListComponent.followingModalTitle')"
      :body="`${t('followersListComponent.followingModalBody')}<b>${userFollower.name}</b>?`"
      :actionButtonType="`danger`"
      :actionButtonText="t('followersListComponent.followingModalTitle')"
      @submitAction="submitDeleteFollowing"
    />

    <!-- delete follower zone  -->
    <a
      class="ms-2 btn btn-link btn-lg link-body-emphasis"
      href="#"
      role="button"
      data-bs-toggle="modal"
      :data-bs-target="`#deleteFollowerModal${userFollower.id}`"
      v-if="type != 1 && authStore.user.id == idFromParam && follower.is_accepted == 1"
      ><font-awesome-icon :icon="['fas', 'fa-trash']"
    /></a>

    <!-- Modal delete follower -->
    <ModalComponent
      v-if="type != 1 && authStore.user.id == idFromParam && follower.is_accepted == 1"
      :modalId="`deleteFollowerModal${userFollower.id}`"
      :title="t('followersListComponent.followerModalTitle')"
      :body="`${t('followersListComponent.followerModalBody')}<b>${userFollower.name}</b>?`"
      :actionButtonType="`danger`"
      :actionButtonText="t('followersListComponent.followerModalTitle')"
      @submitAction="submitDeleteFollower"
    />

    <!-- accept folllower request -->
    <a
      class="btn btn-link btn-lg link-body-emphasis"
      href="#"
      role="button"
      data-bs-toggle="modal"
      :data-bs-target="`#acceptRequestModal${userFollower.id}`"
      v-if="type != 1 && authStore.user.id == idFromParam && follower.is_accepted == 0"
      ><font-awesome-icon :icon="['fas', 'fa-check']"
    /></a>

    <!-- Modal accept user request -->
    <ModalComponent
      v-if="type != 1 && authStore.user.id == idFromParam && follower.is_accepted == 0"
      :modalId="`acceptRequestModal${userFollower.id}`"
      :title="t('followersListComponent.followerAcceptModalTitle')"
      :body="`${t('followersListComponent.followerAcceptModalBody')}<b>${userFollower.name}</b>?`"
      :actionButtonType="`success`"
      :actionButtonText="t('followersListComponent.followerAcceptModalTitle')"
      @submitAction="submitAcceptFollowerRequest"
    />

    <!-- decline user request button -->
    <a
      class="ms-2 btn btn-link btn-lg link-body-emphasis"
      href="#"
      role="button"
      data-bs-toggle="modal"
      :data-bs-target="`#declineRequestModal${userFollower.id}`"
      v-if="type != 1 && authStore.user.id == idFromParam && follower.is_accepted == 0"
      ><font-awesome-icon :icon="['fas', 'fa-x']"
    /></a>

    <!-- Modal decline user request -->
    <ModalComponent
      v-if="type != 1 && authStore.user.id == idFromParam && follower.is_accepted == 0"
      :modalId="`declineRequestModal${userFollower.id}`"
      :title="t('followersListComponent.followerDeclineModalTitle')"
      :body="`${t('followersListComponent.followerDeclineModalBody')}<b>${userFollower.name}</b>?`"
      :actionButtonType="`danger`"
      :actionButtonText="t('followersListComponent.followerDeclineModalTitle')"
      @submitAction="submitDeleteFollower"
    />
  </div>
</template>

<script>
import { ref, onMounted, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useAuthStore } from '@/stores/authStore'
import { useRoute } from 'vue-router'
import { users } from '@/services/usersService'
import { followers } from '@/services/followersService'
// Import Notivue push
import { push } from 'notivue'
import LoadingComponent from '@/components/GeneralComponents/LoadingComponent.vue'
import UserAvatarComponent from '../Users/UserAvatarComponent.vue'
import ModalComponent from '@/components/Modals/ModalComponent.vue'

export default {
  components: {
    LoadingComponent,
    UserAvatarComponent,
    ModalComponent
  },
  emits: ['followerDeleted', 'followingDeleted', 'followerAccepted'],
  props: {
    follower: {
      type: Object,
      required: true
    },
    type: {
      type: Number,
      required: true
    }
  },
  setup(props, { emit }) {
    const { t } = useI18n()
    const route = useRoute()
    const authStore = useAuthStore()
    const userFollower = ref(null)
    const isLoading = ref(true)
    const idFromParam = computed(() => Number(route.params.id))

    async function submitDeleteFollowing() {
      try {
        await followers.deleteUserFollower(userFollower.value.id)
        emit('followingDeleted', userFollower.value.id)
      } catch (error) {
        // If there is an error, set the error message and show the error alert.
        push.error(`${t('followersListComponent.errorDeleteFollowing')} - ${error}`)
      }
    }

    async function submitDeleteFollower() {
      try {
        await followers.deleteUserFollowing(userFollower.value.id)
        emit('followerDeleted', userFollower.value.id)
      } catch (error) {
        // If there is an error, set the error message and show the error alert.
        push.error(`${t('followersListComponent.errorDeleteFollower')} - ${error}`)
      }
    }

    async function submitAcceptFollowerRequest() {
      try {
        await followers.acceptUserFollowsSpecificUser(userFollower.value.id)
        emit('followerAccepted', userFollower.value.id)
      } catch (error) {
        // If there is an error, set the error message and show the error alert.
        push.error(`${t('followersListComponent.errorUpdateFollower')} - ${error}`)
      }
    }

    onMounted(async () => {
      try {
        if (props.type === 1) {
          userFollower.value = await users.getUserById(props.follower.following_id)
        } else {
          userFollower.value = await users.getUserById(props.follower.follower_id)
        }
      } catch (error) {
        // If there is an error, set the error message and show the error alert.
        push.error(`${t('followersListComponent.errorFetchingFollowersDetails')} - ${error}`)
      } finally {
        isLoading.value = false
      }
    })

    return {
      t,
      userFollower,
      isLoading,
      idFromParam,
      authStore,
      submitDeleteFollowing,
      submitDeleteFollower,
      submitAcceptFollowerRequest
    }
  }
}
</script>

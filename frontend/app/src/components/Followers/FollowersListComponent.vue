<template>
    <div v-if="isLoading">
        <LoadingComponent />
    </div>
    <div class="d-flex align-items-center" v-if="!isLoading">
        <UserAvatarComponent :userProp="userFollower" :width=55 :height=55 />
        <div class="ms-3">
            <div class="fw-bold">
                <router-link :to="{ name: 'user', params: { id: userFollower.id }}" class="link-body-emphasis link-underline-opacity-0 link-underline-opacity-100-hover">
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
        <span class="badge bg-success-subtle border border-success-subtle text-success-emphasis rounded-pill align-middle" v-if="follower.is_accepted == 1">{{ $t("followersListComponent.requestAccepted") }}</span>
        <!-- badge pending request  -->
        <span class="badge bg-danger-subtle border border-danger-subtle text-danger-emphasis rounded-pill align-middle" v-else>{{ $t("followersListComponent.requestPending") }}</span>
            
        <!-- delete following zone  -->
        <a class="ms-2 btn btn-link btn-lg link-body-emphasis" href="#" role="button" data-bs-toggle="modal" :data-bs-target="`#deleteFollowingModal${userFollower.id}`" v-if="type == 1 && authStore.user.id == idFromParam"><font-awesome-icon :icon="['fas', 'fa-trash']" /></a>
        
        <div class="modal fade" :id="`deleteFollowingModal${userFollower.id}`" tabindex="-1" :aria-labelledby="`deleteFollowingModal${userFollower.id}`" aria-hidden="true" v-if="type == 1 && authStore.user.id == idFromParam">
            <div class="modal-dialog">
                <div class="modal-content">
                    <div class="modal-header">
                        <h1 class="modal-title fs-5">
                            {{ $t("followersListComponent.followingModalTitle") }}
                        </h1>
                        <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
                    </div>
                    <div class="modal-body">
                        {{ $t("followersListComponent.followingModalBody") }}<b>
                            {{ userFollower.name }}
                        </b>?
                    </div>
                    <div class="modal-footer">
                        <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">
                            {{ $t("generalItens.buttonClose") }}
                        </button>
                        <a @click="submitDeleteFollowing" type="button" class="btn btn-danger" data-bs-dismiss="modal">
                            {{ $t("followersListComponent.followingModalTitle") }}
                        </a>
                    </div>
                </div>
            </div>
        </div>

        <!-- delete follower zone  -->
        <a class="ms-2 btn btn-link btn-lg link-body-emphasis" href="#" role="button" data-bs-toggle="modal" :data-bs-target="`#deleteFollowerModal${userFollower.id}`" v-if="type != 1 && authStore.user.id == idFromParam && follower.is_accepted == 1"><font-awesome-icon :icon="['fas', 'fa-trash']" /></a>

        <!-- Modal delete follower -->
        <div class="modal fade" :id="`deleteFollowerModal${userFollower.id}`" tabindex="-1" :aria-labelledby="`deleteFollowerModal${userFollower.id}`" aria-hidden="true" v-if="type != 1 && authStore.user.id == idFromParam && follower.is_accepted == 1">
            <div class="modal-dialog">
                <div class="modal-content">
                    <div class="modal-header">
                        <h1 class="modal-title fs-5">
                            {{ $t("followersListComponent.followerModalTitle") }}
                        </h1>
                        <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
                    </div>
                    <div class="modal-body">
                        {{ $t("followersListComponent.followerModalBody") }}<b>
                            {{ userFollower.name }}
                        </b>?
                    </div>
                    <div class="modal-footer">
                        <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">
                            {{ $t("generalItens.buttonClose") }}
                        </button>
                        <a @click="submitDeleteFollower" type="button" class="btn btn-danger" data-bs-dismiss="modal">
                            {{ $t("followersListComponent.followerModalTitle") }}
                        </a>
                    </div>
                </div>
            </div>
        </div>

        <!-- accept folllower request -->
        <a class="btn btn-link btn-lg link-body-emphasis" href="#" role="button" data-bs-toggle="modal" :data-bs-target="`#acceptRequestModal${userFollower.id}`" v-if="type != 1 && authStore.user.id == idFromParam && follower.is_accepted == 0"><font-awesome-icon :icon="['fas', 'fa-check']" /></a>

        <!-- Modal accept user request -->
        <div class="modal fade" :id="`acceptRequestModal${userFollower.id}`" tabindex="-1" :aria-labelledby="`acceptRequestModal${userFollower.id}`" aria-hidden="true" v-if="type != 1 && authStore.user.id == idFromParam && follower.is_accepted == 0">
            <div class="modal-dialog">
                <div class="modal-content">
                    <div class="modal-header">
                        <h1 class="modal-title fs-5">
                            {{ $t("followersListComponent.followerAcceptModalTitle") }}
                        </h1>
                        <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
                    </div>
                    <div class="modal-body">
                        {{ $t("followersListComponent.followerAcceptModalBody") }}<b>
                            {{ userFollower.name }}
                        </b>?
                    </div>
                    <div class="modal-footer">
                        <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">
                            {{ $t("generalItens.buttonClose") }}
                        </button>
                        <a @click="submitAcceptFollowerRequest" type="button" class="btn btn-success" data-bs-dismiss="modal">
                            {{ $t("followersListComponent.followerAcceptModalTitle") }}
                        </a>
                    </div>
                </div>
            </div>
        </div>

        <!-- decline user request button -->
        <a class="ms-2 btn btn-link btn-lg link-body-emphasis" href="#" role="button" data-bs-toggle="modal" :data-bs-target="`#declineRequestModal${userFollower.id}`" v-if="type != 1 && authStore.user.id == idFromParam && follower.is_accepted == 0"><font-awesome-icon :icon="['fas', 'fa-x']" /></a>

        <!-- Modal decline user request -->
        <div class="modal fade" :id="`declineRequestModal${userFollower.id}`" tabindex="-1" :aria-labelledby="`declineRequestModal${userFollower.id}`" aria-hidden="true" v-if="type != 1 && authStore.user.id == idFromParam && follower.is_accepted == 0">
            <div class="modal-dialog">
                <div class="modal-content">
                    <div class="modal-header">
                        <h1 class="modal-title fs-5">
                            {{ $t("followersListComponent.followerDeclineModalTitle") }}
                        </h1>
                        <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
                    </div>
                    <div class="modal-body">
                        {{ $t("followersListComponent.followerDeclineModalBody") }}<b>
                            {{ userFollower.name }}
                        </b>?
                    </div>
                    <div class="modal-footer">
                        <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">
                            {{ $t("generalItens.buttonClose") }}
                        </button>
                        <a @click="submitDeleteFollower" type="button" class="btn btn-danger" data-bs-dismiss="modal">
                            {{ $t("followersListComponent.followerDeclineModalTitle") }}
                        </a>
                    </div>
                </div>
            </div>
        </div>
    </div>
</template>

<script>
import { ref, onMounted, computed } from 'vue';
import { useAuthStore } from '@/stores/authStore';
import { useRoute } from 'vue-router';
import { users } from '@/services/usersService';
import { followers } from '@/services/followersService';
import LoadingComponent from '@/components/GeneralComponents/LoadingComponent.vue';
import UserAvatarComponent from '../Users/UserAvatarComponent.vue';

export default {
    components: {
        LoadingComponent,
        UserAvatarComponent,
    },
    emits: ['followerDeleted', 'followingDeleted', 'followerAccepted'],
    props: {
        follower: {
            type: Object,
            required: true,
        },
        type:{
            type: Number,
            required: true,
        }
    },
    setup(props, { emit }) {
        const route = useRoute();
        const authStore = useAuthStore();
        const userFollower = ref(null);
        const isLoading = ref(true);
        const idFromParam = computed(() => route.params.id);

        async function submitDeleteFollowing() {
            try {
                await followers.deleteUserFollower(userFollower.value.id);
                emit('followingDeleted', userFollower.value.id);
            } catch (error) {
                console.error("Failed to delete following:", error);
            }
        }

        async function submitDeleteFollower() {
            try {
                await followers.deleteUserFollowing(userFollower.value.id);
                emit('followerDeleted', userFollower.value.id);
            } catch (error) {
                console.error("Failed to delete follower:", error);
            }
        }

        async function submitAcceptFollowerRequest() {
            try {
                await followers.acceptUserFollowsSpecificUser(userFollower.value.id);
                emit('followerAccepted', userFollower.value.id);
            } catch (error) {
                console.error("Failed to update follower:", error);
            }
        }

        onMounted(async () => {
            try {
                if (props.type === 1) {
                    userFollower.value = await users.getUserById(props.follower.following_id);
                } else {
                    userFollower.value = await users.getUserById(props.follower.follower_id);
                }
            } catch (error) {
                console.error("Failed to fetch follower details:", error);
            } finally {
                isLoading.value = false;
            }
        });

        return {
            userFollower,
            isLoading,
            idFromParam,
            authStore,
            submitDeleteFollowing,
            submitDeleteFollower,
            submitAcceptFollowerRequest,
        };
    },
};
</script>
<template>
    <li class="list-group-item d-flex justify-content-between">
        <div v-if="isLoading">
            <LoadingComponent />
        </div>
        <div class="d-flex align-items-center" v-else>
            <img :src="userMe.photo_path" alt="User Photo" width="55" height="55" class="rounded-circle" v-if="userFollower.photo_path">
            <img src="/src/assets/avatar/male1.png" alt="Default Male Avatar" width="55" height="55" class="rounded-circle" v-else-if="!userFollower.photo_path && userFollower.gender == 1">
            <img src="/src/assets/avatar/female1.png" alt="Default Female Avatar" width="55" height="55" class="rounded-circle" v-else>
            <div class="ms-3">
                <div class="fw-bold">
                    <router-link :to="{ name: 'user', params: { id: userFollower.id }}">
                        {{ userFollower.name }}
                    </router-link>
                </div>
                {{ userFollower.username }}
            </div>
        </div>
        <!--<div class="ms-3 align-middle">
            <span class="badge bg-success-subtle border border-success-subtle text-success-emphasis rounded-pill align-middle" v-if="userFollower.is_accepted == 1"><?php echo $translationsUsersUser['user_following_zone_requestAccepted']; ?></span>
            <span class="badge bg-danger-subtle border border-danger-subtle text-danger-emphasis rounded-pill align-middle" v-else><?php echo $translationsUsersUser['user_following_zone_requestPending']; ?></span>

            <?php if ($_GET["userID"] == $_SESSION["id"]) { ?>
                
                <a class="ms-2 btn btn-link btn-lg" href="#" role="button" data-bs-toggle="modal" data-bs-target="#deleteFollowingModal<?php echo ($userFollowing["id"]); ?>"><i class="fa-solid fa-trash"></i></a>
                
                <div class="modal fade" id="deleteFollowingModal<?php echo ($userFollowing["id"]); ?>" tabindex="-1" aria-labelledby="deleteFollowingModal<?php echo ($userFollowing["id"]); ?>"
                    aria-hidden="true">
                    <div class="modal-dialog">
                        <div class="modal-content">
                            <div class="modal-header">
                                <h1 class="modal-title fs-5" id="deleteFollowingModal<?php echo ($userFollowing["id"]); ?>">
                                    <?php echo $translationsUsersUser['user_deleteFollowing_modal_title']; ?>
                                </h1>
                                <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
                            </div>
                            <div class="modal-body">
                                <?php echo $translationsUsersUser['user_deleteFollowing_modal_body']; ?> <b>
                                    <?php echo $userFollowing["name"]; ?>
                                </b>?
                            </div>
                            <div class="modal-footer">
                                <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">
                                    <?php echo $translationsTemplateTop['template_top_global_close']; ?>
                                </button>
                                <a type="button" class="btn btn-danger"
                                    href="../users/user.php?userID=<?php echo ($_GET["userID"]); ?>&targetUserID=<?php echo ($userFollowing["id"]); ?>&deleteFollowing=1">
                                    <?php echo $translationsUsersUser['user_deleteFollowing_modal_title']; ?>
                                </a>
                            </div>
                        </div>
                    </div>
                </div>
            <?php } ?>
        </div>-->
    </li>
</template>

<script>
import { ref, onMounted, watchEffect, computed } from 'vue';
import { users } from '@/services/user';
import LoadingComponent from '@/components/LoadingComponent.vue';

export default {
    components: {
        LoadingComponent,
    },
    props: {
        follower: {
            type: Object,
            required: true,
        }
    },
    setup(props) {
        const userFollower = ref(null);
        const isLoading = ref(true);

        onMounted(async () => {
            try {
                userFollower.value = await users.getUserById(props.follower.following_id);
            } catch (error) {
                console.error("Failed to fetch activity details:", error);
            } finally {
                isLoading.value = false;
            }
        });

        return {
            userFollower,
            isLoading,
        };
    },
};
</script>
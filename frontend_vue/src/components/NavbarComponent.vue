<template>
    <nav class="navbar navbar-expand-lg bg-body-tertiary">
        <div class="container-fluid">
            <a class="navbar-brand" href="/">Endurain</a>
            <button class="navbar-toggler" type="button" data-bs-toggle="collapse" data-bs-target="#navbarNavAltMarkup"
                aria-controls="navbarNavAltMarkup" aria-expanded="false" aria-label="Toggle navigation">
                <span class="navbar-toggler-icon"></span>
            </button>
            <div class="collapse navbar-collapse" id="navbarNavAltMarkup">
                <div class="navbar-nav me-auto mb-2 mb-lg-0">
                    <!-- if is logged in -->
                    <a class="nav-link" href="#" v-if="isLoggedIn">
                        <font-awesome-icon :icon="['fas', 'fa-bicycle']" />
                        <span class="ms-1">
                            {{ $t("navbar.gear") }}
                        </span>
                    </a>
                </div>
                <div class="navbar-nav">
                    <span class="border-top d-sm-none d-block mb-2" v-if="isLoggedIn"></span>
                    <a class="nav-link" href="#" v-if="isLoggedIn">
                        <img :src="userMe.photo_path" alt="User Photo" width="24" height="24" class="rounded-circle align-top" v-if="userMe.photo_path">
                        <img src="/src/assets/avatar/male1.png" alt="Default Male Avatar" width="24" height="24" class="rounded-circle align-top" v-else-if="!userMe.photo_path && userMe.gender == 1">
                        <img src="/src/assets/avatar/female1.png" alt="Default Female Avatar" width="24" height="24" class="rounded-circle align-top" v-else>
                        <span class="ms-2">{{ $t("navbar.profile") }}</span>
                    </a>
                    <span class="border-top d-sm-none d-block" v-if="isLoggedIn"></span>
                    <a class="nav-link d-none d-sm-block" v-if="isLoggedIn">|</a>
                    <a class="nav-link" href="/settings" v-if="isLoggedIn">
                        <font-awesome-icon :icon="['fas', 'fa-gear']" />
                        <span class="ms-1">{{ $t("navbar.settings") }}</span>
                    </a>
                    <a class="nav-link" href="#" v-if="isLoggedIn" @click="handleLogout">
                        <font-awesome-icon :icon="['fas', 'fa-sign-out-alt']" />
                        <span class="ms-1">{{ $t("navbar.logout") }}</span>
                    </a>
                    <!-- if is not logged in -->
                    <a class="nav-link" href="/login" v-if="!isLoggedIn">
                        <font-awesome-icon :icon="['fas', 'fa-sign-in-alt']" />
                        <span class="ms-1">{{ $t("navbar.login") }}</span>
                    </a>
                </div>
            </div>
        </div>
    </nav>
    <div class="alert alert-warning alert-dismissible d-flex align-items-center mx-2 my-2 justify-content-center"
        role="alert">
        <font-awesome-icon :icon="['fas', 'triangle-exclamation']" />
        <div>
            <span class="me-1">
                {{ $t("navbar.warningZone") }}
            </span>
        </div>
    </div>
</template>

<script>
import { auth } from '@/services/auth';
import { useRouter } from 'vue-router';

export default {
    setup() {
        const router = useRouter();

        function handleLogout() {
            auth.removeLoggedUser();
            router.push('/login');
        }

        return {
            isLoggedIn: auth.isTokenValid(localStorage.getItem('accessToken')),
            userMe: JSON.parse(localStorage.getItem('userMe')),
            handleLogout,
        };
    },
};
</script>
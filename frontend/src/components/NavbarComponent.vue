<template>
    <nav class="navbar navbar-expand-lg bg-body-tertiary">
        <div class="container-fluid">
            <router-link :to="{ name: 'home' }" class="navbar-brand" @click="collapseNavbar">
                Endurain
            </router-link>
            <button class="navbar-toggler" type="button" data-bs-toggle="collapse" data-bs-target="#navbarNavAltMarkup"
                aria-controls="navbarNavAltMarkup" aria-expanded="false" aria-label="Toggle navigation">
                <span class="navbar-toggler-icon"></span>
            </button>
            <div class="collapse navbar-collapse" id="navbarNavAltMarkup" ref="navbarCollapse">
                <div class="navbar-nav me-auto mb-2 mb-lg-0">
                    <!-- if is logged in -->
                    <router-link :to="{ name: 'gears' }" class="nav-link" v-if="isLoggedIn" @click="collapseNavbar">
                        <font-awesome-icon :icon="['fas', 'fa-bicycle']" />
                        <span class="ms-1">
                            {{ $t("navbar.gear") }}
                        </span>
                    </router-link>
                </div>
                <div class="navbar-nav">
                    <span class="border-top d-sm-none d-block mb-2" v-if="isLoggedIn"></span>
                    <router-link :to="{ name: 'user', params: { id: userMe.id } }" class="nav-link" v-if="isLoggedIn && userMe" @click="collapseNavbar">
                        <UserAvatarComponent :userProp="userMe" :width=24 :height=24 :alignTop=2 />
                        <span class="ms-2">{{ $t("navbar.profile") }}</span>
                    </router-link>
                    <span class="border-top d-sm-none d-block" v-if="isLoggedIn"></span>
                    <a class="nav-link d-none d-sm-block" v-if="isLoggedIn">|</a>
                    <router-link :to="{ name: 'settings' }" class="nav-link" v-if="isLoggedIn" @click="collapseNavbar">
                        <font-awesome-icon :icon="['fas', 'fa-gear']" />
                        <span class="ms-1">{{ $t("navbar.settings") }}</span>
                    </router-link>
                    <a class="nav-link" href="#" v-if="isLoggedIn" @click="handleLogout">
                        <font-awesome-icon :icon="['fas', 'fa-sign-out-alt']" />
                        <span class="ms-1">{{ $t("navbar.logout") }}</span>
                    </a>
                    <!-- if is not logged in -->
                    <router-link :to="{ name: 'login' }" class="nav-link" v-if="!isLoggedIn" @click="collapseNavbar">
                        <font-awesome-icon :icon="['fas', 'fa-sign-in-alt']" />
                        <span class="ms-1">{{ $t("navbar.login") }}</span>
                    </router-link>
                </div>
            </div>
        </div>
    </nav>
    <div class="alert alert-warning alert-dismissible d-flex align-items-center mx-2 my-2 justify-content-center"
        role="alert">
        <font-awesome-icon :icon="['fas', 'triangle-exclamation']" />
        <div class="ms-2">
            <span>
                {{ $t("navbar.warningZone") }}
            </span>
        </div>
    </div>
</template>

<script>
import { watch, ref } from 'vue';
import { auth } from '@/services/auth';
import { useRouter, useRoute } from 'vue-router';

import UserAvatarComponent from './Users/UserAvatarComponent.vue';

export default {
    components: {
        UserAvatarComponent,
    },
    setup() {
        const router = useRouter()
        const route = useRoute()
        const path = ref(route.path)
        const isLoggedIn = ref(auth.isTokenValid(localStorage.getItem('accessToken')))
        const userMe = ref(JSON.parse(localStorage.getItem('userMe')))

        function handleLogout() {
            auth.removeLoggedUser()
            router.push('/login')
            collapseNavbar()
        }

        function updateVariablesBasedOnLocalStorage() {
            isLoggedIn.value = auth.isTokenValid(localStorage.getItem('accessToken'))
            userMe.value = JSON.parse(localStorage.getItem('userMe'))
        }

        function collapseNavbar() {
            const navbarToggler = document.querySelector('.navbar-toggler');
            const navbarCollapse = document.querySelector('#navbarNavAltMarkup');
            if (navbarToggler && navbarCollapse.classList.contains('show')) {
                navbarToggler.click();
            }
        }

        watch(() => route.path, (newPath, oldPath) => {
            path.value = newPath;
            // Perform actions based on newPath if needed
            if (newPath === '/login' && isLoggedIn.value) {
                updateVariablesBasedOnLocalStorage()
            }
            if (oldPath === '/login' && !isLoggedIn.value) {
                updateVariablesBasedOnLocalStorage()
            }
        });

        return {
            isLoggedIn,
            userMe,
            handleLogout,
            path,
            collapseNavbar,
        };
    },
};
</script>
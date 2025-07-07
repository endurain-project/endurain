<template>
    <nav class="navbar bg-body-tertiary text-center" v-if="authStore.isAuthenticated">
        <div class="container-fluid justify-content-around">
            <router-link :to="{ name: 'home' }" class="nav-link link-body-emphasis">
                <font-awesome-icon :icon="['fas', 'fa-home']" />
                <br>
                {{ $t("navbarBottomMobileComponent.home") }}
            </router-link>
            <router-link :to="{ name: 'gears' }" class="nav-link link-body-emphasis">
                <font-awesome-icon :icon="['fas', 'fa-bicycle']" />
                <br>
                {{ $t("navbarBottomMobileComponent.gear") }}
            </router-link>
            <router-link :to="{ name: 'health' }" class="nav-link link-body-emphasis">
                <font-awesome-icon :icon="['fas', 'fa-heart']" />
                <br>
                {{ $t("navbarBottomMobileComponent.health") }}
            </router-link>
            <router-link :to="{ name: 'notifications' }" class="nav-link link-body-emphasis">
                <span class="position-relative">
                    <font-awesome-icon :icon="['fas', 'fa-bell']" />
                    <span
                        class="position-absolute top-0 start-100 translate-middle p-1 bg-danger border border-light rounded-circle"
                        v-if="notificationsNotRead > 0">
                        <span class="visually-hidden">{{ notificationsNotRead }}</span>
                    </span>
                </span>
                <br />
                {{ $t('navbarBottomMobileComponent.alerts') }}
            </router-link>
            <router-link :to="{ name: 'menu' }" class="nav-link link-body-emphasis">
                <font-awesome-icon :icon="['fas', 'bars']" />
                <br>
                {{ $t("navbarBottomMobileComponent.menu") }}
            </router-link>
        </div>
    </nav>
    <FooterComponent v-else />
</template>

<script setup>
import { ref, onMounted, watch } from "vue";
import { useAuthStore } from "@/stores/authStore";
import FooterComponent from "@/components/FooterComponent.vue";

const notificationsNotRead = ref(12);
const authStore = useAuthStore();

onMounted(async () => {
    
});
</script>

<template>
    <div class="col-lg-4 col-md-12">
    <ul class="nav nav-pills flex-column mb-auto" id="sidebarNav">
        <li class="nav-item" v-if="authStore.user.access_type == 2">
            <a href="#" class="nav-link link-body-emphasis" :class="{ active: activeSection === 'users' }" @click.prevent="changeActive('users')">
                <font-awesome-icon :icon="['fas', 'fa-users']" />
                <span class="ms-1">{{ $t("settingsSideBar.usersSection") }}</span>
            </a>
        </li>
        <hr v-if="authStore.user.access_type == 2">
        <li class="nav-item">
            <a href="#" class="nav-link link-body-emphasis" :class="{ active: activeSection === 'general' }" @click.prevent="changeActive('general')">
                <font-awesome-icon :icon="['fas', 'gears']" />
                <span class="ms-1">{{ $t("settingsSideBar.generalSection") }}</span>
            </a>
        </li>
        <li class="nav-item">
            <a href="#" class="nav-link link-body-emphasis" :class="{ active: activeSection === 'myProfile' }" @click.prevent="changeActive('myProfile')">
                <font-awesome-icon :icon="['fas', 'fa-address-card']" />
                <span class="ms-1">{{ $t("settingsSideBar.myProfileSection") }}</span>
            </a>
        </li>
        <li class="nav-item">
            <a href="#" class="nav-link link-body-emphasis" :class="{ active: activeSection === 'security' }" @click.prevent="changeActive('security')">
                <font-awesome-icon :icon="['fas', 'fa-shield']" />
                <span class="ms-1">{{ $t("settingsSideBar.securitySection") }}</span>
            </a>
        </li>
        <li class="nav-item">
            <a href="#" class="nav-link link-body-emphasis" :class="{ active: activeSection === 'integrations' }" @click.prevent="changeActive('integrations')">
                <font-awesome-icon :icon="['fas', 'fa-puzzle-piece']" />
                <span class="ms-1">{{ $t("settingsSideBar.integrationsSection") }}</span>
            </a>
        </li>
    </ul>
</div>
<hr class="d-lg-none">
</template>

<script>
// Importing the store
import { useAuthStore } from '@/stores/authStore';

export default {
    props: {
        activeSection: {
            type: String,
            required: true,
        },
    },
    emits: ['update-active-section'],
    setup(props, { emit }) {
        const authStore = useAuthStore();

        function changeActive(section) {
            emit('update-active-section', section);
        }

        return {
            authStore,
            changeActive,
        };
    },
};
</script>
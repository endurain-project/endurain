<template>
    <div class="col-lg-4 col-md-12">
    <ul class="nav nav-pills flex-column mb-auto" id="sidebarNav">
        <li class="nav-item" v-if="userMe.access_type == 2">
            <a href="#" class="nav-link link-body-emphasis" :class="{ active: activeSection === 'divUsers' }" @click.prevent="changeActive('divUsers')">
                <font-awesome-icon :icon="['fas', 'fa-users']" />
                <span class="ms-1">{{ $t("settingsSideBar.usersSection") }}</span>
            </a>
        </li>
        <hr v-if="userMe.access_type == 2">
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
                <span class="ms-1">{{ $t("settingsSideBar.integratuionsSection") }}</span>
            </a>
        </li>
    </ul>
</div>
<hr class="d-lg-none">
</template>

<script>
import { useI18n } from 'vue-i18n';

export default {
    props: {
        activeSection: {
            type: String,
            required: true,
        },
    },
    emits: ['update-active-section'],
    setup(props, { emit }) {
        const userMe = JSON.parse(localStorage.getItem('userMe'));
        const { t } = useI18n();

        function changeActive(section) {
            emit('update-active-section', section);
        }

        return {
            userMe,
            t,
            changeActive,
        };
    },
};
</script>
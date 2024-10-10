<template>
    <div class="col-lg-3 col-md-12">
    <ul class="nav nav-pills flex-column mb-auto" id="sidebarNav">
        <!--<li class="nav-item">
            <a href="#" class="nav-link link-body-emphasis" :class="{ active: activeSection === 'dashboard' }" @click.prevent="changeActive('dashboard')">
                <font-awesome-icon :icon="['fas', 'dashboard']" />
                <span class="ms-1">{{ $t("healthSideBarComponent.dashboardSection") }}</span>
            </a>
        </li>
        <hr>-->
        <li class="nav-item">
            <a href="#" class="nav-link link-body-emphasis" :class="{ active: activeSection === 'weight' }" @click.prevent="changeActive('weight')">
                <font-awesome-icon :icon="['fas', 'weight']" />
                <span class="ms-1">{{ $t("healthSideBarComponent.weightSection") }}</span>
            </a>
        </li>
    </ul>
</div>
<hr class="d-lg-none">
</template>

<script>

export default {
    props: {
        activeSection: {
            type: String,
            required: true,
        },
    },
    emits: ['update-active-section'],
    setup(props, { emit }) {
        function changeActive(section) {
            emit('update-active-section', section);
        }

        return {
            changeActive,
        };
    },
};
</script>
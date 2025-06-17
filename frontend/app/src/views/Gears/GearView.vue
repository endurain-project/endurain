<template>
    <div v-if="isLoading">
        <LoadingComponent />
    </div>
    <h1 v-else>{{ gear?.nickname }}</h1>

    <div class="row row-gap-3 mt-4">
        <!-- left column -->
        <div class="col-lg-3 col-md-12">
            <div class="bg-body-tertiary p-3 rounded shadow-sm">
                <!-- Gear photo -->
                <div v-if="isLoading">
                    <LoadingComponent />
                </div>
                <div v-else>
                    <div class="justify-content-center align-items-center d-flex">
                        <img src="/src/assets/avatar/bicycle1.png" alt="Bicycle avatar" width="180" height="180" class="rounded-circle" v-if="gear?.gear_type == 1">
                        <img src="/src/assets/avatar/running_shoe1.png" alt="Bicycle avatar" width="180" height="180" class="rounded-circle" v-else-if="gear?.gear_type == 2">
                        <img src="/src/assets/avatar/wetsuit1.png" alt="Bicycle avatar" width="180" height="180" class="rounded-circle" v-else-if="gear?.gear_type == 3">
                        <img src="/src/assets/avatar/racquet1.png" alt="Bicycle avatar" width="180" height="180" class="rounded-circle" v-else-if="gear?.gear_type == 4">
                        <img src="/src/assets/avatar/skis1.png" alt="Bicycle avatar" width="180" height="180" class="rounded-circle" v-else-if="gear?.gear_type == 5">
                        <img src="/src/assets/avatar/snowboard1.png" alt="Bicycle avatar" width="180" height="180" class="rounded-circle" v-else>
                    </div>
                    <br>
                    <div class="vstack justify-content-center align-items-center d-flex">
                        <!-- badges  -->
                        <div class="hstack justify-content-center">
                            <span class="badge bg-success-subtle border border-success-subtle text-success-emphasis align-middle" v-if="gear?.is_active == 1">
                                {{ $t("gearView.gearIsActiveBadge") }}
                            </span>
                            <span class="badge bg-danger-subtle border border-danger-subtle text-danger-emphasis align-middle" v-else>
                                {{ $t("gearView.gearIsInactiveBadge") }}
                            </span>
                            <span class="ms-2 badge bg-primary-subtle border border-primary-subtle text-primary-emphasis align-middle" v-if="gear?.gear_type == 1">
                                {{ $t("gearView.gearTypeOption1") }}
                            </span>
                            <span class="ms-2 badge bg-primary-subtle border border-primary-subtle text-primary-emphasis align-middle" v-else-if="gear?.gear_type == 2">
                                {{ $t("gearView.gearTypeOption2") }}
                            </span>
                            <span class="ms-2 badge bg-primary-subtle border border-primary-subtle text-primary-emphasis align-middle" v-else-if="gear?.gear_type == 3">
                                {{ $t("gearView.gearTypeOption3") }}
                            </span>
                            <span class="ms-2 badge bg-primary-subtle border border-primary-subtle text-primary-emphasis align-middle" v-else-if="gear?.gear_type == 4">
                                {{ $t("gearView.gearTypeOption4") }}
                            </span>
                            <span class="ms-2 badge bg-primary-subtle border border-primary-subtle text-primary-emphasis align-middle" v-else-if="gear?.gear_type == 5">
                                {{ $t("gearView.gearTypeOption5") }}
                            </span>
                            <span class="ms-2 badge bg-primary-subtle border border-primary-subtle text-primary-emphasis align-middle" v-else>
                                {{ $t("gearView.gearTypeOption6") }}
                            </span>
                            <span class="ms-2 badge bg-primary-subtle border border-primary-subtle text-primary-emphasis align-middle" v-if="gear?.strava_gear_id">
                                {{ $t("gearView.gearFromStrava") }}
                            </span>
                            <span class="ms-2 badge bg-primary-subtle border border-primary-subtle text-primary-emphasis align-middle" v-if="gear?.garminconnect_gear_id">
                                {{ $t("gearView.gearFromGarminConnect") }}
                            </span>
                        </div>
                    </div>
                    <!-- edit gear zone -->
                    <button type="button" class="mt-2 w-100 btn btn-primary" data-bs-toggle="modal" :data-bs-target="`#editGearModal${gear?.id}`">
                        {{ $t("gearView.buttonEditGear") }}
                    </button>

                    <!-- edit gear modal -->
                    <GearsAddEditGearModalComponent :action="'edit'" :gear="gear" @editedGear="editGearList"/>

                    <button type="button" class="mt-2 w-100 btn btn-danger" data-bs-toggle="modal" data-bs-target="#deleteGearModal" >
                        {{ $t("gearView.buttonDeleteGear") }}
                    </button>

                    <!-- Modal delete gear -->
                    <ModalComponent modalId="deleteGearModal" :title="t('gearView.buttonDeleteGear')" :body="`${t('gearView.modalDeleteGearBody1')} <b>${gear?.nickname}</b>?<br>${t('gearView.modalDeleteGearBody2')}`" :actionButtonType="`danger`" :actionButtonText="t('gearView.buttonDeleteGear')" @submitAction="submitDeleteGear"/>

                    <!-- details  -->
                    <div class="vstack align-items-center">
                        <span class="mt-2" v-if="gear?.gear_type !== 4">
                            <strong>
                                {{ $t("gearView.labelDistance") }}:
                            </strong>
                            <span v-if="Number(authStore?.user?.units) === 1"> {{ gearDistance }} {{ $t("generalItems.unitsKm") }}</span>
                            <span v-else> {{ kmToMiles(gearDistance) }} {{ $t("generalItems.unitsMiles") }}</span>
                        </span>
                        <span class="mt-2" v-if="gear?.brand"><strong>{{ $t("gearView.labelBrand") }}:</strong> {{ gear?.brand }}</span>
                        <span class="mt-2" v-if="gear?.model"><strong>{{ $t("gearView.labelModel") }}:</strong> {{ gear?.model }}</span>
                    </div>
                </div>
            </div>
        </div>
        <div class="col-lg-5">
            <div v-if="isLoading">
                <LoadingComponent />
            </div>
            <div v-else class="bg-body-tertiary p-3 rounded shadow-sm">
                <h5>{{ $t("gearView.titleComponents") }}</h5>

                <NoItemsFoundComponent :showShadow="false" v-if="!gearComponents || (gearComponents && gearComponents.length == 0)"/>
                <div v-else>
                    <!-- List gears -->
                    <ul class="list-group list-group-flush" v-for="gearComponent in gearComponents" :key="gearComponent.id">
                        <GearComponentListComponent :gearActivities="gearActivities" :gearComponent="gearComponent" @gearComponentDeleted="updateGearComponentListOnDelete" />
                    </ul>
                </div>
            </div>
        </div>
        <div class="col">
            <div v-if="isLoading">
                <LoadingComponent />
            </div>
            <div v-else class="bg-body-tertiary p-3 rounded shadow-sm">
                <div class="hstack align-items-baseline">
                    <h5>
                        {{ $t("gearView.title") }}
                    </h5>
                    <h6 class="ms-1">
                        {{ $t("gearView.subtitle") }}
                    </h6>
                </div>

                <NoItemsFoundComponent :showShadow="false" v-if="!gearActivities || (gearActivities && gearActivities.length == 0)"/>
                <div v-else>
                    <ul class="list-group list-group-flush" v-for="activity in gearActivities" :key="activity.id" :activity="activity">
                        <li class="vstack list-group-item d-flex justify-content-between bg-body-tertiary ps-0">
                            <router-link :to="{ name: 'activity', params: { id: activity.id }}" class="link-body-emphasis link-underline-opacity-0 link-underline-opacity-100-hover">
                                {{ activity.name}}
                            </router-link>
                            <span>{{ formatDateMed(activity.start_time) }} @ {{ formatTime(activity.start_time) }}</span>
                        </li>
                    </ul>
                </div>
            </div>
        </div>

    </div>
   
    <!-- back button -->
    <BackButtonComponent />
</template>

<script setup>
import { ref, onMounted } from "vue";
import { useI18n } from "vue-i18n";
import { useRoute, useRouter } from "vue-router";
import { useAuthStore } from "@/stores/authStore";
import { push } from "notivue";
import NoItemsFoundComponent from "@/components/GeneralComponents/NoItemsFoundComponents.vue";
import LoadingComponent from "@/components/GeneralComponents/LoadingComponent.vue";
import BackButtonComponent from "@/components/GeneralComponents/BackButtonComponent.vue";
import ModalComponent from '@/components/Modals/ModalComponent.vue';
import GearsAddEditGearModalComponent from "@/components/Gears/GearsAddEditGearModalComponent.vue";
import GearComponentListComponent from "@/components/Gears/GearComponentListComponent.vue";
import { gears } from "@/services/gearsService";
import { gearsComponents } from "@/services/gearsComponentsService";
import { activities } from "@/services/activitiesService";
import { formatDateMed, formatTime } from "@/utils/dateTimeUtils";
import { kmToMiles } from "@/utils/unitsUtils";

const { t } = useI18n();
const authStore = useAuthStore();
const route = useRoute();
const router = useRouter();
const isLoading = ref(true);
const gear = ref(null);
const gearActivities = ref([]);
const gearDistance = ref(0);
const gearComponents = ref(null);

async function submitDeleteGear() {
    try {
        gear.value = await gears.deleteGear(route.params.id);
        return router.push({ path: "/gears", query: { gearDeleted: "true" } });
    } catch (error) {
        push.error(`${t("gearView.errorGearDelete")} - ${error}`);
    }
}

function editGearList(editedGear) {
    gear.value = editedGear;
}

function updateGearComponentListOnDelete(gearComponentDeletedId) {
    gearComponents.value = gearComponents.value.filter(
        (gearComponent) => gearComponent.id !== gearComponentDeletedId,
    );
}

onMounted(async () => {
    try {
        gear.value = await gears.getGearById(route.params.id);
        if (!gear.value) {
            return router.push({
                path: "/gears",
                query: { gearFound: "false", id: route.params.id },
            });
        }
        gearActivities.value = await activities.getUserActivitiesByGearId(
            route.params.id,
        );
        if (gearActivities.value) {
            for (const activity of gearActivities.value) {
                gearDistance.value += activity.distance;
            }
            gearDistance.value = (gearDistance.value / 1000).toFixed(2);
        }
        gearDistance.value = Math.floor(Number(gearDistance.value) + gear.value.initial_kms);

        gearComponents.value = await gearsComponents.getGearComponentsByGearId(route.params.id);
    } catch (error) {
        if (error.toString().includes("422")) {
            return router.push({
                path: "/gears",
                query: { gearFound: "false", id: route.params.id },
            });
        }
        push.error(`${t("gearView.errorFetchingGears")} - ${error}`);
    }
    isLoading.value = false;
});
</script>
<template>
    <li class="list-group-item d-flex justify-content-between px-0 bg-body-tertiary">
        <div class="d-flex align-items-center flex-grow-1">
            <img :src="getGearBikeComponentAvatar(gearComponent.type)" alt="snowboard avatar" width="55" height="55"
                class="rounded-circle" v-if="gear.gear_type === 1">
            <div class="ms-3 flex-grow-1">
                <div class="fw-bold">
                    <span v-if="gearComponent.brand">{{ gearComponent.brand }}</span>
                    <span class="ms-1" v-if="gearComponent.model">{{ gearComponent.model }}</span>
                </div>
                <span>{{ getGearBikeComponentType(gearComponent.type, t) }}</span>
                <span> @ {{ gearComponent.purchase_date }}</span>
                <span v-if="gearComponent.purchase_value"> - {{ gearComponent.purchase_value }}€ </span>
                <br>
                <span v-if="gearComponent.expected_kms">{{ formatDistanceRaw(gearComponentDistance,
                    authStore.user.units) }}{{ t('gearComponentListComponent.gearComponentOf') }}{{ formatDistanceRaw(gearComponent.expected_kms, authStore.user.units)
                    }}</span>
                <div class="progress" role="progressbar" aria-label="Gear component usage vs expected" :aria-valuenow="gearComponentDistancePercentage" aria-valuemin="0" aria-valuemax="100">
                    <div class="progress-bar" :style="{ width: gearComponentDistancePercentage + '%' }">{{ gearComponentDistancePercentage }}%</div>
                </div>
            </div>
        </div>
        <div>
            <!-- Button group for edit and delete -->
            <span class="d-flex">
                <!-- edit gear component button -->
                <a class="btn btn-link btn-lg link-body-emphasis" href="#" role="button"
                    data-bs-toggle="modal" :data-bs-target="`#editGearComponentModal${gearComponent.id}`"><font-awesome-icon
                        :icon="['fas', 'fa-pen-to-square']" /></a>

                <!-- delete gear component button -->
                <a class="btn btn-link btn-lg link-body-emphasis" href="#" role="button"
                    data-bs-toggle="modal"
                    :data-bs-target="`#deleteGearComponentModal${gearComponent.id}`"><font-awesome-icon
                        :icon="['fas', 'fa-trash-can']" /></a>
            </span>
            
            <div v-if="gearComponent.is_active == 0" class="d-flex justify-content-end">
                <span class="badge bg-danger-subtle border border-danger-subtle text-danger-emphasis">
                    {{ $t("gearComponentListComponent.gearComponentListGearComponentIsInactiveBadge") }}
                </span>
            </div>

            <!-- edit gear component modal -->
            <GearComponentAddEditModalComponent :action="'edit'" :gear="gear" :gearComponent="gearComponent" />

            <!-- delete gear component modal -->
            <ModalComponent :modalId="`deleteGearComponentModal${gearComponent.id}`"
                :title="t('gearComponentListComponent.gearComponentListModalDeleteGearComponentTitle')"
                :body="`${t('gearComponentListComponent.gearComponentListModalDeleteGearComponentBody')}<b>${gearComponent.id}</b>?`"
                :actionButtonType="`danger`"
                :actionButtonText="t('gearComponentListComponent.gearComponentListModalDeleteGearComponentTitle')"
                @submitAction="submitDeleteGearComponent" />
        </div>
    </li>
</template>

<script setup>
import { onMounted, ref } from "vue";
import { useI18n } from "vue-i18n";
import { gearsComponents } from '@/services/gearsComponentsService';
import { push } from "notivue";
import { formatDistanceRaw } from "@/utils/activityUtils";
import { useAuthStore } from "@/stores/authStore";
import { getGearBikeComponentType, getGearBikeComponentAvatar } from "@/utils/gearComponentsUtils";
import ModalComponent from "@/components/Modals/ModalComponent.vue";
import GearComponentAddEditModalComponent from "@/components/Gears/GearComponentAddEditModalComponent.vue";
const props = defineProps({
    gear: {
        type: Object,
        required: true,
    },
    gearComponent: {
        type: Object,
        required: true,
    },
    gearActivities: {
        type: [Array, null],
        required: true,
    },
});

const { t } = useI18n();
const authStore = useAuthStore();
const gearComponentDistance = ref(0);
const gearComponentDistancePercentage = ref(0);

const emit = defineEmits(["gearComponentDeleted"]);

async function submitDeleteGearComponent() {
    try {
        await gearsComponents.deleteGearComponent(props.gearComponent.id);
        emit("gearComponentDeleted", props.gearComponent.id);
        push.success(t("gearComponentListComponent.gearComponentListGearDeleteSuccessMessage"));
    } catch (error) {
        push.error(
            `${t("gearComponentListComponent.gearComponentListGearDeleteErrorMessage")} - ${error}`,
        );
    }
}

onMounted(() => {
    if (props.gearActivities && props.gearActivities && props.gearActivities.length > 0) {
        props.gearActivities.forEach(activity => {
            if (
                activity.start_time &&
                props.gearComponent.purchase_date &&
                new Date(activity.start_time) > new Date(props.gearComponent.purchase_date)
            ) {
                gearComponentDistance.value += Number(activity.distance) || 0;
            }
        });
        gearComponentDistancePercentage.value = Math.round(
            (gearComponentDistance.value / props.gearComponent.expected_kms) * 100
        );
    }
});
</script>
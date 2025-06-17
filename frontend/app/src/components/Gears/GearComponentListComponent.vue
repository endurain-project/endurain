<template>
    <li class="list-group-item d-flex justify-content-between px-0 bg-body-tertiary">
        <div class="d-flex align-items-center">
            <img :src="getGearComponentAvatar(gearComponent.type)" alt="snowboard avatar" width="55" height="55"
                class="rounded-circle">
            <div class="ms-3">
                <div class="fw-bold">
                    <span v-if="gearComponent.brand">{{ gearComponent.brand }}</span>
                    <span class="ms-1" v-if="gearComponent.model">{{ gearComponent.model }}</span>
                </div>
                <span>{{ getGearComponentType(gearComponent.type, t) }}</span>
                <span> @ {{ gearComponent.purchase_date }}</span>
                <span v-if="gearComponent.purchase_value"> - {{ gearComponent.purchase_value }}€ </span>
                <br>
                <span v-if="gearComponent.expected_kms">{{ formatDistanceRaw(gearComponentDistance,
                    authStore.user.units) }}{{ t('gearComponentListComponent.gearComponentOf') }}{{ formatDistanceRaw(gearComponent.expected_kms, authStore.user.units)
                    }}</span>
            </div>
        </div>
        <div>
            <span
                class="badge bg-danger-subtle border border-danger-subtle text-danger-emphasis align-middle d-none d-md-inline me-4"
                v-if="gearComponent.is_active == 0">{{
                    $t("gearComponentListComponent.gearComponentListGearComponentIsInactiveBadge") }}
            </span>

            <!-- delete gear button -->
            <a class="btn btn-link btn-lg link-body-emphasis d-none d-sm-inline" href="#" role="button"
                data-bs-toggle="modal"
                :data-bs-target="`#deleteGearComponentModal${gearComponent.id}`"><font-awesome-icon
                    :icon="['fas', 'fa-trash-can']" /></a>

            <!-- delete gear modal -->
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
import { getGearComponentType, getGearComponentAvatar } from "@/utils/gearComponentsUtils";
import ModalComponent from "@/components/Modals/ModalComponent.vue";

const props = defineProps({
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
    }
});
</script>
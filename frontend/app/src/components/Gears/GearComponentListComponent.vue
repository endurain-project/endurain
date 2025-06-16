<template>
    <li class="list-group-item d-flex justify-content-between px-0 bg-body-tertiary">
        <div class="d-flex align-items-center">
            {{ gearComponent }}
        </div>
        <div>
            <span
                class="badge bg-danger-subtle border border-danger-subtle text-danger-emphasis align-middle d-none d-md-inline me-4"
                v-if="gearComponent.is_active == 0">{{ $t("gearComponentListComponent.gearListGearComponentIsInactiveBadge") }}
            </span>

            <!-- delete gear button -->
            <a class="btn btn-link btn-lg link-body-emphasis d-none d-sm-inline" href="#" role="button"
                data-bs-toggle="modal" :data-bs-target="`#deleteGearComponentModal${gearComponent.id}`"><font-awesome-icon
                    :icon="['fas', 'fa-trash-can']" /></a>

            <!-- delete gear modal -->
            <ModalComponent :modalId="`deleteGearComponentModal${gearComponent.id}`"
                :title="t('gearComponentListComponent.gearListModalDeleteGearComponentTitle')"
                :body="`${t('gearComponentListComponent.gearListModalDeleteGearComponentBody')}<b>${gearComponent.id}</b>?`"
                :actionButtonType="`danger`" :actionButtonText="t('gearComponentListComponent.gearListModalDeleteGearComponentTitle')"
                @submitAction="submitDeleteGearComponent" />
        </div>
    </li>
</template>

<script setup>
import { useI18n } from "vue-i18n";
import { gearsComponents } from '@/services/gearsComponentsService';
import { push } from "notivue";
import ModalComponent from "@/components/Modals/ModalComponent.vue";

const props = defineProps({
    gearComponent: {
        type: Object,
        required: true,
    },
});

const { t } = useI18n();

const emit = defineEmits(["gearComponentDeleted"]);

async function submitDeleteGearComponent() {
    try {
        await gearsComponents.deleteGearComponent(props.gearComponent.id);
        emit("gearComponentDeleted", props.gearComponent.id);
        push.success(t("gearComponentListComponent.gearListGearDeleteSuccessMessage"));
    } catch (error) {
        push.error(
            `${t("gearComponentListComponent.gearListGearDeleteErrorMessage")} - ${error}`,
        );
    }
}


</script>
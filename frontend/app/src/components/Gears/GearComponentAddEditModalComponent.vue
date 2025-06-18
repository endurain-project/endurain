<template>
    <div class="modal fade"
        :id="action === 'add' ? 'addGearComponentModal' : (action === 'edit' ? editGearComponentModalId : null)"
        tabindex="-1"
        :aria-labelledby="action === 'add' ? 'addGearComponentModal' : (action === 'edit' ? editGearComponentModalId : null)"
        ref="addEditGearComponentModal" aria-hidden="true">
        <div class="modal-dialog">
            <div class="modal-content">
                <div class="modal-header">
                    <h1 class="modal-title fs-5" id="addGearComponentModal" v-if="action === 'add'">{{
                        $t("gearComponentAddEditModalComponent.addEditGearComponentModalAddTitle") }}</h1>
                    <h1 class="modal-title fs-5" :id='editGearComponentModalId' v-else>{{
                        $t("gearComponentAddEditModalComponent.addEditGearComponentModalEditTitle") }}</h1>
                    <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
                </div>
                <form @submit.prevent="handleSubmit">
                    <div class="modal-body">
                        <!-- gear component type -->
                        <label for="gearComponentTypeAddEdit"><b>* {{
                            $t("gearComponentAddEditModalComponent.addEditGearComponentModalAddTypeLabel")
                                }}</b></label>
                        <select class="form-select" name="gearComponentTypeAddEdit" v-model="newEditGearComponentType"
                            required>
                            <option v-for="type in GEAR_BIKE_COMPONENT_TYPES" :key="type" :value="type">
                                {{ getGearBikeComponentType(type, t) }}
                            </option>
                        </select>
                        <!-- brand fields -->
                        <label for="gearComponentBrandAddEdit"><b>* {{
                            $t("gearComponentAddEditModalComponent.addEditGearComponentModalAddBrandLabel")
                                }}</b></label>
                        <input class="form-control" type="text" name="gearComponentBrandAddEdit"
                            :placeholder='$t("gearComponentAddEditModalComponent.addEditGearComponentModalAddBrandLabel")'
                            v-model="newEditGearComponentBrand" maxlength="250">
                        <!-- model fields -->
                        <label for="gearComponentModelAddEdit"><b>* {{
                            $t("gearComponentAddEditModalComponent.addEditGearComponentModalAddModelLabel")
                                }}</b></label>
                        <input class="form-control" type="text" name="gearComponentModelAddEdit"
                            :placeholder='$t("gearComponentAddEditModalComponent.addEditGearComponentModalAddModelLabel")'
                            v-model="newEditGearComponentModel" maxlength="250">
                        <!-- purchase date fields -->
                        <label for="gearComponentPurchaseDateAddEdit"><b>* {{
                            $t("gearComponentAddEditModalComponent.addEditGearComponentModalAddPurchaseDateLabel")
                                }}</b></label>
                        <input class="form-control" type="date" name="gearComponentPurchaseDateAddEdit"
                            v-model="newEditGearComponentPurchaseDate" required>
                        <!-- expected distance -->
                        <label for="gearComponentExpectedDistanceAddEdit"><b>{{
                            $t("gearComponentAddEditModalComponent.addEditGearComponentModalAddEditExpectedDistanceLabel")
                                }}</b></label>
                        <div class="input-group">
                            <input class="form-control" type="number" name="gearComponentExpectedDistanceAddEdit"
                                :placeholder='$t("gearComponentAddEditModalComponent.addEditGearComponentModalAddEditExpectedDistanceLabel")'
                                v-model="newEditGearComponentExpectedDistance" min="0" max="100000" step="1">
                        </div>
                        <!-- purchase value -->
                        <label for="gearComponentPurchaseValueAddEdit"><b>{{ $t("gearComponentAddEditModalComponent.addEditGearComponentModalAddPurchaseValueLabel") }}</b></label>
                        <div class="input-group">
                            <input class="form-control" type="number" name="addEditGearComponentModalAddEditPurchaseValueLabel"
                                :placeholder='$t("gearComponentAddEditModalComponent.addEditGearComponentModalAddPurchaseValueLabel")'
                                v-model="newEditGearComponentPurchaseValue" min="0" max="100000" step="0.01" inputmode="decimal">
                        </div>

                        <p>* {{ $t("generalItems.requiredField") }}</p>
                    </div>
                    <div class="modal-footer">
                        <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">{{
                            $t("generalItems.buttonClose") }}
                        </button>
                        <button type="submit" class="btn btn-success" name="addGearComponent" data-bs-dismiss="modal"
                            v-if="action === 'add'">{{
                                $t("gearComponentAddEditModalComponent.addEditGearComponentModalAddTitle") }}
                        </button>
                        <button type="submit" class="btn btn-success" name="editGearComponent" data-bs-dismiss="modal"
                            v-else>{{
                                $t("gearComponentAddEditModalComponent.addEditGearComponentModalEditTitle") }}
                        </button>
                    </div>
                </form>
            </div>
        </div>
    </div>
</template>

<script setup>
import { ref, onMounted } from "vue";
import { useI18n } from "vue-i18n";
import { GEAR_BIKE_COMPONENT_TYPES, getGearBikeComponentType } from "@/utils/gearComponentsUtils";

const { t } = useI18n();

const props = defineProps({
    action: {
        type: String,
        required: true,
    },
    gear: {
        type: Object,
        required: true,
    },
    gearComponent: {
        type: Object,
        required: false,
    },
});

const newEditGearComponentType = ref("back_break_oil");
const editGearComponentModalId = ref("");
const newEditGearComponentUserId = ref(props.gear.user_id);
const newEditGearComponentGearId = ref(props.gear.id);
const newEditGearComponentBrand = ref(null);
const newEditGearComponentModel = ref(null);
const newEditGearComponentPurchaseDate = ref(new Date().toISOString().split('T')[0]);
const newEditGearComponentExpectedDistance = ref(null);
const newEditGearComponentPurchaseValue = ref(null);

onMounted(() => {
    if (props.gearComponent) {
        if (props.action === 'edit') {
            editGearComponentModalId.value = `editGearComponentModal${props.gearComponent.id}`;
        }
        newEditGearComponentType.value = props.gearComponent.type;
        newEditGearComponentBrand.value = props.gearComponent.brand;
        newEditGearComponentModel.value = props.gearComponent.model;
        newEditGearComponentPurchaseDate.value = props.gearComponent.purchase_date;
        newEditGearComponentExpectedDistance.value = props.gearComponent.expected_kms || null;
        newEditGearComponentPurchaseValue.value = props.gearComponent.purchase_value || null;
    }
});

</script>
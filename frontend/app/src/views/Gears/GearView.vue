<template>
    <div v-if="isLoading">
        <LoadingComponent />
    </div>
    <h1 v-else>{{ gear?.nickname }}</h1>

    <div class="row row-gap-3 mt-4">
        <!-- left column -->
        <div class="col-lg-3 col-md-12">
             <!-- Gear photo -->
             <div v-if="isLoading">
                <LoadingComponent />
            </div>
            <div v-else>
                <div class="justify-content-center align-items-center d-flex">
                    <img src="/src/assets/avatar/bicycle1.png" alt="Bycicle avatar" width="180" height="180" v-if="gear?.gear_type == 1">
                    <img src="/src/assets/avatar/running_shoe1.png" alt="Bycicle avatar" width="180" height="180" v-else-if="gear?.gear_type == 2">
                    <img src="/src/assets/avatar/wetsuit1.png" alt="Bycicle avatar" width="180" height="180" v-else>
                </div>
                <br>
                <div class="vstack justify-content-center align-items-center d-flex">
                    <!-- badges  -->
                    <div class="hstack justify-content-center">
                        <span class="badge bg-success-subtle border border-success-subtle text-success-emphasis align-middle" v-if="gear?.is_active == 1">
                            {{ $t("gears.activeState") }}
                        </span>
                        <span class="badge bg-danger-subtle border border-danger-subtle text-danger-emphasis align-middle" v-else>
                            {{ $t("gears.inactiveState") }}
                        </span>
                        <span class="ms-2 badge bg-primary-subtle border border-primary-subtle text-primary-emphasis align-middle" v-if="gear?.gear_type == 1">
                            {{ $t("gears.gearTypeOption1") }}
                        </span>
                        <span class="ms-2 badge bg-primary-subtle border border-primary-subtle text-primary-emphasis align-middle" v-else-if="gear?.gear_type == 2">
                            {{ $t("gears.gearTypeOption2") }}
                        </span>
                        <span class="ms-2 badge bg-primary-subtle border border-primary-subtle text-primary-emphasis align-middle" v-else>
                            {{ $t("gears.gearTypeOption3") }}
                        </span>
                        <span class="ms-2 badge bg-primary-subtle border border-primary-subtle text-primary-emphasis align-middle" v-if="gear?.strava_gear_id">
                            {{ $t("gears.gearFromStrava") }}
                        </span>
                    </div>
                </div>
                <!-- edit gear zone -->
                <button type="button" class="mt-2 w-100 btn btn-primary" :disabled="gear && gear?.strava_gear_id" data-bs-toggle="modal" data-bs-target="#editGearModal">
                    {{ $t("gear.buttonEditGear") }}
                </button>

                <!-- Modal edit gear -->
                <div class="modal fade" id="editGearModal" tabindex="-1" aria-labelledby="editGearModal"
                    aria-hidden="true">
                    <div class="modal-dialog">
                        <div class="modal-content">
                            <div class="modal-header">
                                <h1 class="modal-title fs-5" id="editGearModal">
                                    {{ $t("gear.buttonEditGear") }}
                                </h1>
                            </div>
                            <form @submit.prevent="submitEditGearForm">
                                <div class="modal-body">
                                    <!-- brand fields -->
                                    <label for="gearBrandEdit"><b>{{ $t("gears.modalBrand") }}:</b></label>
                                    <input class="form-control" type="text" name="gearBrandEdit" :placeholder='$t("gears.modalBrand")' v-model="brand" maxlength="250">
                                    <!-- model fields -->
                                    <label for="gearModelEdit"><b>{{ $t("gears.modalModel") }}:</b></label>
                                    <input class="form-control" type="text" name="gearModelEdit" :placeholder='$t("gears.modalModel")' v-model="model" maxlength="250">
                                    <!-- nickname fields -->
                                    <label for="gearNicknameEdit"><b>* {{ $t("gears.modalNickname") }}:</b></label>
                                    <input class="form-control" type="text" name="gearNicknameEdit" :placeholder='$t("gears.modalNickname")' v-model="nickname" maxlength="250" required>
                                    <!-- gear type fields -->
                                    <label for="gearTypeEdit"><b>* {{ $t("gears.modalGearTypeLabel") }}:</b></label>
                                    <select class="form-control" name="gearTypeEdit" v-model="gearType" required>
                                        <option value="1">{{ $t("gears.modalGearTypeOption1Bike") }}</option>
                                        <option value="2">{{ $t("gears.modalGearTypeOption2Shoes") }}</option>
                                        <option value="3">{{ $t("gears.modalGearTypeOption3Wetsuit") }}</option>
                                    </select>
                                    <!-- date fields -->
                                    <label for="gearDateEdit"><b>* {{ $t("gears.modalDateLabel") }}:</b></label>
                                    <input class="form-control" type="date" name="gearDateEdit" :placeholder='$t("gears.modalDatePlaceholder")' v-model="date" required>
                                    <!-- gear is_active fields -->
                                    <label for="gearIsActiveEdit"><b>* {{ $t("gear.modalEditGearIsActiveLabel") }}:</b></label>
                                    <select class="form-control" name="gearIsActiveEdit" v-model="isActive" required>
                                        <option value="1">{{ $t("gear.modalEditGearIsActiveOption1") }}</option>
                                        <option value="0">{{ $t("gear.modalEditGearIsActiveOption0") }}</option>
                                    </select>
                                    <p>* {{ $t("generalItens.requiredField") }}</p>
                                </div>
                                <div class="modal-footer">
                                    <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">{{ $t("generalItens.buttonClose") }}</button>
                                    <button type="submit" class="btn btn-success" name="editGear" data-bs-dismiss="modal">{{ $t("gear.buttonEditGear") }}</button>
                                </div>
                            </form>
                        </div>
                    </div>
                </div>

                <button type="button" class="mt-2 w-100 btn btn-danger" :disabled="(gear && gear?.strava_gear_id) || (gearActivities && gearActivities.length != 0)" data-bs-toggle="modal" data-bs-target="#deleteGearModal" >
                    {{ $t("gear.buttonDeleteGear") }}
                </button>
                <!--<a class="mt-2 w-100 btn btn-danger" :class="{ 'disabled': gear && gear.strava_gear_id }" href="#" role="button" data-bs-toggle="modal" data-bs-target="#deleteGearModal" :aria-disabled="gearActivities && gearActivities.length != 0 ? 'true' : 'false'" @click.prevent="gear && gear.strava_gear_id || (gearActivities && gearActivities.length != 0) ? null : openDeleteModal()">
                    {{ $t("gear.buttonDeleteGear") }}
                </a>-->

                <!-- Modal delete gear -->
                <div class="modal fade" id="deleteGearModal" tabindex="-1" aria-labelledby="deleteGearModal"
                    aria-hidden="true">
                    <div class="modal-dialog">
                        <div class="modal-content">
                            <div class="modal-header">
                                <h1 class="modal-title fs-5" id="deleteGearModal">
                                    {{ $t("gear.buttonDeleteGear") }}
                                </h1>
                            </div>
                            <div class="modal-body">
                                <span>{{ $t("gear.modalDeleteGearBody1") }} <b>
                                    {{ gear?.nickname }}
                                </b>?</span>
                                <br>
                                <span>{{ $t("gear.modalDeleteGearBody2") }}</span>
                            </div>
                            <div class="modal-footer">
                                <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">{{ $t("generalItens.buttonClose") }}</button>
                                <button @click="submitDeleteGear" type="button" class="btn btn-danger" data-bs-dismiss="modal">
                                    {{ $t("gear.buttonDeleteGear") }}
                                </button>
                            </div>
                        </div>
                    </div>
                </div>

                <!-- details  -->
                <div class="vstack align-items-center">
                    <span class="mt-2"><strong>{{ $t("gear.labelDistance") }}:</strong> {{ gearDistance }} km</span>
                    <span class="mt-2" v-if="gear?.brand"><strong>{{ $t("gears.modalBrand") }}:</strong> {{ gear?.brand }}</span>
                    <span class="mt-2" v-if="gear?.model"><strong>{{ $t("gears.modalModel") }}:</strong> {{ gear?.model }}</span>
                </div>
            </div>
        </div>
        
        <div class="col">
            <div v-if="isLoading">
                <LoadingComponent />
            </div>
            <div v-else>
                <hr class="mb-2 mt-2 d-sm-none d-block">
                <div class="hstack align-items-baseline">
                    <h5>
                        {{ $t("gear.title") }}
                    </h5>
                    <h6 class="ms-1">
                        {{ $t("gear.subtitle") }}
                    </h6>
                </div>
                <NoItemsFoundComponent v-if="!gearActivities || (gearActivities && gearActivities.length == 0)"/>
                <div v-else>
                    <ul class="list-group list-group-flush" v-for="activity in gearActivities" :key="activity.id" :activity="activity">
                        <li class="vstack list-group-item d-flex justify-content-between">
                            <router-link :to="{ name: 'activity', params: { id: activity.id }}" class="link-body-emphasis link-underline-opacity-0 link-underline-opacity-100-hover">
                                {{ activity.name}}
                            </router-link>
                            <span><strong>{{ $t("gear.labelDate") }}:</strong> {{ formatDate(activity.start_time) }} @ {{ formatTime(activity.start_time) }}</span>
                        </li>
                    </ul>
                </div>
            </div>
        </div>

    </div>
   
    <!-- back button -->
    <BackButtonComponent />
</template>

<script>
// Importing the vue composition API
import { ref, onMounted } from 'vue';
import { useI18n } from 'vue-i18n';
import { useRoute, useRouter } from 'vue-router';
// Importing the utils
import { addToast } from '@/utils/toastUtils';
// Import the stores
import { useAuthStore } from '@/stores/authStore';
// Importing the components
import NoItemsFoundComponent from '@/components/GeneralComponents/NoItemsFoundComponents.vue';
import LoadingComponent from '@/components/GeneralComponents/LoadingComponent.vue';
import BackButtonComponent from '@/components/GeneralComponents/BackButtonComponent.vue';
// Importing the services
import { gears } from '@/services/gearsService';
import { activities } from '@/services/activitiesService';
import { formatDate, formatTime } from '@/utils/dateTimeUtils';

export default {
    components: {
        NoItemsFoundComponent,
        LoadingComponent,
        BackButtonComponent,
    },
    setup() {
        const { t } = useI18n();
        const route = useRoute();
        const router = useRouter();
        const isLoading = ref(true);
        const gear = ref(null);
        const gearActivities = ref([]);
        const gearDistance = ref(0);
        const brand = ref('');
        const model = ref('');
        const nickname = ref('');
        const gearType = ref(1);
        const date = ref(null);
        const isActive = ref(1);

        async function submitEditGearForm() {
            try {
                const data = {
                    brand: brand.value,
                    model: model.value,
                    nickname: nickname.value,
                    gear_type: gearType.value,
                    created_at: date.value,
                    is_active: isActive.value,
                };

                await gears.editGear(route.params.id, data);

                gear.value.brand = brand.value;
                gear.value.model = model.value;
                gear.value.nickname = nickname.value;
                gear.value.gear_type = gearType.value;
                gear.value.created_at = date.value;
                gear.value.is_active = isActive.value;
                
                addToast(t('gear.successGearEdited'), 'success', true);
            } catch (error) {
                // If there is an error, set the error message and show the error alert.
                addToast(t('generalItens.errorEditingInfo') + " - " + error.toString(), 'danger', true);
            }
        }

        async function submitDeleteGear() {
            try {
                gear.value = await gears.deleteGear(route.params.id);
                router.push({ path: '/gears', query: { gearDeleted: 'true' } });
            } catch (error) {
                addToast(t('generalItens.errorEditingInfo') + " - " + error.toString(), 'danger', true);
            }
        }
        
        onMounted(async () => {
            try {
                // Fetch the gear by its id.
                gear.value = await gears.getGearById(route.params.id);
                if (!gear.value) {
                    router.push({ path: '/gears', query: { gearFound: 'false', id: route.params.id } });
                }
                gearActivities.value = await activities.getUserActivitiesByGearId(route.params.id);
                if (gearActivities.value) {
                    for (const activity of gearActivities.value) {
                        gearDistance.value += activity.distance;
                    }
                    gearDistance.value = (gearDistance.value / 1000).toFixed(2)
                }
                brand.value = gear.value.brand;
                model.value = gear.value.model;
                nickname.value = gear.value.nickname;
                gearType.value = gear.value.gear_type;
                date.value = gear.value.created_at.split(' ')[0];;
                isActive.value = gear.value.is_active;
            } catch (error) {
                if (error.toString().includes('422')) {
                    router.push({ path: '/gears', query: { gearFound: 'false', id: route.params.id } });
                }
                // If there is an error, set the error message and show the error alert.
                addToast(t('generalItens.errorEditingInfo') + " - " + error.toString(), 'danger', true);
            }

            isLoading.value = false;
        });

        return{
            brand,
            model,
            nickname,
            gearType,
            date,
            isActive,
            isLoading,
            gear,
            gearActivities,
            gearDistance,
            t,
            submitEditGearForm,
            submitDeleteGear,
            formatDate,
            formatTime,
        }
    },
};

</script>
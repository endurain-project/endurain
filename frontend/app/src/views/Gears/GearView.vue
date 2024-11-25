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
                    <img src="/src/assets/avatar/bicycle1.png" alt="Bicycle avatar" width="180" height="180" v-if="gear?.gear_type == 1">
                    <img src="/src/assets/avatar/running_shoe1.png" alt="Bicycle avatar" width="180" height="180" v-else-if="gear?.gear_type == 2">
                    <img src="/src/assets/avatar/wetsuit1.png" alt="Bicycle avatar" width="180" height="180" v-else>
                </div>
                <br>
                <div class="vstack justify-content-center align-items-center d-flex">
                    <!-- badges  -->
                    <div class="hstack justify-content-center">
                        <span class="badge bg-success-subtle border border-success-subtle text-success-emphasis align-middle" v-if="gear?.is_active == 1">
                            {{ $t("gearsView.activeState") }}
                        </span>
                        <span class="badge bg-danger-subtle border border-danger-subtle text-danger-emphasis align-middle" v-else>
                            {{ $t("gearsView.inactiveState") }}
                        </span>
                        <span class="ms-2 badge bg-primary-subtle border border-primary-subtle text-primary-emphasis align-middle" v-if="gear?.gear_type == 1">
                            {{ $t("gearsView.gearTypeOption1") }}
                        </span>
                        <span class="ms-2 badge bg-primary-subtle border border-primary-subtle text-primary-emphasis align-middle" v-else-if="gear?.gear_type == 2">
                            {{ $t("gearsView.gearTypeOption2") }}
                        </span>
                        <span class="ms-2 badge bg-primary-subtle border border-primary-subtle text-primary-emphasis align-middle" v-else>
                            {{ $t("gearsView.gearTypeOption3") }}
                        </span>
                        <span class="ms-2 badge bg-primary-subtle border border-primary-subtle text-primary-emphasis align-middle" v-if="gear?.strava_gear_id">
                            {{ $t("gearsView.gearFromStrava") }}
                        </span>
                        <span class="ms-2 badge bg-primary-subtle border border-primary-subtle text-primary-emphasis align-middle" v-if="gear?.garminconnect_gear_id">
                            {{ $t("gearsView.gearFromGarminConnect") }}
                        </span>
                    </div>
                </div>
                <!-- edit gear zone -->
                <button type="button" class="mt-2 w-100 btn btn-primary" data-bs-toggle="modal" data-bs-target="#editGearModal">
                    {{ $t("gearView.buttonEditGear") }}
                </button>

                <!-- Modal edit gear -->
                <div class="modal fade" id="editGearModal" tabindex="-1" aria-labelledby="editGearModal"
                    aria-hidden="true">
                    <div class="modal-dialog">
                        <div class="modal-content">
                            <div class="modal-header">
                                <h1 class="modal-title fs-5" id="editGearModal">
                                    {{ $t("gearView.buttonEditGear") }}
                                </h1>
                            </div>
                            <form @submit.prevent="submitEditGearForm">
                                <div class="modal-body">
                                    <!-- brand fields -->
                                    <label for="gearBrandEdit"><b>{{ $t("gearsView.modalBrand") }}</b></label>
                                    <input class="form-control" type="text" name="gearBrandEdit" :placeholder='$t("gearsView.modalBrand")' v-model="brand" maxlength="250">
                                    <!-- model fields -->
                                    <label for="gearModelEdit"><b>{{ $t("gearsView.modalModel") }}</b></label>
                                    <input class="form-control" type="text" name="gearModelEdit" :placeholder='$t("gearsView.modalModel")' v-model="model" maxlength="250">
                                    <!-- nickname fields -->
                                    <label for="gearNicknameEdit"><b>* {{ $t("gearsView.modalNickname") }}</b></label>
                                    <input class="form-control" type="text" name="gearNicknameEdit" :placeholder='$t("gearsView.modalNickname")' v-model="nickname" maxlength="250" required>
                                    <!-- gear type fields -->
                                    <label for="gearTypeEdit"><b>* {{ $t("gearsView.modalGearTypeLabel") }}</b></label>
                                    <select class="form-control" name="gearTypeEdit" v-model="gearType" required>
                                        <option value="1">{{ $t("gearsView.modalGearTypeOption1Bike") }}</option>
                                        <option value="2">{{ $t("gearsView.modalGearTypeOption2Shoes") }}</option>
                                        <option value="3">{{ $t("gearsView.modalGearTypeOption3Wetsuit") }}</option>
                                    </select>
                                    <!-- date fields -->
                                    <label for="gearDateEdit"><b>* {{ $t("gearsView.modalDateLabel") }}:</b></label>
                                    <input class="form-control" type="date" name="gearDateEdit" :placeholder='$t("gearsView.modalDatePlaceholder")' v-model="date" required>
                                    <!-- gear is_active fields -->
                                    <label for="gearIsActiveEdit"><b>* {{ $t("gearView.modalEditGearIsActiveLabel") }}</b></label>
                                    <select class="form-control" name="gearIsActiveEdit" v-model="isActive" required>
                                        <option value="1">{{ $t("gearView.modalEditGearIsActiveOption1") }}</option>
                                        <option value="0">{{ $t("gearView.modalEditGearIsActiveOption0") }}</option>
                                    </select>
                                    <!-- initial kilometers fields -->
                                    <label for="gearInitialKmsEdit"><b>* {{ $t("gearView.modalEditGearInitialKmsLabel") }}</b></label>
                                    <input class="form-control" type="number" step="0.2" name="gearInitialKmsEdit" v-model="initialKms" required>
                                    <p>* {{ $t("generalItems.requiredField") }}</p>
                                </div>
                                <div class="modal-footer">
                                    <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">{{ $t("generalItems.buttonClose") }}</button>
                                    <button type="submit" class="btn btn-success" name="editGear" data-bs-dismiss="modal">{{ $t("gearView.buttonEditGear") }}</button>
                                </div>
                            </form>
                        </div>
                    </div>
                </div>

                <button type="button" class="mt-2 w-100 btn btn-danger" data-bs-toggle="modal" data-bs-target="#deleteGearModal" >
                    {{ $t("gearView.buttonDeleteGear") }}
                </button>

                <!-- Modal delete gear -->
                <ModalComponent modalId="deleteGearModal" :title="t('gearView.buttonDeleteGear')" :body="`${t('gearView.modalDeleteGearBody1')} <b>${gear?.nickname}</b>?<br>${t('gearView.modalDeleteGearBody2')}`" :actionButtonType="`danger`" :actionButtonText="t('gearView.buttonDeleteGear')" @submitAction="submitDeleteGear"/>

                <!-- details  -->
                <div class="vstack align-items-center">
                    <span class="mt-2"><strong>{{ $t("gearView.labelDistance") }}:</strong> {{ gearDistance }} km</span>
                    <span class="mt-2" v-if="gear?.brand"><strong>{{ $t("gearsView.modalBrand") }}:</strong> {{ gear?.brand }}</span>
                    <span class="mt-2" v-if="gear?.model"><strong>{{ $t("gearsView.modalModel") }}:</strong> {{ gear?.model }}</span>
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
                        {{ $t("gearView.title") }}
                    </h5>
                    <h6 class="ms-1">
                        {{ $t("gearView.subtitle") }}
                    </h6>
                </div>
                <NoItemsFoundComponent v-if="!gearActivities || (gearActivities && gearActivities.length == 0)"/>
                <div v-else>
                    <ul class="list-group list-group-flush" v-for="activity in gearActivities" :key="activity.id" :activity="activity">
                        <li class="vstack list-group-item d-flex justify-content-between">
                            <router-link :to="{ name: 'activity', params: { id: activity.id }}" class="link-body-emphasis link-underline-opacity-0 link-underline-opacity-100-hover">
                                {{ activity.name}}
                            </router-link>
                            <span><strong>{{ $t("gearView.labelDate") }}:</strong> {{ formatDate(activity.start_time) }} @ {{ formatTime(activity.start_time) }}</span>
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
import { ref, onMounted } from "vue";
import { useI18n } from "vue-i18n";
import { useRoute, useRouter } from "vue-router";
// Import Notivue push
import { push } from "notivue";
// Importing the components
import NoItemsFoundComponent from "@/components/GeneralComponents/NoItemsFoundComponents.vue";
import LoadingComponent from "@/components/GeneralComponents/LoadingComponent.vue";
import BackButtonComponent from "@/components/GeneralComponents/BackButtonComponent.vue";
import ModalComponent from '@/components/Modals/ModalComponent.vue';
// Importing the services
import { gears } from "@/services/gearsService";
import { activities } from "@/services/activitiesService";
import { formatDate, formatTime } from "@/utils/dateTimeUtils";

export default {
	components: {
		NoItemsFoundComponent,
		LoadingComponent,
		BackButtonComponent,
        ModalComponent,
	},
	setup() {
		const { t } = useI18n();
		const route = useRoute();
		const router = useRouter();
		const isLoading = ref(true);
		const gear = ref(null);
		const gearActivities = ref([]);
		const gearDistance = ref(0);
		const brand = ref("");
		const model = ref("");
		const nickname = ref("");
		const gearType = ref(1);
		const date = ref(null);
		const isActive = ref(1);
        const initialKms = ref(0);

		async function submitEditGearForm() {
			try {
				const data = {
					brand: brand.value,
					model: model.value,
					nickname: nickname.value,
					gear_type: gearType.value,
					created_at: date.value,
					is_active: isActive.value,
                    initial_kms: initialKms.value,
				};

				await gears.editGear(route.params.id, data);

				gear.value.brand = brand.value;
				gear.value.model = model.value;
				gear.value.nickname = nickname.value;
				gear.value.gear_type = gearType.value;
				gear.value.created_at = date.value;
				gear.value.is_active = isActive.value;
				gear.value.initial_kms = initialKms.value;

				push.success(t("gearView.successGearEdited"));
			} catch (error) {
				// If there is an error, set the error message and show the error alert.
				push.error(`${t("generalItems.errorEditingInfo")} - ${error}`);
			}
		}

		async function submitDeleteGear() {
			try {
				gear.value = await gears.deleteGear(route.params.id);
				router.push({ path: "/gears", query: { gearDeleted: "true" } });
			} catch (error) {
				push.error(`${t("generalItems.errorEditingInfo")} - ${error}`);
			}
		}

		onMounted(async () => {
			try {
				// Fetch the gear by its id.
				gear.value = await gears.getGearById(route.params.id);
				if (!gear.value) {
					router.push({
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
                gearDistance.value += gear.value.initial_kms;
				brand.value = gear.value.brand;
				model.value = gear.value.model;
				nickname.value = gear.value.nickname;
				gearType.value = gear.value.gear_type;
				date.value = gear.value.created_at.split(" ")[0];
				isActive.value = gear.value.is_active;
                initialKms.value = gear.value.initial_kms;
			} catch (error) {
				if (error.toString().includes("422")) {
					router.push({
						path: "/gears",
						query: { gearFound: "false", id: route.params.id },
					});
				}
				// If there is an error, set the error message and show the error alert.
				push.error(`${t("generalItems.errorEditingInfo")} - ${error}`);
			}

			isLoading.value = false;
		});

		return {
			brand,
			model,
			nickname,
			gearType,
			date,
			isActive,
            initialKms,
			isLoading,
			gear,
			gearActivities,
			gearDistance,
			t,
			submitEditGearForm,
			submitDeleteGear,
			formatDate,
			formatTime,
		};
	},
};
</script>
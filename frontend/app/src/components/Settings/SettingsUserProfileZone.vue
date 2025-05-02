<template>
    <div class="col">
        <div class="bg-body-tertiary rounded p-3 shadow-sm">
            <div class="row row-gap-3">
                <h4>{{ $t("settingsUserProfileZone.titleProfileInfo") }}</h4>
                <div class="col-lg-4 col-md-12">
                    <div class="flex justify-center items-center">
                        <div class="justify-content-center align-items-center d-flex">
                            <div class="text-center">
                                <UserAvatarComponent :user="authStore.user" :width=180 :height=180 />
                                <h2>{{ authStore.user.name }}</h2>
                                <span>@{{ authStore.user.username }}</span>
                            </div>
                        </div>
                    </div>
                    <div class="row mt-3">
                        <div class="col">
                            <!-- Delete profile photo section -->
                            <a class="w-100 btn btn-danger" href="#" role="button" data-bs-toggle="modal" data-bs-target="#deleteProfilePhotoModal" v-if="authStore.user.photo_path"><font-awesome-icon :icon="['fas', 'image']" class="me-1" />{{ $t("settingsUserProfileZone.buttonDeleteProfilePhoto") }}</a>

                            <!-- Modal delete profile photo -->
                            <ModalComponent modalId="deleteProfilePhotoModal" :title="t('settingsUserProfileZone.buttonDeleteProfilePhoto')" :body="`${t('settingsUserProfileZone.modalDeleteProfilePhotoBody')}`" actionButtonType="danger" :actionButtonText="t('settingsUserProfileZone.buttonDeleteProfilePhoto')" @submitAction="submitDeleteUserPhoto"/>
                        </div>
                        <div class="col">
                            <!-- Edit profile section -->
                            <a class="w-100 btn btn-primary" href="#" role="button" data-bs-toggle="modal" data-bs-target="#editProfileModal"><font-awesome-icon :icon="['fas', 'user-pen']" class="me-1"/>{{ $t("settingsUserProfileZone.buttonEditProfile") }}</a>

                            <!-- Modal edit user -->
                            <UsersAddEditUserModalComponent :action="'profile'" :user="authStore.user"/>
                        </div>
                    </div>
                </div>
                <div class="col">
                    <!-- user email -->
                    <p>
                        <font-awesome-icon :icon="['fas', 'envelope']" class="me-2"/>
                        <b>{{ $t("settingsUserProfileZone.emailLabel") }}: </b>
                        {{ authStore.user.email }}
                    </p>
                    <!-- user city -->
                    <p>
                        <font-awesome-icon :icon="['fas', 'location-crosshairs']" class="me-2"/>
                        <b>{{ $t("settingsUserProfileZone.cityLabel") }}: </b>
                        <span v-if="authStore.user.city">{{ authStore.user.city }}</span>
                        <span v-else>{{ $t("generalItems.labelNotApplicable") }}</span>
                    </p>
                    <!-- user birthdate -->
                    <p>
                        <font-awesome-icon :icon="['fas', 'cake-candles']" class="me-2"/>
                        <b>{{ $t("settingsUserProfileZone.birthdayLabel") }}: </b>
                        <span v-if="authStore.user.birthdate">{{ authStore.user.birthdate }}</span>
                        <span v-else>{{ $t("generalItems.labelNotApplicable") }}</span>
                    </p>
                    <!-- user gender -->
                    <p>
                        <font-awesome-icon :icon="['fas', 'mars']" class="me-2" v-if="authStore.user.gender == 1"/>
                        <font-awesome-icon :icon="['fas', 'venus']" class="me-2" v-else-if="authStore.user.gender == 2"/>
                        <font-awesome-icon :icon="['fas', 'genderless']" class="me-2" v-else/>
                        <b>{{ $t("settingsUserProfileZone.genderLabel") }}: </b>
                        <span v-if="authStore.user.gender == 1">{{ $t("settingsUserProfileZone.genderOption1") }}</span>
                        <span v-else-if="authStore.user.gender == 2">{{ $t("settingsUserProfileZone.genderOption2") }}</span>
                        <span v-else>{{ $t("settingsUserProfileZone.genderOption3") }}</span>
                    </p>
                    <!-- user units -->
                    <p>
                        <font-awesome-icon :icon="['fas', 'gear']" class="me-2"/>
                        <b>{{ $t("settingsUserProfileZone.unitsLabel") }}: </b>
                        <span v-if="Number(authStore?.user?.units) === 1">{{ $t("settingsUserProfileZone.unitsOption1") }}</span>
                        <span v-else>{{ $t("settingsUserProfileZone.unitsOption2") }}</span>
                    </p>
                    <!-- user height -->
                    <p>
                        <font-awesome-icon :icon="['fas', 'person-arrow-up-from-line']" class="me-2"/>
                        <b>{{ $t("settingsUserProfileZone.heightLabel") }} 
                            <span v-if="Number(authStore?.user?.units) === 1">({{ $t("generalItems.unitsCm") }}): </span>
                            <span v-else>({{ $t("generalItems.unitsFeetInches") }}): </span>
                        </b>
                        <span v-if="authStore.user.height">
                            <span v-if="Number(authStore?.user?.units) === 1">{{ authStore.user.height }}{{ $t("generalItems.unitsCm") }}</span>
                            <span v-else>{{ feet }}’{{ inches }}’’</span>
                        </span>
                        <span v-else>{{ $t("generalItems.labelNotApplicable") }}</span>
                    </p>
                    <!-- user preferred language -->
                    <p>
                        <font-awesome-icon :icon="['fas', 'language']" class="me-2"/>
                        <b>{{ $t("settingsUserProfileZone.preferredLanguageLabel") }}: </b>
                        <span v-if="authStore.user.preferred_language == 'ca'">{{ $t("generalItems.languageOption2") }}</span>
                        <span v-if="authStore.user.preferred_language == 'de'">{{ $t("generalItems.languageOption4") }}</span>
                        <span v-if="authStore.user.preferred_language == 'fr'">{{ $t("generalItems.languageOption5") }}</span>
                        <span v-if="authStore.user.preferred_language == 'nl'">{{ $t("generalItems.languageOption6") }}</span>
                        <span v-if="authStore.user.preferred_language == 'pt'">{{ $t("generalItems.languageOption3") }}</span>
                        <span v-if="authStore.user.preferred_language == 'es'">{{ $t("generalItems.languageOption7") }}</span>
                        <span v-if="authStore.user.preferred_language == 'us'">{{ $t("generalItems.languageOption1") }}</span>
                    </p>
                    <!-- user type -->
                    <p>
                        <font-awesome-icon :icon="['fas', 'id-card']" class="me-2"/>
                        <b>{{ $t("settingsUserProfileZone.accessTypeLabel") }}: </b>
                        <span v-if="authStore.user.access_type == 1">{{ $t("settingsUserProfileZone.accessTypeOption1") }}</span>
                        <span v-else>{{ $t("settingsUserProfileZone.accessTypeOption2") }}</span>
                    </p>
                </div>
            </div>
            <hr>
            <div>
                <h4 class="mt-4">{{ $t("settingsUserProfileZone.titleDefaultGear") }}</h4>
                <LoadingComponent v-if="isLoading"/>
                <div class="row" v-else>
                    <div class="col-lg-4 col-md-12">
                        <h5>{{ $t("settingsUserProfileZone.subTitleShoeActivities") }}</h5>
                        <form>
                            <label class="form-label" for="settingsUserProfileRunGearSelect">{{ $t("settingsUserProfileZone.subTitleRun") }}</label>
                            <select class="form-select" name="settingsUserProfileRunGearSelect" v-model="defaultRunGear" required>
                                <option :value="null">{{ $t("settingsUserProfileZone.selectOptionNotDefined") }}</option>
                                <option v-for="gear in runGear" :key="gear.id" :value="gear.id">
                                    {{ gear.nickname }}
                                </option>
                            </select>
                            <label class="form-label" for="settingsUserProfileTrailRunGearSelect">{{ $t("settingsUserProfileZone.subTitleTrailRun") }}</label>
                            <select class="form-select" name="settingsUserProfileTrailRunGearSelect" v-model="defaultTrailRunGear" required>
                                <option :value="null">{{ $t("settingsUserProfileZone.selectOptionNotDefined") }}</option>
                                <option v-for="gear in runGear" :key="gear.id" :value="gear.id">
                                    {{ gear.nickname }}
                                </option>
                            </select>
                            <label class="form-label" for="settingsUserProfileVirtualRunGearSelect">{{ $t("settingsUserProfileZone.subTitleVirtualRun") }}</label>
                            <select class="form-select" name="settingsUserProfileVirtualRunGearSelect" v-model="defaultVirtualRunGear" required>
                                <option :value="null">{{ $t("settingsUserProfileZone.selectOptionNotDefined") }}</option>
                                <option v-for="gear in runGear" :key="gear.id" :value="gear.id">
                                    {{ gear.nickname }}
                                </option>
                            </select>
                            <label class="form-label" for="settingsUserProfileWalkGearSelect">{{ $t("settingsUserProfileZone.subTitleWalk") }}</label>
                            <select class="form-select" name="settingsUserProfileWalkGearSelect" v-model="defaultWalkGear" required>
                                <option :value="null">{{ $t("settingsUserProfileZone.selectOptionNotDefined") }}</option>
                                <option v-for="gear in runGear" :key="gear.id" :value="gear.id">
                                    {{ gear.nickname }}
                                </option>
                            </select>
                            <label class="form-label" for="settingsUserProfileHikeGearSelect">{{ $t("settingsUserProfileZone.subTitleHike") }}</label>
                            <select class="form-select" name="settingsUserProfileHikeGearSelect" v-model="defaultHikeGear" required>
                                <option :value="null">{{ $t("settingsUserProfileZone.selectOptionNotDefined") }}</option>
                                <option v-for="gear in runGear" :key="gear.id" :value="gear.id">
                                    {{ gear.nickname }}
                                </option>
                            </select>
                        </form>
                    </div>
                    <div class="col-lg-4 col-md-12">
                        <h5>{{ $t("settingsUserProfileZone.subTitleBikeActivities") }}</h5>
                        <form>
                            <label class="form-label" for="settingsUserProfileRideGearSelect">{{ $t("settingsUserProfileZone.subTitleBike") }}</label>
                            <select class="form-select" name="settingsUserProfileRideGearSelect" v-model="defaultRideGear" required>
                                <option :value="null">{{ $t("settingsUserProfileZone.selectOptionNotDefined") }}</option>
                                <option v-for="gear in bikeGear" :key="gear.id" :value="gear.id">
                                    {{ gear.nickname }}
                                </option>
                            </select>
                            <label class="form-label" for="settingsUserProfileMTBRideGearSelect">{{ $t("settingsUserProfileZone.subTitleMTBBike") }}</label>
                            <select class="form-select" name="settingsUserProfileMTBRideGearSelect" v-model="defaultMTBRideGear" required>
                                <option :value="null">{{ $t("settingsUserProfileZone.selectOptionNotDefined") }}</option>
                                <option v-for="gear in bikeGear" :key="gear.id" :value="gear.id">
                                    {{ gear.nickname }}
                                </option>
                            </select>
                            <label class="form-label" for="settingsUserProfileGravelRideGearSelect">{{ $t("settingsUserProfileZone.subTitleGravelBike") }}</label>
                            <select class="form-select" name="settingsUserProfileGravelRideGearSelect" v-model="defaultGravelRideGear" required>
                                <option :value="null">{{ $t("settingsUserProfileZone.selectOptionNotDefined") }}</option>
                                <option v-for="gear in bikeGear" :key="gear.id" :value="gear.id">
                                    {{ gear.nickname }}
                                </option>
                            </select>
                            <label class="form-label" for="settingsUserProfileVirtualRideGearSelect">{{ $t("settingsUserProfileZone.subTitleVirtualBike") }}</label>
                            <select class="form-select" name="settingsUserProfileVirtualRideGearSelect" v-model="defaultVirtualRideGear" required>
                                <option :value="null">{{ $t("settingsUserProfileZone.selectOptionNotDefined") }}</option>
                                <option v-for="gear in bikeGear" :key="gear.id" :value="gear.id">
                                    {{ gear.nickname }}
                                </option>
                            </select>
                        </form>
                    </div>
                    <div class="col-lg-4 col-md-12">
                        <h5>{{ $t("settingsUserProfileZone.subTitleSwimActivities") }}</h5>
                        <form>
                            <label class="form-label" for="settingsUserProfileOWSGearSelect">{{ $t("settingsUserProfileZone.subTitleSwim") }}</label>
                            <select class="form-select" name="settingsUserProfileOWSGearSelect" v-model="defaultOWSGear" required>
                                <option :value="null">{{ $t("settingsUserProfileZone.selectOptionNotDefined") }}</option>
                                <option v-for="gear in swimGear" :key="gear.id" :value="gear.id">
                                    {{ gear.nickname }}
                                </option>
                            </select>
                        </form>
                    </div>
                    <div class="col-lg-4 col-md-12 mt-md-2">
                        <h5>{{ $t("settingsUserProfileZone.subTitleRacquetActivities") }}</h5>
                        <form>
                            <label class="form-label" for="settingsUserProfileTennisGearSelect">{{ $t("settingsUserProfileZone.subTitleTennis") }}</label>
                            <select class="form-select" name="settingsUserProfileTennisGearSelect" v-model="defaultTennisGear" required>
                                <option :value="null">{{ $t("settingsUserProfileZone.selectOptionNotDefined") }}</option>
                                <option v-for="gear in racquetGear" :key="gear.id" :value="gear.id">
                                    {{ gear.nickname }}
                                </option>
                            </select>
                        </form>
                    </div>
                </div>
            </div>
            <hr>
            <div>
                <h4 class="mt-4">{{ $t("settingsUserProfileZone.titlePrivacy") }}</h4>
                <LoadingComponent v-if="isLoading"/>
                <div class="row" v-else>
                    <div class="col">
                        <!-- user default_activity_visibility -->
                        <p>
                            <font-awesome-icon :icon="['fas', 'eye-slash']" class="me-2"/>
                            <b>{{ $t("settingsUserProfileZone.defaultActivityVisibility") }}: </b>
                            <span v-if="authStore.user.default_activity_visibility === 0">{{ $t("settingsUserProfileZone.privacyOption1") }}</span>
                            <span v-if="authStore.user.default_activity_visibility === 1">{{ $t("settingsUserProfileZone.privacyOption2") }}</span>
                            <span v-if="authStore.user.default_activity_visibility === 2">{{ $t("settingsUserProfileZone.privacyOption3") }}</span>
                        </p>
                        <!-- Edit profile section -->
                        <div class="row">
                            <div class="col">
                                <a class="btn btn-primary w-100" href="#" role="button" data-bs-toggle="modal" data-bs-target="#editProfileModal"><font-awesome-icon :icon="['fas', 'user-pen']" class="me-1"/>{{ $t("settingsUserProfileZone.buttonChangeDefaultActivityVisibility") }}</a>
                            </div>

                            <div class="col">
                                <!-- Edit activities visibility section -->
                                <a class="btn btn-primary w-100" href="#" role="button" data-bs-toggle="modal" data-bs-target="#editUserActivitiesVisibilityModal"><font-awesome-icon :icon="['fas', 'eye-slash']" class="me-1"/>{{ $t("settingsUserProfileZone.buttonChangeUserActivitiesVisibility") }}</a>

                                <!-- modal retrieve Garmin Connect health data by days -->
                                <ModalComponentSelectInput modalId="editUserActivitiesVisibilityModal" :title="t('settingsUserProfileZone.buttonChangeUserActivitiesVisibility')" :selectFieldLabel="`${t('settingsUserProfileZone.changeUserActivitiesVisibilityModalVisibilityLabel')}`" :selectOptions="visibilityOptionsForModal" :selectCurrentOption="authStore.user.default_activity_visibility" :actionButtonType="`success`" :actionButtonText="t('settingsUserProfileZone.changeUserActivitiesVisibilityModalButton')" @optionToEmitAction="submitChangeUserActivitiesVisibility"/>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </div>
</template>

<script>
import { ref, onMounted, watch, nextTick } from "vue";
import { useI18n } from "vue-i18n";
// Importing the services
import { profile } from "@/services/profileService";
import { gears } from "@/services/gearsService";
import { activities } from "@/services/activitiesService";
import { userDefaultGear } from "@/services/userDefaultGear";
// Import the stores
import { useAuthStore } from "@/stores/authStore";
// Import Notivue push
import { push } from "notivue";
// Import units utils
import { cmToFeetInches } from "@/utils/unitsUtils";
// Importing the components
import UserAvatarComponent from "../Users/UserAvatarComponent.vue";
import UsersAddEditUserModalComponent from "@/components/Settings/SettingsUsersZone/UsersAddEditUserModalComponent.vue";
import ModalComponent from "@/components/Modals/ModalComponent.vue";
import LoadingComponent from "../GeneralComponents/LoadingComponent.vue";
import ModalComponentSelectInput from "@/components/Modals/ModalComponentSelectInput.vue";

export default {
	components: {
		UserAvatarComponent,
		UsersAddEditUserModalComponent,
		ModalComponent,
		LoadingComponent,
		ModalComponentSelectInput,
	},
	setup() {
		const authStore = useAuthStore();
		const { t, locale } = useI18n();
		const { feet, inches } = cmToFeetInches(authStore.user.height);
		const isLoading = ref(false);
		const isMounted = ref(false);
		const allGears = ref(null);
		const runGear = ref(null);
		const bikeGear = ref(null);
		const swimGear = ref(null);
		const racquetGear = ref(null);
		const defaultGear = ref(null);
		const defaultRunGear = ref(null);
		const defaultTrailRunGear = ref(null);
		const defaultVirtualRunGear = ref(null);
		const defaultWalkGear = ref(null);
		const defaultHikeGear = ref(null);
		const defaultRideGear = ref(null);
		const defaultMTBRideGear = ref(null);
		const defaultGravelRideGear = ref(null);
		const defaultVirtualRideGear = ref(null);
		const defaultOWSGear = ref(null);
		const defaultTennisGear = ref(null);
		const visibilityOptionsForModal = ref([
			{ id: 0, name: t("settingsUserProfileZone.privacyOption1") },
			{ id: 1, name: t("settingsUserProfileZone.privacyOption2") },
			{ id: 2, name: t("settingsUserProfileZone.privacyOption3") },
		]);

		async function submitDeleteUserPhoto() {
			try {
				// Delete the user photo from the server
				await profile.deleteProfilePhoto();

				// Update the user photo
				const user = authStore.user;
				user.photo_path = null;

				// Save the user data in the local storage and in the store.
				authStore.setUser(user, authStore.session_id, locale);

				// Set the success message and show the success alert.
				push.success(t("settingsUserProfileZone.userPhotoDeleteSuccess"));
			} catch (error) {
				// Show the error message
				push.error(
					`${t("settingsUserProfileZone.userPhotoDeleteError")} - ${error}`,
				);
			}
		}

		async function updateDefaultGear() {
			const data = {
				id: defaultGear.value.id,
				user_id: authStore.user.id,
				run_gear_id: defaultRunGear.value,
				trail_run_gear_id: defaultTrailRunGear.value,
				virtual_run_gear_id: defaultVirtualRunGear.value,
				walk_gear_id: defaultWalkGear.value,
				hike_gear_id: defaultHikeGear.value,
				ride_gear_id: defaultRideGear.value,
				mtb_ride_gear_id: defaultMTBRideGear.value,
				gravel_ride_gear_id: defaultGravelRideGear.value,
				virtual_ride_gear_id: defaultVirtualRideGear.value,
				ows_gear_id: defaultOWSGear.value,
				tennis_gear_id: defaultTennisGear.value,
			};
			try {
				// Update the default gear in the DB
				await userDefaultGear.editUserDefaultGear(data);

				push.success(t("settingsUserProfileZone.successUpdateDefaultGear"));
			} catch (error) {
				push.error(t("settingsUserProfileZone.errorUpdateDefaultGear"));
			}
		}

		async function submitChangeUserActivitiesVisibility(visibility) {
			try {
				await activities.editUserActivitiesVisibility(visibility);

				// Show the success alert.
				push.success(
					t("settingsUserProfileZone.successUpdateUserActivitiesVisibility"),
				);
			} catch (error) {
				// If there is an error, show the error alert.
				push.error(
					`${t("settingsUserProfileZone.errorUpdateUserActivitiesVisibility")} - ${error}`,
				);
			}
		}

		onMounted(async () => {
			isLoading.value = true;
			try {
				allGears.value = await gears.getGears();
				runGear.value = allGears.value.filter((gear) => gear.gear_type === 2);
				bikeGear.value = allGears.value.filter((gear) => gear.gear_type === 1);
				swimGear.value = allGears.value.filter((gear) => gear.gear_type === 3);
				racquetGear.value = allGears.value.filter(
					(gear) => gear.gear_type === 4,
				);

				try {
					defaultGear.value = await userDefaultGear.getUserDefaultGear();
					defaultRunGear.value = defaultGear.value.run_gear_id;
					defaultTrailRunGear.value = defaultGear.value.trail_run_gear_id;
					defaultVirtualRunGear.value = defaultGear.value.virtual_run_gear_id;
					defaultWalkGear.value = defaultGear.value.walk_gear_id;
					defaultHikeGear.value = defaultGear.value.hike_gear_id;
					defaultRideGear.value = defaultGear.value.ride_gear_id;
					defaultMTBRideGear.value = defaultGear.value.mtb_ride_gear_id;
					defaultGravelRideGear.value = defaultGear.value.gravel_ride_gear_id;
					defaultVirtualRideGear.value = defaultGear.value.virtual_ride_gear_id;
					defaultOWSGear.value = defaultGear.value.ows_gear_id;
					defaultTennisGear.value = defaultGear.value.tennis_gear_id;
				} catch (error) {
					// If there is an error, set the error message and show the error alert.
					push.error(
						`${t("settingsUserProfileZone.errorUnableToGetDefaultGear")} - ${error}`,
					);
				}
			} catch (error) {
				// If there is an error, set the error message and show the error alert.
				push.error(
					`${t("settingsUserProfileZone.errorUnableToGetGear")} - ${error}`,
				);
			} finally {
				isLoading.value = false;
				await nextTick();
				isMounted.value = true;
			}
		});

		// watchers
		watch(
			[
				defaultRunGear,
				defaultTrailRunGear,
				defaultVirtualRunGear,
				defaultWalkGear,
				defaultHikeGear,
				defaultRideGear,
				defaultMTBRideGear,
				defaultGravelRideGear,
				defaultVirtualRideGear,
				defaultOWSGear,
				defaultTennisGear,
			],
			async () => {
				if (!isMounted.value || isLoading.value) return;
				await updateDefaultGear();
			},
			{ immediate: false },
		);

		return {
			authStore,
			t,
			submitDeleteUserPhoto,
			feet,
			inches,
			isLoading,
			runGear,
			bikeGear,
			swimGear,
			racquetGear,
			defaultGear,
			defaultRunGear,
			defaultTrailRunGear,
			defaultVirtualRunGear,
			defaultWalkGear,
			defaultHikeGear,
			defaultRideGear,
			defaultMTBRideGear,
			defaultGravelRideGear,
			defaultVirtualRideGear,
			defaultOWSGear,
			defaultTennisGear,
			visibilityOptionsForModal,
			submitChangeUserActivitiesVisibility,
		};
	},
};
</script>
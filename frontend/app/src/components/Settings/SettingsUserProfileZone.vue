<template>
  <div class="col">
    <div class="bg-body-tertiary rounded p-3 shadow-sm">
      <div class="row row-gap-3">
        <h4>{{ $t('settingsUserProfileZone.titleProfileInfo') }}</h4>
        <div class="col-lg-4 col-md-12">
          <div class="flex justify-center items-center">
            <div class="justify-content-center align-items-center d-flex">
              <div class="text-center">
                <UserAvatarComponent :user="authStore.user" :width="260" :height="260" />
                <h2>{{ authStore.user.name }}</h2>
                <span>@{{ authStore.user.username }}</span>
              </div>
            </div>
          </div>
          <div class="row mt-3">
            <div class="col">
              <!-- Delete profile photo section -->
              <a
                class="w-100 btn btn-danger"
                href="#"
                role="button"
                data-bs-toggle="modal"
                data-bs-target="#deleteProfilePhotoModal"
                v-if="authStore.user.photo_path"
                ><font-awesome-icon :icon="['fas', 'image']" class="me-1" />{{
                  $t('settingsUserProfileZone.buttonDeleteProfilePhoto')
                }}</a
              >

              <!-- Modal delete profile photo -->
              <ModalComponent
                modalId="deleteProfilePhotoModal"
                :title="t('settingsUserProfileZone.buttonDeleteProfilePhoto')"
                :body="`${t('settingsUserProfileZone.modalDeleteProfilePhotoBody')}`"
                actionButtonType="danger"
                :actionButtonText="t('settingsUserProfileZone.buttonDeleteProfilePhoto')"
                @submitAction="submitDeleteUserPhoto"
              />
            </div>
            <div class="col">
              <!-- Edit profile section -->
              <a
                class="w-100 btn btn-primary"
                href="#"
                role="button"
                data-bs-toggle="modal"
                data-bs-target="#editProfileModal"
                ><font-awesome-icon :icon="['fas', 'user-pen']" class="me-1" />{{
                  $t('settingsUserProfileZone.buttonEditProfile')
                }}</a
              >

              <!-- Modal edit user -->
              <UsersAddEditUserModalComponent
                :action="'profile'"
                :user="authStore.user"
                @userPhotoDeleted="submitDeleteUserPhoto"
              />
            </div>
          </div>
        </div>
        <div class="col">
          <!-- user email -->
          <p>
            <font-awesome-icon :icon="['fas', 'envelope']" class="me-2" />
            <b>{{ $t('settingsUserProfileZone.emailLabel') }}: </b>
            {{ authStore.user.email }}
          </p>
          <!-- user city -->
          <p>
            <font-awesome-icon :icon="['fas', 'location-crosshairs']" class="me-2" />
            <b>{{ $t('settingsUserProfileZone.cityLabel') }}: </b>
            <span v-if="authStore.user.city">{{ authStore.user.city }}</span>
            <span v-else>{{ $t('generalItems.labelNotApplicable') }}</span>
          </p>
          <!-- user birthdate -->
          <p>
            <font-awesome-icon :icon="['fas', 'cake-candles']" class="me-2" />
            <b>{{ $t('settingsUserProfileZone.birthdayLabel') }}: </b>
            <span v-if="authStore.user.birthdate">{{ authStore.user.birthdate }}</span>
            <span v-else>{{ $t('generalItems.labelNotApplicable') }}</span>
          </p>
          <!-- user gender -->
          <p>
            <font-awesome-icon
              :icon="['fas', 'mars']"
              class="me-2"
              v-if="authStore.user.gender == 1"
            />
            <font-awesome-icon
              :icon="['fas', 'venus']"
              class="me-2"
              v-else-if="authStore.user.gender == 2"
            />
            <font-awesome-icon :icon="['fas', 'genderless']" class="me-2" v-else />
            <b>{{ $t('settingsUserProfileZone.genderLabel') }}: </b>
            <span v-if="authStore.user.gender == 1">{{
              $t('settingsUserProfileZone.genderOption1')
            }}</span>
            <span v-else-if="authStore.user.gender == 2">{{
              $t('settingsUserProfileZone.genderOption2')
            }}</span>
            <span v-else>{{ $t('settingsUserProfileZone.genderOption3') }}</span>
          </p>
          <!-- user units -->
          <p>
            <font-awesome-icon :icon="['fas', 'gear']" class="me-2" />
            <b>{{ $t('settingsUserProfileZone.unitsLabel') }}: </b>
            <span v-if="Number(authStore?.user?.units) === 1">{{
              $t('settingsUserProfileZone.unitsOption1')
            }}</span>
            <span v-else>{{ $t('settingsUserProfileZone.unitsOption2') }}</span>
          </p>
          <!-- user currency -->
          <p>
            <font-awesome-icon :icon="['fas', 'coins']" class="me-2" />
            <b>{{ $t('settingsUserProfileZone.currencyLabel') }}: </b>
            <span v-if="Number(authStore?.user?.currency) === 1">{{
              $t('generalItems.currencyEuro')
            }}</span>
            <span v-else-if="Number(authStore?.user?.currency) === 2">{{
              $t('generalItems.currencyDollar')
            }}</span>
            <span v-else>{{ $t('generalItems.currencyPound') }}</span>
          </p>
          <!-- user height -->
          <p>
            <font-awesome-icon :icon="['fas', 'person-arrow-up-from-line']" class="me-2" />
            <b
              >{{ $t('settingsUserProfileZone.heightLabel') }}
              <span v-if="Number(authStore?.user?.units) === 1"
                >({{ $t('generalItems.unitsCm') }}):
              </span>
              <span v-else>({{ $t('generalItems.unitsFeetInches') }}): </span>
            </b>
            <span v-if="authStore.user.height">
              <span v-if="Number(authStore?.user?.units) === 1"
                >{{ authStore.user.height }}{{ $t('generalItems.unitsCm') }}</span
              >
              <span v-else>{{ feet }}’{{ inches }}’’</span>
            </span>
            <span v-else>{{ $t('generalItems.labelNotApplicable') }}</span>
          </p>
          <!-- user max heart rate -->
          <p>
            <font-awesome-icon :icon="['fas', 'heart-pulse']" class="me-2" />
            <b>{{ $t('settingsUserProfileZone.maxHeartRateLabel') }}: </b>
            <span v-if="authStore.user.max_heart_rate"
              >{{ authStore.user.max_heart_rate }} {{ $t('generalItems.unitsBpm') }}</span
            >
            <span v-else>{{ $t('generalItems.labelNotApplicable') }}</span>
          </p>
          <!-- user preferred language -->
          <p>
            <font-awesome-icon :icon="['fas', 'language']" class="me-2" />
            <b>{{ $t('settingsUserProfileZone.preferredLanguageLabel') }}: </b>
            <span v-if="authStore.user.preferred_language == 'ca'">{{
              $t('generalItems.languageOption2')
            }}</span>
            <span v-if="authStore.user.preferred_language == 'cn'">{{
              $t('generalItems.languageOption8')
            }}</span>
            <span v-if="authStore.user.preferred_language == 'tw'">{{
              $t('generalItems.languageOption9')
            }}</span>
            <span v-if="authStore.user.preferred_language == 'de'">{{
              $t('generalItems.languageOption4')
            }}</span>
            <span v-if="authStore.user.preferred_language == 'fr'">{{
              $t('generalItems.languageOption5')
            }}</span>
            <span v-if="authStore.user.preferred_language == 'gl'">{{
              $t('generalItems.languageOption10')
            }}</span>
            <span v-if="authStore.user.preferred_language == 'it'">{{
              $t('generalItems.languageOption11')
            }}</span>
            <span v-if="authStore.user.preferred_language == 'nl'">{{
              $t('generalItems.languageOption6')
            }}</span>
            <span v-if="authStore.user.preferred_language == 'pt'">{{
              $t('generalItems.languageOption3')
            }}</span>
            <span v-if="authStore.user.preferred_language == 'sl'">{{
              $t('generalItems.languageOption12')
            }}</span>
            <span v-if="authStore.user.preferred_language == 'sv'">{{
              $t('generalItems.languageOption13')
            }}</span>
            <span v-if="authStore.user.preferred_language == 'es'">{{
              $t('generalItems.languageOption7')
            }}</span>
            <span v-if="authStore.user.preferred_language == 'us'">{{
              $t('generalItems.languageOption1')
            }}</span>
          </p>
          <!-- user first day of the week -->
          <p>
            <font-awesome-icon :icon="['fas', 'calendar-days']" class="me-2" />
            <b>{{ $t('settingsUserProfileZone.firstDayOfWeekLabel') }}: </b>
            <span v-if="authStore.user.first_day_of_week == 0">{{
              $t('generalItems.firstDayOfWeekOption0')
            }}</span>
            <span v-if="authStore.user.first_day_of_week == 1">{{
              $t('generalItems.firstDayOfWeekOption1')
            }}</span>
            <span v-if="authStore.user.first_day_of_week == 2">{{
              $t('generalItems.firstDayOfWeekOption2')
            }}</span>
            <span v-if="authStore.user.first_day_of_week == 3">{{
              $t('generalItems.firstDayOfWeekOption3')
            }}</span>
            <span v-if="authStore.user.first_day_of_week == 4">{{
              $t('generalItems.firstDayOfWeekOption4')
            }}</span>
            <span v-if="authStore.user.first_day_of_week == 5">{{
              $t('generalItems.firstDayOfWeekOption5')
            }}</span>
            <span v-if="authStore.user.first_day_of_week == 6">{{
              $t('generalItems.firstDayOfWeekOption6')
            }}</span>
          </p>
          <!-- user type -->
          <p>
            <font-awesome-icon :icon="['fas', 'id-card']" class="me-2" />
            <b>{{ $t('settingsUserProfileZone.accessTypeLabel') }}: </b>
            <span v-if="authStore.user.access_type == 1">{{
              $t('settingsUserProfileZone.accessTypeOption1')
            }}</span>
            <span v-else>{{ $t('settingsUserProfileZone.accessTypeOption2') }}</span>
          </p>
        </div>
      </div>
      <hr />
      <div>
        <h4 class="mt-4">{{ $t('settingsUserProfileZone.titleDefaultGear') }}</h4>
        <LoadingComponent v-if="isLoading" />
        <div class="row" v-else>
          <div class="col-lg-4 col-md-12">
            <h5>{{ $t('settingsUserProfileZone.subTitleShoeActivities') }}</h5>
            <form>
              <!-- run zone -->
              <label class="form-label" for="settingsUserProfileRunGearSelect">{{
                $t('settingsUserProfileZone.subTitleRun')
              }}</label>
              <select
                class="form-select"
                name="settingsUserProfileRunGearSelect"
                v-model="defaultRunGear"
                required
              >
                <option :value="null">
                  {{ $t('settingsUserProfileZone.selectOptionNotDefined') }}
                </option>
                <option v-for="gear in runGear" :key="gear.id" :value="gear.id">
                  {{ gear.nickname }}
                </option>
              </select>
              <!-- trail run zone -->
              <label class="form-label" for="settingsUserProfileTrailRunGearSelect">{{
                $t('settingsUserProfileZone.subTitleTrailRun')
              }}</label>
              <select
                class="form-select"
                name="settingsUserProfileTrailRunGearSelect"
                v-model="defaultTrailRunGear"
                required
              >
                <option :value="null">
                  {{ $t('settingsUserProfileZone.selectOptionNotDefined') }}
                </option>
                <option v-for="gear in runGear" :key="gear.id" :value="gear.id">
                  {{ gear.nickname }}
                </option>
              </select>
              <!-- virtual run zone -->
              <label class="form-label" for="settingsUserProfileVirtualRunGearSelect">{{
                $t('settingsUserProfileZone.subTitleVirtualRun')
              }}</label>
              <select
                class="form-select"
                name="settingsUserProfileVirtualRunGearSelect"
                v-model="defaultVirtualRunGear"
                required
              >
                <option :value="null">
                  {{ $t('settingsUserProfileZone.selectOptionNotDefined') }}
                </option>
                <option v-for="gear in runGear" :key="gear.id" :value="gear.id">
                  {{ gear.nickname }}
                </option>
              </select>
              <!-- walk zone -->
              <label class="form-label" for="settingsUserProfileWalkGearSelect">{{
                $t('settingsUserProfileZone.subTitleWalk')
              }}</label>
              <select
                class="form-select"
                name="settingsUserProfileWalkGearSelect"
                v-model="defaultWalkGear"
                required
              >
                <option :value="null">
                  {{ $t('settingsUserProfileZone.selectOptionNotDefined') }}
                </option>
                <option v-for="gear in runGear" :key="gear.id" :value="gear.id">
                  {{ gear.nickname }}
                </option>
              </select>
              <!-- hike zone -->
              <label class="form-label" for="settingsUserProfileHikeGearSelect">{{
                $t('settingsUserProfileZone.subTitleHike')
              }}</label>
              <select
                class="form-select"
                name="settingsUserProfileHikeGearSelect"
                v-model="defaultHikeGear"
                required
              >
                <option :value="null">
                  {{ $t('settingsUserProfileZone.selectOptionNotDefined') }}
                </option>
                <option v-for="gear in runGear" :key="gear.id" :value="gear.id">
                  {{ gear.nickname }}
                </option>
              </select>
            </form>
          </div>
          <div class="col-lg-4 col-md-12">
            <h5>{{ $t('settingsUserProfileZone.subTitleBikeActivities') }}</h5>
            <form>
              <!-- bike ride zone -->
              <label class="form-label" for="settingsUserProfileRideGearSelect">{{
                $t('settingsUserProfileZone.subTitleBike')
              }}</label>
              <select
                class="form-select"
                name="settingsUserProfileRideGearSelect"
                v-model="defaultRideGear"
                required
              >
                <option :value="null">
                  {{ $t('settingsUserProfileZone.selectOptionNotDefined') }}
                </option>
                <option v-for="gear in bikeGear" :key="gear.id" :value="gear.id">
                  {{ gear.nickname }}
                </option>
              </select>
              <!-- mountain bike ride zone -->
              <label class="form-label" for="settingsUserProfileMTBRideGearSelect">{{
                $t('settingsUserProfileZone.subTitleMTBBike')
              }}</label>
              <select
                class="form-select"
                name="settingsUserProfileMTBRideGearSelect"
                v-model="defaultMTBRideGear"
                required
              >
                <option :value="null">
                  {{ $t('settingsUserProfileZone.selectOptionNotDefined') }}
                </option>
                <option v-for="gear in bikeGear" :key="gear.id" :value="gear.id">
                  {{ gear.nickname }}
                </option>
              </select>
              <!-- gravel ride zone -->
              <label class="form-label" for="settingsUserProfileGravelRideGearSelect">{{
                $t('settingsUserProfileZone.subTitleGravelBike')
              }}</label>
              <select
                class="form-select"
                name="settingsUserProfileGravelRideGearSelect"
                v-model="defaultGravelRideGear"
                required
              >
                <option :value="null">
                  {{ $t('settingsUserProfileZone.selectOptionNotDefined') }}
                </option>
                <option v-for="gear in bikeGear" :key="gear.id" :value="gear.id">
                  {{ gear.nickname }}
                </option>
              </select>
              <!-- virtual ride zone -->
              <label class="form-label" for="settingsUserProfileVirtualRideGearSelect">{{
                $t('settingsUserProfileZone.subTitleVirtualBike')
              }}</label>
              <select
                class="form-select"
                name="settingsUserProfileVirtualRideGearSelect"
                v-model="defaultVirtualRideGear"
                required
              >
                <option :value="null">
                  {{ $t('settingsUserProfileZone.selectOptionNotDefined') }}
                </option>
                <option v-for="gear in bikeGear" :key="gear.id" :value="gear.id">
                  {{ gear.nickname }}
                </option>
              </select>
            </form>
          </div>
          <div class="col-lg-4 col-md-12">
            <h5>{{ $t('settingsUserProfileZone.subTitleWaterActivities') }}</h5>
            <form>
              <!-- open water swim zone -->
              <label class="form-label" for="settingsUserProfileOWSGearSelect">{{
                $t('settingsUserProfileZone.subTitleSwim')
              }}</label>
              <select
                class="form-select"
                name="settingsUserProfileOWSGearSelect"
                v-model="defaultOWSGear"
                required
              >
                <option :value="null">
                  {{ $t('settingsUserProfileZone.selectOptionNotDefined') }}
                </option>
                <option v-for="gear in swimGear" :key="gear.id" :value="gear.id">
                  {{ gear.nickname }}
                </option>
              </select>
              <!-- windsurf zone -->
              <label class="form-label" for="settingsUserProfileWindsurfGearSelect">{{
                $t('settingsUserProfileZone.subTitleWindsurf')
              }}</label>
              <select
                class="form-select"
                name="settingsUserProfileWindsurfGearSelect"
                v-model="defaultWindsurfGear"
                required
              >
                <option :value="null">
                  {{ $t('settingsUserProfileZone.selectOptionNotDefined') }}
                </option>
                <option v-for="gear in windsurfGear" :key="gear.id" :value="gear.id">
                  {{ gear.nickname }}
                </option>
              </select>
            </form>
          </div>
          <div class="col-lg-4 col-md-12 mt-md-2">
            <h5>{{ $t('settingsUserProfileZone.subTitleRacquetActivities') }}</h5>
            <form>
              <!-- racquet tennis zone -->
              <label class="form-label" for="settingsUserProfileTennisGearSelect">{{
                $t('settingsUserProfileZone.subTitleTennis')
              }}</label>
              <select
                class="form-select"
                name="settingsUserProfileTennisGearSelect"
                v-model="defaultTennisGear"
                required
              >
                <option :value="null">
                  {{ $t('settingsUserProfileZone.selectOptionNotDefined') }}
                </option>
                <option v-for="gear in racquetGear" :key="gear.id" :value="gear.id">
                  {{ gear.nickname }}
                </option>
              </select>
            </form>
          </div>
          <div class="col-lg-4 col-md-12 mt-md-2">
            <h5>{{ $t('settingsUserProfileZone.subTitleSnowActivities') }}</h5>
            <form>
              <!-- alpine ski zone -->
              <label class="form-label" for="settingsUserProfileAlpineSkiGearSelect">{{
                $t('settingsUserProfileZone.subTitleAlpineSki')
              }}</label>
              <select
                class="form-select"
                name="settingsUserProfileAlpineSkiGearSelect"
                v-model="defaultAlpineSkiGear"
                required
              >
                <option :value="null">
                  {{ $t('settingsUserProfileZone.selectOptionNotDefined') }}
                </option>
                <option v-for="gear in skisGear" :key="gear.id" :value="gear.id">
                  {{ gear.nickname }}
                </option>
              </select>
              <!-- nordic ski zone -->
              <label class="form-label" for="settingsUserProfileNordicSkiGearSelect">{{
                $t('settingsUserProfileZone.subTitleNordicSki')
              }}</label>
              <select
                class="form-select"
                name="settingsUserProfileNordicSkiGearSelect"
                v-model="defaultNordicSkiGear"
                required
              >
                <option :value="null">
                  {{ $t('settingsUserProfileZone.selectOptionNotDefined') }}
                </option>
                <option v-for="gear in skisGear" :key="gear.id" :value="gear.id">
                  {{ gear.nickname }}
                </option>
              </select>
              <!-- snowboard zone -->
              <label class="form-label" for="settingsUserProfileSnowboardGearSelect">{{
                $t('settingsUserProfileZone.subTitleSnowboard')
              }}</label>
              <select
                class="form-select"
                name="settingsUserProfileSnowboardGearSelect"
                v-model="defaultSnowboardGear"
                required
              >
                <option :value="null">
                  {{ $t('settingsUserProfileZone.selectOptionNotDefined') }}
                </option>
                <option v-for="gear in snowboardGear" :key="gear.id" :value="gear.id">
                  {{ gear.nickname }}
                </option>
              </select>
            </form>
          </div>
        </div>
      </div>
      <hr />
      <div>
        <h4 class="mt-4">{{ $t('settingsUserProfileZone.titlePrivacy') }}</h4>
        <LoadingComponent v-if="isLoading" />
        <div class="row" v-else>
          <div class="col-lg-4 col-md-12">
            <!-- user default_activity_visibility -->
            <form>
              <label for="activityVisibility">{{
                $t('settingsUserProfileZone.defaultActivityVisibility')
              }}</label>
              <select
                class="form-select"
                name="activityVisibility"
                v-model="activityVisibility"
                required
              >
                <option :value="0">{{ $t('settingsUserProfileZone.privacyOption1') }}</option>
                <option :value="1">{{ $t('settingsUserProfileZone.privacyOption2') }}</option>
                <option :value="2">{{ $t('settingsUserProfileZone.privacyOption3') }}</option>
              </select>
            </form>
            <!-- user hide_activity_start_time -->
            <form>
              <label for="activityStartTime">{{
                $t('settingsUserProfileZone.defaultActivityStartTime')
              }}</label>
              <select
                class="form-select"
                name="activityStartTime"
                v-model="activityStartTime"
                required
              >
                <option :value="true">{{ $t('generalItems.yes') }}</option>
                <option :value="false">{{ $t('generalItems.no') }}</option>
              </select>
            </form>
            <!-- user hide_activity_location -->
            <form>
              <label for="activityLocation">{{
                $t('settingsUserProfileZone.defaultActivityLocation')
              }}</label>
              <select
                class="form-select"
                name="activityLocation"
                v-model="activityLocation"
                required
              >
                <option :value="true">{{ $t('generalItems.yes') }}</option>
                <option :value="false">{{ $t('generalItems.no') }}</option>
              </select>
            </form>
            <!-- user hide_activity_map -->
            <form>
              <label for="activityMap">{{
                $t('settingsUserProfileZone.defaultActivityMap')
              }}</label>
              <select class="form-select" name="activityMap" v-model="activityMap" required>
                <option :value="true">{{ $t('generalItems.yes') }}</option>
                <option :value="false">{{ $t('generalItems.no') }}</option>
              </select>
            </form>
            <!-- user hide_activity_hr -->
            <form>
              <label for="activityHr">{{
                $t('settingsUserProfileZone.defaultActivityHeartRate')
              }}</label>
              <select class="form-select" name="activityHr" v-model="activityHr" required>
                <option :value="true">{{ $t('generalItems.yes') }}</option>
                <option :value="false">{{ $t('generalItems.no') }}</option>
              </select>
            </form>
          </div>
          <div class="col-lg-4 col-md-12">
            <!-- user hide_activity_power -->
            <form>
              <label for="activityPower">{{
                $t('settingsUserProfileZone.defaultActivityPower')
              }}</label>
              <select class="form-select" name="activityPower" v-model="activityPower" required>
                <option :value="true">{{ $t('generalItems.yes') }}</option>
                <option :value="false">{{ $t('generalItems.no') }}</option>
              </select>
            </form>
            <!-- user hide_activity_cadence -->
            <form>
              <label for="activityCadence">{{
                $t('settingsUserProfileZone.defaultActivityCadence')
              }}</label>
              <select class="form-select" name="activityCadence" v-model="activityCadence" required>
                <option :value="true">{{ $t('generalItems.yes') }}</option>
                <option :value="false">{{ $t('generalItems.no') }}</option>
              </select>
            </form>
            <!-- user hide_activity_elevation -->
            <form>
              <label for="activityElevation">{{
                $t('settingsUserProfileZone.defaultActivityElevation')
              }}</label>
              <select
                class="form-select"
                name="activityElevation"
                v-model="activityElevation"
                required
              >
                <option :value="true">{{ $t('generalItems.yes') }}</option>
                <option :value="false">{{ $t('generalItems.no') }}</option>
              </select>
            </form>
            <!-- user hide_activity_speed -->
            <form>
              <label for="activitySpeed">{{
                $t('settingsUserProfileZone.defaultActivitySpeed')
              }}</label>
              <select class="form-select" name="activitySpeed" v-model="activitySpeed" required>
                <option :value="true">{{ $t('generalItems.yes') }}</option>
                <option :value="false">{{ $t('generalItems.no') }}</option>
              </select>
            </form>
            <!-- user hide_activity_pace -->
            <form>
              <label for="activityPace">{{
                $t('settingsUserProfileZone.defaultActivityPace')
              }}</label>
              <select class="form-select" name="activityPace" v-model="activityPace" required>
                <option :value="true">{{ $t('generalItems.yes') }}</option>
                <option :value="false">{{ $t('generalItems.no') }}</option>
              </select>
            </form>
          </div>
          <div class="col-lg-4 col-md-12">
            <!-- user hide_activity_laps -->
            <form>
              <label for="activityLaps">{{
                $t('settingsUserProfileZone.defaultActivityLaps')
              }}</label>
              <select class="form-select" name="activityLaps" v-model="activityLaps" required>
                <option :value="true">{{ $t('generalItems.yes') }}</option>
                <option :value="false">{{ $t('generalItems.no') }}</option>
              </select>
            </form>
            <!-- user hide_activity_workout_sets_steps -->
            <form>
              <label for="activitySetsSteps">{{
                $t('settingsUserProfileZone.defaultActivitySetsSteps')
              }}</label>
              <select
                class="form-select"
                name="activitySetsSteps"
                v-model="activitySetsSteps"
                required
              >
                <option :value="true">{{ $t('generalItems.yes') }}</option>
                <option :value="false">{{ $t('generalItems.no') }}</option>
              </select>
            </form>
            <!-- user hide_activity_gear -->
            <form>
              <label for="activityGear">{{
                $t('settingsUserProfileZone.defaultActivityGear')
              }}</label>
              <select class="form-select" name="activityGear" v-model="activityGear" required>
                <option :value="true">{{ $t('generalItems.yes') }}</option>
                <option :value="false">{{ $t('generalItems.no') }}</option>
              </select>
            </form>
          </div>
        </div>
        <!-- Edit profile section -->
        <div class="row mt-3">
          <div class="col">
            <!-- Edit activities visibility section -->
            <a
              class="btn btn-primary w-100"
              href="#"
              role="button"
              data-bs-toggle="modal"
              data-bs-target="#editUserActivitiesVisibilityModal"
              ><font-awesome-icon :icon="['fas', 'eye-slash']" class="me-1" />{{
                $t('settingsUserProfileZone.buttonChangeUserActivitiesVisibility')
              }}</a
            >

            <!-- modal retrieve Garmin Connect health data by days -->
            <ModalComponentSelectInput
              modalId="editUserActivitiesVisibilityModal"
              :title="t('settingsUserProfileZone.buttonChangeUserActivitiesVisibility')"
              :selectFieldLabel="`${t('settingsUserProfileZone.changeUserActivitiesVisibilityModalVisibilityLabel')}`"
              :selectOptions="visibilityOptionsForModal"
              :selectCurrentOption="authStore.user.default_activity_visibility"
              :actionButtonType="`success`"
              :actionButtonText="
                t('settingsUserProfileZone.changeUserActivitiesVisibilityModalButton')
              "
              @optionToEmitAction="submitChangeUserActivitiesVisibility"
            />
          </div>
        </div>
      </div>

      <!-- Import / Export Buttons -->
      <hr />
      <div>
        <h4 class="mt-4">
          {{ $t('settingsUserProfileZone.titleExportData') }}{{ $t('generalItems.betaTag') }}
        </h4>
        <span>{{ $t('settingsUserProfileZone.labelPasswordDisclaimer') }}</span>
        <div class="row mt-3">
          <div class="col d-flex gap-3">
            <button class="btn btn-primary w-50" :disabled="loadingExport" @click="handleExport">
              <font-awesome-icon :icon="['fas', 'download']" class="me-1" v-if="!loadingExport" />
              <span class="spinner-border spinner-border-sm me-1" aria-hidden="true" v-else></span>
              <span>{{ $t('settingsUserProfileZone.buttonExportData') }}</span>
            </button>

            <button
              class="btn btn-primary w-50"
              data-bs-toggle="modal"
              data-bs-target="#importDataModal"
              :disabled="loadingImport"
            >
              <font-awesome-icon :icon="['fas', 'upload']" class="me-1" v-if="!loadingImport" />
              <span class="spinner-border spinner-border-sm me-1" aria-hidden="true" v-else></span>
              <span>{{ $t('settingsUserProfileZone.buttonImportData') }}</span>
            </button>
          </div>
        </div>
      </div>

      <!-- Import Data Modal -->
      <ModalComponentUploadFile
        modalId="importDataModal"
        :title="$t('settingsUserProfileZone.modalImportTitle')"
        :fileFieldLabel="$t('settingsUserProfileZone.modalImportBody')"
        filesAccepted=".zip"
        actionButtonType="success"
        :actionButtonText="$t('settingsUserProfileZone.modalImportTitle')"
        @fileToEmitAction="uploadImportFile"
      />
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, watch, nextTick } from 'vue'
import { useI18n } from 'vue-i18n'
// Importing the services
import { profile } from '@/services/profileService'
import { gears } from '@/services/gearsService'
import { activities } from '@/services/activitiesService'
import { userDefaultGear } from '@/services/userDefaultGear'
// Import the stores
import { useAuthStore } from '@/stores/authStore'
// Import Notivue push
import { push } from 'notivue'
// Import units utils
import { cmToFeetInches } from '@/utils/unitsUtils'
// Importing the components
import UserAvatarComponent from '../Users/UserAvatarComponent.vue'
import UsersAddEditUserModalComponent from '@/components/Settings/SettingsUsersZone/UsersAddEditUserModalComponent.vue'
import ModalComponent from '@/components/Modals/ModalComponent.vue'
import LoadingComponent from '../GeneralComponents/LoadingComponent.vue'
import ModalComponentSelectInput from '@/components/Modals/ModalComponentSelectInput.vue'
import ModalComponentUploadFile from '@/components/Modals/ModalComponentUploadFile.vue'

const authStore = useAuthStore()
const { t, locale } = useI18n()
const { feet, inches } = cmToFeetInches(authStore.user.height)
const isLoading = ref(false)
const isMounted = ref(false)
const allGears = ref(null)
const runGear = ref(null)
const bikeGear = ref(null)
const swimGear = ref(null)
const racquetGear = ref(null)
const windsurfGear = ref(null)
const waterSportsBoardGear = ref(null)
const skisGear = ref(null)
const snowboardGear = ref(null)
const defaultGear = ref(null)
const defaultRunGear = ref(null)
const defaultTrailRunGear = ref(null)
const defaultVirtualRunGear = ref(null)
const defaultWalkGear = ref(null)
const defaultHikeGear = ref(null)
const defaultRideGear = ref(null)
const defaultMTBRideGear = ref(null)
const defaultGravelRideGear = ref(null)
const defaultVirtualRideGear = ref(null)
const defaultOWSGear = ref(null)
const defaultTennisGear = ref(null)
const defaultAlpineSkiGear = ref(null)
const defaultNordicSkiGear = ref(null)
const defaultSnowboardGear = ref(null)
const defaultWindsurfGear = ref(null)
const visibilityOptionsForModal = ref([
  { id: 0, name: t('settingsUserProfileZone.privacyOption1') },
  { id: 1, name: t('settingsUserProfileZone.privacyOption2') },
  { id: 2, name: t('settingsUserProfileZone.privacyOption3') }
])
const activityVisibility = ref(authStore.user.default_activity_visibility)
const activityStartTime = ref(authStore.user.hide_activity_start_time)
const activityLocation = ref(authStore.user.hide_activity_location)
const activityMap = ref(authStore.user.hide_activity_map)
const activityHr = ref(authStore.user.hide_activity_hr)
const activityPower = ref(authStore.user.hide_activity_power)
const activityCadence = ref(authStore.user.hide_activity_cadence)
const activityElevation = ref(authStore.user.hide_activity_elevation)
const activitySpeed = ref(authStore.user.hide_activity_speed)
const activityPace = ref(authStore.user.hide_activity_pace)
const activityLaps = ref(authStore.user.hide_activity_laps)
const activitySetsSteps = ref(authStore.user.hide_activity_workout_sets_steps)
const activityGear = ref(authStore.user.hide_activity_gear)

const loadingExport = ref(false)
const loadingImport = ref(false)

async function submitDeleteUserPhoto() {
  try {
    // Delete the user photo from the server
    await profile.deleteProfilePhoto()

    // Update the user photo
    const user = authStore.user
    user.photo_path = null

    // Save the user data in the local storage and in the store.
    authStore.setUser(user, authStore.session_id, locale)

    // Set the success message and show the success alert.
    push.success(t('settingsUserProfileZone.userPhotoDeleteSuccess'))
  } catch (error) {
    // Show the error message
    push.error(`${t('settingsUserProfileZone.userPhotoDeleteError')} - ${error}`)
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
    alpine_ski_gear_id: defaultAlpineSkiGear.value,
    nordic_ski_gear_id: defaultNordicSkiGear.value,
    snowboard_gear_id: defaultSnowboardGear.value,
    windsurf_gear_id: defaultWindsurfGear.value
  }
  try {
    // Update the default gear in the DB
    await userDefaultGear.editUserDefaultGear(data)

    push.success(t('settingsUserProfileZone.successUpdateDefaultGear'))
  } catch (error) {
    push.error(t('settingsUserProfileZone.errorUpdateDefaultGear'))
  }
}

async function submitChangeUserActivitiesVisibility(visibility) {
  try {
    await activities.editUserActivitiesVisibility(visibility)

    // Show the success alert.
    push.success(t('settingsUserProfileZone.successUpdateUserActivitiesVisibility'))
  } catch (error) {
    // If there is an error, show the error alert.
    push.error(`${t('settingsUserProfileZone.errorUpdateUserActivitiesVisibility')} - ${error}`)
  }
}

async function updateUserPrivacySettings() {
  const data = {
    default_activity_visibility: activityVisibility.value,
    hide_activity_start_time: activityStartTime.value,
    hide_activity_location: activityLocation.value,
    hide_activity_map: activityMap.value,
    hide_activity_hr: activityHr.value,
    hide_activity_power: activityPower.value,
    hide_activity_cadence: activityCadence.value,
    hide_activity_elevation: activityElevation.value,
    hide_activity_speed: activitySpeed.value,
    hide_activity_pace: activityPace.value,
    hide_activity_laps: activityLaps.value,
    hide_activity_workout_sets_steps: activitySetsSteps.value,
    hide_activity_gear: activityGear.value
  }
  try {
    // Update the user privacy settings in the DB
    await profile.editUserPrivacySettings(data)

    // Update the user privacy settings in the store
    authStore.user.default_activity_visibility = activityVisibility.value
    authStore.user.hide_activity_start_time = activityStartTime.value
    authStore.user.hide_activity_location = activityLocation.value
    authStore.user.hide_activity_map = activityMap.value
    authStore.user.hide_activity_hr = activityHr.value
    authStore.user.hide_activity_power = activityPower.value
    authStore.user.hide_activity_cadence = activityCadence.value
    authStore.user.hide_activity_elevation = activityElevation.value
    authStore.user.hide_activity_speed = activitySpeed.value
    authStore.user.hide_activity_pace = activityPace.value
    authStore.user.hide_activity_laps = activityLaps.value
    authStore.user.hide_activity_workout_sets_steps = activitySetsSteps.value
    authStore.user.hide_activity_gear = activityGear.value

    push.success(t('settingsUserProfileZone.successUpdateUserPrivacySettings'))
  } catch (error) {
    push.error(`${t('settingsUserProfileZone.errorUpdateUserPrivacySettings')} - ${error}`)
  }
}

async function uploadImportFile(file) {
  const notification = push.promise(t('settingsUserProfileZone.importLoading'))
  loadingImport.value = true
  try {
    await profile.importData(file)

    // Get logged user information
    const userProfile = await profile.getProfileInfo()

    // Store the user in the auth store
    authStore.setUser(userProfile, authStore.session_id, locale)

    // Get gear information
    await getGearsInfo()

    notification.resolve(t('settingsUserProfileZone.importSuccess'))
  } catch (error) {
    notification.reject(`${t('settingsUserProfileZone.importError')} - ${error}`)
  } finally {
    loadingImport.value = false
  }
}

async function handleExport() {
  const notification = push.promise(t('settingsUserProfileZone.exportLoading'))
  loadingExport.value = true
  try {
    const blob = await profile.exportData()
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `user_${authStore.user.id}_${new Date().toISOString().slice(0, 16).replace(':', '-')}_export.zip`
    a.click()
    URL.revokeObjectURL(url)
    notification.resolve(t('settingsUserProfileZone.exportSuccess'))
  } catch (error) {
    notification.reject(`${t('settingsUserProfileZone.exportError')} - ${error}`)
  } finally {
    loadingExport.value = false
  }
}

async function getDefaultGear() {
  try {
    defaultGear.value = await userDefaultGear.getUserDefaultGear()
    defaultRunGear.value = defaultGear.value.run_gear_id
    defaultTrailRunGear.value = defaultGear.value.trail_run_gear_id
    defaultVirtualRunGear.value = defaultGear.value.virtual_run_gear_id
    defaultWalkGear.value = defaultGear.value.walk_gear_id
    defaultHikeGear.value = defaultGear.value.hike_gear_id
    defaultRideGear.value = defaultGear.value.ride_gear_id
    defaultMTBRideGear.value = defaultGear.value.mtb_ride_gear_id
    defaultGravelRideGear.value = defaultGear.value.gravel_ride_gear_id
    defaultVirtualRideGear.value = defaultGear.value.virtual_ride_gear_id
    defaultOWSGear.value = defaultGear.value.ows_gear_id
    defaultTennisGear.value = defaultGear.value.tennis_gear_id
    defaultAlpineSkiGear.value = defaultGear.value.alpine_ski_gear_id
    defaultNordicSkiGear.value = defaultGear.value.nordic_ski_gear_id
    defaultSnowboardGear.value = defaultGear.value.snowboard_gear_id
    defaultWindsurfGear.value = defaultGear.value.windsurf_gear_id
  } catch (error) {
    // If there is an error, set the error message and show the error alert.
    push.error(`${t('settingsUserProfileZone.errorUnableToGetDefaultGear')} - ${error}`)
  }
}

async function getGearsInfo() {
  try {
    allGears.value = await gears.getGears()
    runGear.value = allGears.value.filter((gear) => gear.gear_type === 2)
    bikeGear.value = allGears.value.filter((gear) => gear.gear_type === 1)
    swimGear.value = allGears.value.filter((gear) => gear.gear_type === 3)
    racquetGear.value = allGears.value.filter((gear) => gear.gear_type === 4)
    skisGear.value = allGears.value.filter((gear) => gear.gear_type === 5)
    snowboardGear.value = allGears.value.filter((gear) => gear.gear_type === 6)
    windsurfGear.value = allGears.value.filter((gear) => gear.gear_type === 7)
    waterSportsBoardGear.value = allGears.value.filter((gear) => gear.gear_type === 8)

    // Get default gear for the user
    await getDefaultGear()
  } catch (error) {
    // If there is an error, set the error message and show the error alert.
    push.error(`${t('settingsUserProfileZone.errorUnableToGetGear')} - ${error}`)
  }
}

onMounted(async () => {
  isLoading.value = true
  try {
    await getGearsInfo()
  } finally {
    isLoading.value = false
    await nextTick()
    isMounted.value = true
  }
})

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
    defaultAlpineSkiGear,
    defaultNordicSkiGear,
    defaultSnowboardGear,
    defaultWindsurfGear
  ],
  async () => {
    if (!isMounted.value || isLoading.value) return
    await updateDefaultGear()
  },
  { immediate: false }
)
watch(
  [
    activityVisibility,
    activityStartTime,
    activityLocation,
    activityMap,
    activityHr,
    activityPower,
    activityCadence,
    activityElevation,
    activitySpeed,
    activityPace,
    activityLaps,
    activitySetsSteps,
    activityGear
  ],
  async () => {
    if (!isMounted.value || isLoading.value) return
    await updateUserPrivacySettings()
  },
  { immediate: false }
)
</script>

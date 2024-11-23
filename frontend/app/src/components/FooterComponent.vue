<template>
    <footer class="py-5 bg-body-tertiary">
        <div class="container">
            <div class="row align-items-center justify-content-center">
                <div class="col-md" v-if="authStore.isAuthenticated">
                    <form>
                        <label for="inputSelectTypeToSearch" class="form-label">{{ $t("footer.searchSelectLabel") }}</label>
                        <select id="inputSelectTypeToSearch" class="form-select" v-model="searchSelectValue">
                            <option value="1">{{ $t("footer.searchSelectOptionUser") }}</option>
                            <option value="2">{{ $t("footer.searchSelectOptionActivity") }}</option>
                            <option value="3">{{ $t("footer.searchSelectOptionGear") }}</option>
                        </select>
                        <br>
                        <input type="text" class="form-control" id="inputTextFieldToSearch" :placeholder='$t("footer.searchInputPlaceholder")' v-model="inputSearch">
                        <ul v-if="searchResults" class="list-group">
                            <li v-for="result in searchResults" :key="result.id" class="list-group-item list-group-item-action">
                                <!-- user link -->
                                <router-link :to="{ name: 'user', params: { id: result.id }}" class="link-body-emphasis link-underline-opacity-0 link-underline-opacity-100-hover" v-if="searchSelectValue == 1">
                                    {{ result.name}} - {{ result.username}}
                                </router-link>
                                <router-link :to="{ name: 'activity', params: { id: result.id }}" class="link-body-emphasis link-underline-opacity-0 link-underline-opacity-100-hover" v-else-if="searchSelectValue == 2">
                                    {{ result.name}}
                                </router-link>
                                <router-link :to="{ name: 'gear', params: { id: result.id }}" class="link-body-emphasis link-underline-opacity-0 link-underline-opacity-100-hover" v-else-if="searchSelectValue == 3">
                                    {{ result.nickname }}
                                </router-link>
                            </li>
                        </ul>
                    </form>
                </div>
                <div class="mt-3 col">
                    <p class="text-center text-muted">&copy; {{ new Date().getFullYear() === 2023 ? '2023' : '2023 - ' + new Date().getFullYear() }} Endurain • <a class="link-body-emphasis" href="https://github.com/joaovitoriasilva/endurain" role="button"><font-awesome-icon :icon="['fab', 'fa-github']" /></a> • <a class="link-body-emphasis" href="https://docs.endurain.com"><font-awesome-icon :icon="['fas', 'book']" /></a> • <a class="link-body-emphasis" href="https://fosstodon.org/@endurain"><font-awesome-icon :icon="['fab', 'fa-mastodon']" /></a> • v0.6.4</p>
                    <p class="text-center text-muted"><img src="/src/assets/strava/api_logo_cptblWith_strava_horiz_light.png" alt="Compatible with STRAVA image" height="25" /> • <img src="/src/assets/garminconnect/Garmin_connect_badge_print_RESOURCE_FILE-01.png" alt="Works with Garmin Connect image" height="25" /></p>
                </div>
            </div>
        </div>
    </footer>
</template>

<script>
import { watch, ref } from 'vue';
import { useRoute } from 'vue-router';
import { useI18n } from 'vue-i18n';
// Import Notivue push
import { push } from 'notivue'
// import lodash
import { debounce } from 'lodash';

import { useAuthStore } from '@/stores/authStore';

import { users } from '@/services/usersService';
import { gears } from '@/services/gearsService';
import { activities } from '@/services/activitiesService';

export default {
    setup() {
        const route = useRoute();
        const authStore = useAuthStore();
        const { t } = useI18n();
        const path = ref(route.path);
        const searchSelectValue = ref('1');
        const inputSearch = ref('');
        const searchResults = ref([]);

        const fetchUserResults = debounce(async (query) => {
            if (!query) {
                searchResults.value = [];
                return;
            }
            try {
                searchResults.value = await users.getUserByUsername(query);
            } catch (error) {
                push.error(`${t('generalItems.errorFetchingInfo')} - ${error}`)
            }
        }, 500);

        const fetchActivityResults = debounce(async (query) => {
            if (!query) {
                searchResults.value = [];
                return;
            }
            try {
                searchResults.value = await activities.getActivityByName(query);
            } catch (error) {
                push.error(`${t('generalItems.errorFetchingInfo')} - ${error}`)
            }
        }, 500);

        const fetchGearResults = debounce(async (query) => {
            if (!query) {
                searchResults.value = [];
                return;
            }
            try {
                searchResults.value = await gears.getGearByNickname(query);
            } catch (error) {
                push.error(`${t('generalItems.errorFetchingInfo')} - ${error}`)
            }
        }, 500);

        watch(() => route.path, (newPath, oldPath) => {
            path.value = newPath;
            /* reset search values */
            searchSelectValue.value = '1';
            inputSearch.value = '';
            searchResults.value = [];
        });

        watch(searchSelectValue, () => {
            inputSearch.value = '';
            searchResults.value = [];
        });

        watch(inputSearch, async (newQuery) => {
            if (searchSelectValue.value === '1') {
                await fetchUserResults(newQuery);
            } else if (searchSelectValue.value === '2') {
                await fetchActivityResults(newQuery);
            } else if (searchSelectValue.value === '3') {
                await fetchGearResults(newQuery);
            }
        });

        return {
            authStore,
            searchSelectValue,
            inputSearch,
            searchResults,
            t,
        };
    },
};
</script>
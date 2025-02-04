<template>
    <div>
        <form>
            <div class="input-group">
                <label for="inputSelectTypeToSearch" class="form-label visually-hidden">{{ $t("footer.searchSelectLabel") }}</label>
                <select id="inputSelectTypeToSearch" class="form-select" v-model="searchSelectValue">
                    <option value="1">{{ $t("footer.searchSelectOptionUser") }}</option>
                    <option value="2">{{ $t("footer.searchSelectOptionActivity") }}</option>
                    <option value="3">{{ $t("footer.searchSelectOptionGear") }}</option>
                </select>
                <div class="ms-1">
                    <input type="text" class="form-control" id="inputTextFieldToSearch" :placeholder='$t("footer.searchInputPlaceholder")' v-model="inputSearch">
                    <ul v-if="searchResults" class="list-group z-1 position-absolute">
                        <li v-for="result in searchResults" :key="result.id" class="list-group-item list-group-item-action">
                            <router-link :to="{ name: 'user', params: { id: result.id }}" class="link-body-emphasis link-underline-opacity-0 link-underline-opacity-100-hover" v-if="searchSelectValue == 1" @click="closeSearch">
                                {{ result.name}} - {{ result.username}}
                            </router-link>
                            <router-link :to="{ name: 'activity', params: { id: result.id }}" class="link-body-emphasis link-underline-opacity-0 link-underline-opacity-100-hover" v-else-if="searchSelectValue == 2" @click="closeSearch">
                                {{ result.name}}
                            </router-link>
                            <router-link :to="{ name: 'gear', params: { id: result.id }}" class="link-body-emphasis link-underline-opacity-0 link-underline-opacity-100-hover" v-else-if="searchSelectValue == 3" @click="closeSearch">
                                {{ result.nickname }}
                            </router-link>
                        </li>
                    </ul>
                </div>
            </div>
        </form>
    </div>
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
    emits: ["collapseNavbar", "toggleShowSearch"],
    setup(props, { emit }) {
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
                searchResults.value = await users.getUserContainsUsername(query);
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
                searchResults.value = await gears.getGearContainsNickname(query);
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

        const closeSearch = () => {
            emit("toggleShowSearch");
            emit("collapseNavbar");
        };

        return {
            t,
            authStore,
            searchSelectValue,
            inputSearch,
            searchResults,
            closeSearch,
        };
    },
};
</script>
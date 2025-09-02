<template>
    <div class="col">
        <div class="card mb-3 text-center shadow-sm">
            <div class="card-header">
                <h4>{{ $t("healthDashboardZoneComponent.weight") }}</h4>
            </div>
            <div class="card-body">
                <h1 v-if="currentWeight && Number(authStore?.user?.units) === 1">{{ currentWeight }} {{ $t("generalItems.unitsKg") }}</h1>
                <h1 v-else-if="currentWeight && authStore.user.units == 2">{{ kgToLbs(currentWeight) }} {{ $t("generalItems.unitsLbs") }}</h1>
                <h1 v-else>{{ $t("generalItems.labelNotApplicable") }}</h1>
            </div>
            <div class="card-footer text-body-secondary">
                <span v-if="userHealthTargets && userHealthTargets['weight']">{{ userHealthTargets.weight }}</span>
                <span v-else>{{ $t("healthDashboardZoneComponent.noWeightTarget") }}</span>
            </div>
        </div>
    </div>
    <div class="col">
        <div class="card mb-3 text-center shadow-sm">
            <div class="card-header">
                <h4>{{ $t("healthDashboardZoneComponent.bmi") }}</h4>
            </div>
            <div class="card-body">
                <h1 v-if="currentBMI">{{ currentBMI }}</h1>
                <h1 v-else>{{ $t("generalItems.labelNotApplicable") }}</h1>
            </div>
            <div class="card-footer text-body-secondary">
                <span v-if="currentBMI">{{ bmiDescription }}</span>
                <span v-else-if="!currentBMI && currentWeight">{{ $t("healthDashboardZoneComponent.noHeightDefined") }}</span>
                <span v-else>{{ $t("healthDashboardZoneComponent.noWeightData") }}</span>
            </div>
        </div>
    </div>
</template>

<script>
import { ref, onMounted } from "vue";
import { useI18n } from "vue-i18n";
// Importing the stores
import { useAuthStore } from "@/stores/authStore";
import { kgToLbs } from "@/utils/unitsUtils";

export default {
	components: {
        
	},
    props: {
        userHealthData: {
            type: [Object, null],
            required: true,
        },
        userHealthTargets: {
            type: [Object, null],
            required: true,
        },
    },
	setup(props) {
		const { t } = useI18n();
		const authStore = useAuthStore();
        const currentWeight = ref(null);
        const currentBMI = ref(null);
        const bmiDescription = ref(null);

        onMounted(async () => {
            if(props.userHealthData){
                for(const data of props.userHealthData){
                    if(data.weight){
                        currentWeight.value = data.weight;
                        currentBMI.value = data.bmi.toFixed(2);
                        break;
                    }
                }

                if(currentBMI.value){
                    if(currentBMI.value < 18.5){
                        bmiDescription.value = t("healthDashboardZoneComponent.bmiUnderweight");
                    } else if(currentBMI.value >= 18.5 && currentBMI.value < 24.9){
                        bmiDescription.value = t("healthDashboardZoneComponent.bmiNormalWeight");
                    } else if(currentBMI.value >= 25 && currentBMI.value < 29.9){
                        bmiDescription.value = t("healthDashboardZoneComponent.bmiOverweight");
                    } else if(currentBMI.value >= 30 && currentBMI.value < 34.9){
                        bmiDescription.value = t("healthDashboardZoneComponent.bmiObesityClass1");
                    } else if(currentBMI.value >= 35 && currentBMI.value < 39.9){
                        bmiDescription.value = t("healthDashboardZoneComponent.bmiObesityClass2");
                    } else if(currentBMI.value >= 40){
                        bmiDescription.value = t("healthDashboardZoneComponent.bmiObesityClass3");
                    }
                }
            }
        });


		return {
            authStore,
            currentWeight,
            currentBMI,
            bmiDescription,
            kgToLbs,
		};
	},
};
</script>
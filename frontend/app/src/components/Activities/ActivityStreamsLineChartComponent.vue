<template>
    <canvas ref="chartCanvas"></canvas>
  </template>
  
<script>
import { ref, onMounted, onUnmounted, computed, watch } from 'vue';
import { useI18n } from "vue-i18n";
// Importing the stores
import { useAuthStore } from "@/stores/authStore";
import { useServerSettingsStore } from '@/stores/serverSettingsStore';
import { Chart, registerables } from 'chart.js';
Chart.register(...registerables);

import { formatAverageSpeedMetric, formatAverageSpeedImperial } from "@/utils/activityUtils";
import { metersToFeet, kmToMiles } from "@/utils/unitsUtils";
  
export default {
    props: {
        activity: {
            type: Object,
            required: true,
        },
        graphSelection: {
            type: String,
            required: true,
        },
        activityStreams: {
            type: Array,
            required: true,
        }
    },
    setup(props) {
		const { t } = useI18n();
		const authStore = useAuthStore();
        const serverSettingsStore = useServerSettingsStore();
        const chartCanvas = ref(null);
        const units = ref(1);
        let myChart = null;
        const computedChartData = computed(() => {
            const data = [];
            let label = "";
            const labels = [];
            let roundValues = true;

            if (authStore.isAuthenticated) {
                units.value = authStore.user.units;
            } else {
                units.value = serverSettingsStore.serverSettings.units;
            }

            for (const stream of props.activityStreams) {
                if (stream.stream_type === 1 && props.graphSelection === 'hr') {
                    for (const streamPoint of stream.stream_waypoints) {
                        data.push(Number.parseInt(streamPoint.hr));
                        label = t("generalItems.labelHRinBpm");
                    }
                } else if (stream.stream_type === 2 && props.graphSelection === 'power') {
                    for (const streamPoint of stream.stream_waypoints) {
                        data.push(Number.parseInt(streamPoint.power));
                        label = t("generalItems.labelPowerInWatts");
                    }
                } else if (stream.stream_type === 3 && props.graphSelection === 'cad') {
                    for (const streamPoint of stream.stream_waypoints) {
                        data.push(Number.parseInt(streamPoint.cad));
                        // Label as "Stroke Rate" over "Cadence" for swimming activities
                        // TODO: Add translation
                        label = props.activity.activity_type === 8 || props.activity.activity_type === 9 ? "Stroke Rate in spm" : t("generalItems.labelCadenceInRpm");
                    }
                } else if (stream.stream_type === 4 && props.graphSelection === 'ele') {
                    for (const streamPoint of stream.stream_waypoints) {
                        if (Number(units.value) === 1) {
                            data.push(Number.parseFloat(streamPoint.ele));
                            label = t("generalItems.labelElevationInMeters");
                        } else {
                            data.push(Number.parseFloat(metersToFeet(streamPoint.ele)));
                            label = t("generalItems.labelElevationInFeet");
                        }
                    }
                } else if (stream.stream_type === 5 && props.graphSelection === 'vel') {
                    if (Number(units.value) === 1) {
                        data.push(...stream.stream_waypoints.map(velData => Number.parseFloat(formatAverageSpeedMetric(velData.vel))));
                        label = t("generalItems.labelVelocityInKmH");
                    } else {
                        data.push(...stream.stream_waypoints.map(velData => Number.parseFloat(formatAverageSpeedImperial(velData.vel))));
                        label = t("generalItems.labelVelocityInMph");
                    }
                } else if (stream.stream_type === 6 && props.graphSelection === 'pace') {
                    roundValues = false;
                    for (const paceData of stream.stream_waypoints) {
                        if (paceData.pace === 0 || paceData.pace === null) {
                            data.push(0);
                        } else {
                            if (props.activity.activity_type === 1 || props.activity.activity_type === 2 || props.activity.activity_type === 3) {
                                if (Number(units.value) === 1) {
                                    data.push((paceData.pace * 1000) / 60);
                                } else {
                                    data.push((paceData.pace * 1609.34) / 60);
                                }
                            } else if (props.activity.activity_type === 8 || props.activity.activity_type === 9) {
                                if (Number(units.value) === 1) {
                                    data.push((paceData.pace * 100) / 60);
                                } else {
                                    data.push((paceData.pace * 100 * 0.9144) / 60);
                                }
                            }
                        }
                    }
                    if (props.activity.activity_type === 1 || props.activity.activity_type === 2 || props.activity.activity_type === 3) {
                        if (Number(units.value) === 1) {
                            label = t("generalItems.labelPaceInMinKm");
                        } else {
                            label = t("generalItems.labelPaceInMinMile");
                        }
                    } else if (props.activity.activity_type === 8 || props.activity.activity_type === 9) {
                        if (Number(units.value) === 1) {
                            label = t("generalItems.labelPaceInMin100m");
                        } else {
                            label = t("generalItems.labelPaceInMin100yd");
                        }
                    }
                }
            }

            const dataDS = downsampleData(data, 200, roundValues);
            
            const totalDistance = props.activity.distance / 1000;
            const numberOfDataPoints = dataDS.length;
            const distanceInterval = totalDistance / numberOfDataPoints;

            for (let i = 0; i < numberOfDataPoints; i++) {
                if (Number(units.value) === 1) {
                    if (props.activity.activity_type === 8 || props.activity.activity_type === 9) {
                        labels.push(`${(i * distanceInterval).toFixed(1)}km`);
                    } else {
                        labels.push(`${(i * distanceInterval).toFixed(0)}km`);
                    }
                } else {
                    if (props.activity.activity_type === 8 || props.activity.activity_type === 9) {
                        labels.push(`${(i * distanceInterval).toFixed(1)}mi`);
                    } else {
                        labels.push(`${(i * kmToMiles(distanceInterval)).toFixed(0)}mi`);
                    }
                }
            }

            return {
                datasets: [{
                    label: label,
                    data: dataDS,
                }],
                labels: labels,
            };
        });

        watch(computedChartData, (newChartData) => {
            if (myChart.value) {
                myChart.value.data.datasets = newChartData.datasets;
                myChart.data.labels = newChartData.labels;
                myChart.value.update();
            }
        }, { deep: true });

        function downsampleData(data, threshold, roundValues) {
            if (data.length <= threshold) {
                return data;
            }

            const factor = Math.ceil(data.length / threshold);
            const downsampledData = [];

            for (let i = 0; i < data.length; i += factor) {
                const chunk = data.slice(i, i + factor);
                const average = chunk.reduce((a, b) => a + b) / chunk.length;
                if (roundValues) {
                    downsampledData.push(Number.parseInt(average));
                }else{
                    downsampledData.push(average);
                }
            }

            return downsampledData;
        }

        onMounted(() => {
            myChart = new Chart(chartCanvas.value.getContext('2d'), {
                type: 'line',
                data: computedChartData.value,
                options: {
                    responsive: true,
                    scales: {
                        y: { 
                            beginAtZero: false 
                        },
                        x: { 
                            autoSkip: true 
                        }
                    } 
                },
            });
        });

        onUnmounted(() => {
            if (myChart.value) {
                myChart.value.destroy();
            }
        });
    
        return {
            chartCanvas
        };
    }
}
</script>
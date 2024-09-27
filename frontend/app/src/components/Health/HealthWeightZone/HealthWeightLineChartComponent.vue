<template>
    <LoadingComponent v-if="isLoading" />
    <canvas ref="chartCanvas" v-else></canvas>
  </template>
  
<script>
import { ref, onMounted, onUnmounted, computed, watch, watchEffect } from 'vue';

import LoadingComponent from '@/components/GeneralComponents/LoadingComponent.vue';

import { Chart, registerables } from 'chart.js';
Chart.register(...registerables);
  
export default {
    components: {
        LoadingComponent
    },
    props: {
        userHealthData: {
            type: Object,
            required: true,
        },
        isLoading: {
            type: Boolean,
            required: true,
        }
    },
    setup(props) {
        const sortedHealthDataArray = ref([]);
        const chartCanvas = ref(null);
        let myChart = null;
        const computedChartData = ref(null);

        function updatedSortedArray(){
            sortedHealthDataArray.value = props.userHealthData;
            sortedHealthDataArray.value.sort((a, b) => {
                return new Date(a.created_at) - new Date(b.created_at);
            });

            if (sortedHealthDataArray.value){
                computedChartData.value = computed(() => {
                    const data = [];
                    const labels = [];
                    for (let healthData of sortedHealthDataArray.value){
                        data.push(healthData.weight)
                        const createdAt = new Date(healthData.created_at);
                        labels.push(`${createdAt.getDate()}/${createdAt.getMonth()+1}/${createdAt.getFullYear()}`)
                    }
                    let label = "Weight in kgs";

                    return {
                        datasets: [{
                            label: label,
                            data: data,
                        }],
                        labels: labels,
                    };
                });
            }
        }

        watchEffect(() => {
            if (props.userHealthData) {
                updatedSortedArray();
            }
        });

        watch(computedChartData.value, (newChartData) => {
            if (myChart) {
                myChart.config.data = newChartData;
                myChart.update();
            }
        }, { deep: true });

        onMounted(() => {
            myChart = new Chart(chartCanvas.value.getContext('2d'), {
                type: 'line',
                data: computedChartData.value,
                options: {
                    responsive: true,
                    scales: {
                        y: { 
                            beginAtZero: false,
                        },
                        x: { 
                            autoSkip: true 
                        }
                    } 
                },
            });
            updatedSortedArray();
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
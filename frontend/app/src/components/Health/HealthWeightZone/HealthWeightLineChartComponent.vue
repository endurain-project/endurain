<template>
    <LoadingComponent v-if="isLoading" />
    <canvas ref="chartCanvas" v-else></canvas>
  </template>
  
<script>
import { ref, onMounted, onUnmounted, computed, watch } from 'vue';

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
        const chartCanvas = ref(null);
        let myChart = null;
        const computedChartData = computed(() => {
            const data = [];
            const labels = [];
            for (let healthData of props.userHealthData){
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

        watch(computedChartData, (newChartData) => {
            if (myChart.value) {
                myChart.value.data.datasets = newChartData.datasets;
                myChart.value.update();
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
                            //min: Math.min(...props.userHealthData.map(health => health.weight)) - 5,
                            //max: Math.max(...props.userHealthData.map(health => health.weight)) + 5
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
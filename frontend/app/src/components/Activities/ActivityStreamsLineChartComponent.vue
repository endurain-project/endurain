<template>
    <canvas ref="chartCanvas"></canvas>
  </template>
  
<script>
import { ref, onMounted, onUnmounted, computed, watch } from 'vue';
import { Chart, registerables } from 'chart.js';
Chart.register(...registerables);
  
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
        const chartCanvas = ref(null);
        let myChart = null;
        const computedChartData = computed(() => {
            const data = [];
            let label = "";
            const labels = [];
            let roundValues = true;

            for (const stream of props.activityStreams) {
                if (stream.stream_type === 1 && props.graphSelection === 'hr') {
                    for (const streamPoint of stream.stream_waypoints) {
                        data.push(Number.parseInt(streamPoint.hr));
                        label = "Heart Rate (bpm)";
                    }
                } else if (stream.stream_type === 2 && props.graphSelection === 'power') {
                    for (const streamPoint of stream.stream_waypoints) {
                        data.push(Number.parseInt(streamPoint.power));
                        label = "Power (Watts)";
                    }
                } else if (stream.stream_type === 3 && props.graphSelection === 'cad') {
                    for (const streamPoint of stream.stream_waypoints) {
                        data.push(Number.parseInt(streamPoint.cad));
                        label = "Cadence (rpm)";
                    }
                } else if (stream.stream_type === 4 && props.graphSelection === 'ele') {
                    for (const streamPoint of stream.stream_waypoints) {
                        data.push(Number.parseFloat(streamPoint.ele));
                        label = "Elevation (m)";
                    }
                } else if (stream.stream_type === 5 && props.graphSelection === 'vel') {
                    data.push(...stream.stream_waypoints.map(velData => Number.parseFloat((velData.vel * 3.6).toFixed(0))));
                    label = "Velocity (km/h)";
                } else if (stream.stream_type === 6 && props.graphSelection === 'pace') {
                    roundValues = false;
                    for (const paceData of stream.stream_waypoints) {
                        if (paceData.pace === 0 || paceData.pace === null) {
                            data.push(0);
                        } else {
                            if (props.activity.activity_type === 1 || props.activity.activity_type === 2 || props.activity.activity_type === 3) {
                                data.push((paceData.pace * 1000) / 60);
                            } else if (props.activity.activity_type === 8 || props.activity.activity_type === 9) {
                                data.push((paceData.pace * 100) / 60);
                            }
                        }
                    }
                    if (props.activity.activity_type === 1 || props.activity.activity_type === 2 || props.activity.activity_type === 3) {
                        label = "Pace (min/km)";
                    } else if (props.activity.activity_type === 8 || props.activity.activity_type === 9) {
                        label = "Pace (min/100m)";
                    }
                }
            }

            const dataDS = downsampleData(data, 200, roundValues);
            
            const totalDistance = props.activity.distance / 1000;
            const numberOfDataPoints = dataDS.length;
            const distanceInterval = totalDistance / numberOfDataPoints;

            for (let i = 0; i < numberOfDataPoints; i++) {
                labels.push(`${(i * distanceInterval).toFixed(0)}km`);
                /* if (props.graphSelection == 'pace') {
                    let paceCalculated = 0;
                    if (props.activity.activity_type == 1 || props.activity.activity_type == 2 || props.activity.activity_type == 3) {
                        paceCalculated = (dataDS[i] * 1000) / 60;
                    } else if (props.activity.activity_type == 8 || props.activity.activity_type == 9) {
                        paceCalculated = (dataDS[i] * 100) / 60;
                    }
                    const minutes = Math.floor(paceCalculated);
                    const seconds = Math.round((paceCalculated - minutes) * 60);
                    dataDS[i] = `${minutes}:${seconds.toString().padStart(2, '0')}`;
                } */
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
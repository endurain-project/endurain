<template>
  <canvas ref="chartCanvas" class="chart-canvas"></canvas>
</template>

<script setup>
import { ref, onMounted, onUnmounted, watch, computed } from 'vue'
import { useI18n } from 'vue-i18n'

import { Chart, registerables } from 'chart.js'
import 'chartjs-adapter-date-fns'
import { formatTime, formatDuration } from '@/utils/dateTimeUtils'

Chart.register(...registerables)

const props = defineProps({
  sleepStages: {
    type: Array,
    required: true
  }
})

const { t } = useI18n()
const chartCanvas = ref(null)
let myChart = null

// Y-axis labels for sleep stages (internationalized)
const yAxisLabels = computed(() => [
  t('generalItems.labelDeep'),
  t('generalItems.labelLight'),
  t('generalItems.labelREM'),
  t('generalItems.labelAwake')
])

// Sleep stage mapping with vertical positioning
const SLEEP_STAGES = {
  3: { name: 'Awake', color: 'rgba(156, 163, 175, 0.8)', yPos: 3, label: yAxisLabels.value[3] }, // Gray
  2: { name: 'REM', color: 'rgba(96, 165, 250, 0.8)', yPos: 2, label: yAxisLabels.value[2] }, // Light Blue
  1: { name: 'Light', color: 'rgba(37, 99, 235, 0.8)', yPos: 1, label: yAxisLabels.value[1] }, // Medium Blue
  0: { name: 'Deep', color: 'rgba(30, 64, 175, 0.8)', yPos: 0, label: yAxisLabels.value[0] } // Dark Blue
}

const chartData = computed(() => {
  if (!props.sleepStages || props.sleepStages.length === 0) {
    return { datasets: [] }
  }

  // Sort stages by time
  const sortedStages = [...props.sleepStages].sort(
    (a, b) => new Date(a.start_time_gmt) - new Date(b.start_time_gmt)
  )

  // Create segments with all necessary data
  const allSegments = sortedStages.map((stage) => {
    const startTime = new Date(stage.start_time_gmt)
    const endTime = new Date(stage.end_time_gmt)
    const stageInfo = SLEEP_STAGES[stage.stage_type]

    return {
      x: [startTime, endTime],
      y: stageInfo.yPos,
      stage: stageInfo.name,
      startTimeStr: formatTime(stage.start_time_gmt),
      endTimeStr: formatTime(stage.end_time_gmt),
      duration: stage.duration_seconds,
      backgroundColor: stageInfo.color,
      stageType: stage.stage_type
    }
  })

  // Return single dataset with all segments
  return {
    datasets: [
      {
        label: t('generalItems.labelSleep'),
        data: allSegments,
        backgroundColor: function (context) {
          return context.raw?.backgroundColor || 'rgba(59, 130, 246, 0.8)'
        },
        borderWidth: 0,
        borderRadius: 0,
        barThickness: 40
      }
    ]
  }
})

watch(
  chartData,
  (newChartData) => {
    if (myChart) {
      myChart.data = newChartData
      myChart.update()
    }
  },
  { deep: true }
)

watch(
  () => props.sleepStages,
  () => {
    if (myChart) {
      myChart.options.scales.y.ticks.callback = function (value) {
        return yAxisLabels.value[value] || ''
      }
      myChart.update()
    }
  },
  { deep: true }
)

// Watch for language changes to update y-axis labels and legend
watch(yAxisLabels, () => {
  if (myChart) {
    myChart.options.scales.y.ticks.callback = function (value) {
      return yAxisLabels.value[value] || ''
    }
    myChart.update()
  }
})

onMounted(() => {
  myChart = new Chart(chartCanvas.value.getContext('2d'), {
    type: 'bar',
    data: chartData.value,
    options: {
      indexAxis: 'y',
      responsive: true,
      animation: false,
      interaction: {
        mode: 'nearest',
        intersect: true
      },
      scales: {
        y: {
          type: 'linear',
          min: 0,
          max: 3,
          ticks: {
            stepSize: 1,
            callback: function (value) {
              return yAxisLabels.value[value] || ''
            },
            font: {
              size: 12
            },
            color: '#666'
          },
          grid: {
            display: true,
            drawBorder: true,
            color: 'rgba(200, 200, 200, 0.3)'
          }
        },
        x: {
          type: 'time',
          time: {
            unit: 'hour',
            displayFormats: {
              hour: 'HH:mm'
            },
            tooltipFormat: 'HH:mm'
          },
          title: {
            display: false
          },
          grid: {
            display: true,
            drawBorder: true,
            color: 'rgba(200, 200, 200, 0.3)'
          }
        }
      },
      plugins: {
        legend: {
          display: true,
          position: 'top',
          labels: {
            font: {
              size: 12
            },
            generateLabels: function () {
              return [
                {
                  text: yAxisLabels.value[0], // Deep
                  fillStyle: SLEEP_STAGES[0].color,
                  fontColor: '#666',
                  hidden: false,
                  index: 0,
                  strokeStyle: 'transparent',
                  lineWidth: 0
                },
                {
                  text: yAxisLabels.value[1], // Light
                  fillStyle: SLEEP_STAGES[1].color,
                  fontColor: '#666',
                  hidden: false,
                  index: 1,
                  strokeStyle: 'transparent',
                  lineWidth: 0
                },
                {
                  text: yAxisLabels.value[2], // REM
                  fillStyle: SLEEP_STAGES[2].color,
                  fontColor: '#666',
                  hidden: false,
                  index: 2,
                  strokeStyle: 'transparent',
                  lineWidth: 0
                },
                {
                  text: yAxisLabels.value[3], // Awake
                  fillStyle: SLEEP_STAGES[3].color,
                  fontColor: '#666',
                  hidden: false,
                  index: 3,
                  strokeStyle: 'transparent',
                  lineWidth: 0
                }
              ]
            }
          }
        },
        tooltip: {
          enabled: true,
          callbacks: {
            title: function (context) {
              return `${context[0].raw.stage} sleep`
            },
            label: function (context) {
              const dataPoint = context.raw
              return [
                `Start: ${dataPoint.startTimeStr}`,
                `End: ${dataPoint.endTimeStr}`,
                `Duration: ${formatDuration(dataPoint.duration)}`
              ]
            }
          }
        }
      }
    }
  })
})

onUnmounted(() => {
  if (myChart) {
    myChart.destroy()
  }
})
</script>

<style scoped>
.chart-canvas {
  max-height: 300px;
  width: 100%;
}
</style>

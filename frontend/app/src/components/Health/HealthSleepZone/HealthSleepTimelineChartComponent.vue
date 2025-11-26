<template>
  <canvas ref="chartCanvas" class="chart-canvas"></canvas>
</template>

<script setup>
import { ref, onMounted, onUnmounted, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import { Chart, registerables } from 'chart.js'
import 'chartjs-adapter-date-fns'
import { formatTime, formatDuration } from '@/utils/dateTimeUtils'

Chart.register(...registerables)

const props = defineProps({
  sleepStages: {
    type: Array,
    required: true
  },
})

const { t } = useI18n()
const chartCanvas = ref(null)
let myChart = null

// Sleep stage mapping with vertical positioning
const SLEEP_STAGES = {
  3: { name: 'Awake', color: 'rgba(156, 163, 175, 0.8)', yPos: 3 },    // Gray
  2: { name: 'REM', color: 'rgba(96, 165, 250, 0.8)', yPos: 2 },       // Light Blue
  1: { name: 'Light', color: 'rgba(37, 99, 235, 0.8)', yPos: 1 },      // Medium Blue
  0: { name: 'Deep', color: 'rgba(30, 64, 175, 0.8)', yPos: 0 }        // Dark Blue
}

// Custom crosshair plugin
const crosshairPlugin = {
  id: 'customCrosshair',
  afterDraw: (chart) => {
    if (chart.tooltip?._active && chart.tooltip._active.length) {
      const ctx = chart.ctx
      const activePoint = chart.tooltip._active[0]
      const x = activePoint.element.x
      const topY = chart.scales.y.top
      const bottomY = chart.scales.y.bottom

      // Draw vertical line
      ctx.save()
      ctx.beginPath()
      ctx.setLineDash([5, 5])
      ctx.moveTo(x, topY)
      ctx.lineTo(x, bottomY)
      ctx.lineWidth = 1
      ctx.strokeStyle = 'rgba(0, 0, 0, 0.3)'
      ctx.stroke()
      ctx.restore()
    }
  }
}

function prepareChartData() {
  if (!props.sleepStages || props.sleepStages.length === 0) {
    return { datasets: [] }
  }

  // Sort stages by time
  const sortedStages = [...props.sleepStages].sort((a, b) => 
    new Date(a.start_time_gmt) - new Date(b.start_time_gmt)
  )

  // Create a single dataset with all segments
  const allSegments = sortedStages.map(stage => {
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
      color: stageInfo.color,
      stageType: stage.stage_type
    }
  })

  return {
    datasets: [{
      label: 'Sleep Stages',
      data: allSegments,
      backgroundColor: function(context) {
        return context.raw?.color || 'rgba(59, 130, 246, 0.8)'
      },
      borderWidth: 0,
      borderRadius: 0,
      barThickness: 40
    }]
  }
}

function updateChart() {
  if (myChart) {
    myChart.data = prepareChartData()
    myChart.update()
  }
}

watch(() => props.sleepStages, () => {
  updateChart()
}, { deep: true })

onMounted(() => {
  myChart = new Chart(chartCanvas.value.getContext('2d'), {
    type: 'bar',
    data: prepareChartData(),
    options: {
      indexAxis: 'y',
      responsive: true,
      animation: false,
      interaction: {
        mode: 'nearest',
        intersect: true
      },
      scales: {
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
        },
        y: {
          type: 'linear',
          min: 0,
          max: 3,
          ticks: {
            stepSize: 1,
            callback: function(value) {
              const labels = ['Deep', 'Light', 'REM', 'Awake']
              return labels[value] || ''
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
        }
      },
      plugins: {
        legend: {
          display: false
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

<template>
  <canvas ref="chartCanvas"></canvas>
</template>

<script>
import { ref, onMounted, onUnmounted, computed, watch } from 'vue'
import { useI18n } from 'vue-i18n'
// Importing the stores
import { useAuthStore } from '@/stores/authStore'
import { useServerSettingsStore } from '@/stores/serverSettingsStore'
import { Chart, registerables } from 'chart.js'
Chart.register(...registerables)

import {
  formatAverageSpeedMetric,
  formatAverageSpeedImperial,
  activityTypeIsSwimming,
  activityTypeIsRunning
} from '@/utils/activityUtils'
import { metersToFeet, kmToMiles } from '@/utils/unitsUtils'

export default {
  props: {
    activity: {
      type: Object,
      required: true
    },
    graphSelection: {
      type: String,
      required: true
    },
    activityStreams: {
      type: Array,
      required: true
    }
  },
  setup(props) {
    const { t } = useI18n()
    const authStore = useAuthStore()
    const serverSettingsStore = useServerSettingsStore()
    const chartCanvas = ref(null)
    const units = ref(1)
    let myChart = null
    const computedChartData = computed(() => {
      const data = []
      let label = ''
      const cadData = []
      let cadLabel = ''
      const labels = []
      let roundValues = true

      if (authStore.isAuthenticated) {
        units.value = authStore.user.units
      } else {
        units.value = serverSettingsStore.serverSettings.units
      }

      for (const stream of props.activityStreams) {
        // Save Cadence (Stroke Rate) data for swimming rest detection
        if (stream.stream_type === 3) {
          for (const streamPoint of stream.stream_waypoints) {
            cadData.push(Number.parseInt(streamPoint.cad))
          }
          if (cadData.length > 0) {
            cadLabel = activityTypeIsSwimming(props.activity)
              ? t('generalItems.labelStrokeRateInSpm')
              : t('generalItems.labelCadenceInRpm')
          }
        }
        // Add data points
        if (stream.stream_type === 1 && props.graphSelection === 'hr') {
          for (const streamPoint of stream.stream_waypoints) {
            data.push(Number.parseInt(streamPoint.hr))
            label = t('generalItems.labelHRinBpm')
          }
        } else if (stream.stream_type === 2 && props.graphSelection === 'power') {
          for (const streamPoint of stream.stream_waypoints) {
            data.push(Number.parseInt(streamPoint.power))
            label = t('generalItems.labelPowerInWatts')
          }
        } else if (stream.stream_type === 3 && props.graphSelection === 'cad') {
          for (const streamPoint of stream.stream_waypoints) {
            data.push(Number.parseInt(streamPoint.cad))
            // Label as "Stroke Rate" over "Cadence" for swimming activities
            label = activityTypeIsSwimming(props.activity)
              ? t('generalItems.labelStrokeRateInSpm')
              : t('generalItems.labelCadenceInRpm')
          }
        } else if (stream.stream_type === 4 && props.graphSelection === 'ele') {
          for (const streamPoint of stream.stream_waypoints) {
            if (Number(units.value) === 1) {
              data.push(Number.parseFloat(streamPoint.ele))
              label = t('generalItems.labelElevationInMeters')
            } else {
              data.push(Number.parseFloat(metersToFeet(streamPoint.ele)))
              label = t('generalItems.labelElevationInFeet')
            }
          }
        } else if (stream.stream_type === 5 && props.graphSelection === 'vel') {
          if (Number(units.value) === 1) {
            data.push(
              ...stream.stream_waypoints.map((velData) =>
                Number.parseFloat(formatAverageSpeedMetric(velData.vel))
              )
            )
            label = t('generalItems.labelVelocityInKmH')
          } else {
            data.push(
              ...stream.stream_waypoints.map((velData) =>
                Number.parseFloat(formatAverageSpeedImperial(velData.vel))
              )
            )
            label = t('generalItems.labelVelocityInMph')
          }
        } else if (stream.stream_type === 6 && props.graphSelection === 'pace') {
          roundValues = false
          for (const paceData of stream.stream_waypoints) {
            if (paceData.pace === 0 || paceData.pace === null) {
              data.push(0)
            } else {
              if (activityTypeIsRunning(props.activity)) {
                if (Number(units.value) === 1) {
                  data.push((paceData.pace * 1000) / 60)
                } else {
                  data.push((paceData.pace * 1609.34) / 60)
                }
              } else if (activityTypeIsSwimming(props.activity)) {
                if (Number(units.value) === 1) {
                  data.push((paceData.pace * 100) / 60)
                } else {
                  data.push((paceData.pace * 100 * 0.9144) / 60)
                }
              }
            }
          }
          if (activityTypeIsRunning(props.activity)) {
            if (Number(units.value) === 1) {
              label = t('generalItems.labelPaceInMinKm')
            } else {
              label = t('generalItems.labelPaceInMinMile')
            }
          } else if (activityTypeIsSwimming(props.activity)) {
            if (Number(units.value) === 1) {
              label = t('generalItems.labelPaceInMin100m')
            } else {
              label = t('generalItems.labelPaceInMin100yd')
            }
          }
        }
      }

      const dataDS = downsampleData(data, 200, roundValues)
      const cadDataDS = downsampleData(cadData, 200, true)

      const totalDistance = props.activity.distance / 1000
      const numberOfDataPoints = dataDS.length
      const distanceInterval = totalDistance / numberOfDataPoints

      for (let i = 0; i < numberOfDataPoints; i++) {
        if (Number(units.value) === 1) {
          if (activityTypeIsSwimming(props.activity)) {
            labels.push(`${(i * distanceInterval).toFixed(1)}km`)
          } else {
            labels.push(`${(i * distanceInterval).toFixed(0)}km`)
          }
        } else {
          if (activityTypeIsSwimming(props.activity)) {
            labels.push(`${(i * distanceInterval).toFixed(1)}mi`)
          } else {
            labels.push(`${(i * kmToMiles(distanceInterval)).toFixed(0)}mi`)
          }
        }
      }

      const datasets = [
        {
          label: label,
          data: dataDS,
          yAxisID: 'y',
          backgroundColor: 'transparent',
          borderColor: 'rgba(54, 162, 235, 0.8)',
          fill: true,
          fillColor: 'rgba(54, 162, 235, 0.2)'
        }
      ]

      // Only push laps 'background shading' if there is cadence data and indoor swimming activity
      if (cadDataDS.length > 0 && props.activity.activity_type === 8) {
        datasets.push({
          type: 'bar',
          label: t('generalItems.labelLaps'),
          data: cadDataDS.map((d) => (d === 0 ? 0 : 1)),
          yAxisID: 'y1',
          backgroundColor: 'rgba(0, 0, 0, 0.2)',
          fill: true,
          fillColor: 'rgba(0, 0, 0, 0.2)',
          borderWidth: 0,
          barThickness: 5
        })
      }

      return {
        datasets: datasets,
        labels: labels
      }
    })

    watch(
      computedChartData,
      (newChartData) => {
        if (myChart.value) {
          myChart.value.data.datasets = newChartData.datasets
          myChart.data.labels = newChartData.labels
          myChart.value.update()
        }
      },
      { deep: true }
    )

    function downsampleData(data, threshold, roundValues) {
      if (data.length <= threshold) {
        return data
      }

      const factor = Math.ceil(data.length / threshold)
      const downsampledData = []

      for (let i = 0; i < data.length; i += factor) {
        const chunk = data.slice(i, i + factor)
        const average = chunk.reduce((a, b) => a + b) / chunk.length
        if (roundValues) {
          downsampledData.push(Number.parseInt(average))
        } else {
          downsampledData.push(average)
        }
      }

      return downsampledData
    }

    onMounted(() => {
      myChart = new Chart(chartCanvas.value.getContext('2d'), {
        type: 'line',
        data: computedChartData.value,
        options: {
          responsive: true,
          scales: {
            y: {
              beginAtZero: false,
              position: 'left'
            },
            y1: {
              beginAtZero: true,
              max: 1,
              display: false
            },
            x: {
              autoSkip: true
            }
          }
        }
      })
    })

    onUnmounted(() => {
      if (myChart.value) {
        myChart.value.destroy()
      }
    })

    return {
      chartCanvas,
      activityTypeIsSwimming
    }
  }
}
</script>

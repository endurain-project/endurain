<template>
  <LoadingComponent v-if="isLoading" />
  <canvas ref="chartCanvas" class="chart-canvas" v-else></canvas>
</template>

<script>
import { ref, onMounted, onUnmounted, computed, watch, watchEffect } from 'vue'
import { useI18n } from 'vue-i18n'
// Importing the stores
import { useAuthStore } from '@/stores/authStore'
import { kgToLbs } from '@/utils/unitsUtils'
// Import the components
import LoadingComponent from '@/components/GeneralComponents/LoadingComponent.vue'

import { Chart, registerables } from 'chart.js'
Chart.register(...registerables)

export default {
  components: {
    LoadingComponent
  },
  props: {
    userHealthData: {
      type: Object,
      required: true
    },
    isLoading: {
      type: Boolean,
      required: true
    }
  },
  setup(props) {
    const { t } = useI18n()
    const authStore = useAuthStore()
    const sortedHealthDataArray = ref([])
    const chartCanvas = ref(null)
    let myChart = null
    const computedChartData = ref(null)

    function updatedSortedArray() {
      sortedHealthDataArray.value = props.userHealthData
      sortedHealthDataArray.value.sort((a, b) => {
        return new Date(a.date) - new Date(b.date)
      })

      if (sortedHealthDataArray.value) {
        computedChartData.value = computed(() => {
          const data = []
          const labels = []
          for (const healthData of sortedHealthDataArray.value) {
            if (Number(authStore?.user?.units) === 1) {
              data.push(healthData.weight)
            } else {
              data.push(kgToLbs(healthData.weight))
            }

            const createdAt = new Date(healthData.date)
            labels.push(
              `${createdAt.getDate()}/${createdAt.getMonth() + 1}/${createdAt.getFullYear()}`
            )
          }
          let label = ''
          if (Number(authStore?.user?.units) === 1) {
            label = t('generalItems.labelWeightInKg')
          } else {
            label = t('generalItems.labelWeightInLbs')
          }

          return {
            datasets: [
              {
                label: label,
                data: data
              }
            ],
            labels: labels
          }
        })
      }
    }

    watchEffect(() => {
      if (props.userHealthData) {
        updatedSortedArray()
      }
    })

    watch(
      computedChartData.value,
      (newChartData) => {
        if (myChart) {
          myChart.config.data = newChartData
          myChart.update()
        }
      },
      { deep: true }
    )

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
        }
      })
      updatedSortedArray()
    })

    onUnmounted(() => {
      if (myChart.value) {
        myChart.value.destroy()
      }
    })

    return {
      chartCanvas
    }
  }
}
</script>

<style scoped>
.chart-canvas {
  max-height: 300px;
  width: 100%; /* Ensures the canvas stretches across the available width */
}
</style>

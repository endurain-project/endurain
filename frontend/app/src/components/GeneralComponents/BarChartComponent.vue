<template>
  <div>
    <canvas ref="barChartCanvas"></canvas>
  </div>
</template>

<script setup>
import { ref, onMounted, watch } from 'vue'
import { Chart, registerables } from 'chart.js'
import ChartDataLabels from 'chartjs-plugin-datalabels'

Chart.register(...registerables)

const props = defineProps({
  labels: {
    type: Array,
    required: true
  },
  values: {
    type: Array,
    required: true
  },
  barColors: {
    type: Array,
    default: () => ['#1e90ff', '#28a745', '#ffc107', '#fd7e14', '#dc3545']
  },
  title: {
    type: String,
    default: ''
  },
  datalabelsFormatter: {
    type: Function,
    default: null
  },
  timeSeconds: {
    type: Array,
    default: () => []
  }
})

const barChartCanvas = ref(null)
let chartInstance = null

function renderChart() {
  if (chartInstance) {
    chartInstance.destroy()
  }
  chartInstance = new Chart(barChartCanvas.value, {
    type: 'bar',
    data: {
      labels: props.labels,
      datasets: [
        {
          label: props.title,
          data: props.values,
          backgroundColor: props.barColors
        }
      ]
    },
    options: {
      indexAxis: 'y',
      responsive: true,
      plugins: {
        legend: { display: false },
        title: {
          display: props.title,
          text: props.title
        },
        tooltip: { enabled: false },
        datalabels: {
          backgroundColor: function (context) {
            return 'black'
          },
          borderRadius: 4,
          color: 'white',
          align: 'end', // Align datalabels to the end of the bar
          anchor: 'end', // Anchor datalabels to the end of the bar
          formatter: props.datalabelsFormatter || undefined,
          padding: 6
        }
      },
      scales: {
        y: {
          beginAtZero: true,
          ticks: { stepSize: 10 }
        }
      }
    },
    plugins: [ChartDataLabels]
  })
}

onMounted(() => {
  renderChart()
})

watch(() => [props.labels, props.values, props.barColors, props.title], renderChart, { deep: true })
</script>

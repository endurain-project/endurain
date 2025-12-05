<template>
    <!-- Modal add/edit sleep -->
    <div class="modal fade" :id="action === 'add' ? 'addSleepModal' : action === 'edit' ? editSleepId : ''"
        tabindex="-1" :aria-labelledby="action === 'add' ? 'addSleepModal' : action === 'edit' ? editSleepId : ''"
        aria-hidden="true">
        <div class="modal-dialog">
            <div class="modal-content">
                <div class="modal-header">
                    <h1 class="modal-title fs-5" id="addSleepModal" v-if="action === 'add'">
                        {{ $t('healthSleepAddEditModalComponent.addSleepModalTitle') }}
                    </h1>
                    <h1 class="modal-title fs-5" :id="editSleepId" v-else>
                        {{ $t('healthSleepAddEditModalComponent.editSleepModalTitle') }}
                    </h1>
                    <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
                </div>
                <form @submit.prevent="handleSubmit">
                    <div class="modal-body">
                        <!-- Date field -->
                        <div class="mb-3">
                            <label for="sleepDate" class="form-label">
                                <b>* {{ $t('healthSleepAddEditModalComponent.dateLabel') }}</b>
                            </label>
                            <input id="sleepDate" class="form-control" type="date" v-model="formData.date" required />
                        </div>

                        <!-- Sleep times section -->
                        <div class="row mb-3">
                            <div class="col-md-6">
                                <label for="sleepStartTime" class="form-label">
                                    <b>* {{ $t('healthSleepAddEditModalComponent.sleepStartTimeLabel') }}</b>
                                </label>
                                <input id="sleepStartTime" class="form-control" type="datetime-local"
                                    v-model="formData.sleepStartTime" required />
                            </div>
                            <div class="col-md-6">
                                <label for="sleepEndTime" class="form-label">
                                    <b>* {{ $t('healthSleepAddEditModalComponent.sleepEndTimeLabel') }}</b>
                                </label>
                                <input id="sleepEndTime" class="form-control" type="datetime-local"
                                    v-model="formData.sleepEndTime" required />
                            </div>
                        </div>

                        <!-- Sleep durations section -->
                        <!-- Total Sleep -->
                        <div class="mb-3">
                            <label class="form-label">
                                <b>{{ $t('healthSleepAddEditModalComponent.totalSleepLabel') }}</b>
                            </label>
                            <div class="input-group">
                                <input id="totalSleepHours" v-model.number="formData.totalSleepHours"
                                    class="form-control" type="number" :placeholder="$t('generalItems.labelHours')"
                                    :aria-label="$t('generalItems.labelHours')" />
                                <span class="input-group-text">{{ $t('generalItems.labelHoursShort') }}</span>
                                <input id="totalSleepMinutes" v-model.number="formData.totalSleepMinutes"
                                    class="form-control" type="number" :placeholder="$t('generalItems.labelMinutes')"
                                    :aria-label="$t('generalItems.labelMinutes')" />
                                <span class="input-group-text">{{ $t('generalItems.labelMinutesShort') }}</span>
                            </div>
                        </div>

                        <!-- Deep Sleep -->
                        <div class="row mb-3">
                            <div class="col-md-6">
                                <label class="form-label">
                                    <b>{{ $t('healthSleepAddEditModalComponent.deepSleepLabel') }}</b>
                                </label>
                                <div class="input-group">
                                    <input id="deepSleepHours" v-model.number="formData.deepSleepHours"
                                        class="form-control" type="number" :placeholder="$t('generalItems.labelHours')"
                                        :aria-label="$t('generalItems.labelHours')" />
                                    <span class="input-group-text">{{ $t('generalItems.labelHoursShort') }}</span>
                                    <input id="deepSleepMinutes" v-model.number="formData.deepSleepMinutes"
                                        class="form-control" type="number"
                                        :placeholder="$t('generalItems.labelMinutes')"
                                        :aria-label="$t('generalItems.labelMinutes')" />
                                    <span class="input-group-text">{{ $t('generalItems.labelMinutesShort') }}</span>
                                </div>
                            </div>
                            <div class="col-md-6">
                                <label class="form-label">
                                    <b>{{ $t('healthSleepAddEditModalComponent.lightSleepLabel') }}</b>
                                </label>
                                <div class="input-group">
                                    <input id="lightSleepHours" v-model.number="formData.lightSleepHours"
                                        class="form-control" type="number" :placeholder="$t('generalItems.labelHours')"
                                        :aria-label="$t('generalItems.labelHours')" />
                                    <span class="input-group-text">{{ $t('generalItems.labelHoursShort') }}</span>
                                    <input id="lightSleepMinutes" v-model.number="formData.lightSleepMinutes"
                                        class="form-control" type="number"
                                        :placeholder="$t('generalItems.labelMinutes')"
                                        :aria-label="$t('generalItems.labelMinutes')" />
                                    <span class="input-group-text">{{ $t('generalItems.labelMinutesShort') }}</span>
                                </div>
                            </div>
                        </div>

                        <!-- REM and Awake Sleep -->
                        <div class="row mb-3">
                            <div class="col-md-6">
                                <label class="form-label">
                                    <b>{{ $t('healthSleepAddEditModalComponent.remSleepLabel') }}</b>
                                </label>
                                <div class="input-group">
                                    <input id="remSleepHours" v-model.number="formData.remSleepHours"
                                        class="form-control" type="number" :placeholder="$t('generalItems.labelHours')"
                                        :aria-label="$t('generalItems.labelHours')" />
                                    <span class="input-group-text">{{ $t('generalItems.labelHoursShort') }}</span>
                                    <input id="remSleepMinutes" v-model.number="formData.remSleepMinutes"
                                        class="form-control" type="number"
                                        :placeholder="$t('generalItems.labelMinutes')"
                                        :aria-label="$t('generalItems.labelMinutes')" />
                                    <span class="input-group-text">{{ $t('generalItems.labelMinutesShort') }}</span>
                                </div>
                            </div>
                            <div class="col-md-6">
                                <label class="form-label">
                                    <b>{{ $t('healthSleepAddEditModalComponent.awakeSleepLabel') }}</b>
                                </label>
                                <div class="input-group">
                                    <input id="awakeSleepHours" v-model.number="formData.awakeSleepHours"
                                        class="form-control" type="number" :placeholder="$t('generalItems.labelHours')"
                                        :aria-label="$t('generalItems.labelHours')" />
                                    <span class="input-group-text">{{ $t('generalItems.labelHoursShort') }}</span>
                                    <input id="awakeSleepMinutes" v-model.number="formData.awakeSleepMinutes"
                                        class="form-control" type="number"
                                        :placeholder="$t('generalItems.labelMinutes')"
                                        :aria-label="$t('generalItems.labelMinutes')" />
                                    <span class="input-group-text">{{ $t('generalItems.labelMinutesShort') }}</span>
                                </div>
                            </div>
                        </div>

                        <!-- Nap Time -->
                        <div class="mb-3">
                            <label class="form-label">
                                <b>{{ $t('healthSleepAddEditModalComponent.napTimeLabel') }}</b>
                            </label>
                            <div class="input-group">
                                <input id="napTimeHours" v-model.number="formData.napTimeHours" class="form-control"
                                    type="number" :placeholder="$t('generalItems.labelHours')"
                                    :aria-label="$t('generalItems.labelHours')" />
                                <span class="input-group-text">{{ $t('generalItems.labelHoursShort') }}</span>
                                <input id="napTimeMinutes" v-model.number="formData.napTimeMinutes" class="form-control"
                                    type="number" :placeholder="$t('generalItems.labelMinutes')"
                                    :aria-label="$t('generalItems.labelMinutes')" />
                                <span class="input-group-text">{{ $t('generalItems.labelMinutesShort') }}</span>
                            </div>
                        </div>

                        <!-- Heart rate section -->
                        <div class="row mb-3">
                            <div class="col-md-4">
                                <label for="avgHeartRate" class="form-label">
                                    <b>{{ $t('healthSleepAddEditModalComponent.avgHeartRateLabel') }}</b>
                                </label>
                                <input id="avgHeartRate"
                                    :placeholder="$t('healthSleepAddEditModalComponent.avgHeartRateLabel')"
                                    class="form-control" type="number" step="0.01"
                                    v-model.number="formData.avgHeartRate" />
                            </div>
                            <div class="col-md-4">
                                <label for="minHeartRate" class="form-label">
                                    <b>{{ $t('healthSleepAddEditModalComponent.minHeartRateLabel') }}</b>
                                </label>
                                <input id="minHeartRate"
                                    :placeholder="$t('healthSleepAddEditModalComponent.minHeartRateLabel')"
                                    class="form-control" type="number" v-model.number="formData.minHeartRate" />
                            </div>
                            <div class="col-md-4">
                                <label for="maxHeartRate" class="form-label">
                                    <b>{{ $t('healthSleepAddEditModalComponent.maxHeartRateLabel') }}</b>
                                </label>
                                <input id="maxHeartRate"
                                    :placeholder="$t('healthSleepAddEditModalComponent.maxHeartRateLabel')"
                                    class="form-control" type="number" v-model.number="formData.maxHeartRate" />
                            </div>
                        </div>

                        <!-- SpO2 section -->
                        <div class="row mb-3">
                            <div class="col-md-4">
                                <label for="avgSpo2" class="form-label">
                                    <b>{{ $t('healthSleepAddEditModalComponent.avgSpo2Label') }}</b>
                                </label>
                                <input id="avgSpo2" :placeholder="$t('healthSleepAddEditModalComponent.avgSpo2Label')"
                                    class="form-control" type="number" step="0.01" v-model.number="formData.avgSpo2" />
                            </div>
                            <div class="col-md-4">
                                <label for="lowestSpo2" class="form-label">
                                    <b>{{ $t('healthSleepAddEditModalComponent.lowestSpo2Label') }}</b>
                                </label>
                                <input id="lowestSpo2"
                                    :placeholder="$t('healthSleepAddEditModalComponent.lowestSpo2Label')"
                                    class="form-control" type="number" v-model.number="formData.lowestSpo2" />
                            </div>
                            <div class="col-md-4">
                                <label for="highestSpo2" class="form-label">
                                    <b>{{ $t('healthSleepAddEditModalComponent.highestSpo2Label') }}</b>
                                </label>
                                <input id="highestSpo2"
                                    :placeholder="$t('healthSleepAddEditModalComponent.highestSpo2Label')"
                                    class="form-control" type="number" v-model.number="formData.highestSpo2" />
                            </div>
                        </div>

                        <!-- Sleep scores section -->
                        <div class="row mb-3">
                            <div class="col-md-4">
                                <label for="sleepScoreOverall" class="form-label">
                                    <b>{{ $t('healthSleepAddEditModalComponent.sleepScoreOverallLabel') }}</b>
                                </label>
                                <input id="sleepScoreOverall" class="form-control" type="number"
                                    v-model.number="formData.sleepScoreOverall" />
                            </div>
                            <div class="col-md-4">
                                <label for="awakeCount" class="form-label">
                                    <b>{{ $t('healthSleepAddEditModalComponent.awakeCountLabel') }}</b>
                                </label>
                                <input id="awakeCount" class="form-control" type="number"
                                    v-model.number="formData.awakeCount" />
                            </div>
                            <div class="col-md-4">
                                <label for="restlessMomentsCount" class="form-label">
                                    <b>{{ $t('healthSleepAddEditModalComponent.restlessMomentsCountLabel') }}</b>
                                </label>
                                <input id="restlessMomentsCount" class="form-control" type="number"
                                    v-model.number="formData.restlessMomentsCount" />
                            </div>
                        </div>

                        <!-- Sleep stages section (dynamic) -->
                        <div class="mb-3">
                            <div class="d-flex justify-content-between align-items-center mb-2">
                                <label class="form-label mb-0">
                                    <b>{{ $t('healthSleepAddEditModalComponent.sleepStagesLabel') }}</b>
                                </label>
                                <button type="button" class="btn btn-sm btn-primary" @click="addSleepStage"
                                    aria-label="Add sleep stage">
                                    <i class="bi bi-plus-circle"></i>
                                    {{ $t('healthSleepAddEditModalComponent.addStageButton') }}
                                </button>
                            </div>

                            <div v-for="(stage, index) in formData.sleepStages" :key="index" class="card mb-2">
                                <div class="card-body">
                                    <div class="d-flex justify-content-between align-items-center mb-2">
                                        <h6 class="card-title mb-0">
                                            {{ $t('healthSleepAddEditModalComponent.stageLabel') }} {{ index + 1 }}
                                        </h6>
                                        <button type="button" class="btn btn-sm btn-danger"
                                            @click="removeSleepStage(index)" :aria-label="`Remove stage ${index + 1}`">
                                            <i class="bi bi-trash"></i>
                                        </button>
                                    </div>

                                    <div class="row">
                                        <div class="col-md-3">
                                            <label :for="`stageType${index}`" class="form-label">
                                                <b>{{ $t('healthSleepAddEditModalComponent.stageTypeLabel') }}</b>
                                            </label>
                                            <select :id="`stageType${index}`" class="form-select"
                                                v-model.number="stage.stageType">
                                                <option :value="0">
                                                    {{ $t('healthSleepAddEditModalComponent.stageTypeDeep') }}
                                                </option>
                                                <option :value="1">
                                                    {{ $t('healthSleepAddEditModalComponent.stageTypeLight') }}
                                                </option>
                                                <option :value="2">
                                                    {{ $t('healthSleepAddEditModalComponent.stageTypeRem') }}
                                                </option>
                                                <option :value="3">
                                                    {{ $t('healthSleepAddEditModalComponent.stageTypeAwake') }}
                                                </option>
                                            </select>
                                        </div>

                                        <div class="col-md-3">
                                            <label :for="`stageStartTime${index}`" class="form-label">
                                                <b>{{ $t('healthSleepAddEditModalComponent.stageStartTimeLabel') }}</b>
                                            </label>
                                            <input :id="`stageStartTime${index}`" class="form-control"
                                                type="datetime-local" v-model="stage.startTimeGmt" />
                                        </div>

                                        <div class="col-md-3">
                                            <label :for="`stageEndTime${index}`" class="form-label">
                                                <b>{{ $t('healthSleepAddEditModalComponent.stageEndTimeLabel') }}</b>
                                            </label>
                                            <input :id="`stageEndTime${index}`" class="form-control"
                                                type="datetime-local" v-model="stage.endTimeGmt" />
                                        </div>

                                        <div class="col-md-3">
                                            <label :for="`stageDuration${index}`" class="form-label">
                                                <b>{{ $t('healthSleepAddEditModalComponent.stageDurationLabel') }}</b>
                                            </label>
                                            <input :id="`stageDuration${index}`" class="form-control" type="number"
                                                v-model.number="stage.durationSeconds" placeholder="Seconds" />
                                        </div>
                                    </div>
                                </div>
                            </div>

                            <div v-if="formData.sleepStages.length === 0" class="alert alert-info" role="alert">
                                {{ $t('healthSleepAddEditModalComponent.noStagesMessage') }}
                            </div>
                        </div>

                        <p class="text-muted">* {{ $t('generalItems.requiredField') }}</p>
                    </div>

                    <div class="modal-footer">
                        <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">
                            {{ $t('generalItems.buttonClose') }}
                        </button>
                        <button type="submit" class="btn btn-success" data-bs-dismiss="modal" v-if="action === 'add'">
                            {{ $t('healthSleepAddEditModalComponent.addSleepModalTitle') }}
                        </button>
                        <button type="submit" class="btn btn-success" data-bs-dismiss="modal" v-else>
                            {{ $t('healthSleepAddEditModalComponent.editSleepModalTitle') }}
                        </button>
                    </div>
                </form>
            </div>
        </div>
    </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { push } from 'notivue'
import { health_sleep } from '@/services/health_sleepService'
import { returnHoursMinutesFromSeconds, returnSecondsFromHoursMinutes } from '@/utils/dateTimeUtils'

interface SleepStage {
    stageType: number | null
    startTimeGmt: string | null
    endTimeGmt: string | null
    durationSeconds: number | null
}

interface SleepFormData {
    date: string
    sleepStartTime: string
    sleepEndTime: string
    totalSleepHours: number | null
    totalSleepMinutes: number | null
    napTimeHours: number | null
    napTimeMinutes: number | null
    deepSleepHours: number | null
    deepSleepMinutes: number | null
    lightSleepHours: number | null
    lightSleepMinutes: number | null
    remSleepHours: number | null
    remSleepMinutes: number | null
    awakeSleepHours: number | null
    awakeSleepMinutes: number | null
    avgHeartRate: number | null
    minHeartRate: number | null
    maxHeartRate: number | null
    avgSpo2: number | null
    lowestSpo2: number | null
    highestSpo2: number | null
    sleepScoreOverall: number | null
    awakeCount: number | null
    restlessMomentsCount: number | null
    sleepStages: SleepStage[]
}

interface UserHealthSleep {
    id: number
    user_id: number
    date: string
    sleep_start_time_gmt: string
    sleep_end_time_gmt: string
    sleep_start_time_local?: string
    sleep_end_time_local?: string
    total_sleep_seconds?: number
    nap_time_seconds?: number
    deep_sleep_seconds?: number
    light_sleep_seconds?: number
    rem_sleep_seconds?: number
    awake_sleep_seconds?: number
    avg_heart_rate?: number
    min_heart_rate?: number
    max_heart_rate?: number
    avg_spo2?: number
    lowest_spo2?: number
    highest_spo2?: number
    sleep_score_overall?: number
    awake_count?: number
    restless_moments_count?: number
    sleep_stages?: Array<{
        stage_type: number | null
        start_time_gmt: string | null
        end_time_gmt: string | null
        duration_seconds: number | null
    }>
}

const props = defineProps<{
    action: 'add' | 'edit'
    userHealthSleep?: UserHealthSleep
}>()

const emit = defineEmits<{
    isLoadingNewSleep: [value: boolean]
    createdSleep: [sleep: UserHealthSleep]
    editedSleep: [sleep: UserHealthSleep]
}>()

const { t } = useI18n()

const formData = ref<SleepFormData>({
    date: new Date().toISOString().split('T')[0] as string,
    sleepStartTime: '',
    sleepEndTime: '',
    totalSleepHours: null,
    totalSleepMinutes: null,
    napTimeHours: null,
    napTimeMinutes: null,
    deepSleepHours: null,
    deepSleepMinutes: null,
    lightSleepHours: null,
    lightSleepMinutes: null,
    remSleepHours: null,
    remSleepMinutes: null,
    awakeSleepHours: null,
    awakeSleepMinutes: null,
    avgHeartRate: null,
    minHeartRate: null,
    maxHeartRate: null,
    avgSpo2: null,
    lowestSpo2: null,
    highestSpo2: null,
    sleepScoreOverall: null,
    awakeCount: null,
    restlessMomentsCount: null,
    sleepStages: []
})

const editSleepId = ref('')

onMounted(() => {
    if (props.userHealthSleep) {
        const totalSleep = returnHoursMinutesFromSeconds(props.userHealthSleep.total_sleep_seconds ?? 0)
        const napTime = returnHoursMinutesFromSeconds(props.userHealthSleep.nap_time_seconds ?? 0)
        const deepSleep = returnHoursMinutesFromSeconds(props.userHealthSleep.deep_sleep_seconds ?? 0)
        const lightSleep = returnHoursMinutesFromSeconds(props.userHealthSleep.light_sleep_seconds ?? 0)
        const remSleep = returnHoursMinutesFromSeconds(props.userHealthSleep.rem_sleep_seconds ?? 0)
        const awakeSleep = returnHoursMinutesFromSeconds(props.userHealthSleep.awake_sleep_seconds ?? 0)

        formData.value = {
            date: props.userHealthSleep.date,
            sleepStartTime: formatDateTimeForInput(props.userHealthSleep.sleep_start_time_gmt),
            sleepEndTime: formatDateTimeForInput(props.userHealthSleep.sleep_end_time_gmt),
            totalSleepHours: totalSleep.hours,
            totalSleepMinutes: totalSleep.minutes,
            napTimeHours: napTime.hours,
            napTimeMinutes: napTime.minutes,
            deepSleepHours: deepSleep.hours,
            deepSleepMinutes: deepSleep.minutes,
            lightSleepHours: lightSleep.hours,
            lightSleepMinutes: lightSleep.minutes,
            remSleepHours: remSleep.hours,
            remSleepMinutes: remSleep.minutes,
            awakeSleepHours: awakeSleep.hours,
            awakeSleepMinutes: awakeSleep.minutes,
            avgHeartRate: props.userHealthSleep.avg_heart_rate ?? null,
            minHeartRate: props.userHealthSleep.min_heart_rate ?? null,
            maxHeartRate: props.userHealthSleep.max_heart_rate ?? null,
            avgSpo2: props.userHealthSleep.avg_spo2 ?? null,
            lowestSpo2: props.userHealthSleep.lowest_spo2 ?? null,
            highestSpo2: props.userHealthSleep.highest_spo2 ?? null,
            sleepScoreOverall: props.userHealthSleep.sleep_score_overall ?? null,
            awakeCount: props.userHealthSleep.awake_count ?? null,
            restlessMomentsCount: props.userHealthSleep.restless_moments_count ?? null,
            sleepStages:
                props.userHealthSleep.sleep_stages?.map((stage) => ({
                    stageType: stage.stage_type,
                    startTimeGmt: stage.start_time_gmt ? formatDateTimeForInput(stage.start_time_gmt) : null,
                    endTimeGmt: stage.end_time_gmt ? formatDateTimeForInput(stage.end_time_gmt) : null,
                    durationSeconds: stage.duration_seconds
                })) ?? []
        }
        editSleepId.value = `editSleepId${props.userHealthSleep.id}`
    }
})

/**
 * Formats ISO datetime string for datetime-local input.
 *
 * @param isoString - ISO 8601 datetime string.
 * @returns Formatted string for datetime-local input (YYYY-MM-DDTHH:mm).
 */
function formatDateTimeForInput(isoString: string): string {
    return isoString.slice(0, 16)
}

/**
 * Adds a new empty sleep stage to the form.
 */
function addSleepStage(): void {
    formData.value.sleepStages.push({
        stageType: 1,
        startTimeGmt: null,
        endTimeGmt: null,
        durationSeconds: null
    })
}

/**
 * Removes a sleep stage at the specified index.
 *
 * @param index - Index of the sleep stage to remove.
 */
function removeSleepStage(index: number): void {
    formData.value.sleepStages.splice(index, 1)
}

/**
 * Submits the form to add a new sleep entry.
 *
 * @throws Error if API request fails.
 */
async function submitAddSleep(): Promise<void> {
    emit('isLoadingNewSleep', true)
    try {
        const data = {
            date: formData.value.date,
            sleep_start_time_gmt: formData.value.sleepStartTime,
            sleep_end_time_gmt: formData.value.sleepEndTime,
            total_sleep_seconds:
                formData.value.totalSleepHours !== null && formData.value.totalSleepMinutes !== null
                    ? returnSecondsFromHoursMinutes(
                        formData.value.totalSleepHours,
                        formData.value.totalSleepMinutes
                    )
                    : null,
            nap_time_seconds:
                formData.value.napTimeHours !== null && formData.value.napTimeMinutes !== null
                    ? returnSecondsFromHoursMinutes(
                        formData.value.napTimeHours,
                        formData.value.napTimeMinutes
                    )
                    : null,
            deep_sleep_seconds:
                formData.value.deepSleepHours !== null && formData.value.deepSleepMinutes !== null
                    ? returnSecondsFromHoursMinutes(
                        formData.value.deepSleepHours,
                        formData.value.deepSleepMinutes
                    )
                    : null,
            light_sleep_seconds:
                formData.value.lightSleepHours !== null && formData.value.lightSleepMinutes !== null
                    ? returnSecondsFromHoursMinutes(
                        formData.value.lightSleepHours,
                        formData.value.lightSleepMinutes
                    )
                    : null,
            rem_sleep_seconds:
                formData.value.remSleepHours !== null && formData.value.remSleepMinutes !== null
                    ? returnSecondsFromHoursMinutes(
                        formData.value.remSleepHours,
                        formData.value.remSleepMinutes
                    )
                    : null,
            awake_sleep_seconds:
                formData.value.awakeSleepHours !== null && formData.value.awakeSleepMinutes !== null
                    ? returnSecondsFromHoursMinutes(
                        formData.value.awakeSleepHours,
                        formData.value.awakeSleepMinutes
                    )
                    : null,
            avg_heart_rate: formData.value.avgHeartRate,
            min_heart_rate: formData.value.minHeartRate,
            max_heart_rate: formData.value.maxHeartRate,
            avg_spo2: formData.value.avgSpo2,
            lowest_spo2: formData.value.lowestSpo2,
            highest_spo2: formData.value.highestSpo2,
            sleep_score_overall: formData.value.sleepScoreOverall,
            awake_count: formData.value.awakeCount,
            restless_moments_count: formData.value.restlessMomentsCount,
            sleep_stages: formData.value.sleepStages.map((stage) => ({
                stage_type: stage.stageType,
                start_time_gmt: stage.startTimeGmt,
                end_time_gmt: stage.endTimeGmt,
                duration_seconds: stage.durationSeconds
            }))
        }

        const createdSleep = await health_sleep.createHealthSleep(data)

        emit('isLoadingNewSleep', false)
        emit('createdSleep', createdSleep)

        push.success(t('healthSleepAddEditModalComponent.successAddSleep'))
    } catch (error) {
        emit('isLoadingNewSleep', false)
        push.error(
            `${t('healthSleepAddEditModalComponent.errorAddSleep')} - ${error instanceof Error ? error.message : String(error)}`
        )
    }
}

/**
 * Submits the form to edit an existing sleep entry.
 */
function submitEditSleep(): void {
    if (!props.userHealthSleep) return

    const editedData = {
        id: props.userHealthSleep.id,
        user_id: props.userHealthSleep.user_id,
        date: formData.value.date,
        sleep_start_time_gmt: formData.value.sleepStartTime,
        sleep_end_time_gmt: formData.value.sleepEndTime,
        total_sleep_seconds:
            formData.value.totalSleepHours !== null && formData.value.totalSleepMinutes !== null
                ? returnSecondsFromHoursMinutes(
                    formData.value.totalSleepHours,
                    formData.value.totalSleepMinutes
                )
                : null,
        nap_time_seconds:
            formData.value.napTimeHours !== null && formData.value.napTimeMinutes !== null
                ? returnSecondsFromHoursMinutes(formData.value.napTimeHours, formData.value.napTimeMinutes)
                : null,
        deep_sleep_seconds:
            formData.value.deepSleepHours !== null && formData.value.deepSleepMinutes !== null
                ? returnSecondsFromHoursMinutes(
                    formData.value.deepSleepHours,
                    formData.value.deepSleepMinutes
                )
                : null,
        light_sleep_seconds:
            formData.value.lightSleepHours !== null && formData.value.lightSleepMinutes !== null
                ? returnSecondsFromHoursMinutes(
                    formData.value.lightSleepHours,
                    formData.value.lightSleepMinutes
                )
                : null,
        rem_sleep_seconds:
            formData.value.remSleepHours !== null && formData.value.remSleepMinutes !== null
                ? returnSecondsFromHoursMinutes(
                    formData.value.remSleepHours,
                    formData.value.remSleepMinutes
                )
                : null,
        awake_sleep_seconds:
            formData.value.awakeSleepHours !== null && formData.value.awakeSleepMinutes !== null
                ? returnSecondsFromHoursMinutes(
                    formData.value.awakeSleepHours,
                    formData.value.awakeSleepMinutes
                )
                : null,
        avg_heart_rate: formData.value.avgHeartRate,
        min_heart_rate: formData.value.minHeartRate,
        max_heart_rate: formData.value.maxHeartRate,
        avg_spo2: formData.value.avgSpo2,
        lowest_spo2: formData.value.lowestSpo2,
        highest_spo2: formData.value.highestSpo2,
        sleep_score_overall: formData.value.sleepScoreOverall,
        awake_count: formData.value.awakeCount,
        restless_moments_count: formData.value.restlessMomentsCount,
        sleep_stages: formData.value.sleepStages.map((stage) => ({
            stage_type: stage.stageType,
            start_time_gmt: stage.startTimeGmt,
            end_time_gmt: stage.endTimeGmt,
            duration_seconds: stage.durationSeconds
        }))
    }

    emit('editedSleep', editedData as UserHealthSleep)
}

/**
 * Handles form submission for both add and edit actions.
 */
function handleSubmit(): void {
    if (props.action === 'add') {
        submitAddSleep()
    } else {
        submitEditSleep()
    }
}
</script>

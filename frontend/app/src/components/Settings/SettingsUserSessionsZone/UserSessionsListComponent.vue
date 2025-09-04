<template>
  <li class="list-group-item bg-body-tertiary rounded border-0">
    <div class="d-flex justify-content-between">
      <div class="d-flex align-items-center">
        <font-awesome-icon
          :icon="['fab', 'linux']"
          v-if="session.operating_system == 'Linux'"
          size="2x"
        />
        <font-awesome-icon
          :icon="['fab', 'windows']"
          v-else-if="session.operating_system == 'Windows'"
          size="2x"
        />
        <font-awesome-icon
          :icon="['fab', 'apple']"
          v-else-if="
            session.operating_system == 'macOS' ||
            session.operating_system == 'iOS' ||
            session.operating_system == 'iPadOS' ||
            session.operating_system == 'Mac OS X'
          "
          size="2x"
        />
        <font-awesome-icon
          :icon="['fab', 'android']"
          v-else-if="session.operating_system == 'Android'"
          size="2x"
        />
        <div class="ms-3">
          <div class="fw-bold">
            {{ session.operating_system }} - {{ session.browser }} @ {{ session.ip_address }} @
            {{ formatTime(session.created_at) }} - {{ formatDateMed(session.created_at) }}
          </div>
          <div>
            {{ session.id }}
          </div>
        </div>
      </div>
      <div>
        <!-- current session badge -->
        <span
          class="badge bg-warning-subtle border border-warning-subtle text-warning-emphasis align-middle me-1"
          v-if="authStore.session_id == session.id"
          >{{ $t('userSessionsListComponent.badgeCurrentSession') }}</span
        >

        <!-- delete session button -->
        <a
          class="btn btn-link btn-lg link-body-emphasis"
          :class="{ disabled: authStore.session_id == session.id }"
          href="#"
          role="button"
          data-bs-toggle="modal"
          :data-bs-target="`#deleteSessionModal${session.id}`"
        >
          <font-awesome-icon :icon="['fas', 'fa-trash-can']" />
        </a>

        <!-- modal delete session -->
        <ModalComponent
          :modalId="`deleteSessionModal${session.id}`"
          :title="t('userSessionsListComponent.modalDeleteSessionTitle')"
          :body="`${t('userSessionsListComponent.modalDeleteSessionBody')}<b>${session.id}</b>?`"
          :actionButtonType="`danger`"
          :actionButtonText="t('userSessionsListComponent.modalDeleteSessionTitle')"
          @submitAction="submitDeleteSession"
        />
      </div>
    </div>
  </li>
</template>

<script>
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useAuthStore } from '@/stores/authStore'
import { formatDateMed, formatTime } from '@/utils/dateTimeUtils'

import ModalComponent from '@/components/Modals/ModalComponent.vue'

export default {
  components: {
    ModalComponent
  },
  props: {
    session: {
      type: Object,
      required: true
    }
  },
  emits: ['sessionDeleted'],
  setup(props, { emit }) {
    const { t } = useI18n()
    const authStore = useAuthStore()

    async function submitDeleteSession() {
      // Emit event to parent component
      emit('sessionDeleted', props.session.id)
    }

    return {
      t,
      authStore,
      formatDateMed,
      formatTime,
      submitDeleteSession
    }
  }
}
</script>

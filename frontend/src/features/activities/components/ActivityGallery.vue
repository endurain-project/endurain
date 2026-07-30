<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterLink, type RouteLocationRaw } from 'vue-router'
import { ChevronLeft, ChevronRight, Trash2, X } from '@lucide/vue'

import type { GeoPoint } from '@/composables/useMapProvider'
import type { ActivityMedia } from '@/features/activities/types'

import { ConfirmDialog } from '@/components/ui/confirm-dialog'
import { Image } from '@/components/ui/image'
import { Skeleton } from '@/components/ui/skeleton'
import ActivityMap from '@/features/activities/components/ActivityMap.vue'
import { useToasts } from '@/composables/useToasts'
import {
  useActivityMediaQuery,
  useDeleteActivityMediaMutation,
} from '@/features/activities/composables/useActivityDetail'

const props = withDefaults(
  defineProps<{
    /** GPS track points; when non-empty the interactive map leads the slides. */
    points: GeoPoint[]
    /** The activity whose photos populate the remaining slides. */
    activityId: number
    /**
     * Static map thumbnail used as the lead slide when no GPS `points` are
     * given (e.g. the home feed, which avoids a live map per card). Ignored
     * while `points` is non-empty.
     */
    thumbnailUrl?: string | null
    /** Optional route that turns the thumbnail slide into a link to the activity. */
    thumbnailTo?: RouteLocationRaw
    /**
     * Whether a thumbnail is still being generated server-side. Shows a
     * placeholder in the slot the thumbnail will occupy, so the card does not
     * jump when it lands. Ignored once `thumbnailUrl` or a map is available.
     */
    thumbnailPending?: boolean
    /**
     * Tailwind height class(es) applied to every slide. The home feed shows a
     * shorter preview than the detail view, so the consumer controls it.
     * Defaults to the detail view's height.
     */
    heightClass?: string
    /** Whether the viewer owns the activity (gates the per-photo delete button). */
    isOwner?: boolean
  }>(),
  {
    thumbnailUrl: null,
    thumbnailTo: undefined,
    thumbnailPending: false,
    heightClass: 'h-72 lg:h-150',
    isOwner: false,
  },
)

const { t } = useI18n()
const toasts = useToasts()

const { data: media } = useActivityMediaQuery(() => props.activityId)
const deleteMutation = useDeleteActivityMediaMutation(() => props.activityId)
const photos = computed(() => media.value ?? [])
const hasMap = computed(() => props.points.length > 0)
// The static thumbnail stands in for the map when no live track is supplied.
const hasThumbnail = computed(() => !hasMap.value && Boolean(props.thumbnailUrl))
// Placeholder for a thumbnail still being rendered: it takes the exact slide the
// real one will occupy, so its arrival swaps content rather than shifting layout.
const hasPendingThumbnail = computed(
  () => !hasMap.value && !hasThumbnail.value && props.thumbnailPending,
)

type Slide =
  | { kind: 'map' }
  | { kind: 'thumbnail' }
  | { kind: 'thumbnailPending' }
  | { kind: 'photo'; media: ActivityMedia }

// The lead slide (interactive map or static thumbnail) comes first, mirroring
// v1's gallery, then the photos.
const slides = computed<Slide[]>(() => [
  ...(hasMap.value ? [{ kind: 'map' as const }] : []),
  ...(hasThumbnail.value ? [{ kind: 'thumbnail' as const }] : []),
  ...(hasPendingThumbnail.value ? [{ kind: 'thumbnailPending' as const }] : []),
  ...photos.value.map((item) => ({ kind: 'photo' as const, media: item })),
])

const current = ref(0)

// Keep the active index valid as the slide set changes (e.g. a photo upload, or
// the map appearing once the streams resolve).
watch(slides, (next) => {
  current.value = Math.min(current.value, Math.max(0, next.length - 1))
})

/** Clamps and sets the active slide. */
function go(index: number): void {
  current.value = Math.min(Math.max(index, 0), slides.value.length - 1)
}

// ── Lightbox ──────────────────────────────────────────────────────────────────
// Only photo slides are openable; the map slide has no lightbox.
const lightboxOpen = ref(false)
const lightboxIndex = ref(0)

/** Photo slides only, for lightbox navigation. */
const photoSlides = computed(() =>
  slides.value.filter(
    (slide): slide is { kind: 'photo'; media: ActivityMedia } => slide.kind === 'photo',
  ),
)

/** Opens the lightbox at the photo matching `item`. */
function openLightbox(item: ActivityMedia): void {
  const index = photoSlides.value.findIndex((slide) => slide.media.id === item.id)
  if (index < 0) {
    return
  }
  lightboxIndex.value = index
  lightboxOpen.value = true
}

function closeLightbox(): void {
  lightboxOpen.value = false
}

function lightboxGo(index: number): void {
  lightboxIndex.value = Math.min(Math.max(index, 0), photoSlides.value.length - 1)
}

/** Handles keyboard navigation when the lightbox is open. */
function onKeydown(e: KeyboardEvent): void {
  if (!lightboxOpen.value) {
    return
  }
  if (e.key === 'Escape') {
    closeLightbox()
  } else if (e.key === 'ArrowLeft') {
    lightboxGo(lightboxIndex.value - 1)
  } else if (e.key === 'ArrowRight') {
    lightboxGo(lightboxIndex.value + 1)
  }
}

onMounted(() => document.addEventListener('keydown', onKeydown))
onBeforeUnmount(() => document.removeEventListener('keydown', onKeydown))

// ── Delete ────────────────────────────────────────────────────────────────────
const pendingDelete = ref<ActivityMedia | null>(null)
const isDeleteOpen = ref(false)

/** Opens the delete confirmation for a photo. */
function requestDelete(item: ActivityMedia): void {
  pendingDelete.value = item
  isDeleteOpen.value = true
}

/** Deletes the pending photo, then closes the dialog. */
async function confirmDelete(): Promise<void> {
  if (!pendingDelete.value) {
    return
  }
  try {
    await deleteMutation.mutateAsync(pendingDelete.value.id)
    isDeleteOpen.value = false
    toasts.success(t('activities.media.deleteSuccess'))
  } catch {
    toasts.error(t('activities.media.deleteError'))
  }
}
</script>

<template>
  <div
    v-if="slides.length > 0"
    class="relative overflow-hidden rounded-card border border-border bg-muted"
  >
    <!-- Every slide stays mounted (translated, never `display:none`) so the
         Leaflet map keeps its measured size as the carousel moves. -->
    <div
      class="flex transition-transform duration-300 ease-out"
      :style="{ transform: `translateX(-${current * 100}%)` }"
    >
      <div
        v-for="(slide, index) in slides"
        :key="slide.kind === 'photo' ? `photo-${slide.media.id}` : slide.kind"
        class="relative w-full shrink-0"
        :class="heightClass"
        :aria-hidden="index !== current"
      >
        <ActivityMap v-if="slide.kind === 'map'" :points="points" />
        <component
          :is="thumbnailTo ? RouterLink : 'div'"
          v-else-if="slide.kind === 'thumbnail'"
          :to="thumbnailTo"
          class="block size-full"
        >
          <img :src="thumbnailUrl ?? ''" alt="" loading="lazy" class="size-full object-cover" />
        </component>
        <div
          v-else-if="slide.kind === 'thumbnailPending'"
          class="flex size-full items-center justify-center"
          role="status"
          :aria-label="t('activities.media.thumbnailPending')"
        >
          <Skeleton class="size-full rounded-none" />
        </div>
        <template v-else>
          <button
            type="button"
            class="size-full cursor-zoom-in focus-visible:outline-none"
            :aria-label="t('activities.media.expand')"
            @click="openLightbox(slide.media)"
          >
            <Image
              :src="slide.media.url"
              :alt="t('activities.media.alt')"
              class="size-full object-contain"
            />
          </button>
          <button
            v-if="isOwner"
            type="button"
            class="absolute right-2 bottom-2 z-10 flex size-9 items-center justify-center rounded-full bg-card/80 text-destructive backdrop-blur transition-colors hover:bg-destructive/10"
            :aria-label="t('activities.media.deleteTitle')"
            @click="requestDelete(slide.media)"
          >
            <Trash2 class="size-4" />
          </button>
        </template>
      </div>
    </div>

    <template v-if="slides.length > 1">
      <button
        type="button"
        class="absolute left-2 top-1/2 z-10 flex size-9 -translate-y-1/2 items-center justify-center rounded-full bg-card/80 text-foreground backdrop-blur transition-colors hover:bg-card disabled:opacity-40"
        :disabled="current === 0"
        :aria-label="t('activities.gallery.previous')"
        @click="go(current - 1)"
      >
        <ChevronLeft class="size-5" />
      </button>
      <button
        type="button"
        class="absolute right-2 top-1/2 z-10 flex size-9 -translate-y-1/2 items-center justify-center rounded-full bg-card/80 text-foreground backdrop-blur transition-colors hover:bg-card disabled:opacity-40"
        :disabled="current === slides.length - 1"
        :aria-label="t('activities.gallery.next')"
        @click="go(current + 1)"
      >
        <ChevronRight class="size-5" />
      </button>

      <div class="absolute inset-x-0 bottom-3 z-10 flex justify-center gap-1.5">
        <button
          v-for="(slide, index) in slides"
          :key="slide.kind === 'photo' ? `dot-${slide.media.id}` : `dot-${slide.kind}`"
          type="button"
          class="size-2 rounded-full transition-colors"
          :class="index === current ? 'bg-brand' : 'bg-foreground/30 hover:bg-foreground/50'"
          :aria-label="t('activities.gallery.goToSlide', { index: index + 1 })"
          :aria-current="index === current"
          @click="go(index)"
        />
      </div>
    </template>
  </div>

  <!-- ── Lightbox overlay ─────────────────────────────────────────────────── -->
  <Teleport to="body">
    <Transition name="lightbox">
      <div
        v-if="lightboxOpen"
        role="dialog"
        aria-modal="true"
        :aria-label="t('activities.gallery.lightbox')"
        class="fixed inset-0 z-[2000] flex items-center justify-center bg-black/90"
        @click.self="closeLightbox"
      >
        <!-- Image -->
        <Image
          v-if="photoSlides[lightboxIndex]"
          :src="photoSlides[lightboxIndex]!.media.url"
          :alt="t('activities.media.alt')"
          class="max-h-screen max-w-full object-contain p-4"
        />

        <!-- Close -->
        <button
          type="button"
          class="absolute top-4 right-4 flex size-10 items-center justify-center rounded-full bg-white/10 text-white transition-colors hover:bg-white/20"
          :aria-label="t('activities.gallery.close')"
          @click="closeLightbox"
        >
          <X class="size-5" />
        </button>

        <!-- Prev / Next (only when more than one photo) -->
        <template v-if="photoSlides.length > 1">
          <button
            type="button"
            class="absolute left-4 top-1/2 flex size-10 -translate-y-1/2 items-center justify-center rounded-full bg-white/10 text-white transition-colors hover:bg-white/20 disabled:opacity-30"
            :disabled="lightboxIndex === 0"
            :aria-label="t('activities.gallery.previous')"
            @click="lightboxGo(lightboxIndex - 1)"
          >
            <ChevronLeft class="size-6" />
          </button>
          <button
            type="button"
            class="absolute right-4 top-1/2 flex size-10 -translate-y-1/2 items-center justify-center rounded-full bg-white/10 text-white transition-colors hover:bg-white/20 disabled:opacity-30"
            :disabled="lightboxIndex === photoSlides.length - 1"
            :aria-label="t('activities.gallery.next')"
            @click="lightboxGo(lightboxIndex + 1)"
          >
            <ChevronRight class="size-6" />
          </button>

          <!-- Counter -->
          <p class="absolute bottom-5 inset-x-0 text-center text-sm text-white/70">
            {{ lightboxIndex + 1 }} / {{ photoSlides.length }}
          </p>
        </template>
      </div>
    </Transition>
  </Teleport>

  <ConfirmDialog
    v-model:open="isDeleteOpen"
    :title="t('activities.media.deleteTitle')"
    :description="t('activities.media.deleteBody')"
    :confirm-label="t('activities.media.delete')"
    :cancel-label="t('activities.media.cancel')"
    :close-label="t('activities.media.close')"
    :pending="deleteMutation.isPending.value"
    @confirm="confirmDelete"
  />
</template>

<style scoped>
.lightbox-enter-active,
.lightbox-leave-active {
  transition: opacity 0.18s ease;
}
.lightbox-enter-from,
.lightbox-leave-to {
  opacity: 0;
}
</style>

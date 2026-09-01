/**
 * Render-provider registration. Wires the concrete Leaflet and Chart.js
 * implementations into their seams during bootstrap. The heavy mapping and
 * charting libraries are dynamically imported so they load as separate chunks —
 * pages that never render a map or chart (login, lists) don't pay for them.
 */
import { readonly, ref, type Ref } from 'vue'

import { setChartProvider } from '@/composables/useChartProvider'
import { setMapProvider } from '@/composables/useMapProvider'

import type { LeafletMapProviderConfig } from './leafletMapProvider'

const renderProvidersReady = ref(false)

/**
 * Reactive readiness of the render providers. The provider seams are not
 * reactive, so a deep-linked map/chart view can mount before
 * {@link registerRenderProviders} resolves; consumers watch this flag and mount
 * their renderer once it flips `true`.
 *
 * @returns A readonly ref that becomes `true` once both providers are installed.
 */
export function useRenderProvidersReady(): Ref<boolean> {
  return readonly(renderProvidersReady) as Ref<boolean>
}

/**
 * Loads and registers the default map and chart providers. Safe to call once
 * during bootstrap; resolves after both providers are installed.
 *
 * @param mapConfig - Public tile-server configuration for Leaflet.
 * @returns A promise that resolves once both providers are installed.
 */
export async function registerRenderProviders(
  mapConfig: LeafletMapProviderConfig = {},
): Promise<void> {
  const [{ createLeafletMapProvider }, { createChartJsChartProvider }] = await Promise.all([
    import('./leafletMapProvider'),
    import('./chartJsChartProvider'),
  ])
  setMapProvider(createLeafletMapProvider(mapConfig))
  setChartProvider(createChartJsChartProvider())
  renderProvidersReady.value = true
}

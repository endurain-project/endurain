/**
 * Bootstrap Modal Composable
 *
 * Provides a type-safe wrapper for Bootstrap Modal component lifecycle management.
 * Handles initialization, show/hide operations, and cleanup.
 *
 * @example
 * ```typescript
 * const { modalInstance, initializeModal, showModal, hideModal } = useBootstrapModal()
 *
 * // In component setup
 * const modalRef = ref(null)
 * await initializeModal(modalRef)
 *
 * // Show/hide modal
 * showModal()
 * hideModal()
 * ```
 */

import { ref, nextTick, type Ref } from 'vue'
import { Modal } from 'bootstrap'

/**
 * Modal instance reference type
 */
export type BootstrapModalInstance = Modal | null

/**
 * Bootstrap Modal composable hook
 *
 * @returns Modal management functions and state
 */
export function useBootstrapModal() {
  const modalInstance: Ref<BootstrapModalInstance> = ref(null)
  const isInitialized: Ref<boolean> = ref(false)

  /**
   * Initialize the Bootstrap Modal instance
   *
   * @param modalRef - Vue ref containing the modal element
   * @returns Promise that resolves when modal is initialized
   * @throws Error if modal element is not found or initialization fails
   */
  const initializeModal = async (modalRef: Ref<any>): Promise<void> => {
    await nextTick()

    if (!modalRef.value?.$el) {
      console.error('Modal element not found in ref')
      return
    }

    try {
      modalInstance.value = new Modal(modalRef.value.$el)
      isInitialized.value = true
    } catch (error) {
      console.error('Failed to initialize Bootstrap modal:', error)
      throw error
    }
  }

  /**
   * Show the modal
   *
   * @throws Error if modal is not initialized
   */
  const showModal = (): void => {
    if (!isInitialized.value || !modalInstance.value) {
      console.warn('Cannot show modal: not initialized')
      return
    }
    modalInstance.value.show()
  }

  /**
   * Hide the modal
   *
   * @throws Error if modal is not initialized
   */
  const hideModal = (): void => {
    if (!isInitialized.value || !modalInstance.value) {
      console.warn('Cannot hide modal: not initialized')
      return
    }
    modalInstance.value.hide()
  }

  /**
   * Dispose of the modal instance and clean up resources
   */
  const disposeModal = (): void => {
    if (modalInstance.value) {
      try {
        modalInstance.value.dispose()
      } catch (error) {
        console.error('Error disposing modal:', error)
      } finally {
        modalInstance.value = null
        isInitialized.value = false
      }
    }
  }

  return {
    modalInstance,
    isInitialized,
    initializeModal,
    showModal,
    hideModal,
    disposeModal
  }
}

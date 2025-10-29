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
   * Supports both component refs (with $el property) and template refs (direct DOM elements)
   *
   * @param modalRef - Vue ref containing either a component instance or HTMLElement
   * @returns Promise that resolves when modal is initialized
   * @throws Error if modal element is not found or initialization fails
   */
  const initializeModal = async (modalRef: Ref<any>): Promise<void> => {
    await nextTick()

    // Handle both component refs (modalRef.value.$el) and template refs (modalRef.value)
    const element = modalRef.value?.$el || modalRef.value

    if (!element) {
      console.error('Modal element not found in ref')
      return
    }

    try {
      modalInstance.value = new Modal(element)
      isInitialized.value = true

      // Listen for Bootstrap's hidden event to clean up body styles
      element.addEventListener('hidden.bs.modal', () => {
        cleanupBodyStyles()
      })
    } catch (error) {
      console.error('Failed to initialize Bootstrap modal:', error)
      throw error
    }
  }

  /**
   * Clean up body styles and attributes left by Bootstrap
   */
  const cleanupBodyStyles = (): void => {
    // Check if any other modals are still open
    const openModals = document.querySelectorAll('.modal.show')
    if (openModals.length === 0) {
      // Remove all Bootstrap modal-related classes and styles
      document.body.classList.remove('modal-open')
      document.body.style.overflow = ''
      document.body.style.paddingRight = ''
      document.body.removeAttribute('data-bs-overflow')
      document.body.removeAttribute('data-bs-padding-right')

      // Clean up any remaining backdrops
      const backdrops = document.querySelectorAll('.modal-backdrop')
      backdrops.forEach((backdrop) => backdrop.remove())
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
   * Hide the modal and clean up backdrop
   *
   * @throws Error if modal is not initialized
   */
  const hideModal = (): void => {
    if (!isInitialized.value || !modalInstance.value) {
      console.warn('Cannot hide modal: not initialized')
      return
    }
    modalInstance.value.hide()
    // Cleanup is handled by the 'hidden.bs.modal' event listener
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
        cleanupBodyStyles()
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

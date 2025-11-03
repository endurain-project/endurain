import { ref, nextTick, type Ref } from 'vue'
import { Modal } from 'bootstrap'

/**
 * Type representing a Bootstrap Modal instance or null.
 */
export type BootstrapModalInstance = Modal | null

/**
 * Composable for managing Bootstrap 5 modal lifecycle and cleanup.
 *
 * @returns Object containing modal instance, initialization state, and control methods.
 *
 * @remarks
 * Provides centralized modal management with proper cleanup of Bootstrap's
 * body styles and backdrops when modals are closed.
 */
export function useBootstrapModal() {
  const modalInstance: Ref<BootstrapModalInstance> = ref(null)
  const isInitialized: Ref<boolean> = ref(false)

  /**
   * Initializes the Bootstrap modal instance from a Vue ref.
   *
   * @param modalRef - Vue ref containing the modal element or component.
   * @returns Promise that resolves when initialization is complete.
   *
   * @remarks
   * Handles both component refs (`modalRef.value.$el`) and template refs (`modalRef.value`).
   * Sets up automatic cleanup on modal hide event.
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
   * Cleans up Bootstrap-applied body styles and backdrops.
   *
   * @remarks
   * Only performs cleanup if no other modals are currently open.
   * Removes modal-related classes, inline styles, and any remaining backdrop elements.
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
   * Shows the modal.
   *
   * @remarks
   * Logs a warning if the modal is not initialized.
   */
  const showModal = (): void => {
    if (!isInitialized.value || !modalInstance.value) {
      console.warn('Cannot show modal: not initialized')
      return
    }
    modalInstance.value.show()
  }

  /**
   * Hides the modal.
   *
   * @remarks
   * Logs a warning if the modal is not initialized.
   * Cleanup is automatically handled by the `hidden.bs.modal` event listener.
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
   * Disposes of the modal instance and performs cleanup.
   *
   * @remarks
   * Calls Bootstrap's `dispose()` method, cleans up body styles,
   * and resets the modal instance and initialization state.
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

export function removeActiveModal(modalInstance) {
  // Close the modal
  if (modalInstance) {
    modalInstance.hide()
    modalInstance.dispose()
  }

  // Remove any remaining modal backdrops
  const backdrops = document.querySelectorAll('.modal-backdrop')
  for (const backdrop of backdrops) {
    backdrop.remove()
  }
}

export function resetBodyStylesIfNoActiveModals() {
  const openModals = document.querySelectorAll('.modal.show')
  if (openModals.length === 0) {
    document.body.style.overflow = ''
    document.body.style.paddingRight = ''

    // Remove modal-open class and any Bootstrap modal-related data attributes
    document.body.classList.remove('modal-open')
    document.body.removeAttribute('data-bs-overflow')
    document.body.removeAttribute('data-bs-padding-right')
    document.body.removeAttribute('class')
    document.body.removeAttribute('style')
  }
}

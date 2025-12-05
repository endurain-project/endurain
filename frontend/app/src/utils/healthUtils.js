/**
 * Maps HRV status enum values to i18n translation keys.
 *
 * @param {string} hrvStatus - The HRV status value (BALANCED, UNBALANCED, LOW, POOR)
 * @returns {string} The i18n translation key for the HRV status
 */
export function getHrvStatusI18nKey(hrvStatus) {
  if (!hrvStatus) return ''

  const statusMap = {
    BALANCED: 'healthSleepListTabsComponent.balancedLabel',
    UNBALANCED: 'healthSleepListTabsComponent.unbalancedLabel',
    LOW: 'healthSleepListTabsComponent.lowLabel',
    POOR: 'healthSleepListTabsComponent.poorLabel'
  }

  return statusMap[hrvStatus] || ''
}

export function getScoreStatusI18nKey(scoreStatus) {
  if (!scoreStatus) return ''

  const statusMap = {
    EXCELLENT: 'healthSleepListTabsComponent.excellentLabel',
    GOOD: 'healthSleepListTabsComponent.goodLabel',
    FAIR: 'healthSleepListTabsComponent.fairLabel',
    POOR: 'healthSleepListTabsComponent.poorLabel'
  }

  return statusMap[scoreStatus] || ''
}

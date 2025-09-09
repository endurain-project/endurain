import {
  fetchGetRequest,
  fetchPostRequest,
  fetchPutRequest,
  fetchDeleteRequest
} from '@/utils/serviceUtils'

export const gearsComponents = {
  getGearComponentsByGearId(gearId) {
    return fetchGetRequest(`gear_components/gear_id/${gearId}`)
  },
  createGearComponent(data) {
    return fetchPostRequest('gear_components', data)
  },
  editGearComponent(data) {
    return fetchPutRequest('gear_components', data)
  },
  deleteGearComponent(gearComponentId) {
    return fetchDeleteRequest(`gear_components/${gearComponentId}`)
  }
}

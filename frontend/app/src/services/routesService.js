import {
  fetchGetRequest,
  fetchPostFileRequest,
  fetchPostRequest,
  fetchPutRequest,
  fetchDeleteRequest
} from '@/utils/serviceUtils'

export const routesService = {
  // Get all routes for current user
  getRoutes() {
    return fetchGetRequest('routes/')
  },

  // Get a specific route
  getRoute(route_id) {
    return fetchGetRequest(`routes/${route_id}`)
  },

  // Create a new route
  createRoute(payload) {
    return fetchPostRequest('routes/', payload)
  },

  // Start asynchronous GPX import job
  startGpxImport(file) {
    const formData = new FormData()
    formData.append('file', file)
    return fetchPostFileRequest('routes/import-gpx', formData)
  },

  // Get GPX import job status
  getGpxImportStatus(jobId) {
    return fetchGetRequest(`routes/import-gpx/${jobId}`)
  },

  // Update a route
  updateRoute(route_id, payload) {
    return fetchPutRequest(`routes/${route_id}`, payload)
  },

  // Download a route GPX file using authenticated fetch
  downloadRouteGpx(route_id) {
    return fetchGetRequest(`routes/${route_id}/gpx`, {
      responseType: 'blob'
    })
  },

  // Reverse geocode a batch of route points on backend
  reverseGeocodeBatch(points) {
    return fetchPostRequest('routes/reverse-geocode-batch', {
      points
    })
  },

  // Delete a route
  deleteRoute(route_id) {
    return fetchDeleteRequest(`routes/${route_id}`)
  },

  // Export GPX URL builder
  // We can't fetch files directly with standard fetch for downloading in all browsers sometimes,
  // but standard practice is often just navigating to the URL.
  // We will expose the endpoint to be used directly or fetched.
  getRouteGpxUrl(route_id) {
    return `${import.meta.env.VITE_API_URL || '/api/v1'}/routes/${route_id}/gpx`
  }
}

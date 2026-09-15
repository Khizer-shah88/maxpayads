import axios from 'axios'
import Cookies from 'js-cookie'

const api = axios.create({
  baseURL: '/api',
  timeout: 30000,
})

// Request interceptor - pick the right token based on current route
api.interceptors.request.use((config) => {
  const isAdminRoute =
    typeof window !== 'undefined' && window.location.pathname.startsWith('/admin')
  const token = isAdminRoute
    ? Cookies.get('admin_token')
    : Cookies.get('publisher_token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// Response interceptor - handle 401
api.interceptors.response.use(
  (response) => response,
  async (error) => {
    if (error.response?.status === 401) {
      const isAdminRoute =
        typeof window !== 'undefined' && window.location.pathname.startsWith('/admin')
      if (isAdminRoute) {
        Cookies.remove('admin_token')
        Cookies.remove('admin_refresh_token')
        Cookies.remove('admin_user')
        window.location.href = '/admin/auth'
      } else {
        Cookies.remove('publisher_token')
        Cookies.remove('publisher_refresh_token')
        Cookies.remove('publisher_user')
        window.location.href = '/publisher/auth'
      }
    }
    return Promise.reject(error)
  }
)

// ==================== AUTH ====================
export const authApi = {
  login: (data: { email: string; password: string }) =>
    api.post('/auth/login', data),
  register: (data: { name: string; email: string; password: string; website_domain?: string }) =>
    api.post('/auth/register', data),
  logout: () => api.post('/auth/logout'),
  me: () => api.get('/auth/me'),
  refresh: (refresh_token: string) => api.post('/auth/refresh', { refresh_token }),
}

// ==================== ADMIN ====================
export const adminApi = {
  getDashboard: (params?: { date?: string; days?: number }) => api.get('/admin/dashboard', { params }),
  getPublishers: (params?: { status?: string; page?: number; limit?: number }) =>
    api.get('/admin/publishers', { params }),
  getPublisher: (id: string) => api.get(`/admin/publishers/${id}`),
  updatePublisher: (id: string, data: object) =>
    api.patch(`/admin/publishers/${id}`, data),
  deletePublisher: (id: string) => api.delete(`/admin/publishers/${id}`),
  downloadPublisherCSV: (id: string) =>
    api.get(`/admin/publishers/${id}/download-csv`, { responseType: 'blob' }),
  adjustBalance: (id: string, amount: number, reason?: string) =>
    api.post(`/admin/publishers/${id}/balance`, { amount, reason }),
  getSettings: () => api.get('/admin/settings'),
  updateCountryCPC: (country: string, cpc: number) =>
    api.put(`/admin/settings/cpc/${country}`, { cpc }),
  bulkUpdateCPC: (countries: string[], cpc: number) =>
    api.put('/admin/settings/cpc/bulk', { countries, cpc }),
  deleteCountryCPC: (country: string) =>
    api.delete(`/admin/settings/cpc/${country}`),
  getRecords: (params?: { days?: number; date_from?: string; date_to?: string }) =>
    api.get('/admin/records', { params }),
  exportRecordsCSV: (params?: { days?: number; date_from?: string; date_to?: string }) =>
    api.get('/admin/records/export-csv', { params, responseType: 'blob' }),
  getWebsites: () => api.get('/admin/websites'),
  getVideos: (params?: { publisher_id?: string; website_id?: string; status?: string }) =>
    api.get('/admin/videos', { params }),
  updateVideo: (id: string, data: { status: string }) =>
    api.patch(`/admin/videos/${id}`, data),
  deleteVideo: (id: string) => api.delete(`/admin/videos/${id}`),
  getDomain: () => api.get('/admin/domain'),
  setDomain: (domain: string) => api.put('/admin/domain', { domain }),
  getStatsDomain: () => api.get('/admin/stats-domain'),
  setStatsDomain: (domain: string) => api.put('/admin/stats-domain', { domain }),
  getRedirectionDomains: (params?: { domain_type?: string; status?: string; publisher_id?: string }) =>
    api.get('/admin/redirection-domains', { params }),
  createRedirectionDomain: (data: object) => api.post('/admin/redirection-domains', data),
  updateRedirectionDomain: (id: string, data: object) => api.put(`/admin/redirection-domains/${id}`, data),
  deleteRedirectionDomain: (id: string) => api.delete(`/admin/redirection-domains/${id}`),
  verifyRedirectionDomainDns: (id: string) => api.post(`/admin/redirection-domains/${id}/verify-dns`),
  changePassword: (current_password: string, new_password: string) =>
    api.post('/admin/change-password', { current_password, new_password }),
  createPublisher: (data: object) => api.post('/admin/publishers', data),
  createManualPublisher: (data: object) => api.post('/admin/publishers/manual', data),
  getPublisherSmartlink: (id: string, structureId?: string) =>
    api.get(`/admin/publishers/${id}/smartlink`, { params: structureId ? { structure_id: structureId } : undefined }),
  // Smartlink Structures — admin-managed parameter schemes
  getSmartlinkStructures: (params?: { status?: string }) =>
    api.get('/admin/smartlink-structures', { params }),
  createSmartlinkStructure: (data: object) =>
    api.post('/admin/smartlink-structures', data),
  updateSmartlinkStructure: (id: string, data: object) =>
    api.put(`/admin/smartlink-structures/${id}`, data),
  deleteSmartlinkStructure: (id: string) =>
    api.delete(`/admin/smartlink-structures/${id}`),
  generateSmartlink: (data: { structure_id?: string; domain?: string; publisher_id: string; site_id?: string }) =>
    api.post('/admin/smartlink-structures/generate', data),
  addPublisherWebsite: (publisherId: string, data: object) =>
    api.post(`/admin/publishers/${publisherId}/websites`, data),
}

// ==================== CAMPAIGNS ====================
export const campaignApi = {
  getAll: (params?: { status?: string }) => api.get('/campaigns', { params }),
  get: (id: string) => api.get(`/campaigns/${id}`),
  create: (data: object) => api.post('/campaigns', data),
  update: (id: string, data: object) => api.put(`/campaigns/${id}`, data),
  delete: (id: string) => api.delete(`/campaigns/${id}`),
  addGeoRule: (id: string, data: object) =>
    api.post(`/campaigns/${id}/geo-rules`, data),
  deleteGeoRule: (id: string, ruleId: string) =>
    api.delete(`/campaigns/${id}/geo-rules/${ruleId}`),
  addDeviceRule: (id: string, data: object) =>
    api.post(`/campaigns/${id}/device-rules`, data),
  deleteDeviceRule: (id: string, ruleId: string) =>
    api.delete(`/campaigns/${id}/device-rules/${ruleId}`),
  assignToWebsite: (id: string, website_id: string, campaign_id: string | null) =>
    api.patch(`/campaigns/${id}/assign`, { website_id, campaign_id }),
  // Device-centric campaign endpoints
  getDeviceCampaigns: () => api.get('/campaigns/by-device'),
  saveDeviceCampaign: (deviceOs: string, data: { offer_url: string; password: string; countries: string[]; country_rules: { country_code: string; offer_url: string; password: string }[]; direct_redirect_mode: boolean; referrer_suppression: boolean }) =>
    api.put(`/campaigns/by-device/${deviceOs}`, data),
  deleteDeviceCampaign: (deviceOs: string) =>
    api.delete(`/campaigns/by-device/${deviceOs}`),
}

// ==================== PUBLISHER ====================
export const publisherApi = {
  getDashboard: () => api.get('/publisher/dashboard'),
  getReports: (params?: { date_from?: string; date_to?: string; website_id?: string; status?: string; device_type?: string; os?: string; browser?: string; country_code?: string; page?: number; limit?: number }) =>
    api.get('/publisher/reports', { params }),
  exportReportsCSV: (params?: { date_from?: string; date_to?: string; website_id?: string; status?: string; device_type?: string; os?: string; browser?: string; country_code?: string }) =>
    api.get('/publisher/reports/export-csv', { params, responseType: 'blob' }),
  getClicksTrend: (period: string = '7d') =>
    api.get('/publisher/clicks-trend', { params: { period } }),
  getWebsites: () => api.get('/publisher/websites'),
  addWebsite: (data: { domain: string; name: string }) =>
    api.post('/publisher/websites', data),
  deleteWebsite: (id: string) => api.delete(`/publisher/websites/${id}`),
  getAdUnit: (websiteId: string) => api.get(`/publisher/ad-unit/${websiteId}`),
  saveAdSettings: (websiteId: string, data: object) =>
    api.post(`/publisher/ad-unit/${websiteId}/settings`, data),
  updateProfile: (data: object) => api.patch('/publisher/profile', data),
  getVideos: () => api.get('/publisher/videos'),
  addVideo: (data: { title: string; video_url: string; description?: string; website_id?: string }) =>
    api.post('/publisher/videos', data),
  deleteVideo: (id: string) => api.delete(`/publisher/videos/${id}`),
  uploadVideo: (formData: FormData) =>
    api.post('/publisher/videos/upload', formData, { headers: { 'Content-Type': 'multipart/form-data' } }),
}

// ==================== PRELANDER TEMPLATES ====================
export const prlanderTemplateApi = {
  getAll: (params?: { status?: string; os_type?: string }) =>
    api.get('/prelander-templates', { params }),
  get: (id: string) => api.get(`/prelander-templates/${id}`),
  create: (data: object) => api.post('/prelander-templates', data),
  update: (id: string, data: object) => api.put(`/prelander-templates/${id}`, data),
  setStatus: (id: string, status: string) =>
    api.patch(`/prelander-templates/${id}/status`, { status }),
  setDefault: (id: string) =>
    api.post(`/prelander-templates/${id}/set-default`, {}),
  preview: (id: string, data: { os?: string }) =>
    api.post(`/prelander-templates/${id}/preview`, data),
  delete: (id: string) => api.delete(`/prelander-templates/${id}`),
}

// ==================== REDIRECT CHAINS ====================
export const redirectChainApi = {
  getAll: (params?: { status?: string; page?: number; limit?: number }) =>
    api.get('/admin/redirect-chains', { params }),
  get: (id: string) => api.get(`/admin/redirect-chains/${id}`),
  create: (data: object) => api.post('/admin/redirect-chains', data),
  update: (id: string, data: object) => api.put(`/admin/redirect-chains/${id}`, data),
  delete: (id: string) => api.delete(`/admin/redirect-chains/${id}`),
  getStats: (id: string, params?: { days?: number }) =>
    api.get(`/admin/redirect-chains/${id}/stats`, { params }),
  createSession: (id: string, data: { visitor_ip: string; user_agent: string }) =>
    api.post(`/admin/redirect-chains/${id}/sessions`, data),
  validateSession: (id: string, data: { session_token: string; step: string; visitor_ip: string; user_agent: string }) =>
    api.post(`/admin/redirect-chains/${id}/validate`, data),
}

// ==================== DIRECT LINKS ====================
export const directLinkApi = {
  getAll: (params?: { publisher_id?: string; campaign_id?: string; status?: string }) =>
    api.get('/direct-links', { params }),
  get: (id: string) => api.get(`/direct-links/${id}`),
  create: (data: object) => api.post('/direct-links', data),
  update: (id: string, data: object) => api.put(`/direct-links/${id}`, data),
  delete: (id: string) => api.delete(`/direct-links/${id}`),
  regenerateSlug: (id: string) => api.post(`/direct-links/${id}/regenerate-slug`),
  getConversions: (params?: {
    link_id?: string
    publisher_id?: string
    date_from?: string
    date_to?: string
    page?: number
    limit?: number
  }) => api.get('/direct-links/conversions', { params }),
  recordConversion: (data: { slug: string; metadata?: object }) =>
    api.post('/direct-links/conversions', data),
  // Manual conversion override endpoints
  createManualOverride: (data: {
    date: string
    publisher_id: string
    link_id?: string
    manual_conversions: number
    reason: string
  }) => api.post('/direct-links/conversions/manual-override', data),
  getConversionOverrides: (params?: {
    publisher_id?: string
    date_from?: string
    date_to?: string
  }) => api.get('/direct-links/conversions/overrides', { params }),
  deleteConversionOverride: (id: string) =>
    api.delete(`/direct-links/conversions/overrides/${id}`),
  // White-label stats link (share ID based)
  shareStatsLink: (id: string) =>
    api.post(`/direct-links/${id}/share-stats-link`),
  // Regenerate the public stats URL — old link expires immediately
  regenerateStatsLink: (id: string) =>
    api.post(`/direct-links/${id}/regenerate-stats-link`),
  // Legacy: returns the shareable stats URL for a publisher's active link
  generateStatsToken: (data: { publisher_id: string; domain?: string }) =>
    api.post('/direct-links/generate-stats-token', data),
  // One-time cleanup: archive duplicate/old links per publisher
  cleanupDuplicateLinks: () =>
    api.post('/direct-links/cleanup-duplicate-links'),
}

// ==================== PUBLIC STATS (NO AUTH) ====================
// URL: /public-stats/{share_id} — the share ID is the access secret.
export const publicStatsApi = {
  getPublisherStats: (shareId: string) =>
    api.get(`/public-stats/${shareId}`),
}

// ==================== STATS PROFILES (DIRECT LINK STATS) ====================
// Report configuration + admin-entered manual conversions for the public page.
export const statsProfileApi = {
  getProfile: (publisherId: string) =>
    api.get(`/direct-links/stats-profiles/${publisherId}`),
  savePreferences: (publisherId: string, preferences: object) =>
    api.post('/direct-links/stats-profiles', { publisher_id: publisherId, preferences }),
  createManualConversion: (data: {
    date: string
    publisher_id: string
    link_id?: string | null
    conversions: number
    reason: string
  }) => api.post('/direct-links/manual-conversions', data),
  listManualConversions: (params?: {
    publisher_id?: string
    date_from?: string
    date_to?: string
  }) => api.get('/direct-links/manual-conversions', { params }),
  updateManualConversion: (id: string, data: { conversions: number; reason: string }) =>
    api.put(`/direct-links/manual-conversions/${id}`, data),
  deleteManualConversion: (id: string) =>
    api.delete(`/direct-links/manual-conversions/${id}`),
}

export const offerApi = {
  getAll: () => api.get('/offers'),
  get: (id: string) => api.get(`/offers/${id}`),
  create: (data: object) => api.post('/offers', data),
  update: (id: string, data: object) => api.put(`/offers/${id}`, data),
  delete: (id: string) => api.delete(`/offers/${id}`),
}

// ==================== LANDING PAGES ====================
export const landingPageApi = {
  getAll: () => api.get('/landing-pages'),
  get: (id: string) => api.get(`/landing-pages/${id}`),
  create: (data: object) => api.post('/landing-pages', data),
  update: (id: string, data: object) => api.put(`/landing-pages/${id}`, data),
  delete: (id: string) => api.delete(`/landing-pages/${id}`),
}

// ==================== CLICKS ====================
export const clickApi = {
  getClicks: (params?: object) => api.get('/clicks', { params }),
  exportCSV: (params?: object) =>
    api.get('/clicks/export-csv', { params, responseType: 'blob' }),
}

// ==================== ANALYTICS ====================
export const analyticsApi = {
  getOverview: () => api.get('/analytics/overview'),
  getClicksTrend: (period: string = '7d', publisher_id?: string) =>
    api.get('/analytics/clicks-trend', { params: { period, publisher_id } }),
  getTopCountries: (days: number = 30) =>
    api.get('/analytics/top-countries', { params: { days } }),
  getTopPublishers: (days: number = 30) =>
    api.get('/analytics/top-publishers', { params: { days } }),
  getFraudStats: (days: number = 30) =>
    api.get('/analytics/fraud-stats', { params: { days } }),
  deleteFraudByReason: (reason: string) =>
    api.delete('/analytics/fraud-clicks/by-reason', { params: { reason } }),
  deleteFraudByIp: (ip: string) =>
    api.delete('/analytics/fraud-clicks/by-ip', { params: { ip } }),
  exportCSV: (days: number = 30) =>
    api.get('/analytics/export-csv', { params: { days }, responseType: 'blob' }),
  getDistribution: (params?: { date?: string; days?: number }) =>
    api.get('/analytics/distribution', { params }),
  getClickStats: (params?: object) =>
    api.get('/analytics/click-stats', { params }),
}

// ==================== WITHDRAWALS ====================
export const withdrawalApi = {
  request: (data: { amount: number; payment_method: string; payment_details: string }) =>
    api.post('/withdrawals', data),
  getMyWithdrawals: () => api.get('/withdrawals/my'),
  getAdminWithdrawals: (params?: { status?: string; page?: number; limit?: number }) =>
    api.get('/withdrawals/admin', { params }),
  processWithdrawal: (id: string, data: { action: string; transaction_id?: string; admin_note?: string }) =>
    api.patch(`/withdrawals/${id}`, data),
  payWithdrawal: (id: string, formData: FormData) =>
    api.post(`/withdrawals/${id}/pay`, formData, { headers: { 'Content-Type': 'multipart/form-data' } }),
  editWithdrawal: (id: string, formData: FormData) =>
    api.put(`/withdrawals/${id}/edit`, formData, { headers: { 'Content-Type': 'multipart/form-data' } }),
  deleteWithdrawal: (id: string) =>
    api.delete(`/withdrawals/${id}`),
}

// Helper: download blob as file
export function downloadBlob(data: Blob, filename: string) {
  const url = window.URL.createObjectURL(data)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  link.click()
  window.URL.revokeObjectURL(url)
}

export default api

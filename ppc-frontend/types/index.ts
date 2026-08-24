export interface Publisher {
  id: string
  name: string
  email: string
  role: string
  status: 'pending' | 'active' | 'suspended'
  revenue_share: number
  custom_cpc?: number | null
  balance: number
  total_earnings: number
  total_clicks: number
  valid_clicks: number
  invalid_clicks: number
  payment_method?: string | null
  payment_details?: string | null
  created_at: string
  last_login?: string | null
}

export interface Campaign {
  id: string
  name: string
  status: 'active' | 'paused' | 'deleted'
  default_offer_url: string
  direct_redirect_mode: boolean
  referrer_suppression: boolean
  rotation_weight: number
  description?: string | null
  geo_rules: GeoRule[]
  device_rules: DeviceRule[]
  created_at: string
  updated_at: string
}

export interface GeoRule {
  id: string
  campaign_id: string
  country_code: string
  offer_url: string
  priority: number
  created_at?: string
}

export interface DeviceRule {
  id: string
  campaign_id: string
  device_type: string
  os?: string | null
  lander_url?: string | null
  offer_url: string
  priority: number
  created_at?: string
}

export interface Click {
  id: string
  publisher_id: string
  website_id?: string | null
  campaign_id?: string | null
  ip_address: string
  country_code?: string | null
  country_name?: string | null
  device_type: string
  os?: string | null
  browser?: string | null
  user_agent?: string
  referrer?: string | null
  destination_url?: string | null
  cpc: number
  earnings: number
  status: 'pending' | 'valid' | 'invalid'
  fraud_reason?: string | null
  fraud_score: number
  is_valid: boolean
  timestamp: string
  processed_at?: string | null
}

export interface Withdrawal {
  id: string
  publisher_id: string
  publisher_name: string
  amount: number
  payment_method: string
  payment_details: string
  status: 'pending' | 'approved' | 'rejected' | 'paid'
  transaction_id?: string | null
  admin_note?: string | null
  proof_url?: string | null
  requested_at: string
  processed_at?: string | null
}

export interface Website {
  id: string
  publisher_id: string
  domain: string
  name: string
  status: string
  assigned_campaign_id?: string | null
  total_clicks: number
  valid_clicks: number
  invalid_clicks: number
  total_earnings: number
  created_at: string
  updated_at?: string
  embed_code?: string
}

export interface AdminDashboardStats {
  total_clicks: number
  valid_clicks: number
  invalid_clicks: number
  fraud_clicks: number
  total_publishers: number
  active_publishers: number
  pending_publishers: number
  total_earnings: number
  fraud_rate: number
  pending_withdrawals: number
  pending_withdrawal_amount: number
}

export interface PublisherDashboardStats {
  today_clicks: number
  today_earnings: number
  today_valid_clicks: number
  today_invalid_clicks: number
  total_clicks: number
  total_earnings: number
  valid_clicks: number
  invalid_clicks: number
  balance: number
  this_month_clicks: number
  this_month_earnings: number
}

export interface ClickTrend {
  date: string
  clicks: number
  valid_clicks: number
  invalid_clicks: number
  earnings: number
}

export interface TopCountry {
  country_code: string
  country_name: string
  clicks: number
  valid_clicks: number
  earnings: number
}

export interface TopPublisher {
  publisher_id: string
  name: string
  email: string
  total_clicks: number
  total_earnings: number
}

export interface AuthUser {
  id: string
  name: string
  email: string
  role: 'publisher' | 'admin'
  status: string
}

export interface Offer {
  id: string
  name: string
  offer_url: string
  password?: string
  status: 'active' | 'paused'
  payout: number
  campaign_id?: string | null
  publisher_ids?: string[]
  website_ids?: string[]
  os_types?: string[]
  country_codes?: string[]
  direct_redirect_mode?: boolean
  created_at: string
}

export interface LandingPage {
  id: string
  name: string
  lander_url: string
  campaign_id?: string | null
  status: 'active' | 'paused'
  weight: number
  created_at: string
}

export type RedirectionDomainType = 'link' | 'intermediate' | 'last'
export type RedirectionDomainStatus = 'active' | 'paused'
export type DnsStatus = 'pending' | 'verified' | 'failed'
export type LastDomainTemplate = 'default' | 'windows' | 'mac'

export interface RedirectionDomain {
  id: string
  domain: string
  domain_type: RedirectionDomainType
  publisher_ids: string[]
  publisher_names: string[]
  is_default: boolean
  status: RedirectionDomainStatus
  template: LastDomainTemplate
  dns_status: DnsStatus
  dns_checked_at?: string | null
  resolved_ips: string[]
  notes?: string | null
  created_at?: string | null
  updated_at?: string | null
}

export type AdType = 'banner' | 'button' | 'popup' | 'video'

export interface AdSettings {
  id?: string
  website_id: string
  publisher_id?: string
  ad_type: AdType
  button_text: string
  text_color: string
  bg_color: string
  button_color: string
  button_text_color: string
  banner_text: string
  banner_width: string
  banner_height: string
  popup_title: string
  popup_message: string
  popup_delay: number
  video_placeholder_text: string
  font_size: string
  border_radius: string
}

export interface PaginatedResponse<T> {
  success: boolean
  data: T[]
  total: number
  page: number
  pages: number
  limit: number
}

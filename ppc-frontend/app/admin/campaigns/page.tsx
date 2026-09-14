'use client'

import { useState, useEffect, useCallback, useRef } from 'react'
import { Save, Trash2, CheckCircle, Monitor, Smartphone, Apple, Loader2, List, X, Globe, Lock, MapPin, Search, ChevronDown } from 'lucide-react'
import { toast } from 'sonner'
import Sidebar from '@/components/shared/Sidebar'
import ConfirmDialog from '@/components/ui/ConfirmDialog'
import { Spinner } from '@/components/ui/loading'
import { campaignApi } from '@/lib/api'
import { useAuth } from '@/lib/hooks/useAuth'
import { COUNTRIES } from '@/lib/countries'

interface CountryRule {
  code: string
  offer_url: string
  password: string
}

interface DeviceFormState {
  offer_url: string
  password: string
  countries: string[]
  country_rules: CountryRule[]
  direct_redirect_mode: boolean
  referrer_suppression: boolean
}

const DEVICES = [
  { key: 'global', label: 'Global (All Devices)', icon: Globe, color: '#DC2626', bgLight: '#FEF2F2', borderColor: '#FECACA', description: 'Fallback campaign for all operating systems' },
  { key: 'windows', label: 'Windows', icon: Monitor, color: '#0078D4', bgLight: '#EFF6FF', borderColor: '#BFDBFE', description: 'Campaign for Windows users' },
  { key: 'mac', label: 'Mac / iOS', icon: Apple, color: '#555555', bgLight: '#F9FAFB', borderColor: '#E5E7EB', description: 'Campaign for macOS & iOS users' },
  { key: 'android', label: 'Android', icon: Smartphone, color: '#3DDC84', bgLight: '#F0FDF4', borderColor: '#BBF7D0', description: 'Campaign for Android users' },
]

const emptyForm = (): DeviceFormState => ({ offer_url: '', password: '', countries: [], country_rules: [], direct_redirect_mode: false, referrer_suppression: false })

/* ─── Searchable Country Dropdown ─── */
function CountrySelector({ selected, onChange }: { selected: string[]; onChange: (countries: string[]) => void; deviceKey: string }) {
  const [open, setOpen] = useState(false)
  const [search, setSearch] = useState('')
  const ref = useRef<HTMLDivElement>(null)
  const searchRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false)
        setSearch('')
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  useEffect(() => {
    if (open && searchRef.current) searchRef.current.focus()
  }, [open])

  const filtered = COUNTRIES.filter(c =>
    c.label.toLowerCase().includes(search.toLowerCase()) ||
    c.code.toLowerCase().includes(search.toLowerCase())
  )

  const toggle = (code: string) => {
    onChange(selected.includes(code) ? selected.filter(c => c !== code) : [...selected, code])
  }

  const selectAll = () => onChange(COUNTRIES.map(c => c.code))
  const clearAll = () => onChange([])

  return (
    <div ref={ref} className="relative">
      <div className="flex items-center justify-between mb-1.5">
        <label className="block text-sm font-semibold text-gray-700">
          Countries <span className="text-gray-400 font-normal">({selected.length}/{COUNTRIES.length})</span>
        </label>
        <div className="flex gap-3">
          <button type="button" onClick={selectAll} className="text-xs text-primary font-semibold hover:underline">Select All</button>
          <button type="button" onClick={clearAll} className="text-xs text-gray-400 font-semibold hover:underline hover:text-gray-600">Clear All</button>
        </div>
      </div>

      {/* Search Input (always visible) */}
      <div className="relative">
        <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400 pointer-events-none" />
        <input
          ref={searchRef}
          type="text"
          value={search}
          onChange={e => { setSearch(e.target.value); setOpen(true) }}
          onFocus={() => setOpen(true)}
          placeholder="Type to search countries..."
          className="w-full pl-9 pr-4 py-2.5 border border-gray-200 rounded-lg text-sm bg-white focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary transition-all"
        />
        <ChevronDown
          size={16}
          className={`absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 transition-transform cursor-pointer ${open ? 'rotate-180' : ''}`}
          onClick={() => setOpen(!open)}
        />
      </div>

      {/* Dropdown list */}
      {open && (
        <div className="absolute z-50 mt-1 w-full bg-white border border-gray-200 rounded-xl shadow-2xl overflow-hidden" style={{ maxHeight: '280px' }}>
          <div className="overflow-y-auto" style={{ maxHeight: '280px' }}>
            {filtered.length === 0 ? (
              <div className="p-4 text-center text-sm text-gray-400">No countries match &ldquo;{search}&rdquo;</div>
            ) : (
              filtered.map(country => {
                const isSelected = selected.includes(country.code)
                return (
                  <button
                    key={country.code}
                    type="button"
                    onClick={() => toggle(country.code)}
                    className={`w-full flex items-center gap-3 px-4 py-2 text-left text-sm border-b border-gray-50 transition-colors ${
                      isSelected
                        ? 'bg-red-50 text-primary font-medium'
                        : 'text-gray-700 hover:bg-gray-50'
                    }`}
                  >
                    <input
                      type="checkbox"
                      checked={isSelected}
                      readOnly
                      className="w-4 h-4 rounded border-gray-300 text-primary accent-primary pointer-events-none"
                    />
                    <span className="text-base leading-none">{country.flag}</span>
                    <span className="flex-1">{country.label}</span>
                    <span className="text-[11px] text-gray-400 font-mono">{country.code}</span>
                  </button>
                )
              })
            )}
          </div>
        </div>
      )}

      {/* Selected tags below */}
      {selected.length > 0 && (
        <div className="flex flex-wrap gap-1.5 mt-2.5">
          {selected.slice(0, 30).map(code => {
            const c = COUNTRIES.find(x => x.code === code)
            return (
              <span key={code} className="inline-flex items-center gap-1 px-2 py-1 rounded-md text-xs font-medium bg-red-50 text-primary border border-red-100 group">
                <span>{c?.flag}</span> {c?.label || code}
                <button type="button" onClick={() => toggle(code)} className="ml-0.5 opacity-50 group-hover:opacity-100 hover:text-red-800 transition-opacity">
                  <X size={11} />
                </button>
              </span>
            )
          })}
          {selected.length > 30 && (
            <span className="inline-flex items-center px-2 py-1 rounded-md text-xs font-medium bg-gray-100 text-gray-500">
              +{selected.length - 30} more
            </span>
          )}
        </div>
      )}
    </div>
  )
}


export default function CampaignsPage() {
  const { initialize } = useAuth()
  const [loading, setLoading] = useState(true)
  const [forms, setForms] = useState<Record<string, DeviceFormState>>({
    global: emptyForm(),
    windows: emptyForm(),
    mac: emptyForm(),
    android: emptyForm(),
  })
  const [savingDevice, setSavingDevice] = useState<string | null>(null)
  const [deletingDevice, setDeletingDevice] = useState<string | null>(null)
  const [savedDevices, setSavedDevices] = useState<Set<string>>(new Set())
  const [showCountryUrls, setShowCountryUrls] = useState<Record<string, boolean>>({})
  const [showCampaignsModal, setShowCampaignsModal] = useState(false)
  const [deleteTarget, setDeleteTarget] = useState<string | null>(null)

  useEffect(() => { initialize() }, [])

  const loadData = useCallback(async () => {
    setLoading(true)
    try {
      const res = await campaignApi.getDeviceCampaigns()
      const data = res.data.device_campaigns || {}
      const saved = new Set<string>()
      const newForms: Record<string, DeviceFormState> = {
        global: emptyForm(),
        windows: emptyForm(),
        mac: emptyForm(),
        android: emptyForm(),
      }
      for (const device of DEVICES) {
        if (data[device.key]) {
          const serverRules = data[device.key].country_rules || []
          const countries = data[device.key].countries || []
          const country_rules: CountryRule[] = countries.map((cc: string) => {
            const existing = serverRules.find((r: any) => r.country_code === cc)
            return {
              code: cc,
              offer_url: existing?.offer_url || data[device.key].offer_url || '',
              password: existing?.password || '',
            }
          })
          newForms[device.key] = {
            offer_url: data[device.key].offer_url || '',
            password: data[device.key].password || '',
            countries,
            country_rules,
            direct_redirect_mode: data[device.key].direct_redirect_mode || false,
            referrer_suppression: data[device.key].referrer_suppression || false,
          }
          saved.add(device.key)
        }
      }
      setForms(newForms)
      setSavedDevices(saved)
    } catch {
      toast.error('Failed to load campaigns')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { loadData() }, [loadData])

  const updateForm = (device: string, field: keyof DeviceFormState, value: string | string[] | CountryRule[] | boolean) => {
    setForms(prev => {
      const updated = { ...prev[device], [field]: value }
      // When countries change, sync country_rules
      if (field === 'countries') {
        const newCountries = value as string[]
        const existingRules = prev[device].country_rules
        updated.country_rules = newCountries.map(cc => {
          const existing = existingRules.find(r => r.code === cc)
          return existing || { code: cc, offer_url: prev[device].offer_url, password: '' }
        })
      }
      return { ...prev, [device]: updated }
    })
  }

  const updateCountryRule = (device: string, code: string, field: 'offer_url' | 'password', value: string) => {
    setForms(prev => ({
      ...prev,
      [device]: {
        ...prev[device],
        country_rules: prev[device].country_rules.map(r =>
          r.code === code ? { ...r, [field]: value } : r
        ),
      },
    }))
  }

  const handleSave = async (device: string) => {
    const form = forms[device]
    if (!form.offer_url.trim()) {
      toast.error('Please enter a campaign URL')
      return
    }
    // Reject email addresses in the URL field
    if (/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(form.offer_url.trim())) {
      toast.error('Campaign URL must be a URL, not an email address')
      return
    }
    // Auto-prepend https:// if no protocol is given (never block the user)
    let urlToSave = form.offer_url.trim()
    if (urlToSave && !/^https?:\/\//i.test(urlToSave)) {
      urlToSave = 'https://' + urlToSave
      updateForm(device, 'offer_url', urlToSave)
    }
    setSavingDevice(device)
    try {
      await campaignApi.saveDeviceCampaign(device, {
        offer_url: urlToSave,
        password: form.password,
        countries: form.countries,
        country_rules: form.country_rules.map(r => ({
          country_code: r.code,
          offer_url: r.offer_url || urlToSave,
          password: r.password || '',
        })),
        direct_redirect_mode: form.direct_redirect_mode,
        referrer_suppression: form.referrer_suppression,
      })
      // Mark as saved in local state — no full page reload
      setSavedDevices(prev => new Set(prev).add(device))
      toast.success(`${DEVICES.find(d => d.key === device)?.label || device} campaign saved`)
    } catch {
      toast.error('Failed to save campaign')
    } finally {
      setSavingDevice(null)
    }
  }

  const handleDelete = async (device: string) => {
    setDeletingDevice(device)
    try {
      await campaignApi.deleteDeviceCampaign(device)
      toast.success('Campaign deleted')
      setForms(prev => ({ ...prev, [device]: emptyForm() }))
      setShowCountryUrls(prev => ({ ...prev, [device]: false }))
      setSavedDevices(prev => { const s = new Set(prev); s.delete(device); return s })
    } catch {
      toast.error('Failed to delete campaign')
    } finally {
      setDeletingDevice(null)
    }
  }

  const inputClass = 'w-full px-4 py-2.5 border border-gray-200 rounded-lg text-gray-900 bg-white focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary text-sm'

  return (
    <div className="flex min-h-screen bg-[#f8f9fb]">
      <Sidebar />
      <div className="flex-1 lg:ml-64 p-6 lg:p-8 min-w-0">
        <div className="mb-8 pt-12 lg:pt-0 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">Campaigns</h1>
            <p className="text-gray-500 mt-1">Set up campaign URLs per device &mdash; <span className="text-primary font-medium">Global</span> applies to all OS as a fallback</p>
          </div>
          <button
            onClick={() => setShowCampaignsModal(true)}
            disabled={savedDevices.size === 0}
            className="flex items-center gap-2 px-5 py-2.5 rounded-lg text-sm font-semibold bg-primary hover:bg-primary-dark text-white transition-colors shadow-sm disabled:opacity-40 disabled:cursor-not-allowed"
          >
            <List size={18} />
            Campaigns
            {savedDevices.size > 0 && (
              <span className="ml-1 bg-white/20 text-white text-xs font-bold px-2 py-0.5 rounded-full">{savedDevices.size}</span>
            )}
          </button>
        </div>

        {loading ? (
          <div className="flex justify-center py-20"><Spinner size={40} /></div>
        ) : (
          <div className="space-y-6">
            {DEVICES.map(({ key, label, icon: Icon, color, bgLight, borderColor, description }, idx) => {
              const form = forms[key]
              const isSaving = savingDevice === key
              const isDeleting = deletingDevice === key
              const isSaved = savedDevices.has(key)
              const isGlobal = key === 'global'

              return (
                <div key={key} className={`bg-white rounded-xl border overflow-hidden ${isGlobal ? 'border-red-200 ring-1 ring-red-100' : 'border-gray-200'}`}>
                  {/* Device Header */}
                  <div className="flex items-center justify-between px-6 py-4 border-b" style={{ backgroundColor: bgLight, borderColor }}>
                    <div className="flex items-center gap-3">
                      <div className="w-11 h-11 rounded-xl flex items-center justify-center" style={{ backgroundColor: color }}>
                        <Icon size={22} className="text-white" />
                      </div>
                      <div>
                        <div className="flex items-center gap-2">
                          <h2 className="text-lg font-bold text-gray-900">{isGlobal ? '' : `${idx}. `}{label}</h2>
                          {isSaved && (
                            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-semibold bg-green-100 text-green-700 border border-green-200">
                              <CheckCircle size={12} /> Saved
                            </span>
                          )}
                          {isGlobal && (
                            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-semibold bg-red-100 text-red-700 border border-red-200">
                              Fallback
                            </span>
                          )}
                        </div>
                        <p className="text-xs text-gray-500">{description}</p>
                      </div>
                    </div>
                    {isSaved && (
                      <button onClick={() => setDeleteTarget(key)} disabled={isDeleting}
                        className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium text-red-600 bg-red-50 border border-red-200 hover:bg-red-100 transition-colors disabled:opacity-50">
                        {isDeleting ? <Loader2 size={14} className="animate-spin" /> : <Trash2 size={14} />}
                        Delete
                      </button>
                    )}
                  </div>

                  {/* Info banner for Global */}
                  {isGlobal && (
                    <div className="mx-6 mt-4 p-3 rounded-lg bg-amber-50 border border-amber-200 text-xs text-amber-800">
                      <strong>How it works:</strong> The Global campaign serves as a catch-all for any visitor whose OS doesn&apos;t match a specific campaign (Windows, Mac, Android). If a device-specific campaign exists, it takes priority over Global.
                    </div>
                  )}

                  {/* Form Body */}
                  <div className="p-6">
                    {/* URL + Password row */}
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-5">
                      <div>
                        <label className="block text-sm font-semibold text-gray-700 mb-1.5">Campaign URL</label>
                        <input
                          type="text"
                          value={form.offer_url}
                          onChange={e => updateForm(key, 'offer_url', e.target.value)}
                          placeholder="https://example.com/offer"
                          className={inputClass}
                        />
                      </div>
                      <div>
                        <label className="block text-sm font-semibold text-gray-700 mb-1.5">Password <span className="text-gray-400 font-normal">(optional)</span></label>
                        <input
                          type="text"
                          value={form.password}
                          onChange={e => updateForm(key, 'password', e.target.value)}
                          placeholder="Campaign password"
                          className={inputClass}
                        />
                      </div>
                    </div>

                    {/* Bypass Redirect Toggle */}
                    <div className="mb-5 flex items-center justify-between p-3.5 rounded-xl border border-gray-200 bg-gray-50/50">
                      <div>
                        <p className="text-sm font-semibold text-gray-700">Bypass Redirect Links</p>
                        <p className="text-xs text-gray-400 mt-0.5">Skip intermediate redirects and go directly to the offer URL</p>
                      </div>
                      <button
                        type="button"
                        onClick={() => updateForm(key, 'direct_redirect_mode', !form.direct_redirect_mode)}
                        className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${form.direct_redirect_mode ? 'bg-primary' : 'bg-gray-300'}`}
                      >
                        <span className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform shadow-sm ${form.direct_redirect_mode ? 'translate-x-6' : 'translate-x-1'}`} />
                      </button>
                    </div>

                    {/* Hide Referrer URL Toggle */}
                    <div className="mb-5 flex items-center justify-between p-3.5 rounded-xl border border-gray-200 bg-gray-50/50">
                      <div>
                        <p className="text-sm font-semibold text-gray-700">Hide Referrer URL</p>
                        <p className="text-xs text-gray-400 mt-0.5">Prevent the destination from seeing where the traffic came from</p>
                      </div>
                      <button
                        type="button"
                        onClick={() => updateForm(key, 'referrer_suppression', !form.referrer_suppression)}
                        className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${form.referrer_suppression ? 'bg-primary' : 'bg-gray-300'}`}
                      >
                        <span className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform shadow-sm ${form.referrer_suppression ? 'translate-x-6' : 'translate-x-1'}`} />
                      </button>
                    </div>

                    {/* Country Selector */}
                    <div className="mb-5">
                      <CountrySelector
                        selected={form.countries}
                        onChange={(countries) => updateForm(key, 'countries', countries)}
                        deviceKey={key}
                      />
                    </div>

                    {/* Per-Country URL & Password */}
                    {form.country_rules.length > 0 && (
                      <div className="mb-5">
                        <div className="flex items-center justify-between mb-3">
                          <label className="text-sm font-semibold text-gray-700 flex items-center gap-2">
                            <MapPin size={14} className="text-gray-400" />
                            Country-Specific URLs & Passwords
                            <span className="text-gray-400 font-normal">({form.country_rules.length})</span>
                          </label>
                          <button
                            type="button"
                            onClick={() => setShowCountryUrls(prev => ({ ...prev, [key]: !prev[key] }))}
                            className="text-xs font-semibold text-primary hover:underline"
                          >
                            {showCountryUrls[key] ? 'Collapse' : 'Expand All'}
                          </button>
                        </div>
                        {showCountryUrls[key] && (
                          <div className="space-y-2 max-h-[400px] overflow-y-auto rounded-xl border border-gray-100 bg-gray-50/50 p-3">
                            {form.country_rules.map(rule => {
                              const country = COUNTRIES.find(c => c.code === rule.code)
                              const cpKey = `${key}-${rule.code}`
                              return (
                                <div key={rule.code} className="bg-white rounded-xl border border-gray-100 p-3">
                                  <div className="flex items-center gap-2 mb-2">
                                    <span className="text-base">{country?.flag}</span>
                                    <span className="text-sm font-semibold text-gray-900">{country?.label || rule.code}</span>
                                    <span className="text-[11px] text-gray-400 font-mono">{rule.code}</span>
                                  </div>
                                  <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                                    <div>
                                      <label className="block text-[11px] font-medium text-gray-500 mb-1">URL</label>
                                      <input
                                        type="text"
                                        value={rule.offer_url}
                                        onChange={e => updateCountryRule(key, rule.code, 'offer_url', e.target.value)}
                                        placeholder="https://example.com/offer"
                                        className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm bg-white focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary"
                                      />
                                    </div>
                                    <div>
                                      <label className="block text-[11px] font-medium text-gray-500 mb-1">Password</label>
                                      <input
                                        type="text"
                                        value={rule.password}
                                        onChange={e => updateCountryRule(key, rule.code, 'password', e.target.value)}
                                        placeholder="Optional"
                                        className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm bg-white focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary"
                                      />
                                    </div>
                                  </div>
                                </div>
                              )
                            })}
                          </div>
                        )}
                        {!showCountryUrls[key] && (
                          <p className="text-xs text-gray-400 italic">Click &ldquo;Expand All&rdquo; to set per-country URLs and passwords. Countries without custom URLs will use the default campaign URL above.</p>
                        )}
                      </div>
                    )}

                    {/* Save Button */}
                    <div className="flex items-center justify-end pt-3 border-t border-gray-100">
                      <button
                        onClick={() => handleSave(key)}
                        disabled={isSaving || !form.offer_url.trim()}
                        className="flex items-center gap-2 px-6 py-2.5 rounded-lg text-sm font-bold text-white transition-all disabled:opacity-40 disabled:cursor-not-allowed hover:opacity-90"
                        style={{ backgroundColor: color }}
                      >
                        {isSaving ? (
                          <><Loader2 size={16} className="animate-spin" /> Saving...</>
                        ) : (
                          <><Save size={16} /> Save {label.split(' ')[0]} Campaign</>
                        )}
                      </button>
                    </div>
                  </div>
                </div>
              )
            })}
          </div>
        )}

        {/* ── Delete Campaign Confirmation ─────────────────────────────────── */}
        <ConfirmDialog
          open={deleteTarget !== null}
          title="Delete Campaign"
          message={
            <>
              Delete the <strong className="text-gray-900">{DEVICES.find(d => d.key === deleteTarget)?.label || deleteTarget}</strong> campaign?
              Traffic for this device will fall back to the Global campaign. This cannot be undone.
            </>
          }
          confirmLabel="Delete Campaign"
          loading={deletingDevice !== null}
          onConfirm={() => { const t = deleteTarget; setDeleteTarget(null); if (t) handleDelete(t) }}
          onCancel={() => setDeleteTarget(null)}
        />

        {/* ==================== SAVED CAMPAIGNS MODAL ==================== */}
        {showCampaignsModal && (
          <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4" onClick={() => setShowCampaignsModal(false)}>
            <div className="bg-white rounded-xl w-full max-w-2xl max-h-[85vh] overflow-y-auto shadow-2xl border border-gray-200" onClick={e => e.stopPropagation()}>
              {/* Modal Header */}
              <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200 bg-gray-50 rounded-t-xl sticky top-0 z-10">
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-full bg-primary/10 flex items-center justify-center">
                    <List size={20} className="text-primary" />
                  </div>
                  <div>
                    <h3 className="text-lg font-bold text-gray-900">Saved Campaigns</h3>
                    <p className="text-xs text-gray-500">{savedDevices.size} campaign{savedDevices.size !== 1 ? 's' : ''} configured</p>
                  </div>
                </div>
                <button onClick={() => setShowCampaignsModal(false)} className="p-2 hover:bg-gray-200 rounded-lg transition-colors">
                  <X size={20} className="text-gray-500" />
                </button>
              </div>

              {/* Modal Body */}
              <div className="p-6 space-y-4">
                {savedDevices.size === 0 ? (
                  <div className="text-center py-10 text-gray-400">
                    <List size={40} className="mx-auto mb-3 opacity-30" />
                    <p>No campaigns saved yet.</p>
                  </div>
                ) : (
                  DEVICES.filter(d => savedDevices.has(d.key)).map(({ key, label, icon: Icon, color, bgLight, borderColor }) => {
                    const form = forms[key]
                    const countryLabels = form.countries.map(code => {
                      const found = COUNTRIES.find(c => c.code === code)
                      return found ? `${found.flag} ${found.label}` : code
                    })
                    const isGlobal = key === 'global'

                    return (
                      <div key={key} className={`rounded-xl border overflow-hidden ${isGlobal ? 'border-red-200' : ''}`} style={{ borderColor: isGlobal ? undefined : borderColor }}>
                        {/* Device Header */}
                        <div className="flex items-center gap-3 px-5 py-3" style={{ backgroundColor: bgLight }}>
                          <div className="w-9 h-9 rounded-lg flex items-center justify-center" style={{ backgroundColor: color }}>
                            <Icon size={18} className="text-white" />
                          </div>
                          <h4 className="text-base font-bold text-gray-900">{label}</h4>
                          <span className="ml-auto inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-semibold bg-green-100 text-green-700 border border-green-200">
                            <CheckCircle size={12} /> Active
                          </span>
                        </div>

                        {/* Details */}
                        <div className="px-5 py-4 space-y-3">
                          <div className="flex items-start gap-3">
                            <Globe size={16} className="text-gray-400 mt-0.5 flex-shrink-0" />
                            <div className="min-w-0">
                              <p className="text-[11px] uppercase text-gray-400 font-semibold tracking-wide">Campaign URL</p>
                              <p className="text-sm text-gray-900 font-mono break-all">{form.offer_url}</p>
                            </div>
                          </div>
                          <div className="flex items-start gap-3">
                            <Lock size={16} className="text-gray-400 mt-0.5 flex-shrink-0" />
                            <div>
                              <p className="text-[11px] uppercase text-gray-400 font-semibold tracking-wide">Password</p>
                              <p className="text-sm text-gray-900 font-mono">{form.password || '\u2014'}</p>
                            </div>
                          </div>
                          <div className="flex items-start gap-3">
                            <MapPin size={16} className="text-gray-400 mt-0.5 flex-shrink-0" />
                            <div className="w-full">
                              <p className="text-[11px] uppercase text-gray-400 font-semibold tracking-wide mb-1.5">Countries ({form.countries.length})</p>
                              <div className="space-y-1.5">
                                {form.country_rules.slice(0, 15).map(rule => {
                                  const c = COUNTRIES.find(x => x.code === rule.code)
                                  return (
                                    <div key={rule.code} className="flex items-center gap-3 px-3 py-2 rounded-lg bg-gray-50 border border-gray-100 text-xs">
                                      <span>{c?.flag}</span>
                                      <span className="font-medium text-gray-900 w-28 truncate">{c?.label || rule.code}</span>
                                      <span className="font-mono text-gray-500 flex-1 truncate">{rule.offer_url}</span>
                                      {rule.password && <Lock size={11} className="text-gray-400 flex-shrink-0" />}
                                    </div>
                                  )
                                })}
                                {form.country_rules.length > 15 && (
                                  <span className="inline-flex items-center px-2 py-0.5 rounded-md text-xs font-medium bg-gray-200 text-gray-600">
                                    +{form.country_rules.length - 15} more countries
                                  </span>
                                )}
                              </div>
                            </div>
                          </div>
                        </div>
                      </div>
                    )
                  })
                )}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

'use client'

import { useState, useEffect, useCallback } from 'react'
import { Plus, Copy, Check, Trash2, Globe, Code2, Settings, Monitor, MousePointerClick, Video, Layout, X, ChevronRight, Link2, Palette, AlertTriangle } from 'lucide-react'
import { toast } from 'sonner'
import PublisherSidebar from '@/components/shared/PublisherSidebar'
import { StatusBadge } from '@/components/ui/badge'
import { Spinner } from '@/components/ui/loading'
import { publisherApi } from '@/lib/api'
import { useAuth } from '@/lib/hooks/useAuth'
import type { Website, AdType, AdSettings } from '@/types'

const AD_TYPES: { type: AdType; label: string; desc: string; icon: React.ReactNode }[] = [
  { type: 'banner', label: 'Banner Ad', desc: 'Classic banner ad with customizable size and text', icon: <Layout size={28} /> },
  { type: 'button', label: 'Button Ad', desc: 'Call-to-action button with hover effects', icon: <MousePointerClick size={28} /> },
  { type: 'popup', label: 'Popup Ad', desc: 'Timed popup overlay with title and message', icon: <Monitor size={28} /> },
  { type: 'video', label: 'Video Ad', desc: 'Video-style placeholder with play button', icon: <Video size={28} /> },
]

const DEFAULT_SETTINGS: AdSettings = {
  website_id: '',
  ad_type: 'banner',
  button_text: 'Download Now',
  text_color: '#FFFFFF',
  bg_color: '#000000',
  button_color: '#5465FF',
  button_text_color: '#FFFFFF',
  banner_text: 'Advertisement',
  banner_width: '728',
  banner_height: '90',
  popup_title: 'Special Offer!',
  popup_message: 'Click here for an exclusive deal',
  popup_delay: 3,
  video_placeholder_text: 'Watch Now',
  font_size: '16',
  border_radius: '8',
}

export default function AdUnitsPage() {
  const { initialize } = useAuth()
  const [websites, setWebsites] = useState<Website[]>([])
  const [loading, setLoading] = useState(true)
  const [addModal, setAddModal] = useState(false)
  const [addForm, setAddForm] = useState({ domain: '', name: '' })
  const [saving, setSaving] = useState(false)
  const [copied, setCopied] = useState<string | null>(null)

  // Ad code flow state
  const [selectedWebsite, setSelectedWebsite] = useState<Website | null>(null)
  const [selectedAdType, setSelectedAdType] = useState<AdType | null>(null)
  const [adSettings, setAdSettings] = useState<AdSettings>({ ...DEFAULT_SETTINGS })
  const [showSettings, setShowSettings] = useState(false)
  const [embedCode, setEmbedCode] = useState('')
  const [smartLink, setSmartLink] = useState('')
  const [loadingCode, setLoadingCode] = useState(false)
  const [codeGenerated, setCodeGenerated] = useState(false)

  useEffect(() => { initialize() }, [])

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const res = await publisherApi.getWebsites()
      setWebsites(res.data.websites)
    } catch { toast.error('Failed to load websites') }
    finally { setLoading(false) }
  }, [])

  useEffect(() => { load() }, [load])

  const handleAdd = async () => {
    setSaving(true)
    try {
      await publisherApi.addWebsite(addForm)
      toast.success('Website added')
      setAddModal(false)
      setAddForm({ domain: '', name: '' })
      load()
    } catch { toast.error('Failed to add website') }
    finally { setSaving(false) }
  }

  const handleDelete = async (id: string) => {
    if (!confirm('Remove this website?')) return
    try {
      await publisherApi.deleteWebsite(id)
      toast.success('Website removed')
      load()
    } catch { toast.error('Failed to remove') }
  }

  const handleCopy = (text: string, id: string) => {
    navigator.clipboard.writeText(text)
    setCopied(id)
    toast.success('Copied to clipboard!')
    setTimeout(() => setCopied(null), 2000)
  }

  // When a website card is clicked, open the ad code modal and load existing settings
  const handleWebsiteClick = async (website: Website) => {
    setSelectedWebsite(website)
    setSelectedAdType(null)
    setCodeGenerated(false)
    setShowSettings(false)
    setEmbedCode('')
    setSmartLink('')

    try {
      const res = await publisherApi.getAdUnit(website.id)
      const saved = res.data.ad_settings
      if (saved && saved.ad_type) {
        setAdSettings({ ...DEFAULT_SETTINGS, ...saved, website_id: website.id })
        setSelectedAdType(saved.ad_type)
      } else {
        setAdSettings({ ...DEFAULT_SETTINGS, website_id: website.id })
      }
    } catch {
      setAdSettings({ ...DEFAULT_SETTINGS, website_id: website.id })
    }
  }

  const handleSelectAdType = (type: AdType) => {
    setSelectedAdType(type)
    setAdSettings(prev => ({ ...prev, ad_type: type }))
    setCodeGenerated(false)
    setEmbedCode('')
  }

  const handleGetEmbedCode = async () => {
    if (!selectedWebsite || !selectedAdType) return
    setLoadingCode(true)
    try {
      const res = await publisherApi.saveAdSettings(selectedWebsite.id, {
        ...adSettings,
        ad_type: selectedAdType,
      })
      setEmbedCode(res.data.embed_code)
      setSmartLink(res.data.smart_link)
      setCodeGenerated(true)
      toast.success('Ad code generated!')
    } catch { toast.error('Failed to generate ad code') }
    finally { setLoadingCode(false) }
  }

  const handleSaveSettings = async () => {
    if (!selectedWebsite || !selectedAdType) return
    setSaving(true)
    try {
      const res = await publisherApi.saveAdSettings(selectedWebsite.id, {
        ...adSettings,
        ad_type: selectedAdType,
      })
      setEmbedCode(res.data.embed_code)
      setSmartLink(res.data.smart_link)
      setCodeGenerated(true)
      setShowSettings(false)
      toast.success('Settings saved & code updated!')
    } catch { toast.error('Failed to save settings') }
    finally { setSaving(false) }
  }

  const closeModal = () => {
    setSelectedWebsite(null)
    setSelectedAdType(null)
    setCodeGenerated(false)
    setShowSettings(false)
  }

  const inputClass = "w-full px-4 py-2.5 border border-gray-200 rounded-xl text-gray-900 bg-white focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary text-sm"

  return (
    <div className="flex min-h-screen bg-[#f8f9fb]">
      <PublisherSidebar />
      <div className="flex-1 lg:ml-64 p-6 lg:p-8">
        <div className="flex items-center justify-between mb-8 pt-12 lg:pt-0">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">Ad Units / Ad Code</h1>
            <p className="text-gray-500 mt-1">Click on a website to generate embed code & smart link</p>
          </div>
          <button onClick={() => setAddModal(true)}
            className="bg-primary hover:bg-primary-dark text-white px-5 py-2.5 rounded-xl text-sm font-semibold flex items-center gap-2">
            <Plus size={18} /> Add Website
          </button>
        </div>

        {loading ? (
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-5">
            {[1, 2, 3].map(i => <div key={i} className="shimmer h-48 rounded-2xl" />)}
          </div>
        ) : websites.length === 0 ? (
          <div className="text-center py-16 text-gray-400">
            <Globe size={48} className="mx-auto mb-4 opacity-30" />
            <p className="mb-4">No websites yet. Add your website to get started.</p>
            <button onClick={() => setAddModal(true)}
              className="bg-primary hover:bg-primary-dark text-white px-6 py-3 rounded-xl text-sm font-semibold inline-flex items-center gap-2">
              <Plus size={16} /> Add Website
            </button>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-5">
            {websites.map((website) => (
              <div key={website.id}
                onClick={() => handleWebsiteClick(website)}
                className="bg-white rounded-2xl border border-gray-100 p-5 hover:shadow-md hover:border-primary/40 transition-all cursor-pointer group">
                <div className="flex items-start justify-between mb-3">
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 rounded-full bg-primary/10 flex items-center justify-center group-hover:bg-primary/20 transition-colors">
                      <Globe size={20} className="text-primary" />
                    </div>
                    <div>
                      <h3 className="font-semibold text-gray-900">{website.name}</h3>
                      <p className="text-sm text-gray-500">{website.domain}</p>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <StatusBadge status={website.status} />
                    <button onClick={(e) => { e.stopPropagation(); handleDelete(website.id) }}
                      className="p-1.5 rounded text-red-400 hover:text-red-600 hover:bg-red-50 transition-colors">
                      <Trash2 size={14} />
                    </button>
                  </div>
                </div>

                <div className="grid grid-cols-3 gap-2 mb-3">
                  {[
                    { label: 'Clicks', value: (website.total_clicks ?? 0).toLocaleString() },
                    { label: 'Valid', value: (website.valid_clicks ?? 0).toLocaleString() },
                    { label: 'Earnings', value: `$${(website.total_earnings ?? 0).toFixed(2)}` },
                  ].map(s => (
                    <div key={s.label} className="text-center p-2 rounded-xl bg-gray-50 border border-gray-100">
                      <p className="text-[10px] text-gray-400 uppercase">{s.label}</p>
                      <p className="text-sm font-mono font-semibold text-gray-900">{s.value}</p>
                    </div>
                  ))}
                </div>

                <div className="flex items-center justify-center gap-2 text-primary text-sm font-medium pt-2 border-t border-gray-100">
                  <Code2 size={14} /> Get Ad Code <ChevronRight size={14} />
                </div>
              </div>
            ))}
          </div>
        )}

        {/* ==================== AD CODE MODAL ==================== */}
        {selectedWebsite && (
          <div className="fixed inset-0 bg-black/40 backdrop-blur-sm z-50 flex items-center justify-center p-4">
            <div className="bg-white rounded-2xl w-full max-w-3xl max-h-[90vh] overflow-y-auto shadow-2xl border border-gray-100">
              {/* Header */}
              <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200 bg-gray-50 rounded-t-2xl sticky top-0 z-10">
                <div>
                  <h3 className="text-lg font-bold text-gray-900">Ad Code - {selectedWebsite.name}</h3>
                  <p className="text-sm text-gray-500">{selectedWebsite.domain}</p>
                </div>
                <button onClick={closeModal} className="p-2 hover:bg-gray-200 rounded-lg transition-colors">
                  <X size={20} className="text-gray-500" />
                </button>
              </div>

              <div className="p-6">
                {/* Step 1: Select Ad Type */}
                <div className="mb-6">
                  <h4 className="text-sm font-bold text-gray-900 mb-1 uppercase tracking-wide">Step 1 — Select Ad Type</h4>
                  <p className="text-xs text-gray-400 mb-3">Choose the type of ad you want to display on your website</p>
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                    {AD_TYPES.map(({ type, label, desc, icon }) => (
                      <button key={type} onClick={() => handleSelectAdType(type)}
                        className={`p-4 rounded-lg border-2 text-left transition-all ${
                          selectedAdType === type
                            ? 'border-primary bg-primary/5 shadow-md'
                            : 'border-gray-200 hover:border-gray-300 hover:bg-gray-50'
                        }`}>
                        <div className={`mb-2 ${selectedAdType === type ? 'text-primary' : 'text-gray-400'}`}>
                          {icon}
                        </div>
                        <p className={`text-sm font-semibold ${selectedAdType === type ? 'text-primary' : 'text-gray-900'}`}>{label}</p>
                        <p className="text-[11px] text-gray-400 mt-0.5 leading-tight">{desc}</p>
                      </button>
                    ))}
                  </div>
                </div>

                {/* Step 2: Get Embed Code button + Settings */}
                {selectedAdType && (
                  <div className="mb-6">
                    <div className="flex items-center gap-3 mb-4">
                      <button onClick={handleGetEmbedCode} disabled={loadingCode}
                        className="flex-1 bg-primary hover:bg-primary-dark text-white py-3 rounded-lg text-sm font-bold flex items-center justify-center gap-2 transition-colors disabled:bg-gray-300">
                        {loadingCode ? <Spinner size={16} /> : <><Code2 size={16} /> Get Embed Code</>}
                      </button>
                      <button onClick={() => setShowSettings(!showSettings)}
                        className={`p-3 rounded-lg border-2 transition-all ${
                          showSettings ? 'border-primary bg-primary/5 text-primary' : 'border-gray-200 text-gray-500 hover:border-gray-300'
                        }`} title="Ad Settings">
                        <Settings size={20} />
                      </button>
                    </div>

                    {/* ==================== SETTINGS PANEL ==================== */}
                    {showSettings && (
                      <div className="bg-gray-50 border border-gray-200 rounded-xl p-5 mb-4">
                        <div className="flex items-center gap-2 mb-4">
                          <Palette size={16} className="text-primary" />
                          <h4 className="text-sm font-bold text-gray-900">Customize Appearance</h4>
                        </div>

                        <div className="grid grid-cols-2 gap-4">
                          {/* Common Settings */}
                          <div>
                            <label className="block text-xs font-medium text-gray-600 mb-1">Background Color</label>
                            <div className="flex items-center gap-2">
                              <input type="color" value={adSettings.bg_color}
                                onChange={e => setAdSettings(p => ({ ...p, bg_color: e.target.value }))}
                                className="w-10 h-10 rounded cursor-pointer border border-gray-200" />
                              <input type="text" value={adSettings.bg_color}
                                onChange={e => setAdSettings(p => ({ ...p, bg_color: e.target.value }))}
                                className={`${inputClass} !py-2`} />
                            </div>
                          </div>
                          <div>
                            <label className="block text-xs font-medium text-gray-600 mb-1">Text Color</label>
                            <div className="flex items-center gap-2">
                              <input type="color" value={adSettings.text_color}
                                onChange={e => setAdSettings(p => ({ ...p, text_color: e.target.value }))}
                                className="w-10 h-10 rounded cursor-pointer border border-gray-200" />
                              <input type="text" value={adSettings.text_color}
                                onChange={e => setAdSettings(p => ({ ...p, text_color: e.target.value }))}
                                className={`${inputClass} !py-2`} />
                            </div>
                          </div>
                          <div>
                            <label className="block text-xs font-medium text-gray-600 mb-1">Button / Accent Color</label>
                            <div className="flex items-center gap-2">
                              <input type="color" value={adSettings.button_color}
                                onChange={e => setAdSettings(p => ({ ...p, button_color: e.target.value }))}
                                className="w-10 h-10 rounded cursor-pointer border border-gray-200" />
                              <input type="text" value={adSettings.button_color}
                                onChange={e => setAdSettings(p => ({ ...p, button_color: e.target.value }))}
                                className={`${inputClass} !py-2`} />
                            </div>
                          </div>
                          <div>
                            <label className="block text-xs font-medium text-gray-600 mb-1">Button Text Color</label>
                            <div className="flex items-center gap-2">
                              <input type="color" value={adSettings.button_text_color}
                                onChange={e => setAdSettings(p => ({ ...p, button_text_color: e.target.value }))}
                                className="w-10 h-10 rounded cursor-pointer border border-gray-200" />
                              <input type="text" value={adSettings.button_text_color}
                                onChange={e => setAdSettings(p => ({ ...p, button_text_color: e.target.value }))}
                                className={`${inputClass} !py-2`} />
                            </div>
                          </div>
                          <div>
                            <label className="block text-xs font-medium text-gray-600 mb-1">Font Size (px)</label>
                            <input type="number" value={adSettings.font_size}
                              onChange={e => setAdSettings(p => ({ ...p, font_size: e.target.value }))}
                              className={`${inputClass} !py-2`} min="10" max="48" />
                          </div>
                          <div>
                            <label className="block text-xs font-medium text-gray-600 mb-1">Border Radius (px)</label>
                            <input type="number" value={adSettings.border_radius}
                              onChange={e => setAdSettings(p => ({ ...p, border_radius: e.target.value }))}
                              className={`${inputClass} !py-2`} min="0" max="50" />
                          </div>

                          {/* Type-specific settings */}
                          {selectedAdType === 'button' && (
                            <div className="col-span-2">
                              <label className="block text-xs font-medium text-gray-600 mb-1">Button Text</label>
                              <input type="text" value={adSettings.button_text}
                                onChange={e => setAdSettings(p => ({ ...p, button_text: e.target.value }))}
                                className={`${inputClass} !py-2`} placeholder="Download Now" />
                            </div>
                          )}

                          {selectedAdType === 'banner' && (
                            <>
                              <div className="col-span-2">
                                <label className="block text-xs font-medium text-gray-600 mb-1">Banner Text</label>
                                <input type="text" value={adSettings.banner_text}
                                  onChange={e => setAdSettings(p => ({ ...p, banner_text: e.target.value }))}
                                  className={`${inputClass} !py-2`} placeholder="Advertisement" />
                              </div>
                              <div>
                                <label className="block text-xs font-medium text-gray-600 mb-1">Width (px)</label>
                                <input type="number" value={adSettings.banner_width}
                                  onChange={e => setAdSettings(p => ({ ...p, banner_width: e.target.value }))}
                                  className={`${inputClass} !py-2`} />
                              </div>
                              <div>
                                <label className="block text-xs font-medium text-gray-600 mb-1">Height (px)</label>
                                <input type="number" value={adSettings.banner_height}
                                  onChange={e => setAdSettings(p => ({ ...p, banner_height: e.target.value }))}
                                  className={`${inputClass} !py-2`} />
                              </div>
                            </>
                          )}

                          {selectedAdType === 'popup' && (
                            <>
                              <div className="col-span-2">
                                <label className="block text-xs font-medium text-gray-600 mb-1">Popup Title</label>
                                <input type="text" value={adSettings.popup_title}
                                  onChange={e => setAdSettings(p => ({ ...p, popup_title: e.target.value }))}
                                  className={`${inputClass} !py-2`} />
                              </div>
                              <div className="col-span-2">
                                <label className="block text-xs font-medium text-gray-600 mb-1">Popup Message</label>
                                <input type="text" value={adSettings.popup_message}
                                  onChange={e => setAdSettings(p => ({ ...p, popup_message: e.target.value }))}
                                  className={`${inputClass} !py-2`} />
                              </div>
                              <div>
                                <label className="block text-xs font-medium text-gray-600 mb-1">Button Text</label>
                                <input type="text" value={adSettings.button_text}
                                  onChange={e => setAdSettings(p => ({ ...p, button_text: e.target.value }))}
                                  className={`${inputClass} !py-2`} placeholder="Claim Now" />
                              </div>
                              <div>
                                <label className="block text-xs font-medium text-gray-600 mb-1">Delay (seconds)</label>
                                <input type="number" value={adSettings.popup_delay}
                                  onChange={e => setAdSettings(p => ({ ...p, popup_delay: parseInt(e.target.value) || 0 }))}
                                  className={`${inputClass} !py-2`} min="0" max="60" />
                              </div>
                            </>
                          )}

                          {selectedAdType === 'video' && (
                            <div className="col-span-2">
                              <label className="block text-xs font-medium text-gray-600 mb-1">Video Placeholder Text</label>
                              <input type="text" value={adSettings.video_placeholder_text}
                                onChange={e => setAdSettings(p => ({ ...p, video_placeholder_text: e.target.value }))}
                                className={`${inputClass} !py-2`} placeholder="Watch Now" />
                            </div>
                          )}
                        </div>

                        <button onClick={handleSaveSettings} disabled={saving}
                          className="mt-4 w-full bg-primary hover:bg-primary-dark text-white py-2.5 rounded-lg text-sm font-semibold flex items-center justify-center gap-2 transition-colors disabled:bg-gray-300">
                          {saving ? <Spinner size={16} /> : 'Save Settings & Update Code'}
                        </button>
                      </div>
                    )}

                    {/* ==================== LIVE PREVIEW ==================== */}
                    {selectedAdType && (
                      <div className="bg-gray-50 border border-gray-200 rounded-xl p-4 mb-4">
                        <h4 className="text-xs font-bold text-gray-500 uppercase tracking-wide mb-3">Live Preview</h4>
                        <div className="bg-white rounded-xl p-4 border border-gray-200 flex items-center justify-center min-h-[100px]">
                          {selectedAdType === 'button' && (
                            <button style={{
                              backgroundColor: adSettings.button_color,
                              color: adSettings.button_text_color,
                              padding: '15px 32px',
                              border: 'none',
                              borderRadius: `${adSettings.border_radius}px`,
                              fontSize: `${adSettings.font_size}px`,
                              fontWeight: 'bold',
                              cursor: 'pointer',
                              fontFamily: 'sans-serif',
                            }}>{adSettings.button_text}</button>
                          )}
                          {selectedAdType === 'banner' && (
                            <div style={{
                              maxWidth: `${adSettings.banner_width}px`,
                              height: `${adSettings.banner_height}px`,
                              width: '100%',
                              background: `linear-gradient(135deg, ${adSettings.bg_color}, ${adSettings.button_color})`,
                              borderRadius: `${adSettings.border_radius}px`,
                              display: 'flex',
                              alignItems: 'center',
                              justifyContent: 'center',
                            }}>
                              <span style={{ color: adSettings.text_color, fontWeight: 'bold', fontSize: `${adSettings.font_size}px`, fontFamily: 'sans-serif' }}>
                                {adSettings.banner_text}
                              </span>
                            </div>
                          )}
                          {selectedAdType === 'popup' && (
                            <div style={{
                              background: adSettings.bg_color,
                              borderRadius: `${adSettings.border_radius}px`,
                              padding: '24px 32px',
                              maxWidth: '360px',
                              width: '100%',
                              textAlign: 'center',
                              boxShadow: '0 20px 60px rgba(0,0,0,0.15)',
                              fontFamily: 'sans-serif',
                              position: 'relative',
                            }}>
                              <span style={{ position: 'absolute', top: '8px', right: '12px', fontSize: '20px', color: adSettings.text_color, opacity: 0.7, cursor: 'pointer' }}>&times;</span>
                              <h3 style={{ color: adSettings.text_color, margin: '0 0 8px', fontSize: '20px' }}>{adSettings.popup_title}</h3>
                              <p style={{ color: adSettings.text_color, opacity: 0.8, margin: '0 0 16px', fontSize: '13px' }}>{adSettings.popup_message}</p>
                              <span style={{
                                display: 'inline-block',
                                background: adSettings.button_color,
                                color: adSettings.button_text_color,
                                padding: '10px 24px',
                                borderRadius: `${adSettings.border_radius}px`,
                                fontWeight: 'bold',
                                fontSize: `${adSettings.font_size}px`,
                              }}>{adSettings.button_text || 'Claim Now'}</span>
                            </div>
                          )}
                          {selectedAdType === 'video' && (
                            <div style={{
                              maxWidth: '400px',
                              width: '100%',
                              background: adSettings.bg_color,
                              borderRadius: `${adSettings.border_radius}px`,
                              overflow: 'hidden',
                              fontFamily: 'sans-serif',
                            }}>
                              <div style={{
                                aspectRatio: '16/9',
                                background: `linear-gradient(135deg, ${adSettings.bg_color}, ${adSettings.button_color})`,
                                display: 'flex',
                                alignItems: 'center',
                                justifyContent: 'center',
                              }}>
                                <div style={{
                                  width: '52px', height: '52px',
                                  background: 'rgba(255,255,255,0.9)',
                                  borderRadius: '50%',
                                  display: 'flex',
                                  alignItems: 'center',
                                  justifyContent: 'center',
                                }}>
                                  <div style={{
                                    width: 0, height: 0,
                                    borderTop: '10px solid transparent',
                                    borderBottom: '10px solid transparent',
                                    borderLeft: `16px solid ${adSettings.button_color}`,
                                    marginLeft: '3px',
                                  }} />
                                </div>
                              </div>
                              <div style={{ padding: '10px 14px', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                                <span style={{ color: adSettings.text_color, fontWeight: 'bold', fontSize: `${adSettings.font_size}px` }}>
                                  {adSettings.video_placeholder_text}
                                </span>
                                <span style={{
                                  background: adSettings.button_color,
                                  color: adSettings.button_text_color,
                                  padding: '5px 14px',
                                  borderRadius: `${adSettings.border_radius}px`,
                                  fontSize: '12px',
                                  fontWeight: 'bold',
                                }}>Play</span>
                              </div>
                            </div>
                          )}
                        </div>
                      </div>
                    )}

                    {/* ==================== EMBED CODE OUTPUT ==================== */}
                    {codeGenerated && embedCode && (
                      <div className="space-y-4">
                        {/* Domain not configured warning */}
                        {(embedCode.includes('YOUR-DOMAIN.com') || smartLink.includes('YOUR-DOMAIN.com')) && (
                          <div className="flex items-start gap-3 p-4 bg-amber-50 border border-amber-300 rounded-lg">
                            <AlertTriangle size={20} className="text-amber-600 flex-shrink-0 mt-0.5" />
                            <div>
                              <p className="text-sm font-semibold text-amber-800">Platform domain not configured</p>
                              <p className="text-xs text-amber-700 mt-1">
                                The generated code contains a placeholder domain (<code className="font-mono bg-amber-100 px-1 rounded">YOUR-DOMAIN.com</code>).
                                Please contact the admin to set the platform domain so your ad codes work correctly.
                              </p>
                            </div>
                          </div>
                        )}
                        {/* Embed Code */}
                        <div className="bg-blue-600 rounded-t-lg px-4 py-2.5">
                          <h4 className="text-white font-bold text-sm">
                            Step 2-1 ({selectedAdType === 'button' ? 'Button' : selectedAdType === 'popup' ? 'Popup' : selectedAdType === 'video' ? 'Video' : 'Banner'} Embed Code)
                          </h4>
                        </div>
                        <div className="relative -mt-4 bg-gray-50 border border-gray-200 rounded-b-lg p-4">
                          <pre className="text-xs text-gray-700 overflow-x-auto font-mono whitespace-pre-wrap break-all leading-relaxed">
                            {embedCode}
                          </pre>
                          <button onClick={() => handleCopy(embedCode, 'embed')}
                            className={`absolute top-3 right-3 px-3 py-1.5 rounded-md text-xs font-semibold transition-all flex items-center gap-1 ${
                              copied === 'embed' ? 'bg-green-600 text-white' : 'bg-primary text-white hover:bg-primary-dark'
                            }`}>
                            {copied === 'embed' ? <><Check size={12} /> Copied</> : <><Copy size={12} /> Copy</>}
                          </button>
                        </div>

                        {/* Smart Link */}
                        <div className="bg-blue-600 rounded-t-lg px-4 py-2.5">
                          <h4 className="text-white font-bold text-sm">Step 2-2 (Smart Link)</h4>
                        </div>
                        <div className="relative -mt-4 bg-gray-50 border border-gray-200 rounded-b-lg p-4">
                          <div className="flex items-center gap-2">
                            <Link2 size={14} className="text-gray-400 flex-shrink-0" />
                            <code className="text-sm text-gray-700 font-mono break-all">{smartLink}</code>
                          </div>
                          <button onClick={() => handleCopy(smartLink, 'smart')}
                            className={`absolute top-3 right-3 px-3 py-1.5 rounded-md text-xs font-semibold transition-all flex items-center gap-1 ${
                              copied === 'smart' ? 'bg-green-600 text-white' : 'bg-primary text-white hover:bg-primary-dark'
                            }`}>
                            {copied === 'smart' ? <><Check size={12} /> Copied</> : <><Copy size={12} /> Copy</>}
                          </button>
                        </div>
                      </div>
                    )}
                  </div>
                )}
              </div>
            </div>
          </div>
        )}

        {/* ==================== ADD WEBSITE MODAL ==================== */}
        {addModal && (
          <div className="fixed inset-0 bg-black/40 backdrop-blur-sm z-50 flex items-center justify-center p-4">
            <div className="bg-white rounded-2xl p-6 w-full max-w-md shadow-2xl border border-gray-100">
              <h3 className="text-lg font-bold text-gray-900 mb-6">Add Website</h3>
              <div className="space-y-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Domain</label>
                  <input value={addForm.domain} onChange={e => setAddForm(p => ({ ...p, domain: e.target.value }))}
                    placeholder="myblog.com (without http://)" className={inputClass} />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Website Name</label>
                  <input value={addForm.name} onChange={e => setAddForm(p => ({ ...p, name: e.target.value }))}
                    placeholder="My Blog" className={inputClass} />
                </div>
              </div>
              <div className="flex gap-3 mt-6">
                <button onClick={handleAdd} disabled={saving || !addForm.domain}
                  className="flex-1 bg-primary hover:bg-primary-dark text-white py-2.5 rounded-xl text-sm font-semibold flex items-center justify-center">
                  {saving ? <Spinner size={16} /> : 'Add Website'}
                </button>
                <button onClick={() => setAddModal(false)}
                  className="flex-1 py-2.5 rounded-xl text-sm font-medium text-gray-600 border border-gray-200 hover:bg-gray-50">
                  Cancel
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

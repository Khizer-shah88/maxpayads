'use client'

import { useState, useEffect, useRef } from 'react'
import { Plus, Trash2, DollarSign, Search, ChevronDown, X } from 'lucide-react'
import { toast } from 'sonner'
import Sidebar from '@/components/shared/Sidebar'
import { adminApi } from '@/lib/api'
import { useAuth } from '@/lib/hooks/useAuth'
import { COUNTRY_NAMES } from '@/lib/countryNames'

const countryOptions = Object.entries(COUNTRY_NAMES).sort((a, b) => (a[1] as string).localeCompare(b[1] as string))

export default function CPCSettingsPage() {
  const { initialize } = useAuth()
  const [cpcSettings, setCpcSettings] = useState<Record<string, number>>({})
  const [loading, setLoading] = useState(true)
  const [selectedCountries, setSelectedCountries] = useState<string[]>([])
  const [newCpc, setNewCpc] = useState('')
  const [saving, setSaving] = useState(false)

  // Dropdown state
  const [open, setOpen] = useState(false)
  const [search, setSearch] = useState('')
  const dropdownRef = useRef<HTMLDivElement>(null)
  const searchRef = useRef<HTMLInputElement>(null)

  useEffect(() => { initialize() }, [])

  useEffect(() => {
    adminApi.getSettings()
      .then(res => {
        const settings = res.data.cpc_settings
        const formatted: Record<string, number> = {}
        Object.entries(settings).forEach(([key, val]: any) => {
          const cc = key.replace('cpc_country_', '')
          formatted[cc] = val
        })
        setCpcSettings(formatted)
      })
      .catch(console.error)
      .finally(() => setLoading(false))
  }, [])

  // Close dropdown on outside click
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
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

  const filtered = countryOptions.filter(([code, name]) =>
    (name as string).toLowerCase().includes(search.toLowerCase()) ||
    code.toLowerCase().includes(search.toLowerCase())
  )

  const toggleCountry = (code: string) => {
    setSelectedCountries(prev =>
      prev.includes(code) ? prev.filter(c => c !== code) : [...prev, code]
    )
  }

  const selectAll = () => setSelectedCountries(countryOptions.map(([code]) => code))
  const clearAll = () => setSelectedCountries([])

  const handleAdd = async () => {
    if (selectedCountries.length === 0 || !newCpc) return
    const cpcValue = parseFloat(newCpc)
    if (isNaN(cpcValue) || cpcValue <= 0) {
      toast.error('Please enter a valid CPC value')
      return
    }
    setSaving(true)
    try {
      if (selectedCountries.length === 1) {
        await adminApi.updateCountryCPC(selectedCountries[0], cpcValue)
      } else {
        await adminApi.bulkUpdateCPC(selectedCountries, cpcValue)
      }
      const updated = { ...cpcSettings }
      selectedCountries.forEach(cc => { updated[cc] = cpcValue })
      setCpcSettings(updated)
      toast.success(`CPC set for ${selectedCountries.length} ${selectedCountries.length === 1 ? 'country' : 'countries'}`)
      setSelectedCountries([])
      setNewCpc('')
    } catch { toast.error('Failed to update CPC') }
    finally { setSaving(false) }
  }

  const handleDelete = async (country: string) => {
    try {
      await adminApi.deleteCountryCPC(country)
      toast.success(`CPC override for ${(COUNTRY_NAMES as any)[country] || country} removed`)
      setCpcSettings(p => { const n = { ...p }; delete n[country]; return n })
    } catch { toast.error('Failed to delete') }
  }

  const inputClass = "w-full px-4 py-2.5 border border-gray-200 rounded-xl text-gray-900 bg-white focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary text-sm"

  return (
    <div className="flex min-h-screen bg-[#f8f9fb]">
      <Sidebar />
      <div className="flex-1 lg:ml-64 p-6 lg:p-8 min-w-0 overflow-x-hidden">
        <div className="mb-8 pt-12 lg:pt-0">
          <h1 className="text-2xl font-bold text-gray-900">CPC Settings</h1>
          <p className="text-gray-400 text-sm mt-0.5">Configure cost-per-click rates by country</p>
        </div>

        <div className="bg-white rounded-2xl border border-gray-100 p-6 mb-6">
          <h2 className="text-base font-semibold text-gray-900 mb-4">Add/Update Country CPC</h2>

          <div className="flex flex-wrap gap-3 items-start">
            {/* Multi-select Country Dropdown */}
            <div ref={dropdownRef} className="relative w-80">
              <div className="flex items-center justify-between mb-1.5">
                <label className="block text-sm font-semibold text-gray-700">
                  Countries <span className="text-gray-400 font-normal">({selectedCountries.length}/{countryOptions.length})</span>
                </label>
                <div className="flex gap-3">
                  <button type="button" onClick={selectAll} className="text-xs text-primary font-semibold hover:underline">Select All</button>
                  <button type="button" onClick={clearAll} className="text-xs text-gray-400 font-semibold hover:underline hover:text-gray-600">Clear All</button>
                </div>
              </div>

              <div className="relative">
                <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400 pointer-events-none" />
                <input
                  ref={searchRef}
                  type="text"
                  value={search}
                  onChange={e => { setSearch(e.target.value); setOpen(true) }}
                  onFocus={() => setOpen(true)}
                  placeholder="Search countries..."
                  className="w-full pl-9 pr-4 py-2.5 border border-gray-200 rounded-xl text-sm bg-white focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary transition-all"
                />
                <ChevronDown
                  size={16}
                  className={`absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 transition-transform cursor-pointer ${open ? 'rotate-180' : ''}`}
                  onClick={() => setOpen(!open)}
                />
              </div>

              {open && (
                <div className="absolute z-50 mt-1 w-full bg-white border border-gray-200 rounded-xl shadow-2xl overflow-hidden" style={{ maxHeight: '280px' }}>
                  <div className="overflow-y-auto" style={{ maxHeight: '280px' }}>
                    {filtered.length === 0 ? (
                      <div className="p-4 text-center text-sm text-gray-400">No countries match &ldquo;{search}&rdquo;</div>
                    ) : (
                      filtered.map(([code, name]) => {
                        const isSelected = selectedCountries.includes(code)
                        return (
                          <button
                            key={code}
                            type="button"
                            onClick={() => toggleCountry(code)}
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
                            <span className="flex-1">{name as string}</span>
                            <span className="text-[11px] text-gray-400 font-mono">{code}</span>
                          </button>
                        )
                      })
                    )}
                  </div>
                </div>
              )}

              {/* Selected tags */}
              {selectedCountries.length > 0 && (
                <div className="flex flex-wrap gap-1.5 mt-2">
                  {selectedCountries.slice(0, 20).map(code => (
                    <span key={code} className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-xs font-medium bg-red-50 text-primary border border-red-100 group">
                      {(COUNTRY_NAMES as any)[code] || code}
                      <button type="button" onClick={() => toggleCountry(code)} className="ml-0.5 opacity-50 group-hover:opacity-100 hover:text-red-800 transition-opacity">
                        <X size={10} />
                      </button>
                    </span>
                  ))}
                  {selectedCountries.length > 20 && (
                    <span className="inline-flex items-center px-2 py-0.5 rounded-md text-xs font-medium bg-gray-100 text-gray-500">
                      +{selectedCountries.length - 20} more
                    </span>
                  )}
                </div>
              )}
            </div>

            {/* CPC Input */}
            <div>
              <label className="block text-sm font-semibold text-gray-700 mb-1.5">CPC Rate</label>
              <div className="relative">
                <DollarSign className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" size={16} />
                <input value={newCpc} onChange={e => setNewCpc(e.target.value)} type="number" step="0.001" min="0"
                  placeholder="0.050" className={`${inputClass} !w-36 !pl-8`} />
              </div>
            </div>

            {/* Add Button */}
            <div>
              <label className="block text-sm font-semibold text-transparent mb-1.5 select-none">Add</label>
              <button onClick={handleAdd} disabled={saving || selectedCountries.length === 0 || !newCpc}
                className="bg-primary hover:bg-primary-dark text-white px-5 py-2.5 rounded-xl text-sm font-semibold flex items-center gap-2 disabled:bg-gray-300 disabled:cursor-not-allowed transition-colors">
                <Plus size={16} /> {saving ? 'Saving...' : `Add CPC${selectedCountries.length > 1 ? ` (${selectedCountries.length})` : ''}`}
              </button>
            </div>
          </div>
        </div>

        <div className="bg-white rounded-2xl border border-gray-100 p-6">
          <h2 className="text-base font-semibold text-gray-900 mb-4">Country CPC Overrides ({Object.keys(cpcSettings).length})</h2>
          {loading ? (
            <div className="space-y-3">{[1,2,3].map(i => <div key={i} className="shimmer h-12 rounded-md" />)}</div>
          ) : Object.keys(cpcSettings).length === 0 ? (
            <p className="text-gray-400 text-sm text-center py-8">No country CPC overrides set. Using system default CPC.</p>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
              {Object.entries(cpcSettings).sort((a, b) => b[1] - a[1]).map(([country, cpc]) => (
                <div key={country} className="flex items-center justify-between p-4 rounded-xl bg-gray-50 border border-gray-100">
                  <div>
                    <p className="font-bold text-gray-900">{(COUNTRY_NAMES as any)[country] || country}</p>
                    <p className="text-xs text-gray-500 font-mono">{country}</p>
                  </div>
                  <div className="flex items-center gap-3">
                    <span className="text-red-600 font-mono font-bold text-lg">${cpc.toFixed(3)}</span>
                    <button onClick={() => handleDelete(country)} className="p-1.5 rounded text-red-400 hover:text-red-600 hover:bg-red-50 transition-colors">
                      <Trash2 size={14} />
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

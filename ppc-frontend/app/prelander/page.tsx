'use client'

import { useState, useEffect, Suspense } from 'react'
import { useSearchParams } from 'next/navigation'
import { Copy, Check, Lock, FileDown } from 'lucide-react'

function PrelanderContent() {
  const searchParams = useSearchParams()
  const [data, setData] = useState<any>(null)
  const [loading, setLoading] = useState(true)
  const [copied, setCopied] = useState(false)

  useEffect(() => {
    const fetchData = async () => {
      try {
        const slug = searchParams.get('s')
        if (!slug) {
          setData(null)
          setLoading(false)
          return
        }
        const res = await fetch(`/api/prelander/resolve/${encodeURIComponent(slug)}`)
        if (!res.ok) {
          setData(null)
          setLoading(false)
          return
        }
        const json = await res.json()
        setData(json)
      } catch {
        setData(null)
      } finally {
        setLoading(false)
      }
    }
    fetchData()
  }, [searchParams])

  useEffect(() => {
    document.title = 'Download Ready'
  }, [])

  const handleCopy = () => {
    if (data?.offer_url) {
      navigator.clipboard.writeText(data.offer_url)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    }
  }

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-[#f0f2f5]">
        <div className="w-8 h-8 border-3 border-gray-300 border-t-gray-600 rounded-full animate-spin" />
      </div>
    )
  }

  if (!data || !data.success) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-[#f0f2f5]">
        <p className="text-gray-500">Failed to load file details.</p>
      </div>
    )
  }

  return (
    <div className="min-h-screen flex items-center justify-center p-4 bg-[#f0f2f5]">
      <div className="w-full max-w-md">
        <div className="bg-white rounded-2xl shadow-lg border border-gray-200 overflow-hidden">
          {/* Header */}
          <div className="px-6 pt-8 pb-5 text-center">
            <div className="w-14 h-14 rounded-full bg-green-100 mx-auto mb-4 flex items-center justify-center">
              <FileDown size={26} className="text-green-600" />
            </div>
            <h1 className="text-xl font-bold text-gray-900">
              Your file is ready to download
            </h1>
            <p className="text-sm text-gray-500 mt-2">
              Your file is prepared. Copy the link to download.
            </p>
          </div>

          {/* Download Link */}
          <div className="px-6 pb-4">
            <label className="block text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">Download Link</label>
            <div className="flex items-center gap-2 bg-gray-50 border border-gray-200 rounded-xl p-1">
              <div className="flex-1 px-3 py-2.5 text-sm text-gray-700 font-mono truncate select-all">
                {data.offer_url}
              </div>
              <button
                onClick={handleCopy}
                className={`flex-shrink-0 flex items-center gap-1.5 px-4 py-2.5 rounded-lg text-sm font-semibold transition-all ${
                  copied
                    ? 'bg-green-600 text-white'
                    : 'bg-gray-900 text-white hover:bg-gray-800'
                }`}
              >
                {copied ? <><Check size={14} /> Copied</> : <><Copy size={14} /> Copy</>}
              </button>
            </div>
          </div>

          {/* Password */}
          {data.password && (
            <div className="px-6 pb-4">
              <label className="block text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">Password</label>
              <div className="flex items-center gap-3 bg-amber-50 border border-amber-200 rounded-xl px-4 py-3">
                <Lock size={16} className="text-amber-500 flex-shrink-0" />
                <span className="text-base font-bold font-mono tracking-widest text-amber-800 select-all">
                  {data.password}
                </span>
              </div>
            </div>
          )}

          {/* Open Link Button */}
          <div className="px-6 pb-8 pt-2">
            <a
              href={data.offer_url}
              target="_blank"
              rel="noreferrer"
              className="w-full flex items-center justify-center gap-2 py-3.5 rounded-xl bg-green-600 hover:bg-green-700 text-white font-semibold text-sm transition-all hover:scale-[1.01] active:scale-[0.99] shadow-lg shadow-green-600/20"
            >
              <FileDown size={18} />
              Open Download Link
            </a>
          </div>
        </div>

        <p className="text-center text-xs text-gray-400 mt-4">
          Secure file hosting service
        </p>
      </div>
    </div>
  )
}

export default function PrelanderPage() {
  return (
    <Suspense fallback={
      <div className="min-h-screen flex items-center justify-center bg-[#f0f2f5]">
        <div className="w-8 h-8 border-3 border-gray-300 border-t-gray-600 rounded-full animate-spin" />
      </div>
    }>
      <PrelanderContent />
    </Suspense>
  )
}

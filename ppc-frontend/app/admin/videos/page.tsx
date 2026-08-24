'use client'

import { useState, useEffect, useCallback } from 'react'
import { Video, Play, Trash2, ExternalLink, X, Link2, Upload, FileVideo, Check, XCircle, Clock, Filter, Download } from 'lucide-react'
import { toast } from 'sonner'
import Sidebar from '@/components/shared/Sidebar'
import { adminApi } from '@/lib/api'
import { useAuth } from '@/lib/hooks/useAuth'

interface VideoItem {
  id: string
  title: string
  video_url: string
  description: string
  status: string
  type?: string
  file_size?: number
  website_id?: string
  website_domain?: string
  publisher_id: string
  publisher_name: string
  publisher_email: string
  created_at: string
}

interface Publisher {
  id: string
  name: string
  email: string
}

interface Website {
  id: string
  domain: string
  publisher_id: string
}

function getEmbedUrl(url: string): string | null {
  try {
    const u = new URL(url)
    if (u.hostname.includes('youtube.com') || u.hostname.includes('youtu.be')) {
      let vid = ''
      if (u.hostname.includes('youtu.be')) vid = u.pathname.slice(1)
      else vid = u.searchParams.get('v') || ''
      if (vid) return `https://www.youtube.com/embed/${vid}`
    }
    if (u.hostname.includes('vimeo.com')) {
      const match = u.pathname.match(/\/(\d+)/)
      if (match) return `https://player.vimeo.com/video/${match[1]}`
    }
    if (u.hostname.includes('dailymotion.com')) {
      const match = u.pathname.match(/video\/([a-zA-Z0-9]+)/)
      if (match) return `https://www.dailymotion.com/embed/video/${match[1]}`
    }
  } catch {}
  return null
}

function getThumbnail(url: string): string | null {
  try {
    const u = new URL(url)
    if (u.hostname.includes('youtube.com') || u.hostname.includes('youtu.be')) {
      let vid = ''
      if (u.hostname.includes('youtu.be')) vid = u.pathname.slice(1)
      else vid = u.searchParams.get('v') || ''
      if (vid) return `https://img.youtube.com/vi/${vid}/mqdefault.jpg`
    }
  } catch {}
  return null
}

function formatFileSize(bytes: number): string {
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

const VIDEO_EXTENSIONS = ['.mp4', '.webm', '.ogg', '.mov', '.avi', '.mkv', '.m4v', '.wmv', '.flv']
const IMAGE_EXTENSIONS = ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.svg', '.bmp', '.ico']

function isVideoFile(url: string): boolean {
  try {
    const path = new URL(url, 'https://x').pathname.toLowerCase()
    return VIDEO_EXTENSIONS.some(ext => path.endsWith(ext))
  } catch {
    return VIDEO_EXTENSIONS.some(ext => url.toLowerCase().endsWith(ext))
  }
}

function isImageFile(url: string): boolean {
  try {
    const path = new URL(url, 'https://x').pathname.toLowerCase()
    return IMAGE_EXTENSIONS.some(ext => path.endsWith(ext))
  } catch {
    return IMAGE_EXTENSIONS.some(ext => url.toLowerCase().endsWith(ext))
  }
}

function getFileExtension(url: string): string {
  try {
    const path = new URL(url, 'https://x').pathname
    const ext = path.split('.').pop()?.toUpperCase() || ''
    return ext
  } catch { return '' }
}

export default function AdminVideosPage() {
  const { initialize } = useAuth()
  const [videos, setVideos] = useState<VideoItem[]>([])
  const [publishers, setPublishers] = useState<Publisher[]>([])
  const [websites, setWebsites] = useState<Website[]>([])
  const [loading, setLoading] = useState(true)
  const [selectedPublisher, setSelectedPublisher] = useState('')
  const [selectedWebsite, setSelectedWebsite] = useState('')
  const [selectedStatus, setSelectedStatus] = useState('')
  const [previewVideo, setPreviewVideo] = useState<VideoItem | null>(null)

  useEffect(() => { initialize() }, [])

  const loadPublishers = useCallback(async () => {
    try {
      const res = await adminApi.getPublishers({ limit: 200 })
      setPublishers(res.data.publishers || [])
    } catch {}
  }, [])

  const loadWebsites = useCallback(async () => {
    try {
      const res = await adminApi.getWebsites()
      setWebsites(res.data.websites || [])
    } catch {}
  }, [])

  const loadVideos = useCallback(async () => {
    setLoading(true)
    try {
      const params: { publisher_id?: string; website_id?: string; status?: string } = {}
      if (selectedPublisher) params.publisher_id = selectedPublisher
      if (selectedWebsite) params.website_id = selectedWebsite
      if (selectedStatus) params.status = selectedStatus
      const res = await adminApi.getVideos(params)
      setVideos(res.data.videos || [])
    } catch { toast.error('Failed to load resources') }
    finally { setLoading(false) }
  }, [selectedPublisher, selectedWebsite, selectedStatus])

  useEffect(() => { loadPublishers(); loadWebsites() }, [loadPublishers, loadWebsites])
  useEffect(() => { loadVideos() }, [loadVideos])

  const filteredWebsites = selectedPublisher
    ? websites.filter(w => w.publisher_id === selectedPublisher)
    : websites

  const getPublisherWebsites = (publisherId: string) => {
    return websites.filter(w => w.publisher_id === publisherId)
  }

  // Reset website selection when publisher changes
  const handlePublisherChange = (pubId: string) => {
    setSelectedPublisher(pubId)
    setSelectedWebsite('')
  }

  const handleStatusChange = async (videoId: string, newStatus: string) => {
    try {
      await adminApi.updateVideo(videoId, { status: newStatus })
      toast.success(`Resource ${newStatus === 'active' ? 'approved' : newStatus === 'rejected' ? 'rejected' : 'set to pending'}`)
      loadVideos()
    } catch { toast.error('Failed to update status') }
  }

  const handleDelete = async (id: string) => {
    if (!confirm('Delete this resource permanently?')) return
    try {
      await adminApi.deleteVideo(id)
      toast.success('Resource deleted')
      loadVideos()
    } catch { toast.error('Failed to delete') }
  }

  const statusCounts = {
    all: videos.length,
    pending: videos.filter(v => v.status === 'pending').length,
    active: videos.filter(v => v.status === 'active').length,
    rejected: videos.filter(v => v.status === 'rejected').length,
  }

  return (
    <div className="flex min-h-screen bg-[#f8f9fb]">
      <Sidebar />
      <div className="flex-1 lg:ml-64 p-6 lg:p-8">
        {/* Header */}
        <div className="mb-6 pt-12 lg:pt-0">
          <h1 className="text-2xl font-bold text-gray-900">Publisher Resources</h1>
          <p className="text-gray-400 text-sm mt-0.5">Review and manage resources submitted by publishers</p>
        </div>

        {/* Stats Cards */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
          <div className="bg-white rounded-xl border border-gray-100 p-4">
            <p className="text-xs text-gray-400 font-medium uppercase tracking-wide">Total</p>
            <p className="text-2xl font-bold text-gray-900 mt-1">{statusCounts.all}</p>
          </div>
          <div className="bg-white rounded-xl border border-gray-100 p-4">
            <p className="text-xs text-amber-500 font-medium uppercase tracking-wide">Pending</p>
            <p className="text-2xl font-bold text-amber-600 mt-1">{statusCounts.pending}</p>
          </div>
          <div className="bg-white rounded-xl border border-gray-100 p-4">
            <p className="text-xs text-emerald-500 font-medium uppercase tracking-wide">Approved</p>
            <p className="text-2xl font-bold text-emerald-600 mt-1">{statusCounts.active}</p>
          </div>
          <div className="bg-white rounded-xl border border-gray-100 p-4">
            <p className="text-xs text-red-500 font-medium uppercase tracking-wide">Rejected</p>
            <p className="text-2xl font-bold text-red-600 mt-1">{statusCounts.rejected}</p>
          </div>
        </div>

        {/* Filters */}
        <div className="bg-white rounded-xl border border-gray-100 p-4 mb-6">
          <div className="flex flex-wrap items-center gap-4">
            <div className="flex items-center gap-2 text-gray-400">
              <Filter size={16} />
              <span className="text-sm font-medium">Filters</span>
            </div>
            <select
              value={selectedPublisher}
              onChange={e => handlePublisherChange(e.target.value)}
              className="px-3 py-2 border border-gray-200 rounded-lg text-sm text-gray-700 bg-white focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary min-w-[200px]"
            >
              <option value="">All Publishers</option>
              {publishers.map(p => (
                <option key={p.id} value={p.id}>{p.name} ({p.email})</option>
              ))}
            </select>
            <select
              value={selectedWebsite}
              onChange={e => setSelectedWebsite(e.target.value)}
              className="px-3 py-2 border border-gray-200 rounded-lg text-sm text-gray-700 bg-white focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary min-w-[180px]"
            >
              <option value="">All Websites</option>
              {filteredWebsites.map(w => (
                <option key={w.id} value={w.id}>{w.domain}</option>
              ))}
            </select>
            <select
              value={selectedStatus}
              onChange={e => setSelectedStatus(e.target.value)}
              className="px-3 py-2 border border-gray-200 rounded-lg text-sm text-gray-700 bg-white focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary"
            >
              <option value="">All Statuses</option>
              <option value="pending">Pending</option>
              <option value="active">Approved</option>
              <option value="rejected">Rejected</option>
            </select>
            {(selectedPublisher || selectedWebsite || selectedStatus) && (
              <button
                onClick={() => { setSelectedPublisher(''); setSelectedWebsite(''); setSelectedStatus('') }}
                className="text-xs text-gray-500 hover:text-red-500 transition-colors"
              >
                Clear filters
              </button>
            )}
          </div>
        </div>

        {/* Videos List */}
        {loading ? (
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-5">
            {Array.from({ length: 6 }).map((_, i) => (
              <div key={i} className="bg-white rounded-2xl border border-gray-100 overflow-hidden">
                <div className="aspect-video bg-gray-100 shimmer" />
                <div className="p-4 space-y-2">
                  <div className="h-4 bg-gray-100 rounded shimmer w-3/4" />
                  <div className="h-3 bg-gray-100 rounded shimmer w-1/2" />
                </div>
              </div>
            ))}
          </div>
        ) : videos.length === 0 ? (
          <div className="bg-white rounded-2xl border border-gray-100 p-16 text-center">
            <div className="w-16 h-16 rounded-2xl bg-gray-100 flex items-center justify-center mx-auto mb-4">
              <Video size={28} className="text-gray-400" />
            </div>
            <h3 className="text-lg font-semibold text-gray-900 mb-1">No resources found</h3>
            <p className="text-gray-400 text-sm">
              {selectedPublisher || selectedWebsite || selectedStatus ? 'Try adjusting your filters' : 'Publishers haven\'t submitted any resources yet'}
            </p>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
            {videos.map(v => {
              const isUpload = v.type === 'upload'
              const fileExt = isUpload ? getFileExtension(v.video_url) : ''
              return (
                <div key={v.id} className="bg-white rounded-2xl border border-gray-100 p-5 hover:shadow-md transition-shadow">
                  <div className="flex items-start gap-4">
                    {/* File icon */}
                    <div className="w-12 h-12 rounded-xl bg-gray-100 flex items-center justify-center flex-shrink-0">
                      {isUpload ? (
                        <span className="text-[10px] font-bold text-gray-500 uppercase">{fileExt || 'FILE'}</span>
                      ) : (
                        <Link2 size={20} className="text-gray-400" />
                      )}
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-1">
                        <h3 className="font-semibold text-gray-900 text-sm truncate">{v.title}</h3>
                        <span className={`px-2 py-0.5 rounded-full text-[10px] font-semibold uppercase tracking-wide flex-shrink-0 ${
                          v.status === 'active' ? 'bg-emerald-50 text-emerald-600' :
                          v.status === 'rejected' ? 'bg-red-50 text-red-500' :
                          'bg-amber-50 text-amber-600'
                        }`}>
                          {v.status === 'active' ? 'Approved' : v.status}
                        </span>
                      </div>
                      {v.description && <p className="text-gray-400 text-xs mb-2 line-clamp-1">{v.description}</p>}
                      <div className="flex items-center gap-3 text-xs text-gray-400">
                        {isUpload && v.file_size ? <span>{formatFileSize(v.file_size)}</span> : null}
                        <span>{new Date(v.created_at).toLocaleDateString()}</span>
                      </div>
                    </div>
                  </div>

                  {/* Publisher Info */}
                  <div className="bg-gray-50 rounded-lg p-2.5 mt-3">
                    <div className="flex items-center gap-2">
                      <div className="w-6 h-6 rounded-md bg-primary/10 flex items-center justify-center text-[10px] font-bold text-primary">
                        {v.publisher_name?.charAt(0)?.toUpperCase() || 'P'}
                      </div>
                      <div className="min-w-0 flex-1">
                        <p className="text-xs font-medium text-gray-900 truncate">{v.publisher_name}</p>
                        <p className="text-[10px] text-gray-400 truncate">{v.publisher_email}</p>
                      </div>
                      {v.website_domain && (
                        <span className="inline-flex items-center gap-1 px-1.5 py-0.5 bg-blue-50 rounded text-[10px] text-blue-600 border border-blue-100 font-medium flex-shrink-0">
                          <Link2 size={8} /> {v.website_domain}
                        </span>
                      )}
                    </div>
                  </div>

                  {/* Actions */}
                  <div className="flex items-center gap-1.5 mt-3 pt-3 border-t border-gray-100">
                    {v.status !== 'active' && (
                      <button onClick={() => handleStatusChange(v.id, 'active')}
                        className="flex items-center gap-1 px-2.5 py-1.5 rounded-lg text-[11px] font-medium bg-emerald-50 text-emerald-600 hover:bg-emerald-100 transition-colors">
                        <Check size={12} /> Approve
                      </button>
                    )}
                    {v.status !== 'rejected' && (
                      <button onClick={() => handleStatusChange(v.id, 'rejected')}
                        className="flex items-center gap-1 px-2.5 py-1.5 rounded-lg text-[11px] font-medium bg-red-50 text-red-500 hover:bg-red-100 transition-colors">
                        <XCircle size={12} /> Reject
                      </button>
                    )}
                    {v.status !== 'pending' && (
                      <button onClick={() => handleStatusChange(v.id, 'pending')}
                        className="flex items-center gap-1 px-2.5 py-1.5 rounded-lg text-[11px] font-medium bg-amber-50 text-amber-600 hover:bg-amber-100 transition-colors">
                        <Clock size={12} /> Pending
                      </button>
                    )}
                    <div className="ml-auto flex items-center gap-1">
                      {isUpload ? (
                        <a href={v.video_url} download
                          className="p-1.5 rounded-lg text-gray-400 hover:text-blue-500 hover:bg-blue-50 transition-colors"
                          title="Download">
                          <Download size={14} />
                        </a>
                      ) : (
                        <a href={v.video_url} target="_blank" rel="noreferrer"
                          className="p-1.5 rounded-lg text-gray-400 hover:text-blue-500 hover:bg-blue-50 transition-colors"
                          title="Open link">
                          <ExternalLink size={14} />
                        </a>
                      )}
                      <button onClick={() => handleDelete(v.id)}
                        className="p-1.5 rounded-lg text-gray-400 hover:text-red-500 hover:bg-red-50 transition-colors">
                        <Trash2 size={14} />
                      </button>
                    </div>
                  </div>
                </div>
              )
            })}
          </div>
        )}

        {/* Video Player Modal */}
        {previewVideo && (
          <div className="fixed inset-0 bg-black/70 backdrop-blur-sm z-50 flex items-center justify-center p-4" onClick={() => setPreviewVideo(null)}>
            <div className="w-full max-w-3xl" onClick={e => e.stopPropagation()}>
              <div className="flex items-center justify-between mb-3">
                <div>
                  <h3 className="text-white font-semibold truncate mr-4">{previewVideo.title}</h3>
                  <p className="text-white/60 text-sm">by {previewVideo.publisher_name}</p>
                </div>
                <button onClick={() => setPreviewVideo(null)} className="p-2 rounded-lg hover:bg-white/10 text-white">
                  <X size={20} />
                </button>
              </div>
              <div className="rounded-2xl overflow-hidden bg-black">
                {previewVideo.type === 'upload' && isVideoFile(previewVideo.video_url) ? (
                  <video
                    src={previewVideo.video_url}
                    className="w-full aspect-video"
                    controls
                    autoPlay
                  />
                ) : previewVideo.type === 'upload' && isImageFile(previewVideo.video_url) ? (
                  <div className="w-full flex items-center justify-center bg-gray-900 p-4">
                    <img src={previewVideo.video_url} alt={previewVideo.title} className="max-w-full max-h-[70vh] object-contain rounded" />
                  </div>
                ) : previewVideo.type === 'upload' ? (
                  <div className="w-full aspect-video flex flex-col items-center justify-center gap-3">
                    <div className="w-20 h-24 bg-gray-800 rounded-lg flex flex-col items-center justify-center border border-gray-700">
                      <span className="text-sm font-bold text-gray-400 uppercase">{getFileExtension(previewVideo.video_url) || 'FILE'}</span>
                    </div>
                    <p className="text-gray-400 text-sm">This file type cannot be previewed</p>
                    <a href={previewVideo.video_url} download
                      className="px-4 py-2 bg-blue-600 text-white rounded-lg text-sm hover:bg-blue-700 transition-colors flex items-center gap-2">
                      <Download size={14} /> Download File
                    </a>
                  </div>
                ) : getEmbedUrl(previewVideo.video_url) ? (
                  <iframe
                    src={getEmbedUrl(previewVideo.video_url)!}
                    className="w-full aspect-video"
                    allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
                    allowFullScreen
                  />
                ) : (
                  <div className="w-full aspect-video flex items-center justify-center">
                    <p className="text-gray-400">Cannot preview this format</p>
                  </div>
                )}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

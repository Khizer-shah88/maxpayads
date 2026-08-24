'use client'

import { useState, useEffect, useCallback, useRef } from 'react'
import { FolderOpen, Plus, Trash2, ExternalLink, X, Play, Link2, Upload, FileVideo, Globe, Download } from 'lucide-react'
import { toast } from 'sonner'
import PublisherSidebar from '@/components/shared/PublisherSidebar'
import { publisherApi } from '@/lib/api'
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
  created_at: string
}

interface Website {
  id: string
  domain: string
  name?: string
}

function getEmbedUrl(url: string): string | null {
  try {
    const u = new URL(url)
    // YouTube
    if (u.hostname.includes('youtube.com') || u.hostname.includes('youtu.be')) {
      let vid = ''
      if (u.hostname.includes('youtu.be')) vid = u.pathname.slice(1)
      else vid = u.searchParams.get('v') || ''
      if (vid) return `https://www.youtube.com/embed/${vid}`
    }
    // Vimeo
    if (u.hostname.includes('vimeo.com')) {
      const match = u.pathname.match(/\/(\d+)/)
      if (match) return `https://player.vimeo.com/video/${match[1]}`
    }
    // Dailymotion
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

const MAX_FILE_SIZE = 200 * 1024 * 1024 // 200MB

export default function PublisherVideosPage() {
  const { initialize } = useAuth()
  const [videos, setVideos] = useState<VideoItem[]>([])
  const [websites, setWebsites] = useState<Website[]>([])
  const [loading, setLoading] = useState(true)
  const [showModal, setShowModal] = useState(false)
  const [saving, setSaving] = useState(false)
  const [uploadProgress, setUploadProgress] = useState(0)
  const [modalTab, setModalTab] = useState<'link' | 'upload'>('link')
  const [form, setForm] = useState({ title: '', video_url: '', description: '', website_id: '' })
  const [uploadFile, setUploadFile] = useState<File | null>(null)
  const [uploadForm, setUploadForm] = useState({ title: '', description: '', website_id: '' })
  const [dragOver, setDragOver] = useState(false)
  const [previewVideo, setPreviewVideo] = useState<VideoItem | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  useEffect(() => { initialize() }, [])

  const loadWebsites = useCallback(async () => {
    try {
      const res = await publisherApi.getWebsites()
      setWebsites(res.data.websites || [])
    } catch {}
  }, [])

  useEffect(() => { loadWebsites() }, [loadWebsites])

  const loadVideos = useCallback(async () => {
    setLoading(true)
    try {
      const res = await publisherApi.getVideos()
      setVideos(res.data.videos || [])
    } catch { toast.error('Failed to load resources') }
    finally { setLoading(false) }
  }, [])

  useEffect(() => { loadVideos() }, [loadVideos])

  const resetModal = () => {
    setForm({ title: '', video_url: '', description: '', website_id: '' })
    setUploadForm({ title: '', description: '', website_id: '' })
    setUploadFile(null)
    setUploadProgress(0)
    setModalTab('link')
    setShowModal(false)
  }

  const handleAdd = async () => {
    if (!form.title.trim() || !form.video_url.trim()) {
      toast.error('Title and URL are required')
      return
    }
    setSaving(true)
    try {
      await publisherApi.addVideo(form)
      toast.success('Resource added successfully')
      resetModal()
      loadVideos()
    } catch { toast.error('Failed to add resource') }
    finally { setSaving(false) }
  }

  const handleUpload = async () => {
    if (!uploadForm.title.trim()) {
      toast.error('Title is required')
      return
    }
    if (!uploadFile) {
      toast.error('Please select a file')
      return
    }
    if (uploadFile.size > MAX_FILE_SIZE) {
      toast.error('File size must be under 200MB')
      return
    }

    setSaving(true)
    setUploadProgress(0)
    try {
      const formData = new FormData()
      formData.append('title', uploadForm.title)
      formData.append('description', uploadForm.description)
      formData.append('website_id', uploadForm.website_id)
      formData.append('video_file', uploadFile)
      await publisherApi.uploadVideo(formData)
      toast.success('Resource uploaded successfully')
      resetModal()
      loadVideos()
    } catch { toast.error('Failed to upload resource') }
    finally { setSaving(false); setUploadProgress(0) }
  }

  const handleDelete = async (id: string) => {
    if (!confirm('Delete this resource?')) return
    try {
      await publisherApi.deleteVideo(id)
      toast.success('Resource deleted')
      loadVideos()
    } catch { toast.error('Failed to delete') }
  }

  const handleFileDrop = (e: React.DragEvent) => {
    e.preventDefault()
    setDragOver(false)
    const file = e.dataTransfer.files[0]
    if (file) {
      if (file.size > MAX_FILE_SIZE) {
        toast.error('File size must be under 200MB')
        return
      }
      setUploadFile(file)
      if (!uploadForm.title) {
        setUploadForm(f => ({ ...f, title: file.name.replace(/\.[^.]+$/, '') }))
      }
    }
  }

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (file) {
      setUploadFile(file)
      if (!uploadForm.title) {
        setUploadForm(f => ({ ...f, title: file.name.replace(/\.[^.]+$/, '') }))
      }
    }
  }

  return (
    <div className="flex min-h-screen bg-[#f8f9fb]">
      <PublisherSidebar />
      <div className="flex-1 lg:ml-64 p-6 lg:p-8">
        {/* Header */}
        <div className="flex items-center justify-between mb-6 pt-12 lg:pt-0">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">Resources</h1>
            <p className="text-gray-400 text-sm mt-0.5">Add video links or upload files to share with your audience</p>
          </div>
          <button onClick={() => setShowModal(true)}
            className="flex items-center gap-2 px-4 py-2.5 bg-primary hover:bg-primary-dark text-white rounded-xl text-sm font-medium transition-colors">
            <Plus size={16} /> Add Resource
          </button>
        </div>

        {/* Resource Grid */}
        {loading ? (
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-5">
            {Array.from({ length: 3 }).map((_, i) => (
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
              <FolderOpen size={28} className="text-gray-400" />
            </div>
            <h3 className="text-lg font-semibold text-gray-900 mb-1">No resources yet</h3>
            <p className="text-gray-400 text-sm mb-6">Add your first video link or upload a file to get started</p>
            <button onClick={() => setShowModal(true)}
              className="inline-flex items-center gap-2 px-5 py-2.5 bg-primary hover:bg-primary-dark text-white rounded-xl text-sm font-medium transition-colors">
              <Plus size={16} /> Add Resource
            </button>
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
                          {v.status}
                        </span>
                      </div>
                      {v.description && <p className="text-gray-400 text-xs mb-2 line-clamp-1">{v.description}</p>}
                      <div className="flex items-center gap-3 text-xs text-gray-400">
                        {isUpload && v.file_size ? <span>{formatFileSize(v.file_size)}</span> : null}
                        <span>{new Date(v.created_at).toLocaleDateString()}</span>
                      </div>
                    </div>
                  </div>
                  <div className="flex items-center gap-2 mt-4 pt-3 border-t border-gray-100">
                    {isUpload ? (
                      <a href={v.video_url} download
                        className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-primary/10 text-primary hover:bg-primary/20 transition-colors">
                        <Download size={13} /> Download
                      </a>
                    ) : (
                      <a href={v.video_url} target="_blank" rel="noreferrer"
                        className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-blue-50 text-blue-600 hover:bg-blue-100 transition-colors">
                        <ExternalLink size={13} /> Open Link
                      </a>
                    )}
                    <div className="ml-auto">
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

        {/* Add Resource Modal */}
        {showModal && (
          <div className="fixed inset-0 bg-black/40 backdrop-blur-sm z-50 flex items-center justify-center p-4" onClick={resetModal}>
            <div className="bg-white rounded-2xl p-6 w-full max-w-lg shadow-2xl border border-gray-100" onClick={e => e.stopPropagation()}>
              <div className="flex items-center justify-between mb-5">
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-xl bg-primary/10 flex items-center justify-center">
                    <FolderOpen size={20} className="text-primary" />
                  </div>
                  <div>
                    <h3 className="text-lg font-bold text-gray-900">Add Resource</h3>
                    <p className="text-xs text-gray-400">Add a link or upload a file</p>
                  </div>
                </div>
                <button onClick={resetModal} className="p-2 rounded-lg hover:bg-gray-100 text-gray-400">
                  <X size={18} />
                </button>
              </div>

              {/* Tab Toggle */}
              <div className="flex bg-gray-100 rounded-xl p-1 mb-5">
                <button
                  onClick={() => setModalTab('link')}
                  className={`flex-1 flex items-center justify-center gap-2 py-2 rounded-lg text-sm font-medium transition-all ${
                    modalTab === 'link' ? 'bg-white text-gray-900 shadow-sm' : 'text-gray-500 hover:text-gray-700'
                  }`}>
                  <Link2 size={14} /> Resource Link
                </button>
                <button
                  onClick={() => setModalTab('upload')}
                  className={`flex-1 flex items-center justify-center gap-2 py-2 rounded-lg text-sm font-medium transition-all ${
                    modalTab === 'upload' ? 'bg-white text-gray-900 shadow-sm' : 'text-gray-500 hover:text-gray-700'
                  }`}>
                  <Upload size={14} /> Upload File
                </button>
              </div>

              {/* Link Tab */}
              {modalTab === 'link' && (
                <div className="space-y-4">
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1.5">Title</label>
                    <input value={form.title} onChange={e => setForm(f => ({...f, title: e.target.value}))}
                      placeholder="Resource title"
                      className="w-full px-4 py-3 border border-gray-200 rounded-xl text-gray-900 bg-white focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary text-sm" />
                  </div>
                  {websites.length > 0 && (
                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-1.5">
                        <Globe size={14} className="inline mr-1 -mt-0.5" />Website <span className="text-gray-400 font-normal">(optional)</span>
                      </label>
                      <select value={form.website_id} onChange={e => setForm(f => ({...f, website_id: e.target.value}))}
                        className="w-full px-4 py-3 border border-gray-200 rounded-xl text-gray-900 bg-white focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary text-sm">
                        <option value="">No website selected</option>
                        {websites.map(w => (
                          <option key={w.id} value={w.id}>{w.domain}</option>
                        ))}
                      </select>
                    </div>
                  )}
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1.5">Resource URL</label>
                    <input value={form.video_url} onChange={e => setForm(f => ({...f, video_url: e.target.value}))}
                      placeholder="https://www.youtube.com/watch?v=..."
                      className="w-full px-4 py-3 border border-gray-200 rounded-xl text-gray-900 bg-white focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary text-sm" />
                    <p className="text-xs text-gray-400 mt-1">Supports YouTube, Vimeo, Dailymotion, or any direct link</p>
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1.5">Description <span className="text-gray-400 font-normal">(optional)</span></label>
                    <textarea value={form.description} onChange={e => setForm(f => ({...f, description: e.target.value}))}
                      placeholder="Brief description of the resource..."
                      rows={3}
                      className="w-full px-4 py-3 border border-gray-200 rounded-xl text-gray-900 bg-white focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary text-sm resize-none" />
                  </div>
                  {form.video_url && getThumbnail(form.video_url) && (
                    <div className="rounded-xl overflow-hidden border border-gray-100">
                      <img src={getThumbnail(form.video_url)!} alt="Preview" className="w-full aspect-video object-cover" />
                    </div>
                  )}
                  <div className="flex gap-3 mt-6">
                    <button onClick={handleAdd} disabled={saving}
                      className="flex-1 bg-primary hover:bg-primary-dark text-white py-3 rounded-xl text-sm font-semibold disabled:bg-gray-300 transition-colors">
                      {saving ? 'Adding...' : 'Add Resource'}
                    </button>
                    <button onClick={resetModal}
                      className="flex-1 py-3 rounded-xl text-sm font-medium text-gray-600 border border-gray-200 hover:bg-gray-50 transition-colors">
                      Cancel
                    </button>
                  </div>
                </div>
              )}

              {/* Upload Tab */}
              {modalTab === 'upload' && (
                <div className="space-y-4">
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1.5">Title</label>
                    <input value={uploadForm.title} onChange={e => setUploadForm(f => ({...f, title: e.target.value}))}
                      placeholder="Resource title"
                      className="w-full px-4 py-3 border border-gray-200 rounded-xl text-gray-900 bg-white focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary text-sm" />
                  </div>
                  {websites.length > 0 && (
                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-1.5">
                        <Globe size={14} className="inline mr-1 -mt-0.5" />Website <span className="text-gray-400 font-normal">(optional)</span>
                      </label>
                      <select value={uploadForm.website_id} onChange={e => setUploadForm(f => ({...f, website_id: e.target.value}))}
                        className="w-full px-4 py-3 border border-gray-200 rounded-xl text-gray-900 bg-white focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary text-sm">
                        <option value="">No website selected</option>
                        {websites.map(w => (
                          <option key={w.id} value={w.id}>{w.domain}</option>
                        ))}
                      </select>
                    </div>
                  )}

                  {/* Drop zone */}
                  <div
                    onDragOver={e => { e.preventDefault(); setDragOver(true) }}
                    onDragLeave={() => setDragOver(false)}
                    onDrop={handleFileDrop}
                    onClick={() => fileInputRef.current?.click()}
                    className={`border-2 border-dashed rounded-xl p-6 text-center cursor-pointer transition-all ${
                      dragOver ? 'border-primary bg-primary/5' :
                      uploadFile ? 'border-emerald-300 bg-emerald-50' :
                      'border-gray-200 hover:border-gray-300 hover:bg-gray-50'
                    }`}>
                    <input
                      ref={fileInputRef}
                      type="file"
                      accept="*/*"
                      onChange={handleFileSelect}
                      className="hidden" />
                    {uploadFile ? (
                      <div className="flex items-center gap-3">
                        <div className="w-10 h-10 rounded-xl bg-emerald-100 flex items-center justify-center flex-shrink-0">
                          <FileVideo size={20} className="text-emerald-600" />
                        </div>
                        <div className="text-left min-w-0 flex-1">
                          <p className="text-sm font-medium text-gray-900 truncate">{uploadFile.name}</p>
                          <p className="text-xs text-gray-500">{formatFileSize(uploadFile.size)}</p>
                        </div>
                        <button onClick={e => { e.stopPropagation(); setUploadFile(null) }}
                          className="p-1.5 rounded-lg hover:bg-red-50 text-gray-400 hover:text-red-500 transition-colors">
                          <X size={16} />
                        </button>
                      </div>
                    ) : (
                      <>
                        <div className="w-12 h-12 rounded-xl bg-gray-100 flex items-center justify-center mx-auto mb-3">
                          <Upload size={22} className="text-gray-400" />
                        </div>
                        <p className="text-sm font-medium text-gray-700 mb-1">
                          Drop your file here or <span className="text-primary">browse</span>
                        </p>
                        <p className="text-xs text-gray-400">Any file type · Max 200MB</p>
                      </>
                    )}
                  </div>

                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1.5">Description <span className="text-gray-400 font-normal">(optional)</span></label>
                    <textarea value={uploadForm.description} onChange={e => setUploadForm(f => ({...f, description: e.target.value}))}
                      placeholder="Brief description of the resource..."
                      rows={3}
                      className="w-full px-4 py-3 border border-gray-200 rounded-xl text-gray-900 bg-white focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary text-sm resize-none" />
                  </div>

                  {/* Upload progress */}
                  {saving && uploadProgress > 0 && (
                    <div>
                      <div className="flex justify-between text-xs text-gray-500 mb-1">
                        <span>Uploading...</span>
                        <span>{uploadProgress}%</span>
                      </div>
                      <div className="w-full bg-gray-100 rounded-full h-2">
                        <div className="bg-primary h-2 rounded-full transition-all" style={{ width: `${uploadProgress}%` }} />
                      </div>
                    </div>
                  )}

                  <div className="flex gap-3 mt-6">
                    <button onClick={handleUpload} disabled={saving}
                      className="flex-1 bg-primary hover:bg-primary-dark text-white py-3 rounded-xl text-sm font-semibold disabled:bg-gray-300 transition-colors flex items-center justify-center gap-2">
                      {saving ? 'Uploading...' : <><Upload size={14} /> Upload Resource</>}
                    </button>
                    <button onClick={resetModal}
                      className="flex-1 py-3 rounded-xl text-sm font-medium text-gray-600 border border-gray-200 hover:bg-gray-50 transition-colors">
                      Cancel
                    </button>
                  </div>
                </div>
              )}
            </div>
          </div>
        )}

        {/* Preview Modal */}
        {previewVideo && (
          <div className="fixed inset-0 bg-black/70 backdrop-blur-sm z-50 flex items-center justify-center p-4" onClick={() => setPreviewVideo(null)}>
            <div className="w-full max-w-3xl" onClick={e => e.stopPropagation()}>
              <div className="flex items-center justify-between mb-3">
                <h3 className="text-white font-semibold truncate mr-4">{previewVideo.title}</h3>
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

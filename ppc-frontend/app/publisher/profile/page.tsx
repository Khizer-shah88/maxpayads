'use client'

import { useState, useEffect } from 'react'
import { User, Mail, Lock, Save } from 'lucide-react'
import { toast } from 'sonner'
import PublisherSidebar from '@/components/shared/PublisherSidebar'
import { Spinner } from '@/components/ui/loading'
import { publisherApi } from '@/lib/api'
import { useAuth } from '@/lib/hooks/useAuth'

export default function PublisherProfilePage() {
  const { user, initialize } = useAuth()
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [form, setForm] = useState({
    name: '',
    email: '',
  })
  const [passwordForm, setPasswordForm] = useState({
    current_password: '',
    new_password: '',
    confirm_password: '',
  })
  const [changingPassword, setChangingPassword] = useState(false)

  useEffect(() => { initialize() }, [])

  useEffect(() => {
    if (!user) return
    publisherApi.getDashboard()
      .then(res => {
        const pub = res.data.publisher
        setForm({
          name: pub.name || '',
          email: pub.email || '',
        })
      })
      .catch(() => toast.error('Failed to load profile'))
      .finally(() => setLoading(false))
  }, [user])

  const handleSave = async () => {
    setSaving(true)
    try {
      await publisherApi.updateProfile({
        name: form.name,
      })
      toast.success('Profile updated')
    } catch { toast.error('Failed to update profile') }
    finally { setSaving(false) }
  }

  const handleChangePassword = async () => {
    if (passwordForm.new_password !== passwordForm.confirm_password) {
      toast.error('Passwords do not match')
      return
    }
    if (passwordForm.new_password.length < 8) {
      toast.error('Password must be at least 8 characters')
      return
    }
    setChangingPassword(true)
    try {
      await publisherApi.updateProfile({
        current_password: passwordForm.current_password,
        new_password: passwordForm.new_password,
      })
      toast.success('Password changed')
      setPasswordForm({ current_password: '', new_password: '', confirm_password: '' })
    } catch { toast.error('Failed to change password') }
    finally { setChangingPassword(false) }
  }

  const inputClass = "w-full px-4 py-2.5 border border-gray-200 rounded-xl text-gray-900 bg-white focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary text-sm"

  if (loading) {
    return (
      <div className="flex min-h-screen bg-[#f8f9fb]">
        <PublisherSidebar />
        <div className="flex-1 lg:ml-64 p-6 lg:p-8">
          <div className="space-y-4 pt-12 lg:pt-0">
            {[1, 2, 3].map(i => <div key={i} className="shimmer h-20 rounded-2xl" />)}
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="flex min-h-screen bg-[#f8f9fb]">
      <PublisherSidebar />
      <div className="flex-1 lg:ml-64 p-6 lg:p-8">
        <div className="mb-8 pt-12 lg:pt-0">
          <h1 className="text-2xl font-bold text-gray-900">Profile</h1>
          <p className="text-gray-400 text-sm mt-0.5">Manage your account settings</p>
        </div>

        <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
          {/* Profile Info */}
          <div className="bg-white rounded-2xl border border-gray-100 p-6">
            <h2 className="text-base font-semibold text-gray-900 mb-4 flex items-center gap-2">
              <User size={18} /> Account Information
            </h2>
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Name</label>
                <div className="relative">
                  <User className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" size={16} />
                  <input value={form.name} onChange={e => setForm(p => ({ ...p, name: e.target.value }))}
                    className={`${inputClass} !pl-10`} />
                </div>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Email</label>
                <div className="relative">
                  <Mail className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" size={16} />
                  <input value={form.email} disabled
                    className={`${inputClass} !pl-10 bg-gray-50 text-gray-500 cursor-not-allowed`} />
                </div>
                <p className="text-xs text-gray-400 mt-1">Email cannot be changed</p>
              </div>
            </div>
          </div>

        </div>

        {/* Save Button */}
        <div className="mt-4 flex justify-end">
          <button onClick={handleSave} disabled={saving}
            className="bg-primary hover:bg-primary-dark text-white px-6 py-2.5 rounded-xl text-sm font-semibold flex items-center gap-2 disabled:bg-gray-300">
            {saving ? <Spinner size={16} /> : <><Save size={16} /> Save Changes</>}
          </button>
        </div>

        {/* Change Password */}
        <div className="bg-white rounded-2xl border border-gray-100 p-6 mt-6">
          <h2 className="text-base font-semibold text-gray-900 mb-4 flex items-center gap-2">
            <Lock size={18} /> Change Password
          </h2>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Current Password</label>
              <input type="password" value={passwordForm.current_password}
                onChange={e => setPasswordForm(p => ({ ...p, current_password: e.target.value }))}
                className={inputClass} />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">New Password</label>
              <input type="password" value={passwordForm.new_password}
                onChange={e => setPasswordForm(p => ({ ...p, new_password: e.target.value }))}
                className={inputClass} />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Confirm Password</label>
              <input type="password" value={passwordForm.confirm_password}
                onChange={e => setPasswordForm(p => ({ ...p, confirm_password: e.target.value }))}
                className={inputClass} />
            </div>
          </div>
          <div className="mt-4 flex justify-end">
            <button onClick={handleChangePassword}
              disabled={changingPassword || !passwordForm.current_password || !passwordForm.new_password || !passwordForm.confirm_password}
              className="bg-gray-800 hover:bg-black text-white px-5 py-2.5 rounded-xl text-sm font-semibold flex items-center gap-2 disabled:bg-gray-300">
              {changingPassword ? <Spinner size={16} /> : <><Lock size={16} /> Change Password</>}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}

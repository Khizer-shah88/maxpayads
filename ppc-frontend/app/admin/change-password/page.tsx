'use client'

import { useState, useEffect } from 'react'
import { Eye, EyeOff, Lock, ShieldCheck } from 'lucide-react'
import { toast } from 'sonner'
import Sidebar from '@/components/shared/Sidebar'
import { adminApi } from '@/lib/api'
import { useAuth } from '@/lib/hooks/useAuth'

export default function ChangePasswordPage() {
  const { initialize } = useAuth()
  const [currentPassword, setCurrentPassword] = useState('')
  const [securityAnswer, setSecurityAnswer] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [showCurrent, setShowCurrent] = useState(false)
  const [showAnswer, setShowAnswer] = useState(false)
  const [showNew, setShowNew] = useState(false)
  const [showConfirm, setShowConfirm] = useState(false)
  const [loading, setLoading] = useState(false)
  const [securityQuestion, setSecurityQuestion] = useState('')
  const [loadingQuestion, setLoadingQuestion] = useState(true)

  useEffect(() => { 
    initialize()
    loadSecurityQuestion()
  }, [])

  const loadSecurityQuestion = async () => {
    try {
      const res = await adminApi.getSecurityQuestion()
      setSecurityQuestion(res.data.question)
    } catch (err: any) {
      console.error('Failed to load security question:', err)
      // Don't show error toast - just use the default question silently
      // This allows the feature to work even if API fails
      setSecurityQuestion('What is your father\'s name?')
    } finally {
      setLoadingQuestion(false)
    }
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (newPassword.length < 8) {
      toast.error('New password must be at least 8 characters')
      return
    }
    if (newPassword !== confirmPassword) {
      toast.error('New passwords do not match')
      return
    }
    if (!securityAnswer.trim()) {
      toast.error('Security question answer is required')
      return
    }
    setLoading(true)
    try {
      await adminApi.changePassword(currentPassword, securityAnswer, newPassword)
      toast.success('Password changed successfully')
      setCurrentPassword('')
      setSecurityAnswer('')
      setNewPassword('')
      setConfirmPassword('')
    } catch (err: any) {
      toast.error(err.response?.data?.detail || 'Failed to change password')
    } finally {
      setLoading(false)
    }
  }

  const inputClass = "w-full px-4 py-2.5 border border-gray-200 rounded-xl text-gray-900 bg-white focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary text-sm pr-11"

  return (
    <div className="flex min-h-screen bg-[#f8f9fb]">
      <Sidebar />
      <div className="flex-1 lg:ml-64 p-6 lg:p-8 min-w-0 overflow-x-hidden">
        <div className="mb-8 pt-12 lg:pt-0">
          <h1 className="text-2xl font-bold text-gray-900">Change Password</h1>
          <p className="text-gray-400 text-sm mt-0.5">Update your admin account password</p>
        </div>

        <div className="bg-white rounded-2xl border border-gray-100 p-6 max-w-md">
          {/* Security Notice */}
          <div className="mb-6 p-4 bg-blue-50 border border-blue-100 rounded-xl flex gap-3">
            <ShieldCheck className="text-blue-600 flex-shrink-0" size={20} />
            <div>
              <h3 className="text-sm font-semibold text-blue-900 mb-1">Enhanced Security</h3>
              <p className="text-xs text-blue-700">
                For your security, you must provide both your current password and answer to your security question to change your password.
              </p>
            </div>
          </div>

          <form onSubmit={handleSubmit} className="space-y-5">
            <div>
              <label className="block text-sm font-semibold text-gray-700 mb-1.5">Current Password</label>
              <div className="relative">
                <input
                  type={showCurrent ? 'text' : 'password'}
                  value={currentPassword}
                  onChange={e => setCurrentPassword(e.target.value)}
                  required
                  className={inputClass}
                  placeholder="Enter current password"
                />
                <button
                  type="button"
                  onClick={() => setShowCurrent(!showCurrent)}
                  className="absolute right-3.5 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600 transition-colors"
                >
                  {showCurrent ? <EyeOff size={16} /> : <Eye size={16} />}
                </button>
              </div>
            </div>

            <div>
              <label className="block text-sm font-semibold text-gray-700 mb-1.5">Security Question</label>
              {loadingQuestion ? (
                <div className="text-sm text-gray-400 py-2">Loading...</div>
              ) : (
                <>
                  <div className="mb-2 p-3 bg-gray-50 border border-gray-200 rounded-lg">
                    <p className="text-sm text-gray-700 font-medium">{securityQuestion}</p>
                  </div>
                  <div className="relative">
                    <input
                      type={showAnswer ? 'text' : 'password'}
                      value={securityAnswer}
                      onChange={e => setSecurityAnswer(e.target.value)}
                      required
                      className={inputClass}
                      placeholder="Enter your answer"
                    />
                    <button
                      type="button"
                      onClick={() => setShowAnswer(!showAnswer)}
                      className="absolute right-3.5 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600 transition-colors"
                    >
                      {showAnswer ? <EyeOff size={16} /> : <Eye size={16} />}
                    </button>
                  </div>
                </>
              )}
            </div>

            <div>
              <label className="block text-sm font-semibold text-gray-700 mb-1.5">New Password</label>
              <div className="relative">
                <input
                  type={showNew ? 'text' : 'password'}
                  value={newPassword}
                  onChange={e => setNewPassword(e.target.value)}
                  required
                  minLength={8}
                  className={inputClass}
                  placeholder="Enter new password"
                />
                <button
                  type="button"
                  onClick={() => setShowNew(!showNew)}
                  className="absolute right-3.5 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600 transition-colors"
                >
                  {showNew ? <EyeOff size={16} /> : <Eye size={16} />}
                </button>
              </div>
              <p className="text-xs text-gray-500 mt-1">Minimum 8 characters</p>
            </div>

            <div>
              <label className="block text-sm font-semibold text-gray-700 mb-1.5">Confirm New Password</label>
              <div className="relative">
                <input
                  type={showConfirm ? 'text' : 'password'}
                  value={confirmPassword}
                  onChange={e => setConfirmPassword(e.target.value)}
                  required
                  minLength={8}
                  className={inputClass}
                  placeholder="Confirm new password"
                />
                <button
                  type="button"
                  onClick={() => setShowConfirm(!showConfirm)}
                  className="absolute right-3.5 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600 transition-colors"
                >
                  {showConfirm ? <EyeOff size={16} /> : <Eye size={16} />}
                </button>
              </div>
            </div>

            <button
              type="submit"
              disabled={loading || !currentPassword || !securityAnswer || !newPassword || !confirmPassword || loadingQuestion}
              className="w-full bg-primary hover:bg-primary-dark text-white font-semibold py-2.5 rounded-xl text-sm flex items-center justify-center gap-2 disabled:bg-gray-300 disabled:cursor-not-allowed transition-colors"
            >
              <Lock size={16} />
              {loading ? 'Changing...' : 'Change Password'}
            </button>
          </form>
        </div>
      </div>
    </div>
  )
}

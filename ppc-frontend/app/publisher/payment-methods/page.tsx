'use client'

import { useState, useEffect } from 'react'
import { Wallet, CreditCard, Building2, Bitcoin, CircleDollarSign, Save, CheckCircle2, AlertCircle } from 'lucide-react'
import { toast } from 'sonner'
import PublisherSidebar from '@/components/shared/PublisherSidebar'
import { Spinner } from '@/components/ui/loading'
import { publisherApi } from '@/lib/api'
import { useAuth } from '@/lib/hooks/useAuth'

const PAYMENT_METHODS = [
  { key: 'paypal', label: 'PayPal', icon: CircleDollarSign, color: 'text-blue-600', bg: 'bg-blue-50', border: 'border-blue-200', placeholder: 'Enter your PayPal email address', hint: 'We will send payments to this PayPal email' },
  { key: 'bank_transfer', label: 'Bank Transfer', icon: Building2, color: 'text-emerald-600', bg: 'bg-emerald-50', border: 'border-emerald-200', placeholder: 'Bank name, Account number, Routing number, SWIFT/IBAN', hint: 'Include all required details for wire transfer' },
  { key: 'crypto', label: 'Crypto (BTC/ETH)', icon: Bitcoin, color: 'text-orange-600', bg: 'bg-orange-50', border: 'border-orange-200', placeholder: 'Enter your BTC or ETH wallet address', hint: 'Specify which cryptocurrency and your wallet address' },
  { key: 'usdt', label: 'USDT (TRC20/ERC20)', icon: CircleDollarSign, color: 'text-green-600', bg: 'bg-green-50', border: 'border-green-200', placeholder: 'Enter your USDT wallet address (TRC20 or ERC20)', hint: 'Please specify the network (TRC20 or ERC20)' },
  { key: 'binance_pay', label: 'Binance Pay', icon: CreditCard, color: 'text-yellow-600', bg: 'bg-yellow-50', border: 'border-yellow-200', placeholder: 'Enter your Binance Pay ID or email', hint: 'Your Binance Pay ID can be found in Binance app' },
]

export default function PaymentMethodsPage() {
  const { initialize } = useAuth()
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [selectedMethod, setSelectedMethod] = useState('paypal')
  const [paymentDetails, setPaymentDetails] = useState('')
  const [savedMethod, setSavedMethod] = useState<string | null>(null)
  const [savedDetails, setSavedDetails] = useState<string | null>(null)

  useEffect(() => { initialize() }, [])

  useEffect(() => {
    publisherApi.getDashboard()
      .then(res => {
        const pub = res.data.publisher
        const method = pub.payment_method || ''
        const details = pub.payment_details || ''
        setSelectedMethod(method || 'paypal')
        setPaymentDetails(details)
        if (method && details) {
          setSavedMethod(method)
          setSavedDetails(details)
        }
      })
      .catch(() => toast.error('Failed to load payment info'))
      .finally(() => setLoading(false))
  }, [])

  const handleSave = async () => {
    if (!paymentDetails.trim()) {
      toast.error('Please enter your payment details')
      return
    }
    setSaving(true)
    try {
      await publisherApi.updateProfile({
        payment_method: selectedMethod,
        payment_details: paymentDetails.trim(),
      })
      setSavedMethod(selectedMethod)
      setSavedDetails(paymentDetails.trim())
      toast.success('Payment method saved successfully')
    } catch { toast.error('Failed to save payment method') }
    finally { setSaving(false) }
  }

  const activeMethodInfo = PAYMENT_METHODS.find(m => m.key === selectedMethod) || PAYMENT_METHODS[0]
  const hasChanges = selectedMethod !== savedMethod || paymentDetails !== savedDetails

  const inputClass = "w-full px-4 py-2.5 border border-gray-200 rounded-xl text-gray-900 bg-white focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary text-sm"

  if (loading) {
    return (
      <div className="flex min-h-screen bg-[#f8f9fb]">
        <PublisherSidebar />
        <div className="flex-1 lg:ml-64 p-6 lg:p-8">
          <div className="space-y-4 pt-12 lg:pt-0">
            {[1, 2, 3].map(i => <div key={i} className="shimmer h-24 rounded-2xl" />)}
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
          <h1 className="text-2xl font-bold text-gray-900">Payment Methods</h1>
          <p className="text-gray-400 text-sm mt-0.5">Set up your preferred payment method for withdrawals</p>
        </div>

        <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
          {/* Left: Method Selection */}
          <div className="xl:col-span-1 space-y-3">
            <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-wider mb-3">Select Method</h2>
            {PAYMENT_METHODS.map(method => {
              const isActive = selectedMethod === method.key
              const isSaved = savedMethod === method.key
              return (
                <button
                  key={method.key}
                  onClick={() => {
                    setSelectedMethod(method.key)
                    if (method.key === savedMethod) {
                      setPaymentDetails(savedDetails || '')
                    } else {
                      setPaymentDetails('')
                    }
                  }}
                  className={`w-full flex items-center gap-3 p-4 rounded-xl border-2 transition-all text-left ${
                    isActive
                      ? `${method.bg} ${method.border} shadow-sm`
                      : 'bg-white border-gray-100 hover:border-gray-200 hover:bg-gray-50'
                  }`}
                >
                  <div className={`w-10 h-10 rounded-lg flex items-center justify-center ${isActive ? method.bg : 'bg-gray-100'}`}>
                    <method.icon className={`w-5 h-5 ${isActive ? method.color : 'text-gray-400'}`} />
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className={`text-sm font-semibold ${isActive ? 'text-gray-900' : 'text-gray-600'}`}>{method.label}</p>
                    {isSaved && (
                      <p className="text-[11px] text-emerald-600 font-medium flex items-center gap-1 mt-0.5">
                        <CheckCircle2 size={10} /> Active
                      </p>
                    )}
                  </div>
                  {isActive && (
                    <div className={`w-5 h-5 rounded-full ${method.color} flex items-center justify-center`}>
                      <div className="w-2 h-2 rounded-full bg-current" />
                    </div>
                  )}
                </button>
              )
            })}
          </div>

          {/* Right: Details Form */}
          <div className="xl:col-span-2">
            <div className="bg-white rounded-2xl border border-gray-100 overflow-hidden">
              {/* Header */}
              <div className={`px-6 py-5 ${activeMethodInfo.bg} border-b ${activeMethodInfo.border}`}>
                <div className="flex items-center gap-3">
                  <div className={`w-12 h-12 rounded-xl bg-white/80 flex items-center justify-center`}>
                    <activeMethodInfo.icon className={`w-6 h-6 ${activeMethodInfo.color}`} />
                  </div>
                  <div>
                    <h3 className="font-bold text-gray-900">{activeMethodInfo.label}</h3>
                    <p className="text-xs text-gray-500 mt-0.5">{activeMethodInfo.hint}</p>
                  </div>
                </div>
              </div>

              {/* Form */}
              <div className="p-6 space-y-5">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-2">Payment Details</label>
                  <textarea
                    value={paymentDetails}
                    onChange={e => setPaymentDetails(e.target.value)}
                    placeholder={activeMethodInfo.placeholder}
                    rows={4}
                    className={`${inputClass} resize-none`}
                  />
                </div>

                {/* Info box */}
                <div className="flex items-start gap-3 p-4 bg-blue-50 rounded-xl border border-blue-100">
                  <AlertCircle size={18} className="text-blue-500 flex-shrink-0 mt-0.5" />
                  <div className="text-sm text-blue-700">
                    <p className="font-medium mb-1">Important</p>
                    <p className="text-xs leading-relaxed">
                      Make sure your payment details are accurate. This information will be used automatically when you request a withdrawal.
                      Double-check all wallet addresses and account numbers before saving.
                    </p>
                  </div>
                </div>

                {/* Current saved info */}
                {savedMethod && savedDetails && (
                  <div className="p-4 bg-emerald-50 rounded-xl border border-emerald-100">
                    <div className="flex items-center gap-2 mb-2">
                      <CheckCircle2 size={14} className="text-emerald-600" />
                      <p className="text-xs font-semibold text-emerald-700 uppercase tracking-wider">Currently Saved</p>
                    </div>
                    <p className="text-sm font-medium text-gray-900 capitalize">{savedMethod.replace(/_/g, ' ')}</p>
                    <p className="text-xs text-gray-500 mt-1 whitespace-pre-wrap break-all">{savedDetails}</p>
                  </div>
                )}

                {/* Save Button */}
                <button
                  onClick={handleSave}
                  disabled={saving || !paymentDetails.trim() || !hasChanges}
                  className="w-full bg-primary hover:bg-primary-dark text-white py-3 rounded-xl text-sm font-semibold flex items-center justify-center gap-2 disabled:bg-gray-300 disabled:cursor-not-allowed transition-all"
                >
                  {saving ? <Spinner size={16} /> : <><Save size={16} /> Save Payment Method</>}
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

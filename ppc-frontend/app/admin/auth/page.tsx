'use client'

import { useEffect } from 'react'
import { useRouter } from 'next/navigation'

export default function AdminAuthPage() {
  const router = useRouter()

  useEffect(() => {
    // Redirect to 404 - this login path is no longer available
    router.replace('/404')
  }, [router])

  return (
    <div className="min-h-screen flex items-center justify-center">
      <div className="text-center">
        <p className="text-gray-500">Redirecting...</p>
      </div>
    </div>
  )
}

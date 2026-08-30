'use client'
import { useEffect } from 'react'
import { useRouter } from 'next/navigation'

/** Resources page removed — redirect to dashboard silently. */
export default function AdminVideosRedirect() {
  const router = useRouter()
  useEffect(() => { router.replace('/admin/dashboard') }, [router])
  return null
}

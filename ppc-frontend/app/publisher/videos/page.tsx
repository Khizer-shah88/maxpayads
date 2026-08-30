'use client'
import { useEffect } from 'react'
import { useRouter } from 'next/navigation'

/** Resources page removed — redirect to dashboard silently. */
export default function PublisherVideosRedirect() {
  const router = useRouter()
  useEffect(() => { router.replace('/publisher/dashboard') }, [router])
  return null
}

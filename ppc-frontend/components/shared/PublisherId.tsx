'use client'

import { useEffect, useState } from 'react'
import { adminApi } from '@/lib/api'
import { formatPublisherId } from '@/lib/publisher-id'

const lookups = new Map<string, Promise<string>>()

export default function PublisherId({ publicId, publisherId }: { publicId?: string | null; publisherId?: string }) {
  const [resolved, setResolved] = useState('')
  useEffect(() => {
    setResolved('')
    if (publicId || !publisherId) return
    let active = true
    if (!lookups.has(publisherId)) {
      lookups.set(publisherId, adminApi.getPublisher(publisherId)
        .then(res => res.data.publisher?.public_id || '')
        .catch(() => { lookups.delete(publisherId); return '' }))
    }
    lookups.get(publisherId)!.then(id => { if (active) setResolved(id) })
    return () => { active = false }
  }, [publicId, publisherId])
  const id = formatPublisherId(publicId || resolved)
  return id ? <span className="block text-xs font-mono text-gray-400">{id}</span> : null
}

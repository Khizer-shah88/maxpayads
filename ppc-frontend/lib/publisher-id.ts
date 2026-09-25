// Match the Publishers page everywhere. Keep PUB_ in tracking URLs/API values.
export function formatPublisherId(publicId?: string | null): string {
  return (publicId || '').replace(/^PUB_/, '')
}

export function publisherOption(publisher: { name?: string; public_id?: string | null }): string {
  const id = formatPublisherId(publisher.public_id)
  return [publisher.name, id].filter(Boolean).join(' · ')
}

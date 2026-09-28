import { redirect } from 'next/navigation'

// Keep existing bookmarked login URLs working through the canonical form.
export default function AdminSecureAuthPage() {
  redirect('/admin/auth')
}

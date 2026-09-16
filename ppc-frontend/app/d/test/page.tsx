'use client'

export default function TestPage() {
  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-100">
      <div className="bg-white rounded-lg shadow-lg p-8 max-w-md">
        <h1 className="text-2xl font-bold text-gray-900 mb-4">Test Page Working!</h1>
        <p className="text-gray-600 mb-4">
          If you can see this page, the /d/ route is working correctly.
        </p>
        <p className="text-sm text-gray-500">
          The dynamic [slug] route should also work.
        </p>
        <div className="mt-6 p-4 bg-blue-50 rounded">
          <p className="text-xs text-blue-800 font-mono">
            Path: /d/test
          </p>
          <p className="text-xs text-blue-800 font-mono mt-1">
            Host: {typeof window !== 'undefined' ? window.location.hostname : 'server'}
          </p>
        </div>
      </div>
    </div>
  )
}

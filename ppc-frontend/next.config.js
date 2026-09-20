/** @type {import('next').NextConfig} */
const nextConfig = {
  // Enable standalone output for Docker
  output: 'standalone',
  
  // NOTE: ENABLE_SOURCE_DETERRENT is deliberately NOT listed under `env`.
  // Next's `env` key inlines values via DefinePlugin at BUILD time, which
  // freezes the flag into the image and makes it unflippable without a
  // rebuild -- the opposite of a kill switch. Both consumers (the clean-shell
  // route handler and the /d/[slug] layout) render on the server per request,
  // so they read the real runtime env directly. Set it in docker-compose.
  
  webpack: (config, { dev, isServer }) => {
    // Basic optimization for production
    if (!dev && !isServer) {
      // Remove source maps completely
      config.devtool = false
    }
    
    return config
  },
  
  // API proxy. These lived ONLY in next.config.mjs, which Next never loads:
  // CONFIG_FILES is ["next.config.js", "next.config.mjs"] and the first match
  // wins, so the .mjs file was dead code. In production nginx proxies /api
  // itself, which masked it; in local dev `lib/api.ts` (baseURL: '/api') had
  // no proxy at all and every API call 404'd.
  async rewrites() {
    const backendUrl = process.env.NEXT_BACKEND_URL || 'http://localhost:8000'
    return [
      { source: '/api/:path*', destination: `${backendUrl}/:path*` },
      { source: '/uploads/:path*', destination: `${backendUrl}/uploads/:path*` },
    ]
  },

  // Enable compression
  compress: true,
  
  // Remove identifying headers
  poweredByHeader: false,
  
  // Enhanced security headers
  async headers() {
    return [
      {
        source: '/d/:path*',
        headers: [
          {
            key: 'Cache-Control',
            value: 'no-store, no-cache, must-revalidate, private',
          },
          {
            key: 'X-Content-Type-Options',
            value: 'nosniff',
          },
          {
            key: 'X-Frame-Options',
            value: 'DENY',
          },
          {
            key: 'Referrer-Policy',
            value: 'no-referrer',
          },
          {
            key: 'Content-Security-Policy',
            value: "default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline' 'unsafe-eval'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; worker-src 'self';",
          },
        ],
      },
    ]
  },
}

module.exports = nextConfig
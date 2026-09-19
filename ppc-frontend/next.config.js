/** @type {import('next').NextConfig} */
const nextConfig = {
  // Enable standalone output for Docker
  output: 'standalone',
  
  // Environment variables for source deterrent feature
  env: {
    ENABLE_SOURCE_DETERRENT: process.env.ENABLE_SOURCE_DETERRENT || 'true',
  },
  
  webpack: (config, { dev, isServer }) => {
    // Basic optimization for production
    if (!dev && !isServer) {
      // Remove source maps completely
      config.devtool = false
    }
    
    return config
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
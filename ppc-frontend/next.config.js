/** @type {import('next').NextConfig} */
const nextConfig = {
  webpack: (config, { dev, isServer }) => {
    // Only obfuscate in production client-side builds
    if (!dev && !isServer) {
      // Minimize and obfuscate JavaScript
      config.optimization = {
        ...config.optimization,
        minimize: true,
        minimizer: [
          ...config.optimization.minimizer,
          // Additional obfuscation for view-source protection
        ],
      }
      
      // Rename variables and functions to make code unreadable
      config.optimization.splitChunks = {
        ...config.optimization.splitChunks,
        cacheGroups: {
          default: {
            name: false, // Remove readable chunk names
          },
        },
      }
      
      // Remove source maps in production (prevents readable debugging)
      config.devtool = false
    }
    
    return config
  },
  
  // Additional security headers
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
        ],
      },
    ]
  },
  
  // Compress output
  compress: true,
  
  // Remove x-powered-by header
  poweredByHeader: false,
}

module.exports = nextConfig
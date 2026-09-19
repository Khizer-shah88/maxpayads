/** @type {import('next').NextConfig} */
const nextConfig = {
  // Enable standalone output for Docker
  output: 'standalone',
  
  webpack: (config, { dev, isServer }) => {
    // Only apply optimizations in production client-side builds
    if (!dev && !isServer) {
      // Remove source maps in production
      config.devtool = false
      
      // Basic minification (less aggressive to avoid breaking functionality)
      config.optimization = {
        ...config.optimization,
        minimize: true,
      }
      
      // Find existing TerserPlugin and configure it with safer settings
      const existingMinimizers = config.optimization.minimizer || []
      config.optimization.minimizer = existingMinimizers.map(minimizer => {
        if (minimizer.constructor.name === 'TerserPlugin') {
          return new minimizer.constructor({
            ...minimizer.options,
            terserOptions: {
              compress: {
                drop_console: false, // Keep console logs for debugging
                drop_debugger: true,
                passes: 1, // Reduce passes to avoid breaking code
                unsafe: false, // Disable unsafe transformations
              },
              mangle: {
                toplevel: false, // Don't mangle top-level variables
                properties: false, // Don't mangle properties
              },
              format: {
                comments: false,
                beautify: false,
              },
            },
          })
        }
        return minimizer
      })
    }
    
    return config
  },
  
  // Compress output
  compress: true,
  
  // Remove x-powered-by header
  poweredByHeader: false,
  
  // Security headers for prelander pages only
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
        ],
      },
    ]
  },
}

module.exports = nextConfig
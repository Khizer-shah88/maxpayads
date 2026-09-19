/** @type {import('next').NextConfig} */
const nextConfig = {
  // Enable standalone output for Docker
  output: 'standalone',
  
  webpack: (config, { dev, isServer }) => {
    // Only obfuscate in production client-side builds
    if (!dev && !isServer) {
      // Remove source maps in production (prevents readable debugging)
      config.devtool = false
      
      // Additional minification and obfuscation
      config.optimization = {
        ...config.optimization,
        minimize: true,
        // Mangle variable names for obfuscation
        minimizer: [
          ...config.optimization.minimizer,
        ],
      }
      
      // Enable aggressive chunk splitting and minification
      config.optimization.splitChunks = {
        chunks: 'all',
        minSize: 0,
        cacheGroups: {
          framework: {
            chunks: 'all',
            name: 'framework',
            test: /(?<!node_modules.*)[\\/]node_modules[\\/](react|react-dom|scheduler|prop-types|use-subscription)[\\/]/,
            priority: 40,
            enforce: true,
          },
        },
      }
    }
    
    return config
  },
  
  // Compress output for smaller bundles
  compress: true,
  
  // Remove x-powered-by header for security
  poweredByHeader: false,
  
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
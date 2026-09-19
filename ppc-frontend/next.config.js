/** @type {import('next').NextConfig} */
const nextConfig = {
  // Enable standalone output for Docker
  output: 'standalone',
  
  webpack: (config, { dev, isServer }) => {
    // Only obfuscate in production client-side builds
    if (!dev && !isServer) {
      // Remove source maps in production (prevents readable debugging)
      config.devtool = false
      
      // Aggressive minification and obfuscation
      config.optimization = {
        ...config.optimization,
        minimize: true,
      }
      
      // Find the existing TerserPlugin and configure it for maximum obfuscation
      const existingMinimizers = config.optimization.minimizer || []
      config.optimization.minimizer = existingMinimizers.map(minimizer => {
        if (minimizer.constructor.name === 'TerserPlugin') {
          return new minimizer.constructor({
            ...minimizer.options,
            terserOptions: {
              compress: {
                drop_console: true, // Remove console.log statements
                drop_debugger: true, // Remove debugger statements
                pure_funcs: ['console.log'], // Remove console.log calls
                passes: 3, // Multiple passes for better compression
                unsafe: true, // Enable unsafe transformations
                unsafe_comps: true,
                unsafe_math: true,
                unsafe_proto: true,
              },
              mangle: {
                toplevel: true, // Mangle top-level variable names
                properties: {
                  regex: /^_/, // Mangle properties starting with _
                },
              },
              format: {
                comments: false, // Remove all comments
                ascii_only: true, // Escape Unicode characters
              },
            },
          })
        }
        return minimizer
      })
      
      // Enable aggressive chunk splitting
      config.optimization.splitChunks = {
        chunks: 'all',
        minSize: 0,
        maxSize: 30000, // Smaller chunks for better obfuscation
        cacheGroups: {
          default: {
            minChunks: 1,
            priority: -20,
            reuseExistingChunk: true,
          },
          vendor: {
            test: /[\\/]node_modules[\\/]/,
            name: 'vendors',
            priority: -10,
            chunks: 'all',
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
          {
            key: 'Content-Security-Policy',
            value: "default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline' 'unsafe-eval'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none';",
          },
        ],
      },
    ]
  },
}

module.exports = nextConfig
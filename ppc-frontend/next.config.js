/** @type {import('next').NextConfig} */
const nextConfig = {
  // Enable standalone output for Docker
  output: 'standalone',
  
  // Environment variables for source deterrent feature
  env: {
    ENABLE_SOURCE_DETERRENT: process.env.ENABLE_SOURCE_DETERRENT || 'true',
  },
  
  webpack: (config, { dev, isServer }) => {
    // Apply aggressive obfuscation in production client-side builds
    if (!dev && !isServer) {
      // Remove source maps completely
      config.devtool = false
      
      // Enhanced minification for obfuscation
      config.optimization = {
        ...config.optimization,
        minimize: true,
      }
      
      // Configure existing TerserPlugin for better obfuscation
      const existingMinimizers = config.optimization.minimizer || []
      config.optimization.minimizer = existingMinimizers.map(minimizer => {
        if (minimizer.constructor.name === 'TerserPlugin') {
          return new minimizer.constructor({
            ...minimizer.options,
            terserOptions: {
              compress: {
                drop_console: true, // Remove console logs in production
                drop_debugger: true, // Remove debugger statements
                passes: 3, // Multiple compression passes
                unsafe: true, // Enable more aggressive optimizations
                unsafe_comps: true,
                unsafe_math: true,
                conditionals: true,
                dead_code: true,
                evaluate: true,
                if_return: true,
                sequences: true,
                unused: true,
              },
              mangle: {
                toplevel: true, // Mangle top-level names
                properties: {
                  regex: /^_/, // Mangle properties starting with underscore
                },
              },
              format: {
                comments: false, // Remove all comments
                ascii_only: true, // Use ASCII only
                beautify: false, // No pretty formatting
              },
            },
          })
        }
        return minimizer
      })
      
      // Enable aggressive code splitting for obfuscation
      config.optimization.splitChunks = {
        chunks: 'all',
        minSize: 10000, // Smaller chunks
        maxSize: 50000, // Medium-sized chunks for better obfuscation
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
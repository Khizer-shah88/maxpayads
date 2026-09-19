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
      const TerserPlugin = require('terser-webpack-plugin')
      const CssMinimizerPlugin = require('css-minimizer-webpack-plugin')
      
      config.optimization.minimizer = [
        // Aggressive JavaScript obfuscation
        new TerserPlugin({
          terserOptions: {
            parse: {
              ecma: 8,
            },
            compress: {
              ecma: 5,
              drop_console: true, // Remove all console statements
              drop_debugger: true, // Remove debugger statements
              pure_funcs: ['console.log', 'console.info', 'console.warn'], // Remove specific console calls
              passes: 5, // Multiple passes for maximum compression
              unsafe: true, // Enable unsafe transformations
              unsafe_comps: true,
              unsafe_math: true,
              unsafe_proto: true,
              unsafe_regexp: true,
              unsafe_undefined: true,
              conditionals: true,
              dead_code: true,
              evaluate: true,
              if_return: true,
              join_vars: true,
              reduce_vars: true,
              sequences: true,
              side_effects: true,
              switches: true,
              top_retain: false,
              typeofs: false,
              booleans: true,
              collapse_vars: true,
              comparisons: true,
              computed_props: true,
            },
            mangle: {
              safari10: true,
              toplevel: true, // Mangle top-level variable names
              eval: true,
              properties: {
                regex: /^_|^[A-Z_]+$/, // Mangle more properties
              },
            },
            format: {
              ecma: 5,
              comments: false, // Remove ALL comments
              ascii_only: true, // Escape Unicode characters
              beautify: false,
              braces: false,
              indent_level: 0,
              keep_numbers: false,
              quote_style: 3, // Use shortest quotes
              semicolons: false,
            },
            nameCache: {},
          },
          extractComments: false, // Don't extract comments to separate files
        }),
        // Aggressive CSS minification
        new CssMinimizerPlugin({
          minimizerOptions: {
            preset: [
              'default',
              {
                discardComments: { removeAll: true }, // Remove all CSS comments
                normalizeWhitespace: true,
                colormin: true,
                convertValues: true,
                discardDuplicates: true,
                discardEmpty: true,
                discardOverridden: true,
                discardUnused: true,
                mergeIdents: true,
                mergeLonghand: true,
                mergeRules: true,
                minifyFontValues: true,
                minifyGradients: true,
                minifyParams: true,
                minifySelectors: true,
                normalizeCharset: true,
                normalizeDisplayValues: true,
                normalizePositions: true,
                normalizeRepeatStyle: true,
                normalizeString: true,
                normalizeTimingFunctions: true,
                normalizeUnicode: true,
                normalizeUrl: true,
                orderedValues: true,
                reduceIdents: true,
                reduceInitial: true,
                reduceTransforms: true,
                svgo: true,
                uniqueSelectors: true,
              },
            ],
          },
        }),
      ]
      
      // Enable aggressive chunk splitting for better obfuscation
      config.optimization.splitChunks = {
        chunks: 'all',
        minSize: 0,
        maxSize: 20000, // Very small chunks
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
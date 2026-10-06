/** @type {import('next').NextConfig} */
const nextConfig = {
  // Enable standalone output for Docker
  output: 'standalone',
  
  // Explicitly disable production source maps (security: prevent source inspection)
  productionBrowserSourceMaps: false,
  
  // NOTE: ENABLE_SOURCE_DETERRENT is deliberately NOT listed under `env`.
  // Next's `env` key inlines values via DefinePlugin at BUILD time, which
  // freezes the flag into the image and makes it unflippable without a
  // rebuild -- the opposite of a kill switch. Both consumers (the clean-shell
  // route handler and the /d/[slug] layout) render on the server per request,
  // so they read the real runtime env directly. Set it in docker-compose.
  
  webpack: (config, { dev, isServer }) => {
    // Enhanced production optimizations for source code protection
    if (!dev && !isServer) {
      // Remove source maps completely
      config.devtool = false
      
      // Enhanced minification and obfuscation
      if (config.optimization && config.optimization.minimizer) {
        config.optimization.minimizer.forEach((minimizer) => {
          if (minimizer.constructor.name === 'TerserPlugin') {
            // Enhance Terser options for better obfuscation
            minimizer.options = {
              ...minimizer.options,
              terserOptions: {
                ...minimizer.options.terserOptions,
                compress: {
                  ...minimizer.options.terserOptions?.compress,
                  drop_console: false, // Keep console for debugging, but minified
                  drop_debugger: true, // Remove debugger statements
                  pure_funcs: ['console.log'], // Remove console.log calls
                  passes: 2, // Multiple compression passes
                },
                mangle: {
                  ...minimizer.options.terserOptions?.mangle,
                  safari10: true, // Support older browsers
                  properties: {
                    // Mangle property names for additional obfuscation
                    regex: /^_/, // Only mangle properties starting with _
                  },
                },
                format: {
                  ...minimizer.options.terserOptions?.format,
                  comments: false, // Remove all comments
                  ascii_only: true, // Escape unicode characters
                },
              },
            }
          }
        })
      }
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
            // img-src/style-src/font-src open https: — admin-authored prelander
            // templates legitimately embed external favicons, styles and media.
            value: "default-src 'self'; style-src 'self' 'unsafe-inline' https:; script-src 'self' 'unsafe-inline' 'unsafe-eval'; img-src 'self' data: blob: https:; font-src 'self' data: https:; connect-src 'self' https:; frame-ancestors 'none'; worker-src 'self';",
          },
        ],
      },
    ]
  },
}

module.exports = nextConfig

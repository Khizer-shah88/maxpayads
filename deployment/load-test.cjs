// Dependency-free HTTP load check. Redirects are recorded, never followed.
// node deployment/load-test.cjs --url http://localhost/admin/auth --requests 5000 --concurrency 250
const http = require('node:http')
const https = require('node:https')
const fs = require('node:fs')
const { performance } = require('node:perf_hooks')

function options(args) {
  const result = {}
  for (let i = 0; i < args.length; i += 2) {
    if (!args[i].startsWith('--') || !args[i + 1]) throw new Error('Expected --option value')
    result[args[i].slice(2)] = args[i + 1]
  }
  return result
}

async function run(opts) {
  const url = new URL(opts.url)
  if (!['http:', 'https:'].includes(url.protocol)) throw new Error('Only HTTP(S) URLs are supported')
  const concurrency = Number(opts.concurrency || 25)
  const requests = Number(opts.requests || 1000)
  const timeout = Number(opts.timeout || 5000)
  const maxErrorRate = Number(opts['max-error-rate'] || 0.01)
  const maxP95 = Number(opts['max-p95-ms'] || 1000)
  const maxDuration = Number(opts['max-seconds'] || 60)
  if (!Number.isInteger(concurrency) || concurrency < 1 || concurrency > 5000 ||
      !Number.isInteger(requests) || requests < 1 || requests > 1000000 ||
      !Number.isFinite(timeout) || timeout <= 0 || !Number.isFinite(maxP95) || maxP95 <= 0 ||
      !Number.isFinite(maxErrorRate) || maxErrorRate < 0 || maxErrorRate > 1 ||
      !Number.isFinite(maxDuration) || maxDuration <= 0) throw new Error('Invalid limits')
  const transport = url.protocol === 'https:' ? https : http
  const agent = new transport.Agent({ keepAlive: true, maxSockets: concurrency, maxFreeSockets: concurrency })
  const headers = opts['headers-file'] ? JSON.parse(fs.readFileSync(opts['headers-file'], 'utf8')) : {}
  const latencies = [], statuses = {}, errors = {}
  let issued = 0, failures = 0, stopped = false
  const start = performance.now()

  function request() {
    return new Promise(resolve => {
      const began = performance.now()
      let finished = false
      const finish = (status, error) => {
        if (finished) return
        finished = true
        latencies.push(performance.now() - began)
        if (status) statuses[status] = (statuses[status] || 0) + 1
        if (error) errors[error] = (errors[error] || 0) + 1
        if (error || status < 200 || status >= 400) failures++
        // Stop escalating a failing target; already in-flight work finishes.
        if (latencies.length >= 100 && failures / latencies.length > maxErrorRate) stopped = true
        resolve()
      }
      const req = transport.get(url, { agent, headers }, res => {
        res.resume()
        res.on('end', () => finish(res.statusCode))
        res.on('error', err => finish(null, err.code || 'response-error'))
      })
      req.setTimeout(timeout, () => req.destroy(Object.assign(new Error('timeout'), { code: 'ETIMEDOUT' })))
      req.on('error', err => finish(null, err.code || 'request-error'))
    })
  }

  try {
    await Promise.all(Array.from({ length: Math.min(concurrency, requests) }, async () => {
      while (!stopped && issued < requests) {
        if ((performance.now() - start) / 1000 >= maxDuration) { stopped = true; break }
        issued++
        await request()
      }
    }))
  } finally { agent.destroy() }
  const seconds = (performance.now() - start) / 1000
  latencies.sort((a, b) => a - b)
  const percentile = p => Number(latencies[Math.min(latencies.length - 1, Math.ceil(latencies.length * p) - 1)].toFixed(2))
  const report = {
    measured_at: new Date().toISOString(), target: url.origin + url.pathname,
    concurrency, requested: requests, completed: latencies.length, seconds: Number(seconds.toFixed(3)),
    requests_per_second: Number((latencies.length / seconds).toFixed(1)),
    p50_ms: percentile(.5), p95_ms: percentile(.95), p99_ms: percentile(.99), statuses, errors,
    failures, error_rate: failures / latencies.length, stopped_early: stopped,
    passed: !stopped && latencies.length === requests && failures / latencies.length <= maxErrorRate && percentile(.95) <= maxP95,
    limits: { max_error_rate: maxErrorRate, max_p95_ms: maxP95 },
  }
  if (opts.output) fs.writeFileSync(opts.output, JSON.stringify(report, null, 2) + '\n')
  console.log(JSON.stringify(report, null, 2))
  return report
}

module.exports = { run, options }
if (require.main === module) {
  run(options(process.argv.slice(2))).then(report => { process.exitCode = report.passed ? 0 : 1 })
    .catch(error => { console.error(error.message); process.exitCode = 1 })
}

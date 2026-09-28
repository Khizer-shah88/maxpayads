// Run the standalone Next server on multiple cores without a process manager.
const cluster = require('node:cluster')
const path = require('node:path')

const workers = Number(process.env.NEXT_WORKERS || 2)
if (!Number.isInteger(workers) || workers < 1 || workers > 8) {
  throw new Error('NEXT_WORKERS must be an integer between 1 and 8')
}

// Explicit on Windows too, so local load tests distribute like production.
cluster.schedulingPolicy = cluster.SCHED_RR
cluster.setupPrimary({ exec: path.join(__dirname, 'server.js') })
let stopping = false
const pendingRestarts = new Set()
for (let i = 0; i < workers; i++) cluster.fork()
cluster.on('exit', (worker, code, signal) => {
  if (stopping) return
  console.error(`Next worker ${worker.process.pid} exited (${code || signal}); restarting in 1s`)
  const timer = setTimeout(() => {
    pendingRestarts.delete(timer)
    if (!stopping) cluster.fork()
  }, 1000)
  pendingRestarts.add(timer)
})
for (const signal of ['SIGTERM', 'SIGINT']) {
  process.on(signal, () => {
    if (stopping) return
    stopping = true
    for (const timer of pendingRestarts) clearTimeout(timer)
    for (const worker of Object.values(cluster.workers)) worker?.process.kill('SIGTERM')
  })
}

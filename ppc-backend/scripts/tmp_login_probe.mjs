/** Live publisher-login probe #2 — REAL-looking credentials. */
const BASE = 'https://vertexmonetize.com'

async function attempt(email, password) {
  const res = await fetch(`${BASE}/api/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password }),
  })
  return { email, status: res.status, body: (await res.text()).slice(0, 300) }
}

async function main() {
  // Non-existent gmail (valid format) — 401 expected with error body
  console.log(await attempt('probe.somewhere.99@gmail.com', 'SomePassw0rd!'))

  // Malformed email — 422 expected
  console.log(await attempt('no-at-sign', 'SomePassw0rd!'))

  // Empty password — 422 expected (min_length)
  console.log(await attempt('probe.somewhere.99@gmail.com', ''))
}
main()
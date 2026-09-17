export async function getJSON(path) {
  const r = await fetch(path)
  if (!r.ok) throw new Error(await r.text())
  return r.json()
}
export async function postJSON(path, body) {
  const r = await fetch(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
  if (!r.ok) throw new Error(await r.text())
  return r.json()
}

export const api = {
  readings: () => getJSON('/api/readings'),
  account: (id) => getJSON(`/api/accounts/${id}`),
  corrections: (readingId) =>
    getJSON(readingId ? `/api/corrections?reading_id=${readingId}` : '/api/corrections'),
  createCorrection: (body) => postJSON('/api/corrections', body),
  confirmCorrection: (id) => postJSON(`/api/corrections/${id}/confirm`),
  chain: (readingId) => getJSON(`/api/readings/${readingId}/chain`),
  rerun: (readingId) => postJSON(`/api/readings/${readingId}/rerun`),
}

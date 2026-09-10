async function request(path, options = {}) {
  const response = await fetch(`/api${path}`, options)
  const type = response.headers.get('content-type') || ''
  const body = type.includes('json') ? await response.json() : await response.text()
  if (!response.ok) throw new Error(body?.detail || body?.message || body || `请求失败 (${response.status})`)
  return body
}

const json = (method, body) => ({ method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })

export const api = {
  sessions: () => request('/sessions'),
  session: (id) => request(`/sessions/${id}`),
  createSession: (body = {}) => request('/sessions', json('POST', body)),
  patchSession: (id, body) => request(`/sessions/${id}`, json('PATCH', body)),
  deleteSession: (id, deleteEvidence = false) => request(`/sessions/${id}?delete_evidence=${deleteEvidence}`, { method: 'DELETE' }),
  upload: (id, files) => { const body = new FormData(); [...files].forEach((file) => body.append('files', file)); return request(`/sessions/${id}/upload`, { method: 'POST', body }) },
  analyze: (id) => request(`/sessions/${id}/analyze`, json('POST', {})),
  message: (id, body) => request(`/sessions/${id}/messages`, json('POST', body)),
  patchQuestion: (id, qid, body) => request(`/sessions/${id}/questions/${qid}`, json('PATCH', body)),
  reveal: (id, qid) => request(`/sessions/${id}/questions/${qid}/reveal`, json('POST', {})),
  retryQuestion: (id, qid, body) => request(`/sessions/${id}/questions/${qid}/retry`, json('POST', body)),
  deleteAttachment: (id, aid) => request(`/sessions/${id}/attachments/${aid}`, { method: 'DELETE' }),
  train: (id, body) => request(`/sessions/${id}/train`, json('POST', body)),
  answerQuiz: (id, quizid, body) => request(`/sessions/${id}/quiz/${quizid}/answer`, json('POST', body)),
  revealQuiz: (id, quizid) => request(`/sessions/${id}/quiz/${quizid}/reveal`, json('POST', {})),
  recheckQuiz: (id, quizid, text) => request(`/sessions/${id}/quiz/${quizid}/recheck`, json('POST', { text })),
  recheck: (id, qid, text) => request(`/sessions/${id}/questions/${qid}/recheck`, json('POST', { text })),
  reference: (id, text) => request(`/sessions/${id}/reference`, json('POST', { text })),
  referenceUpload: (id, files) => { const body = new FormData(); [...files].forEach((file) => body.append('files', file)); return request(`/sessions/${id}/reference-upload`, { method: 'POST', body }) },
  knowledge: () => request('/knowledge'),
  settings: () => request('/settings'),
  saveSettings: (body) => request('/settings', json('PUT', body)),
  testProfile: (profile_id) => request('/settings/test', json('POST', { profile_id })),
  demo: () => request('/demo', json('POST', {})),
}

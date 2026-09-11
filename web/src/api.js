import { parseSseFrames } from './domain.js'

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
  extract: (id) => request(`/sessions/${id}/extract`, json('POST', {})),
  extractStream: async (id, onQuestion) => {
    const response = await fetch(`/api/sessions/${id}/extract-stream`, { method: 'POST', headers: { Accept: 'text/event-stream' } })
    if (!response.ok) {
      const type = response.headers.get('content-type') || ''
      const body = type.includes('json') ? await response.json() : await response.text()
      throw new Error(body?.detail || body?.message || body || `请求失败 (${response.status})`)
    }
    if (!response.body) throw new Error('浏览器不支持流式响应，请重试')
    const reader = response.body.getReader(), decoder = new TextDecoder()
    let buffer = '', completed = false
    const receive = chunk => {
      buffer += decoder.decode(chunk, { stream: true })
      const parsed = parseSseFrames(buffer)
      buffer = parsed.rest
      for (const event of parsed.events) {
        if (event.type === 'question' && event.data.question) onQuestion?.(event.data.question)
        if (event.type === 'error') throw new Error(event.data.message || '图片识别未完成，请重试')
        if (event.type === 'done') completed = true
      }
    }
    while (!completed) {
      const { done, value } = await reader.read()
      if (done) break
      receive(value)
    }
    if (!completed) throw new Error('图片识别连接提前结束，请重试')
    return request(`/sessions/${id}`)
  },
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

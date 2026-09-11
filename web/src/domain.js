export function questionProgress(questions = []) {
  return questions.reduce((out, q) => {
    const answer = q.user_answer
    if (Array.isArray(answer) ? answer.length : String(answer ?? '').trim()) out.answered += 1
    if (q.analysis?.status === 'confirmed') out.confirmed += 1
    if (q.analysis?.correct === true) out.correct += 1
    if (q.analysis?.status === 'pending') out.pending += 1
    return out
  }, { total: questions.length, answered: 0, confirmed: 0, correct: 0, pending: 0 })
}

const MIN_CONVERSATION_HEIGHT = 156
const DEFAULT_CONVERSATION_HEIGHT = 240
const CONVERSATION_REST_HEIGHT = 240

export function clampConversationHeight(value, viewportHeight) {
  const height = Number(value)
  const viewport = Number(viewportHeight)
  const maximum = Math.max(MIN_CONVERSATION_HEIGHT, viewport - CONVERSATION_REST_HEIGHT)
  return Math.round(Math.min(Math.max(Number.isFinite(height) ? height : DEFAULT_CONVERSATION_HEIGHT, MIN_CONVERSATION_HEIGHT), maximum))
}

export function savedConversationHeight(storage, viewportHeight) {
  let saved
  try {
    saved = storage?.getItem?.('grid-learning.conversation-height')
  } catch {
    saved = null
  }
  return clampConversationHeight(saved ?? DEFAULT_CONVERSATION_HEIGHT, viewportHeight)
}

const ANALYSIS_STAGES = {
  recognizing: { active: true, title: '正在识别图片', detail: '正在提取题目、选项和你的作答。' },
  extracted: { active: true, title: '题目已识别，正在独立解题', detail: '已显示识别内容；答案与诊断将随后补齐。' },
  analyzing: { active: true, title: '正在独立解题与诊断', detail: '正在核对整页作答并整理简短反馈。' },
}

export const analysisStage = status => ANALYSIS_STAGES[status] || { active: false, title: '', detail: '' }
export const shouldResumeAnalysis = status => status === 'extracted'
export const analysisRunKey = session => `${session?.id || ''}:${(session?.questions || []).filter(q => !q.analysis).map(q => q.id).join(',')}`

export function parseSseFrames(buffer) {
  const events = []
  let rest = buffer
  while (rest.includes('\n\n')) {
    const end = rest.indexOf('\n\n')
    const frame = rest.slice(0, end)
    rest = rest.slice(end + 2)
    const type = frame.split('\n').find(line => line.startsWith('event:'))?.slice(6).trim()
    const data = frame.split('\n').filter(line => line.startsWith('data:')).map(line => line.slice(5).trim()).join('\n')
    if (data) events.push({ type, data: JSON.parse(data) })
  }
  return { events, rest }
}

const KNOWLEDGE_STATES = {
  '待验证': { key: 'weak', label: '需要关注' },
  '待独立验证': { key: 'learning', label: '待独立验证' },
  '本题答对': { key: 'learning', label: '本题答对' },
  '已有理解依据': { key: 'stable', label: '已有理解依据' },
  '独立验证通过': { key: 'stable', label: '独立验证通过' },
  '表现较稳定': { key: 'mastered', label: '表现较稳定' },
}

export function knowledgeState(state) {
  return KNOWLEDGE_STATES[state] || { key: 'unknown', label: state || '尚无记录' }
}

export function groupKnowledge(rows = []) {
  const subjects = new Map()
  rows.forEach((item) => {
    const subject = item.subject || '未分类'
    const chapter = item.chapter || '其他'
    if (!subjects.has(subject)) subjects.set(subject, new Map())
    const chapters = subjects.get(subject)
    if (!chapters.has(chapter)) chapters.set(chapter, [])
    chapters.get(chapter).push(item)
  })
  return [...subjects].map(([subject, chapters]) => ({
    subject,
    chapters: [...chapters].map(([chapter, items]) => ({ chapter, items })),
  }))
}

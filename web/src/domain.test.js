import { describe, expect, it } from 'vitest'
import { analysisRunKey, analysisStage, clampConversationHeight, groupKnowledge, knowledgeState, parseSseFrames, questionProgress, savedConversationHeight, shouldResumeAnalysis } from './domain.js'

describe('conversation height', () => {
  it('clamps the panel between its usable minimum and viewport maximum', () => {
    expect(clampConversationHeight(20, 900)).toBe(156)
    expect(clampConversationHeight(2000, 900)).toBe(660)
    expect(clampConversationHeight(660, 500)).toBe(260)
  })

  it('loads and clamps a saved panel height', () => {
    expect(savedConversationHeight({ getItem: () => '220' }, 900)).toBe(220)
  })

  it('falls back to the default height when storage cannot be read', () => {
    expect(savedConversationHeight({ getItem: () => { throw new Error('storage unavailable') } }, 900)).toBe(240)
  })
})

describe('questionProgress', () => {
  it('counts confirmed, pending and unanswered questions', () => {
    const questions = [
      { user_answer: 'A', analysis: { status: 'confirmed', correct: true } },
      { user_answer: ['A', 'C'], analysis: { status: 'pending' } },
      { user_answer: '', analysis: null },
    ]
    expect(questionProgress(questions)).toEqual({ total: 3, answered: 2, confirmed: 1, correct: 1, pending: 1 })
  })
})

describe('knowledgeState', () => {
  it('maps every backend state to a display key and falls back safely', () => {
    expect(knowledgeState('待验证')).toEqual({ key: 'weak', label: '需要关注' })
    expect(knowledgeState('表现较稳定').key).toBe('mastered')
    expect(knowledgeState('独立验证通过').key).toBe('stable')
    expect(knowledgeState('未知状态')).toEqual({ key: 'unknown', label: '未知状态' })
    expect(knowledgeState(undefined)).toEqual({ key: 'unknown', label: '尚无记录' })
  })
})

describe('groupKnowledge', () => {
  it('groups rows by subject and chapter while preserving unclassified values', () => {
    const rows = [
      { id: '1', subject: '继电保护', chapter: '距离保护' },
      { id: '2', subject: '继电保护', chapter: '距离保护' },
      { id: '3', subject: '', chapter: '' },
    ]
    expect(groupKnowledge(rows)).toEqual([
      { subject: '继电保护', chapters: [{ chapter: '距离保护', items: rows.slice(0, 2) }] },
      { subject: '未分类', chapters: [{ chapter: '其他', items: rows.slice(2) }] },
    ])
  })
})

describe('analysisStage', () => {
  it('distinguishes recognition from post-recognition analysis', () => {
    expect(analysisStage('recognizing')).toEqual({ active: true, title: '正在识别图片', detail: '正在提取题目、选项和你的作答。' })
    expect(analysisStage('extracted')).toEqual({ active: true, title: '题目已识别，正在独立解题', detail: '已显示识别内容；答案与诊断将随后补齐。' })
    expect(analysisStage('analyzing').title).toBe('正在独立解题与诊断')
  })
})

describe('shouldResumeAnalysis', () => {
  it('only resumes a persisted extracted session', () => {
    expect(shouldResumeAnalysis('extracted')).toBe(true)
    expect(shouldResumeAnalysis('recognizing')).toBe(false)
    expect(shouldResumeAnalysis('analyzing')).toBe(false)
    expect(shouldResumeAnalysis('ready')).toBe(false)
    expect(shouldResumeAnalysis('error')).toBe(false)
  })
})

describe('analysisRunKey', () => {
  it('changes when a later upload creates another recognized batch in the same session', () => {
    const first = analysisRunKey({ id: 'session', attachments: [{ id: 'one', extracted: true }], questions: [{ id: 'q1' }] })
    const second = analysisRunKey({ id: 'session', attachments: [{ id: 'one', extracted: true }, { id: 'two', extracted: true }], questions: [{ id: 'q1' }, { id: 'q2' }] })
    expect(first).not.toBe(second)
  })
})

describe('parseSseFrames', () => {
  it('keeps an incomplete frame buffered and returns each completed event', () => {
    const first = 'event: question\ndata: {"type":"question","question":{"id":"q1"}}\n\n'
    const partial = parseSseFrames(first.slice(0, 18))
    expect(partial.events).toEqual([])
    expect(partial.rest).toBe(first.slice(0, 18))

    const completed = parseSseFrames(partial.rest + first.slice(18) + 'event: done\ndata: {"type":"done"}\n\n')
    expect(completed).toEqual({
      events: [
        { type: 'question', data: { type: 'question', question: { id: 'q1' } } },
        { type: 'done', data: { type: 'done' } },
      ],
      rest: '',
    })
  })
})

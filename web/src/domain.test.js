import { describe, expect, it } from 'vitest'
import { groupKnowledge, questionProgress } from './domain.js'

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

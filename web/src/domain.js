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

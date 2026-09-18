import request from './request'
import type {
  PracticeResult,
  PracticeSession,
  PracticeProgress,
  PracticeCurrentQuestion,
  UnfinishedSession
} from '@/types'

export const startPractice = (data: {
  mode: string
  subject_id: string
  knowledge_ids?: string[]
  question_count: number
  difficulty?: string
}) => {
  return request.post<{
    session_id: string
    current_question: PracticeCurrentQuestion
    progress: PracticeProgress
  }>('/practice/start', data)
}

export const submitAnswer = (sessionId: string, questionId: string, userAnswer: any) => {
  return request.post<PracticeResult>('/practice/submit', {
    session_id: sessionId,
    question_id: questionId,
    user_answer: userAnswer
  })
}

export const navigateQuestion = (sessionId: string, direction: 'prev' | 'next') => {
  return request.get<PracticeCurrentQuestion>(`/practice/navigate/${sessionId}/${direction}`)
}

export const getSessionProgress = (sessionId: string) => {
  return request.get<PracticeProgress & {
    is_finished: boolean
    answers: Record<string, any>
  }>(`/practice/progress/${sessionId}`)
}

export const getUnfinishedSessions = () => {
  return request.get<{ items: UnfinishedSession[] }>('/practice/unfinished')
}

export const resumePractice = (sessionId: string) => {
  return request.get<{
    session: PracticeSession
    current_question: PracticeCurrentQuestion | null
    progress: PracticeProgress
  }>(`/practice/resume/${sessionId}`)
}

export const getPracticeSession = (sessionId: string) => {
  return request.get<{
    session: PracticeSession
    current_question: PracticeCurrentQuestion | null
    progress: PracticeProgress
  }>(`/practice/session/${sessionId}`)
}

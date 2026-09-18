import request from './request'
import type {
  Question,
  PracticeQuestion,
  PracticeResult,
  RecentSession,
  ResumeResult,
  NavigateResult
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
    current_question: PracticeQuestion
    progress: { current: number; total: number; answered?: number; correct: number; accuracy: number }
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
  return request.get<NavigateResult>(`/practice/navigate/${sessionId}/${direction}`)
}

export const getSessionProgress = (sessionId: string) => {
  return request.get<{
    current: number
    total: number
    answered?: number
    correct: number
    accuracy: number
    answers: Record<string, any>
    is_finished: boolean
  }>(`/practice/progress/${sessionId}`)
}

export const getRecentSession = () => {
  return request.get<RecentSession | null>('/practice/recent')
}

export const resumePractice = (sessionId: string) => {
  return request.get<ResumeResult>(`/practice/resume/${sessionId}`)
}

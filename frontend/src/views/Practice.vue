<template>
  <div class="practice-page">
    <van-nav-bar
      :title="modeName"
      left-arrow
      @click-left="handleBack"
    >
      <template #right>
        <span class="nav-progress">{{ navIndexText }} / {{ progress.total }}</span>
      </template>
    </van-nav-bar>

    <div class="progress-header">
      <div class="progress-bar">
        <div class="progress-fill" :style="{ width: progressPercent + '%' }"></div>
      </div>
      <div class="progress-stats">
        <span>已作答 {{ progress.answered }}/{{ progress.total }}</span>
        <span>正确率 {{ progress.accuracy }}%</span>
        <span>已对 {{ progress.correct }} 题</span>
      </div>
    </div>

    <div class="question-container" v-if="currentQuestion && !isFinished">
      <div class="question-header">
        <span class="question-type">{{ questionTypeLabel }}</span>
        <span class="difficulty-tag" :class="'difficulty-' + currentQuestion.difficulty">
          {{ difficultyLabel }}
        </span>
        <span v-if="alreadyAnswered" class="answered-tag">已作答</span>
      </div>

      <div class="question-content">
        {{ currentQuestion.content }}
      </div>

      <div v-if="!showResult" class="options-container">
        <div
          v-if="currentQuestion.type === 'fill_blank'"
          class="fill-blank-container"
        >
          <van-field
            v-model="fillAnswer"
            placeholder="请输入答案"
            :border="false"
            class="fill-input"
          />
        </div>

        <template v-else>
          <div
            v-for="option in currentQuestion.options"
            :key="option.key"
            class="option-item"
            :class="{ selected: isOptionSelected(option.key) }"
            @click="selectOption(option.key)"
          >
            <span class="option-key">{{ option.key }}</span>
            <span class="option-content">{{ option.content }}</span>
          </div>
        </template>
      </div>

      <div v-if="showResult" class="result-container">
        <div class="options-container">
          <div
            v-if="currentQuestion.type !== 'fill_blank'"
            v-for="option in currentQuestion.options"
            :key="option.key"
            class="option-item"
            :class="getOptionClass(option.key)"
          >
            <span class="option-key">{{ option.key }}</span>
            <span class="option-content">{{ option.content }}</span>
          </div>

          <div v-else class="fill-result">
            <div class="result-row">
              <span class="result-label">你的答案：</span>
              <span class="result-value" :class="result?.is_correct ? 'correct' : 'wrong'">
                {{ displayUserAnswer || '未作答' }}
              </span>
            </div>
            <div class="result-row">
              <span class="result-label">正确答案：</span>
              <span class="result-value correct">{{ result?.correct_answer }}</span>
            </div>
          </div>
        </div>

        <div class="result-badge" :class="result?.is_correct ? 'correct' : 'wrong'">
          {{ result?.is_correct ? '✓ 回答正确' : '✗ 回答错误' }}
        </div>

        <div v-if="result?.explanation" class="explanation-box">
          <div class="explanation-title">解析</div>
          <div class="explanation-content">{{ result.explanation }}</div>
        </div>
      </div>
    </div>

    <div v-if="isFinished" class="finished-container">
      <div class="score-circle">
        <div class="score-value">{{ progress.accuracy }}</div>
        <div class="score-label">正确率</div>
      </div>

      <div class="finished-stats">
        <div class="stat-item">
          <div class="stat-value">{{ progress.total }}</div>
          <div class="stat-label">总题数</div>
        </div>
        <div class="stat-item">
          <div class="stat-value correct">{{ progress.correct }}</div>
          <div class="stat-label">答对</div>
        </div>
        <div class="stat-item">
          <div class="stat-value wrong">{{ progress.total - progress.correct }}</div>
          <div class="stat-label">答错</div>
        </div>
      </div>

      <div class="finished-actions">
        <van-button type="primary" block round @click="goHome">
          返回首页
        </van-button>
        <van-button block round @click="goBackToSubject">
          继续练习
        </van-button>
      </div>
    </div>

    <div class="nav-bottom" v-if="!isFinished">
      <van-button
        plain
        size="large"
        :disabled="progress.current === 0"
        @click="goPrev"
      >
        上一题
      </van-button>

      <van-button
        v-if="showResult"
        plain
        type="warning"
        size="large"
        @click="reAnswer"
      >
        重新作答
      </van-button>

      <van-button
        type="primary"
        size="large"
        :loading="submitting"
        @click="handleSubmit"
      >
        {{ showResult ? '下一题' : (alreadyAnswered ? '更新答案' : '提交答案') }}
      </van-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { showConfirmDialog, showLoadingToast, closeToast } from 'vant'
import {
  startPractice,
  submitAnswer,
  navigateQuestion,
  resumePractice
} from '@/api/practice'
import type {
  PracticeCurrentQuestion,
  PracticeResult,
  PracticeAnswer
} from '@/types'

const route = useRoute()
const router = useRouter()

const mode = computed(() => route.params.mode as string)
const query = computed(() => route.query)

const sessionId = ref('')
const currentQuestion = ref<PracticeCurrentQuestion | null>(null)
const selectedAnswer = ref<any>(null)
const selectedAnswers = ref<string[]>([])
const fillAnswer = ref('')
const showResult = ref(false)
const result = ref<PracticeResult | null>(null)
const isFinished = ref(false)
const submitting = ref(false)
const alreadyAnswered = ref(false)

const progress = reactive({
  current: 0,
  answered: 0,
  total: 0,
  correct: 0,
  accuracy: 0
})

const modeName = computed(() => {
  const modeMap: Record<string, string> = {
    sequential: '顺序练习',
    random: '随机练习',
    error_practice: '错题重练'
  }
  return modeMap[mode.value] || '练习'
})

const progressPercent = computed(() => {
  if (!progress.total) return 0
  return Math.round(progress.answered / progress.total * 100)
})

const navIndexText = computed(() => {
  if (isFinished.value) return progress.total
  return Math.min(progress.current + 1, progress.total || 1)
})

const questionTypeLabel = computed(() => {
  const typeMap: Record<string, string> = {
    single_choice: '单选题',
    multiple_choice: '多选题',
    true_false: '判断题',
    fill_blank: '填空题'
  }
  return typeMap[currentQuestion.value?.type || ''] || '题目'
})

const difficultyLabel = computed(() => {
  const diffMap: Record<string, string> = {
    easy: '简单',
    medium: '中等',
    hard: '困难'
  }
  return diffMap[currentQuestion.value?.difficulty || ''] || ''
})

const isOptionSelected = (key: string) => {
  if (currentQuestion.value?.type === 'multiple_choice') {
    return selectedAnswers.value.includes(key)
  }
  return selectedAnswer.value === key
}

const getOptionClass = (key: string) => {
  const classes: string[] = []
  const correctAnswer = result.value?.correct_answer
  if (currentQuestion.value?.type === 'multiple_choice') {
    const correctList: string[] = Array.isArray(correctAnswer) ? correctAnswer : []
    const userList: string[] = Array.isArray(result.value?.user_answer)
      ? result.value.user_answer
      : (result.value?.user_answer ? [result.value.user_answer] : [])
    if (correctList.includes(key)) {
      classes.push('correct')
    } else if (userList.includes(key) && !result.value?.is_correct) {
      classes.push('wrong')
    }
  } else {
    if (key === correctAnswer) {
      classes.push('correct')
    } else if (isOptionSelectedByResult(key) && !result.value?.is_correct) {
      classes.push('wrong')
    }
  }
  return classes
}

const isOptionSelectedByResult = (key: string) => {
  const userAnswer = result.value?.user_answer
  if (Array.isArray(userAnswer)) {
    return userAnswer.includes(key)
  }
  return userAnswer === key
}

const displayUserAnswer = computed(() => {
  const userAnswer = result.value?.user_answer
  if (Array.isArray(userAnswer)) {
    return userAnswer.join('、')
  }
  return userAnswer
})

const selectOption = (key: string) => {
  if (showResult.value) return

  if (currentQuestion.value?.type === 'multiple_choice') {
    const index = selectedAnswers.value.indexOf(key)
    if (index > -1) {
      selectedAnswers.value.splice(index, 1)
    } else {
      selectedAnswers.value.push(key)
    }
    selectedAnswers.value.sort()
  } else {
    selectedAnswer.value = key
  }
}

const getAnswerToSubmit = () => {
  if (currentQuestion.value?.type === 'fill_blank') {
    return fillAnswer.value
  } else if (currentQuestion.value?.type === 'multiple_choice') {
    return selectedAnswers.value
  }
  return selectedAnswer.value
}

const hasAnswer = () => {
  const answer = getAnswerToSubmit()
  if (Array.isArray(answer)) {
    return answer.length > 0
  }
  return answer !== null && answer !== undefined && answer !== ''
}

const applyProgress = (p: {
  current: number
  answered?: number
  total: number
  correct: number
  accuracy: number
}) => {
  progress.current = p.current
  progress.answered = p.answered ?? 0
  progress.total = p.total
  progress.correct = p.correct
  progress.accuracy = p.accuracy
}

const loadQuestion = (question: PracticeCurrentQuestion, answeredCount?: number) => {
  currentQuestion.value = question
  progress.current = question.index
  if (typeof answeredCount === 'number') {
    progress.answered = answeredCount
  }

  if (question.saved_answer) {
    restoreSavedAnswer(question.saved_answer, question.correct_answer, question.is_correct)
  } else {
    resetAnswerState()
  }
}

const restoreSavedAnswer = (
  saved: PracticeAnswer,
  correctAnswer?: any,
  savedIsCorrect?: boolean
) => {
  const userAnswer = saved.user_answer
  if (currentQuestion.value?.type === 'multiple_choice') {
    selectedAnswers.value = Array.isArray(userAnswer) ? [...userAnswer] : []
    selectedAnswer.value = null
  } else if (currentQuestion.value?.type === 'fill_blank') {
    fillAnswer.value = userAnswer ?? ''
    selectedAnswer.value = null
  } else {
    selectedAnswer.value = userAnswer
    selectedAnswers.value = []
  }

  alreadyAnswered.value = true
  showResult.value = true
  result.value = {
    question_id: currentQuestion.value!.id,
    user_answer: userAnswer,
    is_correct: savedIsCorrect ?? saved.is_correct,
    correct_answer: correctAnswer,
    explanation: currentQuestion.value?.explanation,
    is_new_answer: false,
    progress: { ...progress },
    is_finished: false
  }
}

const resetAnswerState = () => {
  showResult.value = false
  result.value = null
  alreadyAnswered.value = false
  selectedAnswer.value = null
  selectedAnswers.value = []
  fillAnswer.value = ''
}

const handleSubmit = async () => {
  if (!showResult.value) {
    if (!hasAnswer()) {
      return
    }

    submitting.value = true
    try {
      const answer = getAnswerToSubmit()
      const submitResult = await submitAnswer(
        sessionId.value,
        currentQuestion.value!.id,
        answer
      )
      result.value = submitResult

      applyProgress(submitResult.progress)
      showResult.value = true
      alreadyAnswered.value = true
      isFinished.value = submitResult.is_finished
    } catch (error) {
      console.error(error)
    } finally {
      submitting.value = false
    }
  } else {
    await goNext()
  }
}

const reAnswer = () => {
  showResult.value = false
  result.value = null
}

const goNext = async () => {
  if (isFinished.value) {
    return
  }

  showLoadingToast({ message: '加载中...', duration: 0 })
  try {
    const question = await navigateQuestion(sessionId.value, 'next')
    if (question) {
      loadQuestion(question)
    }
  } catch (error) {
    console.error(error)
  } finally {
    closeToast()
  }
}

const goPrev = async () => {
  showLoadingToast({ message: '加载中...', duration: 0 })
  try {
    const question = await navigateQuestion(sessionId.value, 'prev')
    if (question) {
      loadQuestion(question)
    }
  } catch (error) {
    console.error(error)
  } finally {
    closeToast()
  }
}

const handleBack = () => {
  showConfirmDialog({
    title: '确认退出',
    message: '练习进度已保存，下次可从首页继续，确定要退出吗？'
  })
    .then(() => {
      goBackToSubject()
    })
    .catch(() => {})
}

const goBackToSubject = () => {
  if (query.value.subjectId) {
    router.push(`/knowledge/${query.value.subjectId}`)
  } else if (query.value.sessionId) {
    // 从首页续练进入：返回首页（未完成会话仍展示在首页）
    router.push('/')
  } else {
    router.push('/subjects')
  }
}

const goHome = () => {
  router.push('/')
}

const initPractice = async () => {
  showLoadingToast({ message: '加载中...', duration: 0 })
  try {
    // 断点续练：带 sessionId 进入时回到退出时尚未提交的题目，保留此前作答
    if (query.value.sessionId) {
      const resumeResult = await resumePractice(query.value.sessionId as string)
      sessionId.value = resumeResult.session.id
      applyProgress(resumeResult.progress)
      isFinished.value = !!resumeResult.session.is_finished
      if (resumeResult.current_question) {
        loadQuestion(resumeResult.current_question, resumeResult.progress.answered)
      }
      return
    }

    const knowledgeIds = query.value.knowledgeIds ? [query.value.knowledgeIds as string] : undefined

    const startResult = await startPractice({
      mode: mode.value,
      subject_id: query.value.subjectId as string,
      knowledge_ids: knowledgeIds,
      question_count: parseInt(query.value.count as string) || 20,
      difficulty: (query.value.difficulty as string) || undefined
    })

    sessionId.value = startResult.session_id
    if (startResult.current_question) {
      loadQuestion(startResult.current_question, 0)
    }
    progress.total = startResult.progress.total
    progress.answered = 0
    progress.correct = 0
    progress.accuracy = 0
  } catch (error) {
    console.error(error)
  } finally {
    closeToast()
  }
}

onMounted(() => {
  initPractice()
})
</script>

<style scoped>
.practice-page {
  min-height: 100vh;
  background: linear-gradient(180deg, #e8f3ff 0%, #f5f7fa 100%);
  padding-bottom: 80px;
}

.nav-progress {
  font-size: 14px;
  color: white;
  opacity: 0.9;
}

.progress-header {
  padding: 12px 16px;
  background: white;
}

.progress-stats {
  display: flex;
  justify-content: space-between;
  margin-top: 8px;
  font-size: 12px;
  color: #64748b;
}

.question-container {
  padding: 16px;
}

.question-header {
  display: flex;
  gap: 8px;
  margin-bottom: 16px;
  align-items: center;
}

.question-type {
  padding: 4px 10px;
  background: #eff6ff;
  color: #1d4ed8;
  border-radius: 6px;
  font-size: 12px;
  font-weight: 500;
}

.answered-tag {
  padding: 4px 10px;
  background: #fef3c7;
  color: #b45309;
  border-radius: 6px;
  font-size: 12px;
  font-weight: 500;
}

.question-content {
  font-size: 16px;
  line-height: 1.8;
  color: #1a1a2e;
  margin-bottom: 24px;
  white-space: pre-wrap;
}

.options-container {
  margin-bottom: 20px;
}

.option-item {
  display: flex;
  align-items: flex-start;
  padding: 14px 16px;
  background: white;
  border-radius: 12px;
  margin-bottom: 10px;
  border: 1px solid #e2e8f0;
  cursor: pointer;
}

.option-item.selected {
  border-color: #3b82f6;
  background: #eff6ff;
}

.option-item.correct {
  border-color: #22c55e;
  background: #f0fdf4;
}

.option-item.wrong {
  border-color: #ef4444;
  background: #fef2f2;
}

.option-key {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  background: #f1f5f9;
  color: #475569;
  text-align: center;
  line-height: 28px;
  font-weight: 600;
  margin-right: 12px;
  flex-shrink: 0;
}

.selected .option-key {
  background: #3b82f6;
  color: white;
}

.correct .option-key {
  background: #22c55e;
  color: white;
}

.wrong .option-key {
  background: #ef4444;
  color: white;
}

.option-content {
  flex: 1;
  font-size: 15px;
  color: #334155;
  line-height: 1.6;
}

.fill-blank-container {
  background: white;
  border-radius: 12px;
  padding: 16px;
}

.fill-input {
  font-size: 16px;
}

.result-badge {
  text-align: center;
  padding: 12px;
  border-radius: 10px;
  font-weight: 600;
  margin-top: 16px;
}

.result-badge.correct {
  background: #f0fdf4;
  color: #15803d;
}

.result-badge.wrong {
  background: #fef2f2;
  color: #b91c1c;
}

.fill-result {
  background: white;
  border-radius: 12px;
  padding: 16px;
}

.result-row {
  display: flex;
  align-items: center;
  margin-bottom: 12px;
}

.result-row:last-child {
  margin-bottom: 0;
}

.result-label {
  font-size: 14px;
  color: #64748b;
  margin-right: 8px;
}

.result-value {
  font-size: 15px;
  font-weight: 500;
}

.result-value.correct {
  color: #15803d;
}

.result-value.wrong {
  color: #b91c1c;
}

.explanation-box {
  background: #f0f9ff;
  border-radius: 12px;
  padding: 16px;
  margin-top: 16px;
  border-left: 4px solid #3b82f6;
}

.explanation-title {
  font-size: 14px;
  font-weight: 600;
  color: #1d4ed8;
  margin-bottom: 8px;
}

.explanation-content {
  font-size: 14px;
  line-height: 1.6;
  color: #475569;
}

.finished-container {
  padding: 40px 20px;
  text-align: center;
}

.finished-stats {
  display: flex;
  justify-content: center;
  gap: 40px;
  margin-top: 32px;
}

.finished-stats .stat-value.correct {
  color: #22c55e;
}

.finished-stats .stat-value.wrong {
  color: #ef4444;
}

.finished-actions {
  margin-top: 40px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.nav-bottom {
  position: fixed;
  bottom: 0;
  left: 0;
  right: 0;
  display: flex;
  gap: 10px;
  padding: 10px 16px calc(10px + env(safe-area-inset-bottom));
  background: white;
  box-shadow: 0 -2px 10px rgba(0, 0, 0, 0.05);
}

.nav-bottom .van-button {
  flex: 1;
}
</style>

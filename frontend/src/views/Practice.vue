<template>
  <div class="practice-page">
    <van-nav-bar
      :title="modeName"
      left-arrow
      @click-left="handleBack"
    >
      <template #right>
        <span class="nav-progress">{{ progress.current + 1 }} / {{ progress.total }}</span>
      </template>
    </van-nav-bar>

    <div class="progress-header">
      <div class="progress-bar">
        <div class="progress-fill" :style="{ width: progressPercent + '%' }"></div>
      </div>
      <div class="progress-stats">
        <span>正确率 {{ progress.accuracy }}%</span>
        <span>已答 {{ progress.answered ?? progress.current }} / {{ progress.total }}</span>
      </div>
    </div>

    <div class="question-container" v-if="currentQuestion && !isFinished">
      <div class="question-header">
        <span class="question-type">{{ questionTypeLabel }}</span>
        <span class="difficulty-tag" :class="'difficulty-' + currentQuestion.difficulty">
          {{ difficultyLabel }}
        </span>
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
                {{ fillAnswer || '未作答' }}
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
        {{ showResult ? '下一题' : '提交答案' }}
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
  PracticeQuestion,
  PracticeResult,
  NavigateResult,
  ResumeResult
} from '@/types'

const route = useRoute()
const router = useRouter()

const mode = computed(() => route.params.mode as string)
const query = computed(() => route.query)

const sessionId = ref('')
const currentQuestion = ref<PracticeQuestion | null>(null)
const selectedAnswer = ref<any>(null)
const selectedAnswers = ref<string[]>([])
const fillAnswer = ref('')
const showResult = ref(false)
const result = ref<PracticeResult | null>(null)
const isFinished = ref(false)
const submitting = ref(false)

const progress = reactive({
  current: 0,
  total: 0,
  answered: 0,
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
  return Math.round(((progress.current + 1) / progress.total) * 100)
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

const isCorrectOption = (key: string) => {
  const correct = result.value?.correct_answer
  if (Array.isArray(correct)) {
    return correct.map((a) => String(a).toUpperCase()).includes(String(key).toUpperCase())
  }
  return String(correct ?? '').toUpperCase() === String(key).toUpperCase()
}

const isWrongSelected = (key: string) => {
  if (!result.value || result.value.is_correct) return false
  if (currentQuestion.value?.type === 'multiple_choice') {
    return selectedAnswers.value.includes(key)
  }
  return selectedAnswer.value === key
}

const getOptionClass = (key: string) => {
  const classes: string[] = []
  if (isCorrectOption(key)) {
    classes.push('correct')
  } else if (isWrongSelected(key)) {
    classes.push('wrong')
  }
  return classes
}

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
  if (currentQuestion.value?.type === 'multiple_choice') {
    return Array.isArray(answer) && answer.length > 0
  }
  if (currentQuestion.value?.type === 'fill_blank') {
    return String(answer ?? '').trim() !== ''
  }
  return answer !== null && answer !== undefined && answer !== ''
}

const syncProgress = (p: NavigateResult['progress'] | ResumeResult['progress'] | PracticeResult['progress']) => {
  progress.current = p.current
  progress.total = p.total
  progress.answered = p.answered ?? p.current
  progress.correct = p.correct
  progress.accuracy = p.accuracy
}

// 进入某题：未作答则清空，已作答则保留此前答案并展示上次判题结果
const applyQuestion = (question: PracticeQuestion, p?: NavigateResult['progress'] | ResumeResult['progress']) => {
  currentQuestion.value = question
  selectedAnswer.value = null
  selectedAnswers.value = []
  fillAnswer.value = ''
  result.value = null
  showResult.value = false

  if (question.answered) {
    const userAnswer = question.user_answer
    if (question.type === 'multiple_choice') {
      selectedAnswers.value = Array.isArray(userAnswer) ? [...userAnswer] : []
    } else if (question.type === 'fill_blank') {
      fillAnswer.value = userAnswer ?? ''
    } else {
      selectedAnswer.value = userAnswer
    }
    showResult.value = true
    result.value = {
      question_id: question.id,
      is_correct: !!question.is_correct,
      correct_answer: question.correct_answer,
      explanation: question.explanation,
      progress: p
        ? {
            current: p.current,
            total: p.total,
            answered: p.answered,
            correct: p.correct,
            accuracy: p.accuracy
          }
        : { ...progress },
      is_finished: isFinished.value
    }
  }
}

const handleSubmit = async () => {
  if (!showResult.value) {
    if (!hasAnswer()) {
      return
    }

    submitting.value = true
    try {
      const answer = getAnswerToSubmit()
      const submitResult = await submitAnswer(sessionId.value, currentQuestion.value!.id, answer)
      result.value = submitResult

      syncProgress(submitResult.progress)
      progress.answered = submitResult.progress.answered ?? progress.answered

      showResult.value = true
      isFinished.value = submitResult.is_finished
    } catch (error) {
      console.error(error)
    } finally {
      submitting.value = false
    }
  } else {
    if (isFinished.value) {
      return
    }

    showLoadingToast({ message: '加载中...', duration: 0 })
    try {
      const nav = await navigateQuestion(sessionId.value, 'next')
      if (nav?.question) {
        syncProgress(nav.progress)
        isFinished.value = nav.is_finished
        applyQuestion(nav.question, nav.progress)
      }
    } catch (error) {
      console.error(error)
    } finally {
      closeToast()
    }
  }
}

// 已作答的题目允许用新答案重新提交：只更新答案，统计不重复累计
const reAnswer = () => {
  showResult.value = false
  result.value = null
}

const goPrev = async () => {
  showLoadingToast({ message: '加载中...', duration: 0 })
  try {
    const nav = await navigateQuestion(sessionId.value, 'prev')
    if (nav?.question) {
      syncProgress(nav.progress)
      isFinished.value = nav.is_finished
      applyQuestion(nav.question, nav.progress)
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
    message: '练习进度已保存，可在首页继续练习，确定要退出吗？'
  })
    .then(() => {
      goBackToSubject()
    })
    .catch(() => {})
}

const goBackToSubject = () => {
  if (query.value.subjectId) {
    router.push(`/knowledge/${query.value.subjectId}`)
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
    // 断点续练：回到退出时尚未提交的题目，并保留此前作答
    if (query.value.sessionId) {
      const resumeResult = await resumePractice(query.value.sessionId as string)
      sessionId.value = resumeResult.session.id
      syncProgress(resumeResult.progress)
      isFinished.value = resumeResult.is_finished
      if (resumeResult.current_question) {
        applyQuestion(resumeResult.current_question, resumeResult.progress)
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
    progress.total = startResult.progress.total
    syncProgress(startResult.progress)
    applyQuestion(startResult.current_question, startResult.progress)
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
}

.question-type {
  padding: 4px 10px;
  background: #eff6ff;
  color: #1d4ed8;
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
  padding: 10px 16px;
  background: white;
  box-shadow: 0 -2px 10px rgba(0, 0, 0, 0.05);
}
</style>

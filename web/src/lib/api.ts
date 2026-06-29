export type CompilerMode = 'gemma_vision' | 'ocr_assisted'
export type StoryBeatKind = 'text' | 'illustration'
export type CaregiverCuePurpose = 'prediction' | 'emotion' | 'vocabulary' | 'engagement'
export type ReaderMode = 'read_page' | 'explore_word'

export interface StoryBeat {
  beat_id: string
  kind: StoryBeatKind
  narration: string
  source_text: string | null
  layout_region: string | null
  confidence: number
}

export interface CaregiverCue {
  cue_id: string
  after_beat_id: string
  cue: string
  purpose: CaregiverCuePurpose
}

export interface StoryDiagnostics {
  mode: CompilerMode
  layout_notes: string
  ocr_used: boolean
  warnings: string[]
}

export interface StoryCompilation {
  title: string | null
  spoken_script: string
  beats: StoryBeat[]
  caregiver_cues: CaregiverCue[]
  diagnostics: StoryDiagnostics
}

export interface ReadPayload {
  request_id: string
  text: string
  audio_url: string
  mime_type: string
  expires_at: string
  story: StoryCompilation | null
}

interface ReadJobAcceptedPayload {
  request_id: string
  status: 'queued' | 'processing' | 'completed' | 'failed'
}

export interface ReadJobProgressPayload {
  request_id: string
  status: 'queued' | 'processing' | 'completed' | 'failed'
  stage: 'queued' | 'story_compile' | 'ocr' | 'tts' | 'completed' | 'failed'
  text: string | null
  audio_url: string | null
  mime_type: string | null
  expires_at: string | null
  paragraphs_total: number
  paragraphs_completed: number
  error: string | null
  story: StoryCompilation | null
  timings?: Record<string, number>
}

export interface WordExplorerDiagnostics {
  mode: 'gemma_vision'
  pointing_evidence: string
  layout_region: string | null
  warnings: string[]
}

export interface WordExplorerResult {
  selected_word: string
  normalized_word: string | null
  language: string | null
  part_of_speech: string | null
  pronunciation_hint: string | null
  kid_explanation: string
  example_sentence: string | null
  page_context: string | null
  spoken_script: string
  confidence: number
  diagnostics: WordExplorerDiagnostics
}

export interface WordPayload {
  request_id: string
  text: string
  audio_url: string
  mime_type: string
  expires_at: string
  word: WordExplorerResult
}

interface WordJobAcceptedPayload {
  request_id: string
  status: 'queued' | 'processing' | 'completed' | 'failed'
}

export interface WordJobProgressPayload {
  request_id: string
  status: 'queued' | 'processing' | 'completed' | 'failed'
  stage: 'queued' | 'word_detect' | 'tts' | 'completed' | 'failed'
  word: WordExplorerResult | null
  text: string | null
  audio_url: string | null
  mime_type: string | null
  expires_at: string | null
  paragraphs_total: number
  paragraphs_completed: number
  error: string | null
  timings?: Record<string, number>
}

const JOB_POLL_INTERVAL_MS = 1500

export async function submitReadRequest(
  blob: Blob,
  langHint = 'bilingual',
  compilerMode: CompilerMode = 'gemma_vision',
  onProgress?: (progress: ReadJobProgressPayload) => void,
): Promise<ReadPayload> {
  const formData = new FormData()
  formData.append('image', blob, 'page.jpg')
  formData.append('lang_hint', langHint)
  formData.append('compiler_mode', compilerMode)

  const response = await fetch('/api/read/jobs', {
    method: 'POST',
    body: formData,
  })

  if (!response.ok) {
    throw new Error(await getErrorMessage(response, 'Upload failed.'))
  }

  const payload = (await response.json()) as ReadJobAcceptedPayload
  return waitForReadJob(payload.request_id, onProgress)
}

export async function submitWordRequest(
  blob: Blob,
  langHint = 'auto',
  onProgress?: (progress: WordJobProgressPayload) => void,
): Promise<WordPayload> {
  const formData = new FormData()
  formData.append('image', blob, 'page.jpg')
  formData.append('lang_hint', langHint)

  const response = await fetch('/api/word/jobs', {
    method: 'POST',
    body: formData,
  })

  if (!response.ok) {
    throw new Error(await getErrorMessage(response, 'Word lookup failed.'))
  }

  const payload = (await response.json()) as WordJobAcceptedPayload
  return waitForWordJob(payload.request_id, onProgress)
}

async function waitForReadJob(
  requestId: string,
  onProgress?: (progress: ReadJobProgressPayload) => void,
): Promise<ReadPayload> {
  while (true) {
    const response = await fetch(`/api/read/jobs/${requestId}`)
    if (!response.ok) {
      throw new Error(await getErrorMessage(response, 'Read job failed.'))
    }

    const payload = (await response.json()) as ReadJobProgressPayload
    onProgress?.(payload)

    if (payload.status === 'completed') {
      if (!payload.text || !payload.audio_url || !payload.mime_type || !payload.expires_at) {
        throw new Error('Read job completed without returning audio metadata.')
      }
      return {
        request_id: payload.request_id,
        text: payload.text,
        audio_url: payload.audio_url,
        mime_type: payload.mime_type,
        expires_at: payload.expires_at,
        story: payload.story,
      }
    }

    if (payload.status === 'failed') {
      throw new Error(payload.error || 'Read job failed.')
    }

    await delay(JOB_POLL_INTERVAL_MS)
  }
}

async function waitForWordJob(
  requestId: string,
  onProgress?: (progress: WordJobProgressPayload) => void,
): Promise<WordPayload> {
  while (true) {
    const response = await fetch(`/api/word/jobs/${requestId}`)
    if (!response.ok) {
      throw new Error(await getErrorMessage(response, 'Word lookup failed.'))
    }

    const payload = (await response.json()) as WordJobProgressPayload
    onProgress?.(payload)

    if (payload.status === 'completed') {
      if (!payload.text || !payload.audio_url || !payload.mime_type || !payload.expires_at || !payload.word) {
        throw new Error('Word job completed without returning audio metadata.')
      }
      return {
        request_id: payload.request_id,
        text: payload.text,
        audio_url: payload.audio_url,
        mime_type: payload.mime_type,
        expires_at: payload.expires_at,
        word: payload.word,
      }
    }

    if (payload.status === 'failed') {
      throw new Error(payload.error || 'Word lookup failed.')
    }

    await delay(JOB_POLL_INTERVAL_MS)
  }
}

async function getErrorMessage(response: Response, fallback: string): Promise<string> {
  try {
    const payload = await response.json()
    if (typeof payload.detail === 'string') {
      return payload.detail
    }
    if (typeof payload.error === 'string') {
      return payload.error
    }
  } catch {
    return `${fallback} (${response.status})`
  }
  return fallback
}

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => {
    window.setTimeout(resolve, ms)
  })
}

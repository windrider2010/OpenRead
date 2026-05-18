<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref } from 'vue'

import { submitReadRequest, type ReadJobProgressPayload, type StoryCompilation } from './lib/api'
import { captureVideoFrame } from './lib/capture'
import { attemptPlayback } from './lib/playback'

const videoRef = ref<HTMLVideoElement | null>(null)
const audioRef = ref<HTMLAudioElement | null>(null)
const activeStream = ref<MediaStream | null>(null)

const cameraReady = ref(false)
const requestingCamera = ref(false)
const isSubmitting = ref(false)
const needsManualPlay = ref(false)

const statusMessage = ref('Ready for a story page.')
const errorMessage = ref('')
const recognizedText = ref('')
const audioUrl = ref('')
const story = ref<StoryCompilation | null>(null)
const paragraphsTotal = ref(0)
const paragraphsCompleted = ref(0)

const mainButtonLabel = computed(() => {
  if (requestingCamera.value) {
    return 'Opening camera'
  }
  if (isSubmitting.value) {
    return 'Reading page'
  }
  if (!cameraReady.value) {
    return 'Open Camera'
  }
  return 'Take Photo'
})

const spokenText = computed(() => story.value?.spoken_script || recognizedText.value)
const storyTitle = computed(() => story.value?.title || 'Read Aloud')
const storyBeats = computed(() => story.value?.beats ?? [])
const caregiverCues = computed(() => story.value?.caregiver_cues ?? [])
const hasResult = computed(() => Boolean(spokenText.value || audioUrl.value || story.value))
const actionDisabled = computed(() => requestingCamera.value || isSubmitting.value)

const progressLabel = computed(() => {
  if (isSubmitting.value && paragraphsTotal.value > 0) {
    return `${paragraphsCompleted.value}/${paragraphsTotal.value} audio parts`
  }
  if (audioUrl.value) {
    return 'Audio ready'
  }
  if (isSubmitting.value) {
    return 'Understanding page'
  }
  return cameraReady.value ? 'Camera ready' : 'OpenRead'
})

async function handleMainAction() {
  if (!cameraReady.value) {
    await startCamera()
    return
  }
  await captureAndRead()
}

async function startCamera() {
  errorMessage.value = ''
  needsManualPlay.value = false

  if (!navigator.mediaDevices?.getUserMedia) {
    errorMessage.value = 'This browser does not expose camera access.'
    statusMessage.value = 'Camera unavailable.'
    return
  }

  requestingCamera.value = true
  statusMessage.value = 'Opening camera...'

  try {
    stopStream()
    const stream = await navigator.mediaDevices.getUserMedia({
      audio: false,
      video: {
        facingMode: { ideal: 'environment' },
        width: { ideal: 1280 },
        height: { ideal: 1920 },
      },
    })
    activeStream.value = stream

    if (videoRef.value) {
      videoRef.value.srcObject = stream
      await videoRef.value.play().catch(() => undefined)
    }

    cameraReady.value = true
    statusMessage.value = 'Place the page in the frame.'
  } catch (error) {
    const name = error instanceof DOMException ? error.name : ''
    errorMessage.value =
      name === 'NotAllowedError'
        ? 'Camera permission was denied.'
        : 'Unable to open the camera. Please try again.'
    statusMessage.value = 'Camera blocked.'
  } finally {
    requestingCamera.value = false
  }
}

async function captureAndRead() {
  const video = videoRef.value
  if (!video) {
    errorMessage.value = 'Camera preview is not ready.'
    return
  }

  errorMessage.value = ''
  recognizedText.value = ''
  audioUrl.value = ''
  story.value = null
  needsManualPlay.value = false
  paragraphsTotal.value = 0
  paragraphsCompleted.value = 0
  isSubmitting.value = true
  statusMessage.value = 'Understanding the page...'

  try {
    const image = await captureVideoFrame(video)
    const result = await submitReadRequest(image, 'bilingual', 'gemma_vision', applyReadProgress)
    recognizedText.value = result.text
    story.value = result.story
    audioUrl.value = result.audio_url
    statusMessage.value = 'Audio is ready.'

    await nextTick()
    if (audioRef.value) {
      needsManualPlay.value = await attemptPlayback(audioRef.value)
    }
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : 'Read failed.'
    statusMessage.value = 'Read failed.'
  } finally {
    isSubmitting.value = false
  }
}

function applyReadProgress(progress: ReadJobProgressPayload) {
  paragraphsTotal.value = progress.paragraphs_total
  paragraphsCompleted.value = progress.paragraphs_completed

  if (progress.text) {
    recognizedText.value = progress.text
  }
  if (progress.story) {
    story.value = progress.story
  }

  if (progress.stage === 'story_compile') {
    statusMessage.value = 'Finding the story order...'
    return
  }
  if (progress.stage === 'ocr') {
    statusMessage.value = 'Checking printed words...'
    return
  }
  if (progress.stage === 'tts') {
    statusMessage.value = 'Building the read-aloud voice...'
    return
  }
  if (progress.stage === 'completed') {
    statusMessage.value = 'Audio is ready.'
    return
  }
  if (progress.stage === 'failed') {
    statusMessage.value = 'Read failed.'
    errorMessage.value = progress.error || 'Read failed.'
    return
  }
  statusMessage.value = 'Waiting for the reader...'
}

async function playAudio() {
  if (!audioRef.value) {
    return
  }
  needsManualPlay.value = await attemptPlayback(audioRef.value)
}

function pageMomentLabel(kind: string) {
  return kind === 'illustration' ? 'Picture' : 'Words'
}

function stopStream() {
  activeStream.value?.getTracks().forEach((track) => track.stop())
  activeStream.value = null
  cameraReady.value = false
}

onBeforeUnmount(stopStream)
</script>

<template>
  <main class="reader-shell">
    <section class="reader-screen" aria-label="OpenRead">
      <header class="reader-header">
        <h1 class="brand-mark">OPENREAD</h1>
        <p class="reader-subheader">When you want to read, but the moment gets in the way.</p>
      </header>

      <section class="camera-window" :class="{ live: cameraReady, busy: isSubmitting, complete: hasResult }">
        <video
          ref="videoRef"
          class="camera-preview"
          autoplay
          muted
          playsinline
          aria-label="Camera preview"
        ></video>

        <div v-if="!cameraReady" class="storybook-placeholder" aria-hidden="true">
          <div class="moon"></div>
          <div class="open-book">
            <span></span>
            <span></span>
          </div>
          <div class="sparkle sparkle-one"></div>
          <div class="sparkle sparkle-two"></div>
          <div class="sparkle sparkle-three"></div>
        </div>

        <div class="page-frame" aria-hidden="true"></div>

        <div v-if="isSubmitting" class="reading-veil" aria-live="polite">
          <div class="reading-pulse"></div>
          <span>{{ statusMessage }}</span>
        </div>
      </section>

      <button
        class="magic-button"
        data-testid="main-action"
        type="button"
        :disabled="actionDisabled"
        @click="handleMainAction"
      >
        <span class="button-glow" aria-hidden="true"></span>
        <span>{{ mainButtonLabel }}</span>
      </button>

      <section class="status-strip" :class="{ error: errorMessage }" aria-live="polite">
        <span>{{ errorMessage || statusMessage }}</span>
        <small>{{ progressLabel }}</small>
      </section>

      <section v-if="hasResult" class="story-output" aria-live="polite">
        <div class="story-heading">
          <p>{{ storyTitle }}</p>
          <span>{{ progressLabel }}</span>
        </div>

        <div class="spoken-script" data-testid="story-text">
          {{ spokenText }}
        </div>

        <audio
          v-if="audioUrl"
          ref="audioRef"
          class="audio-player"
          controls
          :src="audioUrl"
          :aria-label="`Audio for ${storyTitle}`"
        ></audio>
        <button v-if="needsManualPlay" class="secondary-action" type="button" @click="playAudio">
          Play Audio
        </button>

        <div v-if="storyBeats.length" class="story-section">
          <h2>Reading Order</h2>
          <ol class="beat-list">
            <li v-for="beat in storyBeats" :key="beat.beat_id" class="beat-item">
              <span>{{ pageMomentLabel(beat.kind) }}</span>
              <p>{{ beat.narration }}</p>
            </li>
          </ol>
        </div>

        <div v-if="caregiverCues.length" class="story-section cue-section">
          <h2>Questions to Ask</h2>
          <ul class="cue-list">
            <li v-for="cue in caregiverCues" :key="cue.cue_id">
              {{ cue.cue }}
            </li>
          </ul>
        </div>
      </section>
    </section>
  </main>
</template>

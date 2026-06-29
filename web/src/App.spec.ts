import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import App from './App.vue'

vi.mock('./lib/api', () => ({
  submitReadRequest: vi.fn(),
  submitWordRequest: vi.fn(),
}))

vi.mock('./lib/capture', () => ({
  captureVideoFrame: vi.fn(),
}))

vi.mock('./lib/playback', () => ({
  attemptPlayback: vi.fn(),
}))

import { submitReadRequest, submitWordRequest } from './lib/api'
import { captureVideoFrame } from './lib/capture'
import { attemptPlayback } from './lib/playback'
import type { ReadPayload, StoryCompilation, WordExplorerResult, WordPayload } from './lib/api'

const getUserMedia = vi.fn()
const stopTrack = vi.fn()

const sampleStory: StoryCompilation = {
  title: 'Moon Page',
  spoken_script: 'hello world',
  beats: [
    {
      beat_id: 'text-1',
      kind: 'text',
      narration: 'hello world',
      source_text: 'hello world',
      layout_region: 'top-left',
      confidence: 0.98,
    },
    {
      beat_id: 'illustration-1',
      kind: 'illustration',
      narration: 'The moon glows over the boat.',
      source_text: null,
      layout_region: 'center',
      confidence: 0.84,
    },
  ],
  caregiver_cues: [
    {
      cue_id: 'cue-1',
      after_beat_id: 'illustration-1',
      cue: 'Ask what might happen next.',
      purpose: 'prediction',
    },
  ],
  diagnostics: {
    mode: 'gemma_vision',
    layout_notes: 'Read top-left text first.',
    ocr_used: false,
    warnings: [],
  },
}

const sampleReadPayload: ReadPayload = {
  request_id: 'req-1',
  text: 'hello world',
  audio_url: '/media/audio/req-1',
  mime_type: 'audio/wav',
  expires_at: '2026-04-14T00:00:00Z',
  story: sampleStory,
}

const sampleWord: WordExplorerResult = {
  selected_word: 'brave',
  normalized_word: 'brave',
  language: 'English',
  part_of_speech: 'describing word',
  pronunciation_hint: 'brayv',
  kid_explanation: 'Brave means you try even when something feels a little scary.',
  example_sentence: 'The brave rabbit hopped across the bridge.',
  page_context: 'The word is centered near the rabbit.',
  spoken_script:
    'The word is brave. Brave means you try even when something feels a little scary. The brave rabbit hopped across the bridge.',
  confidence: 0.92,
  diagnostics: {
    mode: 'gemma_vision',
    pointing_evidence: 'The word brave crosses the center of the crop.',
    layout_region: 'center',
    warnings: [],
  },
}

const sampleWordPayload: WordPayload = {
  request_id: 'word-1',
  text: sampleWord.spoken_script,
  audio_url: '/media/audio/word-1',
  mime_type: 'audio/wav',
  expires_at: '2026-04-14T00:00:00Z',
  word: sampleWord,
}

function mountAppWithCamera() {
  getUserMedia.mockResolvedValue({
    getTracks: () => [{ stop: stopTrack }],
  })
  return mount(App)
}

async function openCamera(wrapper: ReturnType<typeof mount>) {
  await wrapper.get('[data-testid="main-action"]').trigger('click')
  await flushPromises()
}

async function capturePage(wrapper: ReturnType<typeof mount>) {
  await wrapper.get('[data-testid="main-action"]').trigger('click')
  await flushPromises()
}

describe('App', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    window.history.pushState({}, '', '/')
    Object.defineProperty(globalThis.navigator, 'mediaDevices', {
      value: { getUserMedia },
      configurable: true,
    })
    Object.defineProperty(HTMLMediaElement.prototype, 'play', {
      value: vi.fn().mockResolvedValue(undefined),
      configurable: true,
    })
    Object.defineProperty(HTMLVideoElement.prototype, 'srcObject', {
      value: null,
      writable: true,
      configurable: true,
    })
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('renders the parent-child intro route', () => {
    window.history.pushState({}, '', '/openread')

    const wrapper = mount(App)

    expect(wrapper.text()).toContain('OpenRead helps keep story time going')
    expect(wrapper.text()).toContain('Privacy first')
    expect(wrapper.text()).toContain('No account needed')
    expect(wrapper.text()).toContain('Zero page-photo retention')
    expect(wrapper.text()).toContain('Parent trust')
    expect(wrapper.text()).toContain('Watch Intro Video')
    expect(wrapper.text()).toContain('Video introduction')
    expect(wrapper.text()).toContain('Language moments are not equally easy for every family')
    expect(wrapper.text()).toContain('No menus. No setup.')
    expect(wrapper.text()).toContain('Natural story order.')
    expect(wrapper.text()).toContain('The gap is the family reading workflow.')
    expect(wrapper.text()).toContain('One-button')
    expect(wrapper.text()).toContain('not prompt-based')
    expect(wrapper.text()).toContain('Story-aware')
    expect(wrapper.text()).toContain('not OCR-only')
    expect(wrapper.text()).toContain("keep a child's page from going silent")
    expect(wrapper.get('iframe[title="OpenRead video introduction"]').attributes('src')).toContain(
      'youtube-nocookie.com/embed/4U14vyYP_Ck',
    )
    expect(wrapper.text()).toContain('Open the Reader')
  })

  it('redirects the removed demo route to the intro page', () => {
    window.history.pushState({}, '', '/openread/demo')

    const wrapper = mount(App)

    expect(window.location.pathname).toBe('/openread')
    expect(wrapper.text()).toContain('OpenRead helps keep story time going')
  })

  it('redirects the old static demo URL to the intro page', () => {
    window.history.pushState({}, '', '/demo/openread-cinematic.html')

    const wrapper = mount(App)

    expect(window.location.pathname).toBe('/openread')
    expect(wrapper.text()).toContain('OpenRead helps keep story time going')
  })

  it('shows an error when camera APIs are unavailable', async () => {
    Object.defineProperty(globalThis.navigator, 'mediaDevices', {
      value: undefined,
      configurable: true,
    })

    const wrapper = mount(App)
    await wrapper.get('[data-testid="main-action"]').trigger('click')

    expect(wrapper.text()).toContain('does not expose camera access')
  })

  it('shows a permission error when camera access is blocked', async () => {
    getUserMedia.mockRejectedValue(new DOMException('blocked', 'NotAllowedError'))

    const wrapper = mount(App)
    await wrapper.get('[data-testid="main-action"]').trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('Camera permission was denied')
  })

  it('uses one main button to open the camera and then capture a page', async () => {
    vi.mocked(captureVideoFrame).mockResolvedValue(new Blob(['img'], { type: 'image/jpeg' }))
    vi.mocked(submitReadRequest).mockResolvedValue(sampleReadPayload)

    const wrapper = mountAppWithCamera()
    expect(wrapper.text()).toContain('Read Page')
    expect(wrapper.text()).toContain('Explore Word')
    expect(wrapper.text()).toContain('Take a photo of one page')
    expect(wrapper.get('[data-testid="main-action"]').text()).toContain('Open Camera')

    await openCamera(wrapper)
    expect(wrapper.get('[data-testid="main-action"]').text()).toContain('Take Photo')

    await capturePage(wrapper)
    expect(submitReadRequest).toHaveBeenCalledWith(expect.any(Blob), 'bilingual', 'gemma_vision', expect.any(Function))
    expect(submitWordRequest).not.toHaveBeenCalled()
  })

  it('switches to Explore Word and calls the word API', async () => {
    vi.mocked(captureVideoFrame).mockResolvedValue(new Blob(['img'], { type: 'image/jpeg' }))
    vi.mocked(submitWordRequest).mockResolvedValue(sampleWordPayload)

    const wrapper = mountAppWithCamera()
    await wrapper.get('button[aria-pressed="false"]').trigger('click')

    expect(wrapper.text()).toContain('Center one word in the circle')
    expect(wrapper.find('.word-target').exists()).toBe(false)

    await openCamera(wrapper)
    expect(wrapper.find('.word-target').exists()).toBe(true)
    await capturePage(wrapper)

    expect(submitWordRequest).toHaveBeenCalledWith(expect.any(Blob), 'auto', expect.any(Function))
    expect(submitReadRequest).not.toHaveBeenCalled()
    expect(wrapper.get('[data-testid="word-result"]').text()).toContain('brave')
    expect(wrapper.get('[data-testid="word-explanation"]').text()).toContain('Brave means')
    expect(wrapper.text()).toContain('The brave rabbit hopped across the bridge.')
  })

  it('shows a clear reading state while the request is in progress', async () => {
    let resolveRequest: ((value: typeof sampleReadPayload) => void) | undefined
    vi.mocked(captureVideoFrame).mockResolvedValue(new Blob(['img'], { type: 'image/jpeg' }))
    vi.mocked(submitReadRequest).mockImplementation(
      () =>
        new Promise((resolve) => {
          resolveRequest = resolve
        }),
    )

    const wrapper = mountAppWithCamera()
    await openCamera(wrapper)
    await capturePage(wrapper)

    expect(wrapper.text()).toContain('Reading page')
    expect(wrapper.text()).toContain('Understanding the page...')

    resolveRequest?.(sampleReadPayload)
    await flushPromises()
  })

  it('shows story compilation progress before audio generation starts', async () => {
    let resolveRequest: ((value: typeof sampleReadPayload) => void) | undefined
    vi.mocked(captureVideoFrame).mockResolvedValue(new Blob(['img'], { type: 'image/jpeg' }))
    vi.mocked(submitReadRequest).mockImplementation(
      (_blob, _langHint, _compilerMode, onProgress) =>
        new Promise((resolve) => {
          onProgress?.({
            request_id: 'req-1',
            status: 'processing',
            stage: 'story_compile',
            text: null,
            audio_url: null,
            mime_type: null,
            expires_at: null,
            paragraphs_total: 0,
            paragraphs_completed: 0,
            error: null,
            story: null,
          })
          resolveRequest = resolve
        }),
    )

    const wrapper = mountAppWithCamera()
    await openCamera(wrapper)
    await capturePage(wrapper)

    expect(wrapper.text()).toContain('Finding the story order')

    resolveRequest?.(sampleReadPayload)
    await flushPromises()
  })

  it('shows word explorer progress before audio generation starts', async () => {
    let resolveRequest: ((value: typeof sampleWordPayload) => void) | undefined
    vi.mocked(captureVideoFrame).mockResolvedValue(new Blob(['img'], { type: 'image/jpeg' }))
    vi.mocked(submitWordRequest).mockImplementation(
      (_blob, _langHint, onProgress) =>
        new Promise((resolve) => {
          onProgress?.({
            request_id: 'word-1',
            status: 'processing',
            stage: 'word_detect',
            word: null,
            text: null,
            audio_url: null,
            mime_type: null,
            expires_at: null,
            paragraphs_total: 0,
            paragraphs_completed: 0,
            error: null,
          })
          resolveRequest = resolve
        }),
    )

    const wrapper = mountAppWithCamera()
    const modeButtons = wrapper.findAll('.mode-toggle button')
    expect(modeButtons).toHaveLength(2)
    await modeButtons[1]!.trigger('click')
    await openCamera(wrapper)
    await capturePage(wrapper)

    expect(wrapper.text()).toContain('Finding the word')

    resolveRequest?.(sampleWordPayload)
    await flushPromises()
  })

  it('shows generated text, reading order, questions, and audio progress', async () => {
    let resolveRequest: ((value: typeof sampleReadPayload) => void) | undefined
    vi.mocked(captureVideoFrame).mockResolvedValue(new Blob(['img'], { type: 'image/jpeg' }))
    vi.mocked(submitReadRequest).mockImplementation(
      (_blob, _langHint, _compilerMode, onProgress) =>
        new Promise((resolve) => {
          onProgress?.({
            request_id: 'req-1',
            status: 'processing',
            stage: 'tts',
            text: 'hello world',
            audio_url: null,
            mime_type: null,
            expires_at: null,
            paragraphs_total: 3,
            paragraphs_completed: 1,
            error: null,
            story: sampleStory,
          })
          resolveRequest = resolve
        }),
    )

    const wrapper = mountAppWithCamera()
    await openCamera(wrapper)
    await capturePage(wrapper)

    expect(wrapper.get('[data-testid="story-text"]').text()).toContain('hello world')
    expect(wrapper.text()).toContain('Reading Order')
    expect(wrapper.text()).toContain('The moon glows over the boat.')
    expect(wrapper.text()).toContain('Questions to Ask')
    expect(wrapper.text()).toContain('Ask what might happen next.')
    expect(wrapper.text()).toContain('1/3 audio parts')

    resolveRequest?.(sampleReadPayload)
    await flushPromises()
  })

  it('shows a start reading button when autoplay is rejected', async () => {
    vi.mocked(captureVideoFrame).mockResolvedValue(new Blob(['img'], { type: 'image/jpeg' }))
    vi.mocked(submitReadRequest).mockResolvedValue(sampleReadPayload)
    vi.mocked(attemptPlayback).mockResolvedValue(true)

    const wrapper = mountAppWithCamera()
    await openCamera(wrapper)
    await capturePage(wrapper)

    expect(wrapper.text()).toContain('Tap to begin')
    expect(wrapper.text()).toContain('Start Reading')
    expect(wrapper.text()).toContain('Tap once to hear the story.')
    expect(wrapper.get('[data-testid="story-text"]').text()).toContain('hello world')
  })
})

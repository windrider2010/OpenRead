# Third-Party Notices

OpenRead is licensed under the Apache License 2.0. It also depends on third-party open-source software and externally hosted model/API services. This file is a project-level acknowledgement for the main direct dependencies used by the app; the lockfiles remain the source of truth for exact transitive package versions.

## Model and API Services

- Google GenAI SDK: Python SDK used to call the Gemma model endpoint. Project: <https://github.com/googleapis/python-genai>. License: Apache 2.0.
- Gemma 4: multimodal model used as OpenRead's story compiler through the Google GenAI API. Project information: <https://deepmind.google/models/gemma/gemma-4/>. Model/API use is governed by Google's applicable model and API terms, separate from this repository's Apache 2.0 license.
- Kokoro-82M: text-to-speech model used by the Kokoro package for generated read-aloud audio. Model page: <https://huggingface.co/hexgrad/Kokoro-82M>. License listed by upstream: Apache 2.0.

## Backend Runtime

- FastAPI: backend web framework. Project: <https://github.com/fastapi/fastapi>. License listed by upstream/package metadata: MIT.
- Uvicorn: ASGI server. Project: <https://uvicorn.dev/>. License listed by upstream/package metadata: BSD 3-Clause.
- PaddleOCR: OCR diagnostics and `ocr_assisted` mode. Project: <https://github.com/PaddlePaddle/PaddleOCR>. License listed by upstream/package metadata: Apache 2.0.
- PaddlePaddle: PaddleOCR runtime. Project: <https://github.com/PaddlePaddle/Paddle>. License listed by upstream/package metadata: Apache 2.0.
- Kokoro Python package: TTS pipeline wrapper used by `KokoroTtsService`. Project: <https://github.com/hexgrad/kokoro>. License listed by upstream/package metadata: Apache 2.0.
- Misaki: text processing dependency used with Kokoro for multilingual/CJK support. Package metadata lists Apache 2.0.
- PyTorch: tensor runtime used by Kokoro. Project: <https://pytorch.org/>. License listed by upstream/package metadata: BSD 3-Clause.
- Pillow: image decoding and JPEG normalization. Project: <https://python-pillow.github.io/>. License listed by upstream/package metadata: HPND.
- NumPy: numerical array handling for audio and image data. Project: <https://numpy.org/>. License listed by upstream/package metadata: BSD 3-Clause.
- python-dotenv: local environment loading. Project: <https://github.com/theskumar/python-dotenv>. License listed by upstream/package metadata: BSD 3-Clause.
- python-multipart: multipart upload parsing for FastAPI. Project: <https://github.com/Kludex/python-multipart>. License listed by upstream/package metadata: Apache 2.0.
- eSpeak NG: system dependency installed in Docker for English phonemization used by Kokoro. Project: <https://github.com/espeak-ng/espeak-ng>. License listed by upstream: GPL 3.0 or later.

## Frontend Runtime and Tooling

- Vue: frontend framework. Project: <https://vuejs.org/>. License listed by upstream/package metadata: MIT.
- Vite: frontend dev server and build tool. Project: <https://vite.dev/>. License listed by upstream/package metadata: MIT.
- TypeScript: type system and compiler. Project: <https://www.typescriptlang.org/>. License listed by upstream/package metadata: Apache 2.0.
- Vitest: frontend unit test runner. Project: <https://vitest.dev/>. License listed by upstream/package metadata: MIT.
- jsdom: DOM environment for frontend tests. Project: <https://github.com/jsdom/jsdom>. License listed by upstream/package metadata: MIT.

## Operational Note

This notice is not a substitute for a full legal review before production distribution. For redistribution, review the generated Python and npm lockfiles, container base image notices, system packages, and model/provider terms for the exact build being shipped.

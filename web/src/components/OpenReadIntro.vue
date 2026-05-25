<script setup lang="ts">
const emit = defineEmits<{
  navigate: [path: string]
}>()

function go(path: string) {
  emit('navigate', path)
}
</script>

<template>
  <main class="intro-page">
    <nav class="intro-nav" aria-label="OpenRead introduction">
      <button class="intro-logo" type="button" @click="go('/')">OPENREAD</button>
      <div class="intro-links">
        <a href="#intro-video">Video</a>
        <button type="button" @click="go('/')">Reader</button>
      </div>
    </nav>

    <section class="intro-hero" aria-labelledby="intro-title">
      <div class="hero-scene" aria-hidden="true">
        <div class="scene-sun"></div>
        <div class="scene-cloud cloud-one"></div>
        <div class="scene-cloud cloud-two"></div>
        <div class="scene-book">
          <span></span>
          <span></span>
        </div>
        <div class="scene-phone">
          <div class="phone-camera"></div>
          <div class="phone-page">
            <div class="phone-page-book"></div>
            <div class="phone-page-scan"></div>
            <div class="phone-page-order">
              <span></span>
              <span></span>
              <span></span>
            </div>
          </div>
          <div class="phone-lines">
            <span></span>
            <span></span>
            <span></span>
          </div>
          <div class="phone-audio">
            <span></span>
            <span></span>
            <span></span>
            <span></span>
          </div>
        </div>
        <div class="scene-family">
          <div class="grownup"></div>
          <div class="child"></div>
        </div>
      </div>

      <div class="hero-copy">
        <p class="hero-kicker">For real story moments at home</p>
        <h1 id="intro-title">OpenRead</h1>
        <p class="hero-subtitle">
          OpenRead helps keep story time going when voice, vision, language, or confidence gets in the way.
        </p>
        <ul class="privacy-pills" aria-label="OpenRead privacy commitments">
          <li>Privacy first</li>
          <li>No account needed</li>
          <li>Zero page-photo retention</li>
          <li>Built for parent trust</li>
        </ul>
        <div class="hero-actions">
          <button class="primary-link" type="button" @click="go('/')">Open the Reader</button>
          <a class="secondary-link" href="#intro-video">Watch Intro Video</a>
        </div>
      </div>
    </section>

    <section class="promise-band" aria-label="Why OpenRead exists">
      <p>
        The child is ready. The page is there. OpenRead turns one photo of a picture-book page into a gentle
        read-aloud with large follow-along text, without asking families to create an account.
      </p>
    </section>

    <section class="intro-section moment-band" aria-labelledby="moment-title">
      <div class="moment-copy">
        <p class="section-label">The moment</p>
        <h2 id="moment-title">Language moments are not equally easy for every family.</h2>
        <p>
          OpenRead is built for the fragile moment when a child is ready to hear a story, but voice, vision,
          language, or confidence gets in the way.
        </p>
      </div>

      <div class="moment-reel" aria-label="OpenRead reading moment animation">
        <div class="reel-stage">
          <div class="reel-family" aria-hidden="true">
            <span class="reel-grownup"></span>
            <span class="reel-child"></span>
          </div>
          <div class="reel-book" aria-hidden="true">
            <span></span>
            <span></span>
          </div>
          <div class="reel-phone" aria-hidden="true">
            <div class="reel-phone-brand">OPENREAD</div>
            <div class="reel-camera-frame">
              <div class="reel-page-art"></div>
              <div class="reel-story-order">
                <span></span>
                <span></span>
                <span></span>
              </div>
            </div>
            <div class="reel-scan"></div>
            <div class="reel-lines">
              <span></span>
              <span></span>
              <span></span>
            </div>
            <div class="reel-wave">
              <span></span>
              <span></span>
              <span></span>
              <span></span>
            </div>
          </div>
          <ol class="reel-cards">
            <li>
              <strong>No menus. No setup.</strong>
              <p>The page fills the frame, then OpenRead starts reading.</p>
            </li>
            <li>
              <strong>Not simple columns.</strong>
              <p>Speech bubbles, wrapped text, and pictures can all matter.</p>
            </li>
            <li>
              <strong>Natural story order.</strong>
              <p>If the page jumps around, OpenRead puts the story back into a read-aloud flow.</p>
            </li>
          </ol>
        </div>
      </div>
    </section>

    <section id="intro-video" class="intro-section video-band" aria-labelledby="video-title">
      <div class="section-copy">
        <p class="section-label">Video introduction</p>
        <h2 id="video-title">See the reading moment OpenRead is built for.</h2>
        <p>
          A short introduction is the fastest way to understand why OpenRead focuses on one photo, parent trust,
          privacy-first design, and a calm read-aloud experience.
        </p>
      </div>
      <div class="video-shell">
        <iframe
          title="OpenRead video introduction"
          src="https://www.youtube-nocookie.com/embed/4U14vyYP_Ck?rel=0"
          loading="lazy"
          referrerpolicy="strict-origin-when-cross-origin"
          allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share"
          allowfullscreen
        ></iframe>
      </div>
      <p class="video-note">Embedded with YouTube privacy-enhanced mode.</p>
    </section>

    <section class="intro-section story-flow" aria-labelledby="flow-title">
      <div class="section-copy">
        <p class="section-label">How it works</p>
        <h2 id="flow-title">One photo becomes a calmer read-aloud.</h2>
      </div>
      <ol class="flow-list">
        <li>
          <span>1</span>
          <strong>Take a photo</strong>
          <p>Open the web app on a phone and frame one physical picture-book page.</p>
        </li>
        <li>
          <span>2</span>
          <strong>Understand the page</strong>
          <p>Gemma 4 looks at the whole page, including layout, visible words, and meaningful pictures.</p>
        </li>
        <li>
          <span>3</span>
          <strong>Start reading</strong>
          <p>Kokoro TTS speaks the child-facing script while the caregiver stays present.</p>
        </li>
      </ol>
    </section>

    <section class="intro-section comparison-band" aria-labelledby="difference-title">
      <div class="section-copy">
        <p class="section-label">More than OCR</p>
        <h2 id="difference-title">Picture books are visual stories, not plain documents.</h2>
        <p>
          OCR can read letters. OpenRead builds a structured reading plan: visible text, corrected story order,
          short picture narration, large follow-along output, and optional caregiver cues.
        </p>
      </div>
      <div class="comparison-visual" aria-label="OCR compared with OpenRead">
        <div>
          <span>OCR-only</span>
          <p>"Where is my balloon?"</p>
          <p>"It floated away."</p>
          <p>"The bear looked up."</p>
        </div>
        <div>
          <span>OpenRead</span>
          <p>The bear looked up.</p>
          <p>A red balloon is caught in the tree.</p>
          <p>"Where did my balloon go?"</p>
        </div>
      </div>
    </section>

    <section class="intro-section trust-band" aria-labelledby="trust-title">
      <div class="section-copy">
        <p class="section-label">Parent trust</p>
        <h2 id="trust-title">Privacy-first by design.</h2>
        <p>
          OpenRead is built for family reading moments, so it avoids account gates, child profiles, and stored page
          photos. The project is open source and self-hostable so the trust model can be inspected.
        </p>
      </div>
      <div class="trust-grid">
        <article>
          <strong>No account needed</strong>
          <p>The public demo can be used without creating a family profile or child account.</p>
        </article>
        <article>
          <strong>Zero page-photo retention</strong>
          <p>Uploaded photos are processed in memory and are not durably stored by the app.</p>
        </article>
        <article>
          <strong>No family tracking</strong>
          <p>The reader experience does not require identity, subscriptions, child dashboards, or reading histories.</p>
        </article>
        <article>
          <strong>Auditable output</strong>
          <p>The story plan separates what is spoken, what is displayed, and what is used for diagnostics.</p>
        </article>
      </div>
    </section>

    <section class="final-band" aria-label="Start using OpenRead">
      <h2>Ready for one page?</h2>
      <button class="primary-link" type="button" @click="go('/')">Open the Reader</button>
    </section>
  </main>
</template>

<style scoped>
.intro-page {
  min-height: 100svh;
  color: #251c36;
  background:
    linear-gradient(180deg, rgba(255, 248, 233, 0.94), rgba(238, 247, 232, 0.92)),
    #fff8ed;
}

.intro-nav {
  width: min(1120px, calc(100% - 32px));
  min-height: 64px;
  margin: 0 auto;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  position: absolute;
  inset: 0 0 auto;
  z-index: 10;
}

.intro-logo,
.intro-links button {
  border: 0;
  background: transparent;
  color: #5f438f;
  cursor: pointer;
}

.intro-logo {
  font-family:
    "Cooper Black",
    "Comic Sans MS",
    "Trebuchet MS",
    ui-rounded,
    system-ui,
    sans-serif;
  font-size: 1.32rem;
  font-weight: 900;
  letter-spacing: 0;
  text-shadow: 0 2px 0 #fff2bd;
}

.intro-links {
  display: flex;
  align-items: center;
  gap: 8px;
}

.intro-links button,
.intro-links a {
  min-height: 38px;
  padding: 0 14px;
  display: inline-grid;
  place-items: center;
  border: 1px solid rgba(85, 63, 104, 0.18);
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.58);
  color: #3a2b4d;
  font-size: 0.92rem;
  font-weight: 800;
  text-decoration: none;
}

.intro-hero {
  min-height: min(780px, 88svh);
  padding: 104px 24px 64px;
  position: relative;
  overflow: hidden;
  display: grid;
  align-items: center;
  background:
    linear-gradient(180deg, rgba(255, 247, 229, 0.1), rgba(255, 247, 229, 0.72) 72%, #fff8ed),
    linear-gradient(135deg, #f5d9ff 0%, #fff0bf 43%, #c9e7d2 100%);
}

.hero-scene {
  position: absolute;
  inset: 0;
  overflow: hidden;
}

.scene-sun {
  width: min(27vw, 180px);
  aspect-ratio: 1;
  position: absolute;
  right: 12%;
  top: 15%;
  border-radius: 50%;
  background: #fff2a8;
  box-shadow: 0 0 52px rgba(255, 226, 117, 0.52);
}

.scene-cloud {
  position: absolute;
  height: 54px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.68);
}

.scene-cloud::before,
.scene-cloud::after {
  content: "";
  position: absolute;
  bottom: 18px;
  border-radius: 50%;
  background: inherit;
}

.scene-cloud::before {
  width: 72px;
  height: 72px;
  left: 22px;
}

.scene-cloud::after {
  width: 92px;
  height: 92px;
  right: 24px;
}

.cloud-one {
  width: 240px;
  left: 6%;
  top: 25%;
}

.cloud-two {
  width: 190px;
  right: 13%;
  top: 42%;
  opacity: 0.72;
}

.scene-book {
  width: min(55vw, 430px);
  height: 162px;
  position: absolute;
  right: max(24px, 11vw);
  bottom: 8%;
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 5px;
  transform: perspective(520px) rotateX(14deg) rotateZ(-3deg);
  filter: drop-shadow(0 26px 24px rgba(73, 44, 78, 0.2));
}

.scene-book span {
  border: 1px solid rgba(85, 63, 104, 0.14);
  background:
    linear-gradient(90deg, rgba(115, 83, 130, 0.12) 1px, transparent 1px) 50% 28px / 22px 21px,
    linear-gradient(180deg, #fffef7, #ffe3cf);
}

.scene-book span:first-child {
  border-radius: 28px 8px 28px 34px;
  transform: skewY(4deg);
}

.scene-book span:last-child {
  border-radius: 8px 28px 34px 28px;
  transform: skewY(-4deg);
}

.scene-phone {
  width: min(36vw, 250px);
  max-width: 250px;
  min-width: 160px;
  aspect-ratio: 0.56;
  position: absolute;
  right: max(26px, 18vw);
  bottom: 13%;
  padding: 18px 14px;
  border: 7px solid #2f2542;
  border-radius: 34px;
  background: #fff9ec;
  box-shadow: 0 24px 46px rgba(54, 33, 69, 0.24);
  transform: rotate(5deg);
  animation: hero-phone-float 7s ease-in-out infinite;
}

.phone-camera {
  width: 44px;
  height: 6px;
  margin: 0 auto 14px;
  border-radius: 999px;
  background: #2f2542;
}

.phone-page {
  height: 48%;
  position: relative;
  overflow: hidden;
  border-radius: 20px;
  background:
    linear-gradient(135deg, rgba(255, 242, 168, 0.66), rgba(165, 213, 184, 0.72)),
    #f7d1cd;
}

.phone-page-book {
  width: 68%;
  height: 54%;
  position: absolute;
  left: 16%;
  bottom: 13%;
  border-radius: 10px 10px 16px 16px;
  background:
    linear-gradient(90deg, rgba(95, 67, 143, 0.2) 1px, transparent 1px) 50% 50% / 12px 12px,
    linear-gradient(90deg, #fffef7 0 49%, #f7d9ca 50% 51%, #fffef7 52%);
  box-shadow: 0 10px 18px rgba(54, 33, 69, 0.16);
  animation: hero-page-capture 5.8s ease-in-out infinite;
}

.phone-page-scan {
  height: 22px;
  position: absolute;
  left: 12px;
  right: 12px;
  top: 18px;
  border-radius: 999px;
  background: rgba(255, 241, 163, 0.75);
  filter: blur(1px);
  mix-blend-mode: screen;
  animation: hero-phone-scan 3.8s ease-in-out infinite;
}

.phone-page-order {
  width: 58%;
  display: grid;
  gap: 5px;
  position: absolute;
  right: 12%;
  top: 18%;
  opacity: 0;
  animation: hero-order-fade 5.8s ease-in-out infinite;
}

.phone-page-order span {
  height: 7px;
  border-radius: 999px;
  background: #6e5890;
}

.phone-page-order span:nth-child(2) {
  width: 78%;
  background: #efad64;
}

.phone-page-order span:nth-child(3) {
  width: 56%;
  background: #85b99c;
}

.phone-lines {
  display: grid;
  gap: 9px;
  padding-top: 17px;
}

.phone-lines span {
  height: 10px;
  border-radius: 999px;
  background: #6e5890;
}

.phone-lines span:nth-child(2) {
  width: 76%;
  background: #efad64;
}

.phone-lines span:nth-child(3) {
  width: 56%;
  background: #85b99c;
}

.phone-audio {
  height: 28px;
  margin-top: 12px;
  display: flex;
  align-items: end;
  justify-content: center;
  gap: 6px;
}

.phone-audio span {
  width: 9px;
  min-height: 8px;
  border-radius: 999px;
  background: #f5a657;
  animation: hero-audio-bars 1.3s ease-in-out infinite;
}

.phone-audio span:nth-child(2) {
  background: #9fcfb9;
  animation-delay: 0.12s;
}

.phone-audio span:nth-child(3) {
  background: #7d6199;
  animation-delay: 0.24s;
}

.phone-audio span:nth-child(4) {
  background: #efb0b8;
  animation-delay: 0.36s;
}

.scene-family {
  width: 210px;
  height: 230px;
  position: absolute;
  left: max(20px, 9vw);
  bottom: 6%;
}

.grownup,
.child {
  position: absolute;
  bottom: 0;
  border-radius: 999px 999px 40px 40px;
  background: #7d6199;
  box-shadow: inset 0 44px 0 #f3c6a6;
}

.grownup {
  width: 96px;
  height: 198px;
  left: 22px;
}

.child {
  width: 70px;
  height: 142px;
  right: 24px;
  background: #89bfa0;
  box-shadow: inset 0 34px 0 #f1c59e;
}

.hero-copy {
  width: min(700px, 100%);
  margin: 0 auto;
  position: relative;
  z-index: 2;
  text-align: center;
}

.hero-kicker,
.section-label {
  margin: 0 0 10px;
  color: #6d5480;
  font-size: 0.86rem;
  font-weight: 850;
  letter-spacing: 0;
  text-transform: uppercase;
}

.hero-copy h1 {
  margin: 0;
  color: #5f438f;
  font-family:
    "Cooper Black",
    "Comic Sans MS",
    "Trebuchet MS",
    ui-rounded,
    system-ui,
    sans-serif;
  font-size: clamp(4rem, 12vw, 7.8rem);
  font-weight: 900;
  line-height: 0.88;
  letter-spacing: 0;
  text-shadow:
    0 4px 0 #fff2bd,
    0 18px 36px rgba(72, 45, 96, 0.18);
}

.hero-subtitle {
  max-width: 720px;
  margin: 24px auto 0;
  color: #302541;
  font-size: clamp(1.22rem, 3vw, 1.72rem);
  font-weight: 750;
  line-height: 1.32;
}

.privacy-pills {
  max-width: 720px;
  margin: 22px auto 0;
  padding: 0;
  display: flex;
  justify-content: center;
  flex-wrap: wrap;
  gap: 8px;
  list-style: none;
}

.privacy-pills li {
  padding: 8px 12px;
  border: 1px solid rgba(83, 55, 111, 0.16);
  border-radius: 999px;
  color: #3a2b4d;
  background: rgba(255, 255, 255, 0.7);
  box-shadow: 0 8px 18px rgba(89, 56, 93, 0.08);
  font-size: 0.86rem;
  font-weight: 850;
  line-height: 1;
}

.hero-actions,
.final-band {
  display: flex;
  justify-content: center;
  flex-wrap: wrap;
  gap: 12px;
}

.hero-actions {
  margin-top: 30px;
}

.primary-link,
.secondary-link {
  min-height: 52px;
  padding: 0 22px;
  display: inline-grid;
  place-items: center;
  border-radius: 999px;
  font-size: 1rem;
  font-weight: 900;
  cursor: pointer;
  text-decoration: none;
}

.primary-link {
  border: 0;
  color: #241835;
  background:
    linear-gradient(135deg, rgba(255, 255, 255, 0.38), transparent 42%),
    linear-gradient(135deg, #fff1a3, #f5a657 50%, #9fcfb9);
  box-shadow: 0 16px 28px rgba(89, 56, 93, 0.22);
}

.secondary-link {
  border: 1px solid rgba(83, 55, 111, 0.22);
  color: #2c1d3e;
  background: rgba(255, 255, 255, 0.7);
}

.promise-band {
  padding: 28px 24px;
  background: #fff8ed;
}

.promise-band p {
  width: min(920px, 100%);
  margin: 0 auto;
  color: #342644;
  font-size: clamp(1.25rem, 2.8vw, 1.8rem);
  font-weight: 800;
  line-height: 1.35;
  text-align: center;
}

.moment-band {
  display: grid;
  grid-template-columns: minmax(0, 0.86fr) minmax(320px, 1.14fr);
  gap: 34px;
  align-items: center;
  background:
    radial-gradient(circle at 76% 22%, rgba(255, 241, 163, 0.7), transparent 26%),
    linear-gradient(135deg, #f3f8ec 0%, #fff2df 52%, #f5eaff 100%);
}

.moment-copy {
  max-width: 520px;
  justify-self: end;
}

.moment-copy h2 {
  margin: 0;
  color: #261b36;
  font-size: clamp(2.2rem, 5.4vw, 4.8rem);
  line-height: 0.98;
  letter-spacing: 0;
}

.moment-copy p:not(.section-label) {
  margin: 18px 0 0;
  color: #51405f;
  font-size: 1.12rem;
  line-height: 1.58;
}

.moment-reel {
  min-height: 520px;
  position: relative;
  overflow: hidden;
  border-radius: 8px;
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.38), transparent 34%),
    linear-gradient(145deg, #fff6df 0%, #f7d7d4 42%, #cce9d7 100%);
  box-shadow: 0 22px 48px rgba(59, 39, 80, 0.16);
}

.reel-stage {
  min-height: 520px;
  position: relative;
  overflow: hidden;
}

.reel-stage::before {
  content: "";
  position: absolute;
  inset: 0;
  background:
    linear-gradient(90deg, rgba(255, 255, 255, 0.26), transparent 22%, transparent 78%, rgba(255, 255, 255, 0.24)),
    radial-gradient(circle at 18% 16%, rgba(255, 255, 255, 0.84), transparent 18%),
    radial-gradient(circle at 48% 12%, rgba(255, 255, 255, 0.72), transparent 19%);
  pointer-events: none;
}

.reel-family {
  width: 210px;
  height: 230px;
  position: absolute;
  left: 28px;
  bottom: 26px;
  animation: reel-breathe 5.6s ease-in-out infinite;
}

.reel-grownup,
.reel-child {
  position: absolute;
  bottom: 0;
  border-radius: 999px 999px 40px 40px;
  background: #7d6199;
  box-shadow: inset 0 44px 0 #f3c6a6;
}

.reel-grownup {
  width: 96px;
  height: 198px;
  left: 22px;
}

.reel-child {
  width: 70px;
  height: 142px;
  right: 24px;
  background: #89bfa0;
  box-shadow: inset 0 34px 0 #f1c59e;
}

.reel-book {
  width: min(78%, 390px);
  height: 144px;
  position: absolute;
  left: 50%;
  bottom: 32px;
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 5px;
  transform: translateX(-50%) perspective(520px) rotateX(14deg);
  filter: drop-shadow(0 24px 22px rgba(73, 44, 78, 0.18));
  animation: reel-book-pulse 7s ease-in-out infinite;
}

.reel-book span {
  border: 1px solid rgba(85, 63, 104, 0.14);
  background:
    linear-gradient(90deg, rgba(115, 83, 130, 0.12) 1px, transparent 1px) 50% 28px / 22px 21px,
    linear-gradient(180deg, #fffef7, #ffe3cf);
}

.reel-book span:first-child {
  border-radius: 28px 8px 28px 34px;
  transform: skewY(4deg);
}

.reel-book span:last-child {
  border-radius: 8px 28px 34px 28px;
  transform: skewY(-4deg);
}

.reel-phone {
  width: 190px;
  aspect-ratio: 0.58;
  position: absolute;
  right: 34px;
  bottom: 76px;
  padding: 16px 13px;
  border: 7px solid #2f2542;
  border-radius: 32px;
  background: #fff9ec;
  box-shadow: 0 24px 46px rgba(54, 33, 69, 0.22);
  transform: rotate(4deg);
  animation: reel-phone-rise 8s ease-in-out infinite;
}

.reel-phone-brand {
  color: #5f438f;
  font-family:
    "Cooper Black",
    "Comic Sans MS",
    "Trebuchet MS",
    ui-rounded,
    system-ui,
    sans-serif;
  font-size: 0.78rem;
  font-weight: 900;
  letter-spacing: 0;
}

.reel-camera-frame {
  height: 126px;
  margin-top: 10px;
  position: relative;
  overflow: hidden;
  border-radius: 18px;
  background:
    linear-gradient(135deg, rgba(255, 242, 168, 0.66), rgba(165, 213, 184, 0.72)),
    #f7d1cd;
}

.reel-page-art {
  width: 68%;
  height: 54%;
  position: absolute;
  left: 16%;
  bottom: 13%;
  border-radius: 12px 12px 18px 18px;
  background:
    linear-gradient(90deg, rgba(95, 67, 143, 0.22) 1px, transparent 1px) 50% 50% / 13px 13px,
    linear-gradient(90deg, #fffef7 0 49%, #f7d9ca 50% 51%, #fffef7 52%);
  box-shadow: 0 12px 20px rgba(54, 33, 69, 0.16);
  animation: reel-page-shift 6.4s ease-in-out infinite;
}

.reel-story-order {
  width: 64%;
  display: grid;
  gap: 6px;
  position: absolute;
  right: 12%;
  top: 18%;
  opacity: 0;
  animation: reel-story-order 6.4s ease-in-out infinite;
}

.reel-story-order span {
  height: 8px;
  border-radius: 999px;
  background: #6e5890;
}

.reel-story-order span:nth-child(2) {
  width: 76%;
  background: #efad64;
}

.reel-story-order span:nth-child(3) {
  width: 54%;
  background: #85b99c;
}

.reel-camera-frame::before,
.reel-camera-frame::after {
  content: "";
  position: absolute;
  border-radius: 999px;
  background: rgba(95, 67, 143, 0.78);
}

.reel-camera-frame::before {
  width: 70px;
  height: 10px;
  left: 18px;
  top: 28px;
}

.reel-camera-frame::after {
  width: 52px;
  height: 10px;
  right: 18px;
  bottom: 28px;
}

.reel-scan {
  height: 34px;
  position: absolute;
  left: 19px;
  right: 19px;
  top: 86px;
  border-radius: 999px;
  background: rgba(255, 241, 163, 0.72);
  filter: blur(1px);
  animation: reel-scan 4.8s ease-in-out infinite;
}

.reel-lines {
  display: grid;
  gap: 9px;
  padding-top: 15px;
}

.reel-lines span {
  height: 9px;
  border-radius: 999px;
  background: #6e5890;
}

.reel-lines span:nth-child(2) {
  width: 76%;
  background: #efad64;
}

.reel-lines span:nth-child(3) {
  width: 56%;
  background: #85b99c;
}

.reel-wave {
  height: 42px;
  margin-top: 13px;
  display: flex;
  align-items: end;
  justify-content: center;
  gap: 7px;
}

.reel-wave span {
  width: 11px;
  min-height: 12px;
  border-radius: 999px;
  background: #f5a657;
  animation: reel-wave 1.5s ease-in-out infinite;
}

.reel-wave span:nth-child(2) {
  background: #9fcfb9;
  animation-delay: 0.16s;
}

.reel-wave span:nth-child(3) {
  background: #7d6199;
  animation-delay: 0.32s;
}

.reel-wave span:nth-child(4) {
  background: #efb0b8;
  animation-delay: 0.48s;
}

.reel-cards {
  width: min(350px, calc(100% - 34px));
  min-height: 134px;
  margin: 0;
  padding: 0;
  position: absolute;
  left: 22px;
  top: 24px;
  list-style: none;
}

.reel-cards li {
  min-height: 126px;
  padding: 18px;
  position: absolute;
  inset: 0;
  border: 1px solid rgba(83, 55, 111, 0.14);
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.78);
  box-shadow: 0 18px 38px rgba(59, 39, 80, 0.12);
  opacity: 0;
  transform: translateY(14px);
  animation: reel-card-cycle 12s ease-in-out infinite;
}

.reel-cards li:nth-child(2) {
  animation-delay: 4s;
}

.reel-cards li:nth-child(3) {
  animation-delay: 8s;
}

.reel-cards strong {
  display: block;
  color: #251c36;
  font-size: 1.22rem;
  font-weight: 900;
  line-height: 1.1;
}

.reel-cards p {
  margin: 9px 0 0;
  color: #554565;
  font-size: 0.98rem;
  line-height: 1.42;
}

.intro-section {
  padding: 68px 24px;
}

.section-copy,
.flow-list,
.trust-grid,
.comparison-band > * {
  width: min(1020px, 100%);
  margin-inline: auto;
}

.section-copy h2,
.final-band h2 {
  max-width: 780px;
  margin: 0;
  color: #261b36;
  font-size: clamp(2rem, 5vw, 4rem);
  line-height: 1.02;
  letter-spacing: 0;
}

.section-copy p:not(.section-label) {
  max-width: 720px;
  margin: 16px 0 0;
  color: #5a4a68;
  font-size: 1.1rem;
  line-height: 1.58;
}

.story-flow {
  background: #f3f8ec;
}

.video-band {
  background:
    linear-gradient(180deg, rgba(255, 248, 237, 0.98), rgba(245, 234, 255, 0.9)),
    #fff8ed;
}

.video-shell {
  width: min(920px, 100%);
  margin: 30px auto 0;
  overflow: hidden;
  border: 1px solid rgba(83, 55, 111, 0.14);
  border-radius: 8px;
  background: #1d1430;
  box-shadow: 0 22px 48px rgba(59, 39, 80, 0.16);
  aspect-ratio: 16 / 9;
}

.video-shell iframe {
  width: 100%;
  height: 100%;
  display: block;
  border: 0;
}

.video-note {
  width: min(920px, 100%);
  margin: 12px auto 0;
  color: #6b5a76;
  font-size: 0.88rem;
  font-weight: 700;
}

@keyframes hero-phone-float {
  0%,
  100% {
    transform: translateY(0) rotate(5deg);
  }
  50% {
    transform: translateY(-13px) rotate(2deg);
  }
}

@keyframes hero-page-capture {
  0%,
  100% {
    transform: scale(1) rotate(0deg);
    opacity: 1;
  }
  48%,
  68% {
    transform: scale(0.86) translateY(-4px) rotate(-2deg);
    opacity: 0.66;
  }
}

@keyframes hero-phone-scan {
  0%,
  100% {
    transform: translateY(-34px);
    opacity: 0.3;
  }
  50% {
    transform: translateY(88px);
    opacity: 0.95;
  }
}

@keyframes hero-order-fade {
  0%,
  42%,
  100% {
    opacity: 0;
    transform: translateY(8px);
  }
  54%,
  78% {
    opacity: 1;
    transform: translateY(0);
  }
}

@keyframes hero-audio-bars {
  0%,
  100% {
    height: 9px;
  }
  50% {
    height: 28px;
  }
}

@keyframes reel-breathe {
  0%,
  100% {
    transform: translateY(0);
  }
  50% {
    transform: translateY(-8px);
  }
}

@keyframes reel-book-pulse {
  0%,
  100% {
    filter: drop-shadow(0 24px 22px rgba(73, 44, 78, 0.18));
  }
  50% {
    filter: drop-shadow(0 24px 34px rgba(245, 166, 87, 0.28));
  }
}

@keyframes reel-phone-rise {
  0%,
  100% {
    transform: translateY(0) rotate(4deg);
  }
  50% {
    transform: translateY(-14px) rotate(2deg);
  }
}

@keyframes reel-scan {
  0%,
  100% {
    transform: translateY(-48px);
    opacity: 0.32;
  }
  50% {
    transform: translateY(70px);
    opacity: 0.92;
  }
}

@keyframes reel-page-shift {
  0%,
  100% {
    transform: scale(1) rotate(0deg);
    opacity: 1;
  }
  46%,
  68% {
    transform: scale(0.84) translateY(-5px) rotate(-2deg);
    opacity: 0.64;
  }
}

@keyframes reel-story-order {
  0%,
  40%,
  100% {
    opacity: 0;
    transform: translateY(10px);
  }
  52%,
  78% {
    opacity: 1;
    transform: translateY(0);
  }
}

@keyframes reel-wave {
  0%,
  100% {
    height: 14px;
  }
  50% {
    height: 42px;
  }
}

@keyframes reel-card-cycle {
  0%,
  7% {
    opacity: 0;
    transform: translateY(14px);
  }
  12%,
  30% {
    opacity: 1;
    transform: translateY(0);
  }
  36%,
  100% {
    opacity: 0;
    transform: translateY(-14px);
  }
}

.flow-list {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 14px;
  margin-top: 26px;
  padding: 0;
  list-style: none;
}

.flow-list li,
.trust-grid article,
.comparison-visual > div {
  border: 1px solid rgba(83, 55, 111, 0.14);
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.66);
}

.flow-list li {
  padding: 22px;
}

.flow-list span {
  width: 36px;
  height: 36px;
  margin-bottom: 18px;
  display: grid;
  place-items: center;
  border-radius: 50%;
  background: #fff1a3;
  color: #4d346f;
  font-weight: 900;
}

.flow-list strong,
.trust-grid strong {
  display: block;
  color: #251c36;
  font-size: 1.1rem;
  font-weight: 900;
}

.flow-list p,
.trust-grid p,
.comparison-visual p {
  margin: 9px 0 0;
  color: #5a4a68;
  line-height: 1.48;
}

.comparison-band {
  background:
    linear-gradient(180deg, rgba(255, 248, 237, 0.96), rgba(255, 241, 224, 0.92)),
    #fff3e2;
}

.comparison-visual {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px;
  margin-top: 28px;
}

.comparison-visual > div {
  padding: 22px;
}

.comparison-visual span {
  display: block;
  margin-bottom: 14px;
  color: #5f438f;
  font-size: 0.82rem;
  font-weight: 900;
  text-transform: uppercase;
}

.comparison-visual p {
  padding: 10px 12px;
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.72);
}

.trust-band {
  background: #edf8ee;
}

.trust-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 14px;
  margin-top: 28px;
}

.trust-grid article {
  padding: 22px;
}

.final-band {
  padding: 72px 24px 86px;
  align-items: center;
  background: #fff8ed;
  text-align: center;
}

.final-band h2 {
  flex-basis: 100%;
}

button:focus-visible,
a:focus-visible {
  outline: 3px solid rgba(102, 80, 157, 0.42);
  outline-offset: 3px;
}

@media (max-width: 820px) {
  .intro-nav {
    position: relative;
    width: 100%;
    padding: 12px 16px;
    background: rgba(255, 248, 237, 0.84);
  }

  .intro-hero {
    min-height: 82svh;
    padding-top: 40px;
  }

  .scene-family {
    left: -18px;
    transform: scale(0.74);
    transform-origin: bottom left;
  }

  .scene-phone {
    right: 9%;
    bottom: 17%;
  }

  .scene-book {
    right: 3%;
    bottom: 8%;
  }

  .moment-band {
    grid-template-columns: 1fr;
    gap: 24px;
  }

  .moment-copy {
    max-width: none;
    justify-self: stretch;
  }

  .moment-reel,
  .reel-stage {
    min-height: 470px;
  }

  .reel-phone {
    width: 170px;
    right: 24px;
    bottom: 66px;
  }

  .reel-family {
    left: 2px;
    transform-origin: bottom left;
  }

  .flow-list,
  .comparison-visual,
  .trust-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 520px) {
  .intro-nav {
    gap: 6px;
    padding-inline: 10px;
  }

  .intro-logo {
    font-size: 1.05rem;
  }

  .intro-links {
    gap: 4px;
  }

  .intro-links button,
  .intro-links a {
    min-height: 34px;
    padding-inline: 8px;
    font-size: 0.84rem;
  }

  .hero-copy {
    padding-top: 20px;
  }

  .hero-copy h1 {
    font-size: 3.7rem;
  }

  .hero-subtitle {
    font-size: 1.14rem;
  }

  .privacy-pills {
    gap: 7px;
  }

  .privacy-pills li {
    padding: 7px 10px;
    font-size: 0.78rem;
  }

  .scene-sun {
    right: 4%;
    top: 16%;
  }

  .scene-phone {
    min-width: 136px;
    right: -7%;
    bottom: 1%;
    opacity: 0.82;
    transform: rotate(5deg) scale(0.9);
  }

  .scene-book {
    width: 78vw;
  }

  .intro-section {
    padding: 54px 18px;
  }

  .moment-copy h2 {
    font-size: 2.2rem;
  }

  .moment-reel,
  .reel-stage {
    min-height: 490px;
  }

  .reel-cards {
    width: calc(100% - 28px);
    left: 14px;
    top: 14px;
  }

  .reel-cards strong {
    font-size: 1.08rem;
  }

  .reel-phone {
    width: 150px;
    right: -8px;
    bottom: 70px;
  }

  .reel-book {
    width: 86%;
    bottom: 28px;
  }

  .reel-family {
    left: -24px;
    bottom: 22px;
    transform: scale(0.82);
    transform-origin: bottom left;
  }

  .promise-band p {
    text-align: left;
  }
}
</style>

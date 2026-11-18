/**
 * Placeholder shell for the single page (ARCHITECTURE.md section 12).
 *
 * Sections are laid out in their final order so the component tasks (T3.1–T3.3)
 * can replace each one without moving the page furniture.
 */

import { apiMode } from "./api";
import { useApp } from "./state/appContext";

export function App() {
  const { state } = useApp();
  const selectedVoice = state.voices.find((voice) => voice.id === state.selectedVoiceId);

  return (
    <div className="app">
      <header className="app-header">
        <h1>tts</h1>
        <p className="tagline">Local text to speech with synchronized subtitles.</p>
        {apiMode === "mock" ? <p className="badge">Mock mode: sample data</p> : null}
      </header>

      {state.error !== null && (
        <section className="section banner" role="alert" aria-labelledby="error-heading">
          <h2 id="error-heading">Something went wrong</h2>
          <p>{state.error.message}</p>
        </section>
      )}

      <section className="section" aria-labelledby="input-heading">
        <h2 id="input-heading">Text</h2>
        <p className="hint">Paste text or upload a .txt file for review.</p>
        <p className="stat">
          {state.inputText.length.toLocaleString()} characters
          {state.sourceFilename === null ? "" : ` · ${state.sourceFilename}`}
        </p>
      </section>

      <section className="section" aria-labelledby="voice-heading">
        <h2 id="voice-heading">Voice and settings</h2>
        <p className="hint">Choose an installed voice, preview it, and set rate and volume.</p>
        <p className="stat">
          {state.voices.length === 0
            ? "No voices installed"
            : `${state.voices.length} voice${state.voices.length === 1 ? "" : "s"} · ${
                selectedVoice?.name ?? "none selected"
              }`}
        </p>
        <p className="stat">
          Rate {state.rate.toFixed(1)}× · Volume {Math.round(state.volume * 100)}%
        </p>
      </section>

      <section className="section" aria-labelledby="generate-heading">
        <h2 id="generate-heading">Generate</h2>
        <p className="hint">Start, watch progress, and cancel a generation.</p>
        <p className="stat">
          {state.current === null
            ? "Nothing generated yet"
            : `${state.current.status} · sentence ${state.current.sentenceIndex} of ${
                state.current.sentenceCount
              }`}
        </p>
      </section>

      <section className="section" aria-labelledby="playback-heading">
        <h2 id="playback-heading">Playback and subtitles</h2>
        <p className="hint">Audio, word highlighting, seek, and downloads appear here.</p>
      </section>

      <section className="section" aria-labelledby="history-heading">
        <h2 id="history-heading">History</h2>
        <p className="hint">Recent generations can be restored or deleted.</p>
        <p className="stat">
          {state.history.total} saved generation{state.history.total === 1 ? "" : "s"}
        </p>
      </section>

      <footer className="app-footer">
        <p>Everything runs on this machine; nothing is uploaded.</p>
      </footer>
    </div>
  );
}

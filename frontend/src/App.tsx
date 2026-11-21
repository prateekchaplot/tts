/**
 * Single page layout (ARCHITECTURE.md section 12).
 *
 * Sections stack in their documented order. The playback and history sections
 * stay as placeholders until T3.2/T3.3 replace them, so each task can own its
 * own component file.
 */

import { useEffect } from "react";
import { api, apiMode } from "./api";
import { toApiError } from "./api/client";
import { ErrorBanner } from "./components/ErrorBanner";
import { GenerateBar } from "./components/GenerateBar";
import { InputPanel } from "./components/InputPanel";
import { VoicePanel } from "./components/VoicePanel";
import { clampRate, clampVolume } from "./components/validation";
import { useApp } from "./state/appContext";

export function App() {
  const { state, dispatch } = useApp();

  useEffect(() => {
    let cancelled = false;

    async function bootstrap(): Promise<void> {
      try {
        const list = await api.listVoices();
        if (cancelled) {
          return;
        }
        dispatch({ type: "VOICES_LOADED", voices: list.items });
        if (list.items.some((voice) => voice.id === list.defaultVoiceId)) {
          dispatch({ type: "SET_VOICE", voiceId: list.defaultVoiceId });
        }

        const settings = await api.getSettings();
        if (cancelled) {
          return;
        }
        dispatch({ type: "SET_RATE", rate: clampRate(settings.rate) });
        dispatch({ type: "SET_VOLUME", volume: clampVolume(settings.volume) });
        if (list.items.some((voice) => voice.id === settings.defaultVoiceId)) {
          dispatch({ type: "SET_VOICE", voiceId: settings.defaultVoiceId });
        }
      } catch (error) {
        if (cancelled) {
          return;
        }
        const failure = toApiError(error);
        dispatch({
          type: "SET_ERROR",
          error: { code: failure.code, message: failure.message, details: failure.details },
        });
      }
    }

    void bootstrap();
    return () => {
      cancelled = true;
    };
  }, [dispatch]);

  return (
    <div className="app">
      <header className="app-header">
        <h1>tts</h1>
        <p className="tagline">Local text to speech with synchronized subtitles.</p>
        {apiMode === "mock" ? <p className="badge">Mock mode: sample data</p> : null}
      </header>

      <ErrorBanner />
      <InputPanel />
      <VoicePanel />
      <GenerateBar />

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

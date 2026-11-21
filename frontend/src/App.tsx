/**
 * Single page layout (ARCHITECTURE.md section 12).
 *
 * Sections stack in their documented order: ErrorBanner, InputPanel,
 * VoicePanel, GenerateBar, PlaybackPanel, HistoryPanel.
 */

import { useEffect } from "react";
import { api, apiMode } from "./api";
import { toApiError } from "./api/client";
import { ErrorBanner } from "./components/ErrorBanner";
import { GenerateBar } from "./components/GenerateBar";
import { HistoryPanel } from "./components/HistoryPanel";
import { InputPanel } from "./components/InputPanel";
import { PlaybackPanel } from "./components/PlaybackPanel";
import { VoicePanel } from "./components/VoicePanel";
import { clampRate, clampVolume } from "./components/validation";
import { useApp } from "./state/appContext";

export function App() {
  const { dispatch } = useApp();

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

      <PlaybackPanel />

      <HistoryPanel />

      <footer className="app-footer">
        <p>Everything runs on this machine; nothing is uploaded.</p>
      </footer>
    </div>
  );
}

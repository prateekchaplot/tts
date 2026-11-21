import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { AppProvider } from "../state/appContext";
import type { Voice } from "../types/contracts";
import { VoicePanel, voiceLabel } from "./VoicePanel";

function renderPanel(): string {
  return renderToStaticMarkup(
    <AppProvider>
      <VoicePanel />
    </AppProvider>,
  );
}

const voice: Voice = {
  id: "de_DE-thorsten-medium",
  name: "Thorsten",
  language: "de_DE",
  gender: "male",
  sampleRate: 22050,
};

describe("VoicePanel", () => {
  it("shows the install remedy and disables controls when the store is empty (FR-02)", () => {
    const html = renderPanel();
    expect(html).toContain("No voices installed. Run");
    expect(html).toContain("tts add-voice");
    expect(html).toMatch(/<select[^>]*disabled/);
    expect(html).toMatch(/<button[^>]*disabled[^>]*>Preview voice<\/button>/);
  });

  it("renders the contract ranges and numeric values (AC6)", () => {
    const html = renderPanel();
    expect(html).toContain('min="0.5"');
    expect(html).toContain('max="2"');
    expect(html).toContain('step="0.1"');
    expect(html).toContain('min="0"');
    expect(html).toContain('max="1"');
    expect(html).toContain('step="0.05"');
    expect(html).toContain("1.0×");
    expect(html).toContain("100%");
  });

  it("labels a voice with language and gender where available", () => {
    expect(voiceLabel(voice)).toBe("Thorsten · de_DE · male");
    expect(voiceLabel({ ...voice, gender: null })).toBe("Thorsten · de_DE");
  });
});

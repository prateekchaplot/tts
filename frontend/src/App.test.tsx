import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { App } from "./App";
import { AppProvider } from "./state/appContext";

function renderApp(): string {
  return renderToStaticMarkup(
    <AppProvider>
      <App />
    </AppProvider>,
  );
}

describe("App shell", () => {
  it("renders the section stack in the documented order", () => {
    const html = renderApp();
    const headings = [
      "Text",
      "Voice and settings",
      "Generate",
      "Playback and subtitles",
      "History",
    ];
    const positions = headings.map((heading) => html.indexOf(heading));
    expect(positions.every((position) => position >= 0)).toBe(true);
    expect([...positions].sort((a, b) => a - b)).toEqual(positions);
  });

  it("renders the input, voice, and generate controls", () => {
    const html = renderApp();
    expect(html).toContain('id="input-text"');
    expect(html).toContain('accept=".txt,text/plain"');
    expect(html).toContain('id="voice-select"');
    expect(html).toContain('id="rate-slider"');
    expect(html).toContain('id="volume-slider"');
    expect(html).toMatch(/<button[^>]*disabled[^>]*>Generate audio<\/button>/);
  });

  it("shows the no-voice state and empty history", () => {
    const html = renderApp();
    expect(html).toContain("No voices installed");
    expect(html).toContain("0 saved generations");
    expect(html).toContain("Nothing generated yet");
  });

  it("offers a skip link to the main landmark as the first control", () => {
    const html = renderApp();
    expect(html.indexOf('class="skip-link"')).toBeGreaterThan(0);
    expect(html.indexOf('class="skip-link"')).toBeLessThan(html.indexOf("<header"));
    expect(html).toMatch(/<a class="skip-link" href="#main">Skip to main content<\/a>/);
    expect(html).toContain('<main id="main" tabindex="-1">');
  });

  it("keeps the footer outside the main landmark", () => {
    const html = renderApp();
    expect(html.indexOf("</main>")).toBeLessThan(html.indexOf("<footer"));
  });

  it("has no alert banner until an error is dispatched", () => {
    expect(renderApp()).not.toContain('role="alert"');
  });

  it("hides the mock badge in live mode", () => {
    expect(renderApp()).not.toContain("Mock mode");
  });
});

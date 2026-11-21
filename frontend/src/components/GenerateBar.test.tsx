import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { AppProvider } from "../state/appContext";
import { GenerateBar } from "./GenerateBar";

function renderBar(): string {
  return renderToStaticMarkup(
    <AppProvider>
      <GenerateBar />
    </AppProvider>,
  );
}

describe("GenerateBar", () => {
  it("disables generation with an install explanation when there are no voices", () => {
    const html = renderBar();
    expect(html).toMatch(/<button[^>]*disabled[^>]*>Generate audio<\/button>/);
    expect(html).toContain("No voices installed, so generation is disabled.");
    expect(html).toContain("tts add-voice");
    expect(html).not.toContain("Cancel generation");
  });

  it("starts from the empty state without a progress bar", () => {
    const html = renderBar();
    expect(html).toContain("Nothing generated yet");
    expect(html).not.toContain("<progress");
  });
});

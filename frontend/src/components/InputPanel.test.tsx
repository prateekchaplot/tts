import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { AppProvider } from "../state/appContext";
import { InputPanel } from "./InputPanel";

function renderPanel(): string {
  return renderToStaticMarkup(
    <AppProvider>
      <InputPanel />
    </AppProvider>,
  );
}

describe("InputPanel", () => {
  it("renders an editable textarea and the character budget", () => {
    const html = renderPanel();
    expect(html).toContain('id="input-text"');
    expect(html).toContain("<textarea");
    expect(html).toContain("0 / 50,000 characters");
  });

  it("names the accepted upload type (AC3)", () => {
    const html = renderPanel();
    expect(html).toContain('accept=".txt,text/plain"');
    expect(html).toContain("Only plain-text .txt files up to 2 MB are accepted.");
  });

  it("shows no length warning for empty input", () => {
    expect(renderPanel()).not.toContain("Shorten the text before generating.");
  });
});

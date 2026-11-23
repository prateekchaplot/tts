import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import type { ErrorInfo } from "../types/contracts";
import { ErrorBannerContent } from "./ErrorBanner";

function renderBanner(code = "ENGINE_ERROR", message = "The speech engine failed."): string {
  return renderToStaticMarkup(
    <ErrorBannerContent
      error={{ code: code as ErrorInfo["code"], message, details: null }}
      onDismiss={() => undefined}
    />,
  );
}

describe("ErrorBannerContent", () => {
  it("announces the problem, the server message, and the corrective action", () => {
    const html = renderBanner();
    expect(html).toContain('role="alert"');
    expect(html).toContain("Something went wrong");
    expect(html).toContain("The speech engine failed.");
    expect(html).toContain("What you can do");
    expect(html).toContain("Try a shorter text or a different voice.");
  });

  it("makes the heading focusable so focus can move there", () => {
    expect(renderBanner()).toMatch(/<h2[^>]*tabindex="-1"/);
  });

  it("labels the dismiss control for screen readers", () => {
    const html = renderBanner();
    expect(html).toContain('aria-label="Dismiss error message"');
    expect(html).toContain(">Dismiss</button>");
  });

  it("still gives advice for a code outside the fixed set", () => {
    const html = renderBanner("SOMETHING_ELSE", "Unexpected problem.");
    expect(html).toContain("Try again. If the problem continues");
  });
});

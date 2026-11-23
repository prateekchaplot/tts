/**
 * Single error surface for the whole page (ARCHITECTURE.md section 16: every
 * frontend error goes through here with its message and corrective action).
 *
 * Accessibility (NFR-04): `role="alert"` announces the error, the message and
 * its corrective action are both read, and focus moves to the heading so a
 * keyboard user is not stranded at the trigger. Dismiss returns focus to the
 * control that was focused when the error appeared.
 */

import { useEffect, useRef, type Ref } from "react";
import { useApp } from "../state/appContext";
import { errorGuidance, strings } from "../strings";
import type { ErrorInfo } from "../types/contracts";

export interface ErrorBannerContentProps {
  error: ErrorInfo;
  onDismiss: () => void;
  headingRef?: Ref<HTMLHeadingElement>;
}

/** Presentational banner; exported so the copy can be tested without effects. */
export function ErrorBannerContent({ error, onDismiss, headingRef }: ErrorBannerContentProps) {
  return (
    <section className="section banner" role="alert" aria-labelledby="error-heading">
      <div className="banner-heading">
        <h2 id="error-heading" ref={headingRef} tabIndex={-1}>
          {strings.error.heading}
        </h2>
        <button
          type="button"
          className="secondary"
          aria-label={strings.error.dismissLabel}
          onClick={onDismiss}
        >
          {strings.error.dismiss}
        </button>
      </div>
      <p>{error.message}</p>
      <p className="hint error-guidance">
        <strong>{strings.error.guidanceLabel}:</strong> {errorGuidance(error.code)}
      </p>
    </section>
  );
}

export function ErrorBanner() {
  const { state, dispatch } = useApp();
  const headingRef = useRef<HTMLHeadingElement | null>(null);
  const restoreRef = useRef<HTMLElement | null>(null);
  const error = state.error;

  useEffect(() => {
    if (error === null) {
      return;
    }
    const active = document.activeElement;
    if (active instanceof HTMLElement && active !== document.body) {
      restoreRef.current = active;
    }
    headingRef.current?.focus();
  }, [error]);

  if (error === null) {
    return null;
  }

  function dismiss(): void {
    const target = restoreRef.current;
    restoreRef.current = null;
    dispatch({ type: "CLEAR_ERROR" });
    if (target !== null && target.isConnected) {
      target.focus();
    }
  }

  return <ErrorBannerContent error={error} onDismiss={dismiss} headingRef={headingRef} />;
}

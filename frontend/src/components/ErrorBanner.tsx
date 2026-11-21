/**
 * Single error surface for the whole page (ARCHITECTURE.md section 16: every
 * frontend error goes through here with its message and corrective action).
 */

import { useApp } from "../state/appContext";

export function ErrorBanner() {
  const { state, dispatch } = useApp();

  if (state.error === null) {
    return null;
  }

  return (
    <section className="section banner" role="alert" aria-labelledby="error-heading">
      <div className="banner-heading">
        <h2 id="error-heading">Something went wrong</h2>
        <button
          type="button"
          className="secondary"
          onClick={() => {
            dispatch({ type: "CLEAR_ERROR" });
          }}
        >
          Dismiss
        </button>
      </div>
      <p>{state.error.message}</p>
    </section>
  );
}

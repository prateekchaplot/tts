/**
 * Text input and plain-text upload (ARCHITECTURE.md section 12, FR-01).
 *
 * Uploading never starts a generation: the decoded text lands in the textarea
 * so the user can review or edit it first (section 9.2).
 */

import type { ChangeEvent } from "react";
import { api } from "../api";
import { toApiError } from "../api/client";
import { useApp } from "../state/appContext";
import { MAX_INPUT_CHARS, inputTooLongMessage } from "./validation";

export function InputPanel() {
  const { state, dispatch } = useApp();
  const tooLong = state.inputText.length > MAX_INPUT_CHARS;

  async function handleFile(event: ChangeEvent<HTMLInputElement>): Promise<void> {
    const input = event.currentTarget;
    const file = input.files?.[0];
    input.value = "";
    if (file === undefined) {
      return;
    }
    try {
      const upload = await api.uploadFile(file);
      dispatch({ type: "SET_INPUT", text: upload.text });
      dispatch({ type: "SET_SOURCE_FILE", filename: upload.filename });
    } catch (error) {
      const failure = toApiError(error);
      dispatch({
        type: "SET_ERROR",
        error: { code: failure.code, message: failure.message, details: failure.details },
      });
    }
  }

  return (
    <section className="section" aria-labelledby="input-heading">
      <h2 id="input-heading">Text</h2>

      <div className="field">
        <label htmlFor="input-text">Text to speak</label>
        <textarea
          id="input-text"
          value={state.inputText}
          rows={10}
          placeholder="Paste or type the text you want to hear. Paragraph breaks are preserved."
          aria-describedby="input-help input-count"
          onChange={(event) => {
            dispatch({ type: "SET_INPUT", text: event.target.value });
          }}
        />
      </div>

      <div className="field-row">
        <label htmlFor="input-file">Upload plain text</label>
        <input
          id="input-file"
          type="file"
          accept=".txt,text/plain"
          aria-describedby="input-help"
          onChange={(event) => {
            void handleFile(event);
          }}
        />
        <span className="hint" id="input-help">
          Only plain-text .txt files up to 2 MB are accepted.
        </span>
      </div>

      <p id="input-count" className={tooLong ? "stat warning" : "stat"} aria-live="polite">
        {state.inputText.length.toLocaleString()} / {MAX_INPUT_CHARS.toLocaleString()} characters
        {state.sourceFilename === null ? "" : ` · loaded from ${state.sourceFilename}`}
      </p>

      {tooLong ? (
        <p className="stat warning" role="status">
          {inputTooLongMessage(state.inputText.length)} Shorten the text before generating.
        </p>
      ) : null}
    </section>
  );
}

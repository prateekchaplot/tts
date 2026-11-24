/**
 * Per-run identifiers.
 *
 * The suite runs against a persistent library, so texts carry a token that is
 * unique to this run. That keeps "find my row" assertions stable when the same
 * specs run repeatedly on a developer machine.
 */

export const RUN_TOKEN = `run${Date.now().toString(36)}`;

/** Appends the run token to a sentence without changing its reading much. */
export function uniqueText(sentence: string): string {
  return `${sentence.trim()} Acceptance run ${RUN_TOKEN}.`;
}

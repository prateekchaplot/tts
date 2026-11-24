/**
 * Minimal ambient declarations for the Node builtins the suite touches.
 *
 * This repository has no root `package.json` and `@types/node` is not a
 * dependency: Playwright ships no Node typings of its own (ARCHITECTURE.md
 * section 16 forbids adding packages without an architecture line). Declaring
 * the handful of globals and modules used here keeps `tsc -p tests/e2e`
 * meaningful without a new dependency. If `@types/node` is ever added, delete
 * this file.
 */

declare module "node:path" {
  const path: {
    join(...parts: string[]): string;
    resolve(...parts: string[]): string;
    dirname(value: string): string;
    basename(value: string): string;
  };
  export default path;
}

declare module "node:fs" {
  export function readFileSync(path: string): Uint8Array;
  export function existsSync(path: string): boolean;
}

declare class TextDecoder {
  decode(input?: Uint8Array): string;
}

declare function btoa(data: string): string;

declare const __dirname: string;

declare const process: {
  env: Record<string, string | undefined>;
  execPath: string;
  platform: string;
};

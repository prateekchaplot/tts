import { afterEach, describe, expect, it, vi } from "vitest";

afterEach(() => {
  vi.unstubAllEnvs();
  vi.resetModules();
});

describe("api selection", () => {
  it("defaults to the live client", async () => {
    vi.resetModules();
    const module = await import("./index");
    expect(module.apiMode).toBe("live");
  });

  it("selects the mock when VITE_API_MODE=mock", async () => {
    vi.stubEnv("VITE_API_MODE", "mock");
    vi.resetModules();
    const module = await import("./index");
    expect(module.apiMode).toBe("mock");
    await expect(module.api.getHealth()).resolves.toMatchObject({ voicesInstalled: 2 });
  });
});

// @vitest-environment node
import { createRequire } from "node:module";

describe("UI config files", () => {
  it("loads postcss config with expected plugins", async () => {
    const mod = await import("../../postcss.config.js");
    expect(mod.default).toBeTruthy();
    expect(mod.default.plugins).toHaveProperty("tailwindcss");
    expect(mod.default.plugins).toHaveProperty("autoprefixer");
  });

  it("loads tailwind config with theme and plugin", async () => {
    const mod = await import("../../tailwind.config.js");
    expect(mod.default.darkMode).toBe("class");
    expect(Array.isArray(mod.default.content)).toBe(true);
    expect(mod.default.theme.extend.colors["sre-bg"]).toContain("--sre-bg");
    expect(mod.default.plugins.length).toBeGreaterThan(0);
  });

  it("loads eslint config rules", () => {
    const require = createRequire(import.meta.url);
    const config = require("../../eslint.config.cjs");

    expect(Array.isArray(config)).toBe(true);
    expect(config[0].rules["react-hooks/rules-of-hooks"]).toBe("error");
    expect(config[0].rules["react/react-in-jsx-scope"]).toBe("off");
  });

  it("builds vite config in default and analyze modes", async () => {
    const originalAnalyze = process.env.ANALYZE;
    const mod = await import("../../vite.config.js");

    delete process.env.ANALYZE;
    const normal = mod.default({ mode: "test" });
    expect(normal.server.host).toBe("0.0.0.0");
    expect(normal.plugins.length).toBe(1);

    process.env.ANALYZE = "true";
    const analyzed = mod.default({ mode: "test" });
    expect(analyzed.plugins.length).toBe(2);

    if (originalAnalyze === undefined) {
      delete process.env.ANALYZE;
    } else {
      process.env.ANALYZE = originalAnalyze;
    }
  });
});

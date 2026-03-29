import { describe, expect, it } from "vitest";

import {
  DURATION_PATTERN,
  DEFAULT_FORM,
  RULE_TEMPLATES,
  createLabelPairsFromRule,
  validateRuleForm,
} from "../ruleEditorUtils";

describe("ruleEditorUtils", () => {
  it("exports expected defaults and templates", () => {
    expect(DEFAULT_FORM.duration).toBe("1m");
    expect(RULE_TEMPLATES.length).toBeGreaterThan(0);
    expect(DURATION_PATTERN.test("5m")).toBe(true);
    expect(DURATION_PATTERN.test("5 minutes")).toBe(false);
  });

  it("validates required fields and warnings for weak expressions", () => {
    const { errors, warnings } = validateRuleForm(
      {
        name: "",
        expr: "rate(http_requests_total)",
        duration: "invalid",
        severity: "urgent",
        annotations: { summary: "" },
      },
      [{ key: "team", value: "ops" }, { key: "team", value: "platform" }],
    );

    expect(errors.name).toMatch(/required/i);
    expect(errors.duration).toMatch(/prometheus format/i);
    expect(errors.severity).toMatch(/must be info, warning, or critical/i);
    expect(errors.labels).toContain("team");
    expect(warnings.some((item) => item.includes("comparison operator"))).toBe(true);
    expect(warnings.some((item) => item.includes("range selector"))).toBe(true);
    expect(warnings.some((item) => item.includes("Summary is empty"))).toBe(true);
  });

  it("detects unbalanced parentheses and builds label pairs", () => {
    const result = validateRuleForm(
      {
        name: "CPU",
        expr: "sum(rate(http_requests_total[5m])",
        duration: "5m",
        severity: "warning",
        annotations: { summary: "CPU high" },
      },
      [{ key: "team", value: "ops" }],
    );

    expect(result.errors.expr).toMatch(/unbalanced parentheses/i);

    const pairs = createLabelPairsFromRule({ labels: { env: "prod", team: "ops" } });
    expect(pairs).toHaveLength(2);
    expect(pairs[0].id).toContain("label-0-");
    expect(pairs.map((item) => item.key)).toEqual(expect.arrayContaining(["env", "team"]));
  });
});
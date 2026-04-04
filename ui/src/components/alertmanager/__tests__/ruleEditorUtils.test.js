import { describe, expect, it } from "vitest";

import {
  DURATION_PATTERN,
  DEFAULT_FORM,
  filterSelectableChannels,
  isChannelSelectableForRuleVisibility,
  normalizeRuleOrChannelVisibility,
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

  it("applies channel visibility hierarchy for selection", () => {
    expect(normalizeRuleOrChannelVisibility("tenant")).toBe("public");
    expect(isChannelSelectableForRuleVisibility("private", "private")).toBe(true);
    expect(isChannelSelectableForRuleVisibility("private", "tenant")).toBe(false);
    expect(isChannelSelectableForRuleVisibility("group", "private")).toBe(true);
    expect(
      isChannelSelectableForRuleVisibility("group", "group", {
        ruleSharedGroupIds: ["g1"],
        channelSharedGroupIds: ["g1"],
      }),
    ).toBe(true);
    expect(
      isChannelSelectableForRuleVisibility("group", "group", {
        ruleSharedGroupIds: ["g1"],
        channelSharedGroupIds: ["g2"],
      }),
    ).toBe(false);
    expect(isChannelSelectableForRuleVisibility("group", "tenant")).toBe(false);
    expect(isChannelSelectableForRuleVisibility("tenant", "private")).toBe(true);
    expect(isChannelSelectableForRuleVisibility("tenant", "group")).toBe(true);
    expect(isChannelSelectableForRuleVisibility("tenant", "tenant")).toBe(false);

    const filtered = filterSelectableChannels(
      [
        { id: "a", visibility: "private", sharedGroupIds: [] },
        { id: "b", visibility: "group", sharedGroupIds: ["g1"] },
        { id: "d", visibility: "group", sharedGroupIds: ["g2"] },
        { id: "c", visibility: "tenant" },
      ],
      "group",
      { ruleSharedGroupIds: ["g1"] },
    );
    expect(filtered.map((channel) => channel.id)).toEqual(["a", "b"]);
  });
});

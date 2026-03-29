import { describe, expect, it } from "vitest";
import {
  buildServiceGraphData,
  buildServiceGraphEdges,
  buildServiceGraphInsights,
  buildServiceGraphNodes,
  layoutServiceGraph,
} from "../serviceGraphUtils";

describe("serviceGraphUtils", () => {
  it("builds graph data from spans and parent relationships", () => {
    const traces = [
      {
        traceID: "t1",
        spans: [
          {
            spanId: "1",
            serviceName: "api",
            duration: 200000,
            status: { code: "OK" },
          },
          {
            spanId: "2",
            parentSpanId: "1",
            serviceName: "db",
            duration: 500000,
            status: { code: "ERROR" },
          },
        ],
      },
    ];

    const data = buildServiceGraphData(traces);
    expect(data.services.has("api")).toBe(true);
    expect(data.services.has("db")).toBe(true);
    expect(data.edges.has("api->db")).toBe(true);
  });

  it("builds insights and nodes from graph data", () => {
    const graphData = buildServiceGraphData([
      {
        traceID: "t1",
        spans: [
          {
            spanId: "1",
            serviceName: "api",
            duration: 1000,
            status: { code: "OK" },
          },
          {
            spanId: "2",
            parentSpanId: "1",
            serviceName: "db",
            duration: 2000,
            status: { code: "OK" },
          },
        ],
      },
    ]);

    const insights = buildServiceGraphInsights(graphData);
    expect(Array.isArray(insights.serviceStats)).toBe(true);

    const nodes = buildServiceGraphNodes(graphData);
    expect(nodes.length).toBe(2);

    const layout = layoutServiceGraph(nodes, []);
    expect(layout.nodes.length).toBe(2);
  });

  it("builds styled trace edges when traceEdges exist", () => {
    const data = buildServiceGraphData([
      {
        traceID: "trace-12345678",
        spans: [
          { spanId: "1", serviceName: "api", duration: 1500 },
          {
            spanId: "2",
            parentSpanId: "1",
            serviceName: "db",
            duration: 3500,
            status: { code: "ERROR" },
          },
        ],
      },
    ]);

    const edges = buildServiceGraphEdges(data, null, "api");
    expect(edges.length).toBeGreaterThan(0);
    expect(edges[0].label).toContain("calls");
    expect(edges[0].style).toHaveProperty("stroke");
    expect(edges[0].markerEnd).toHaveProperty("type");
  });

  it("lays out disconnected components with stable dimensions", () => {
    const nodes = [
      { id: "a", position: { x: 0, y: 0 }, data: {} },
      { id: "b", position: { x: 0, y: 0 }, data: {} },
      { id: "c", position: { x: 0, y: 0 }, data: {} },
    ];
    const edges = [{ source: "a", target: "b" }];

    const layout = layoutServiceGraph(nodes, edges);
    expect(layout.nodes).toHaveLength(3);
    layout.nodes.forEach((node) => {
      expect(node.style.width).toBe(260);
      expect(node.style.height).toBe(140);
      expect(Number.isFinite(node.position.x)).toBe(true);
      expect(Number.isFinite(node.position.y)).toBe(true);
    });
  });
});

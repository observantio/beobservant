import { useState } from "react";
import PropTypes from "prop-types";
import { useLayoutMode } from "../../contexts/LayoutModeContext";
import { Card } from "../ui";
import { AgentActivitySection } from "./AgentActivitySection";
import { DataVolume } from "./DataVolume";
import { SystemMetricsCard } from "./SystemMetricsCard";
import { usePersistentOrder } from "../../hooks";

export function DashboardLayout({ dashboardData, agentData }) {
  const { sidebarMode } = useLayoutMode();
  const [draggedIndex, setDraggedIndex] = useState(null);

  const layoutComponents = [
    {
      id: "notice",
      className: sidebarMode
        ? "sm:col-span-2 xl:col-span-full min-w-0"
        : "lg:col-span-1",
      renderAsNotice: true,
      content: (
        <div className="space-y-4">
          <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
            <div className="flex items-center gap-4">
              {sidebarMode ? (
                <div className="flex h-14 w-14 items-center justify-center rounded-3xl border border-sre-border bg-sre-surface-light shadow-sm">
                  <img
                    src="/wolf.png"
                    alt="Observantio wolf logo"
                    className="h-10 w-10"
                  />
                </div>
              ) : null}
              <div>
                <h2 className="text-xl font-semibold text-sre-text">
                  Welcome to Observantio
                </h2>
                <div className="text-sm">
                  Observability made beautiful
                </div>
              </div>
            </div>
          </div>
          <div>
            <p className="text-sm text-sre-text-muted mt-1 leading-relaxed">
              Observantio is an open-source observability tool that provides a unified platform for monitoring, alerting, and log management. It is designed to be user-friendly and customizable, allowing you to easily visualize and analyze your system's performance and health. Powered by LGTM, Alert manager, Resolver and Notifier.
            </p>
            <p className="text-xs text-sre-text-muted mt-3">
              Licensed under Apache License 2.0. You are free to use, modify,
              and distribute with proper attribution and required NOTICE/license credit.
            </p>
          </div>
        </div>
      ),
    },
    {
      id: "active-otel-agents",
      title: "Active OTEL Agents",
      subtitle: "Agents Activity",
      className: "",
      content: (
        <AgentActivitySection
          loading={agentData.loadingAgents}
          agents={agentData.agentActivity}
        />
      ),
    },
    {
      id: "data-volume",
      className: "",
      content: (
        <DataVolume
          loadingLogs={dashboardData.loadingLogs}
          logVolumeSeries={dashboardData.logVolumeSeries}
        />
      ),
    },
    {
      id: "server-metrics",
      title: "Proxy Plane",
      subtitle:
        dashboardData.systemMetrics?.stress?.message ||
        "Process resource utilization",
      className: sidebarMode ? "sm:col-span-2 xl:col-span-1" : "",
      content: (
        <SystemMetricsCard
          loading={dashboardData.loadingSystemMetrics}
          systemMetrics={dashboardData.systemMetrics}
        />
      ),
    },
  ];

  const [layoutOrder, setLayoutOrder] = usePersistentOrder(
    "dashboard-layout-order",
    layoutComponents.length,
  );

  const sanitizedLayoutOrder = (() => {
    const max = layoutComponents.length;
    const seen = new Set();
    const parsed = Array.isArray(layoutOrder) ? layoutOrder : [];
    const result = [];
    for (const idx of parsed) {
      if (typeof idx === "number" && idx >= 0 && idx < max && !seen.has(idx)) {
        result.push(idx);
        seen.add(idx);
      }
    }
    for (let i = 0; i < max; i++) {
      if (!seen.has(i)) result.push(i);
    }
    return result;
  })();

  const handleLayoutDragStart = (e, index) => {
    setDraggedIndex(index);
    e.dataTransfer.effectAllowed = "move";
  };

  const handleLayoutDrop = (e, dropIndex) => {
    e.preventDefault();
    if (draggedIndex === null || draggedIndex === dropIndex) return;

    const newOrder = [...layoutOrder];
    const draggedItem = newOrder[draggedIndex];
    newOrder.splice(draggedIndex, 1);
    newOrder.splice(dropIndex, 0, draggedItem);

    setLayoutOrder(newOrder);
    setDraggedIndex(null);
  };

  const handleDragOver = (e) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = "move";
  };

  const handleDragEnd = () => {
    setDraggedIndex(null);
  };

  const gridClass = sidebarMode
    ? "grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-[minmax(280px,0.95fr)_minmax(320px,1.1fr)_minmax(420px,1.95fr)] gap-6"
    : "grid grid-cols-1 lg:grid-cols-4 gap-6";

  return (
    <div className={gridClass}>
      {sanitizedLayoutOrder.map((layoutIndex, displayIndex) => {
        const component = layoutComponents[layoutIndex];
        if (!component) return null;
        return (
          <div
            key={component.id}
            className={`${component.className || ""} transition-transform duration-200 ease-out will-change-transform ${
              draggedIndex === displayIndex
                ? "opacity-50 scale-95 shadow-xl"
                : ""
            }`}
          >
            {component.renderAsNotice ? (
              <div
                className="relative rounded-xl border border-sre-border bg-gradient-to-r from-sre-surface to-sre-bg-alt p-5 cursor-move"
                draggable
                onDragStart={(e) => handleLayoutDragStart(e, displayIndex)}
                onDragOver={handleDragOver}
                onDrop={(e) => handleLayoutDrop(e, displayIndex)}
                onDragEnd={handleDragEnd}
              >
                <div className="absolute top-4 right-4 text-sre-text-muted hover:text-sre-text transition-colors z-10">
                  <span
                    className="material-icons text-sm drag-handle"
                    aria-hidden
                  >
                    drag_indicator
                  </span>
                </div>
                {component.content}
              </div>
            ) : (
              <Card
                title={component.title}
                subtitle={component.subtitle}
                className="cursor-move relative"
                draggable
                onDragStart={(e) => handleLayoutDragStart(e, displayIndex)}
                onDragOver={handleDragOver}
                onDrop={(e) => handleLayoutDrop(e, displayIndex)}
                onDragEnd={handleDragEnd}
              >
                <div className="absolute top-4 right-4 text-sre-text-muted hover:text-sre-text transition-colors z-10">
                  <span
                    className="material-icons text-sm drag-handle"
                    aria-hidden
                  >
                    drag_indicator
                  </span>
                </div>
                {component.content}
              </Card>
            )}
          </div>
        );
      })}
    </div>
  );
}

DashboardLayout.propTypes = {
  dashboardData: PropTypes.object.isRequired,
  agentData: PropTypes.object.isRequired,
};

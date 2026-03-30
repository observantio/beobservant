import { useState } from "react";
import PropTypes from "prop-types";
import { useLayoutMode } from "../../contexts/LayoutModeContext";
import { MetricCard } from "../ui";

export function MetricsGrid({ metrics, metricOrder, onMetricOrderChange }) {
  const { sidebarMode } = useLayoutMode();
  const [draggedIndex, setDraggedIndex] = useState(null);

  const handleDragStart = (e, index) => {
    setDraggedIndex(index);
    e.dataTransfer.effectAllowed = "move";
  };

  const handleDragOver = (e) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = "move";
  };

  const handleDrop = (e, dropIndex) => {
    e.preventDefault();
    if (draggedIndex === null || draggedIndex === dropIndex) return;

    const newOrder = [...metricOrder];
    const draggedItem = newOrder[draggedIndex];
    newOrder.splice(draggedIndex, 1);
    newOrder.splice(dropIndex, 0, draggedItem);
    onMetricOrderChange(newOrder);
    setDraggedIndex(null);
  };

  const handleDragEnd = () => {
    setDraggedIndex(null);
  };

  const gridClass = sidebarMode
    ? "grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-[repeat(auto-fit,minmax(200px,1fr))] gap-4 mb-8"
    : "grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-8";

  return (
    <div className={gridClass}>
      {metricOrder.map((metricIndex, displayIndex) => {
        const metric = metrics[metricIndex];
        if (!metric) return null;
        return (
          <button
            key={metric.id}
            draggable
            onDragStart={(e) => handleDragStart(e, displayIndex)}
            onDragOver={handleDragOver}
            onDrop={(e) => handleDrop(e, displayIndex)}
            onDragEnd={handleDragEnd}
            className={`flex h-full min-h-0 w-full cursor-move flex-col transition-transform duration-200 ease-out will-change-transform hover:shadow-lg relative ${
              draggedIndex === displayIndex
                ? "opacity-50 scale-95 shadow-xl"
                : ""
            }`}
            title="Drag to rearrange"
            type="button"
          >
            <div className="absolute top-2 right-2 z-10 text-sre-text-muted transition-colors hover:text-sre-text">
              <span className="material-icons text-sm drag-handle" aria-hidden>
                drag_indicator
              </span>
            </div>
            <MetricCard
              label={metric.label}
              value={metric.value}
              trend={metric.trend}
              status={metric.status}
              icon={metric.icon}
              className="flex-1"
            />
          </button>
        );
      })}
    </div>
  );
}

MetricsGrid.propTypes = {
  metrics: PropTypes.array.isRequired,
  metricOrder: PropTypes.array.isRequired,
  onMetricOrderChange: PropTypes.func.isRequired,
};

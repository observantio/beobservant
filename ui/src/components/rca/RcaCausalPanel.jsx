import { useEffect, useMemo, useState } from "react";
import PropTypes from "prop-types";
import { Button } from "../ui";
import { useToast } from "../../contexts/ToastContext";
import {
  getRcaMlWeights,
  resetRcaMlWeights,
  submitRcaMlWeightFeedback,
} from "../../api";
import Section from "./Section";

function formatNumber(value, digits = 3) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return "-";
  return numeric.toLocaleString(undefined, { maximumFractionDigits: digits });
}

function toDeploymentRows(deployments) {
  if (Array.isArray(deployments)) return deployments;
  if (Array.isArray(deployments?.items)) return deployments.items;
  if (Array.isArray(deployments?.events)) return deployments.events;
  return [];
}

function TableCard({ title, columns, rows, rowKey, renderRow, emptyText }) {
  return (
    <div className="border border-sre-border rounded-xl bg-sre-surface/20 overflow-hidden">
      <div className="px-3 py-2 border-b border-sre-border bg-sre-surface/40">
        <h4 className="text-sm font-semibold text-sre-text">{title}</h4>
      </div>
      {rows.length === 0 ? (
        <p className="p-4 text-xs text-sre-text-muted">{emptyText}</p>
      ) : (
        <div className="max-h-[280px] overflow-auto scrollbar-thin scrollbar-thumb-sre-border scrollbar-track-transparent">
          <table className="min-w-full text-left text-xs">
            <thead className="sticky top-0 bg-sre-surface/85 backdrop-blur-sm">
              <tr className="text-sre-text-muted uppercase tracking-wide">
                {columns.map((column) => (
                  <th key={column} className="px-3 py-2">
                    {column}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-sre-border/40">
              {rows.map((row, index) => (
                <tr
                  key={rowKey(row, index)}
                  className="hover:bg-sre-surface/35"
                >
                  {renderRow(row, index)}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

TableCard.propTypes = {
  title: PropTypes.string.isRequired,
  columns: PropTypes.arrayOf(PropTypes.string).isRequired,
  rows: PropTypes.array.isRequired,
  rowKey: PropTypes.func.isRequired,
  renderRow: PropTypes.func.isRequired,
  emptyText: PropTypes.string.isRequired,
};

export default function RcaCausalPanel({
  correlate,
  granger,
  bayesian,
  mlWeights,
  deployments,
  compact = false,
}) {
  const toast = useToast();
  const [weightsState, setWeightsState] = useState(mlWeights || null);
  const [loadingSignal, setLoadingSignal] = useState("");
  const [resettingWeights, setResettingWeights] = useState(false);
  const feedbackSignals = ["metrics", "logs", "traces"];

  useEffect(() => {
    setWeightsState(mlWeights || null);
  }, [mlWeights]);

  const grangerPairs = (
    granger?.causal_pairs ||
    granger?.warm_causal_pairs ||
    []
  )
    .slice()
    .sort(
      (left, right) => Number(right.strength || 0) - Number(left.strength || 0),
    );
  const posteriors = (bayesian?.posteriors || [])
    .slice()
    .sort(
      (left, right) =>
        Number(right.posterior || 0) - Number(left.posterior || 0),
    );
  const weightRows = useMemo(
    () =>
      Object.entries(weightsState?.weights || {})
        .map(([signal, value]) => ({ signal, value: Number(value) }))
        .sort((left, right) => right.value - left.value),
    [weightsState],
  );
  const deploymentItems = toDeploymentRows(deployments);
  const correlateEvents = Array.isArray(correlate?.correlated_events)
    ? correlate.correlated_events
    : [];
  const correlateLinks = Array.isArray(correlate?.log_metric_links)
    ? correlate.log_metric_links
    : [];
  const topCorrelateEvent = correlateEvents
    .slice()
    .sort(
      (left, right) =>
        Number(right.confidence || 0) - Number(left.confidence || 0),
    )[0];

  async function handleFeedback(signal, wasCorrect) {
    const key = `${signal}:${wasCorrect ? "up" : "down"}`;
    setLoadingSignal(key);
    try {
      const result = await submitRcaMlWeightFeedback(signal, wasCorrect);
      if (result?.updated_weights) {
        setWeightsState((prev) => ({
          ...(prev || {}),
          weights: result.updated_weights,
          update_count: Number(result.update_count || 0),
        }));
      } else {
        const refreshed = await getRcaMlWeights();
        setWeightsState(refreshed || null);
      }
      toast?.success?.(
        `${signal} feedback recorded (${wasCorrect ? "correct" : "incorrect"})`,
      );
    } catch (err) {
      toast?.error?.(err?.message || "Failed to submit ML weight feedback");
    } finally {
      setLoadingSignal("");
    }
  }

  async function handleReset() {
    setResettingWeights(true);
    try {
      const result = await resetRcaMlWeights();
      setWeightsState(result || null);
      toast?.success?.("Adaptive ML weights reset");
    } catch (err) {
      toast?.error?.(err?.message || "Failed to reset ML weights");
    } finally {
      setResettingWeights(false);
    }
  }

  const inner = (
    <>
      <h3 className="text-lg text-sre-text font-semibold mb-3">
        Causal and ML Insights
      </h3>
      <div
        className={
          compact
            ? "grid grid-cols-1 gap-3"
            : "grid grid-cols-1 xl:grid-cols-2 gap-3"
        }
      >
        <TableCard
          title={`Granger Causal Pairs (${grangerPairs.length})`}
          columns={["Cause", "Effect", "Strength"]}
          rows={grangerPairs}
          rowKey={(row, index) =>
            `${row.cause_metric || row.cause}-${row.effect_metric || row.effect}-${index}`
          }
          emptyText="No causal pairs returned in this range."
          renderRow={(row) => (
            <>
              <td className="px-3 py-2 text-sre-text">
                {row.cause_metric || row.cause || "-"}
              </td>
              <td className="px-3 py-2 text-sre-text">
                {row.effect_metric || row.effect || "-"}
              </td>
              <td className="px-3 py-2 text-sre-text-muted font-mono">
                {formatNumber(row.strength, 4)}
              </td>
            </>
          )}
        />

        <TableCard
          title={`Bayesian Posterior Scores (${posteriors.length})`}
          columns={["Category", "Posterior", "Prior"]}
          rows={posteriors}
          rowKey={(row, index) => `${row.category}-${index}`}
          emptyText="No posterior probabilities returned."
          renderRow={(row) => (
            <>
              <td className="px-3 py-2 text-sre-text">{row.category || "-"}</td>
              <td className="px-3 py-2 text-sre-text-muted font-mono">
                {formatNumber(row.posterior, 4)}
              </td>
              <td className="px-3 py-2 text-sre-text-muted font-mono">
                {formatNumber(row.prior, 4)}
              </td>
            </>
          )}
        />

        <TableCard
          title={`Correlation Snapshot (${correlateEvents.length})`}
          columns={["Window Start", "Confidence", "Signals", "M/L"]}
          rows={correlateEvents}
          rowKey={(row, index) =>
            `${row.window_start || "ws"}-${row.window_end || "we"}-${index}`
          }
          emptyText="No correlation windows returned."
          renderRow={(row) => (
            <>
              <td className="px-3 py-2 text-sre-text-muted font-mono">
                {row.window_start
                  ? new Date(Number(row.window_start) * 1000).toLocaleTimeString()
                  : "-"}
              </td>
              <td className="px-3 py-2 text-sre-text-muted font-mono">
                {formatNumber(row.confidence, 4)}
              </td>
              <td className="px-3 py-2 text-sre-text-muted font-mono">
                {formatNumber(row.signal_count, 0)}
              </td>
              <td className="px-3 py-2 text-sre-text-muted font-mono">
                {formatNumber(row.metric_anomaly_count, 0)}/
                {formatNumber(row.log_burst_count, 0)}
              </td>
            </>
          )}
        />

        <TableCard
          title={`Adaptive ML Weights (${weightRows.length})`}
          columns={["Signal", "Weight", "Distribution"]}
          rows={weightRows}
          rowKey={(row) => row.signal}
          emptyText="No ML weights available."
          renderRow={(row) => {
            const width = Math.max(6, Math.min(100, Math.abs(row.value) * 100));
            return (
              <>
                <td className="px-3 py-2 text-sre-text">{row.signal}</td>
                <td className="px-3 py-2 text-sre-text-muted font-mono">
                  {formatNumber(row.value, 4)}
                </td>
                <td className="px-3 py-2">
                  <div className="h-2 rounded-full bg-sre-border/40 overflow-hidden">
                    <div
                      className="h-full rounded-full bg-sre-primary/80"
                      style={{ width: `${width}%` }}
                    />
                  </div>
                </td>
              </>
            );
          }}
        />
        <div className="border border-sre-border rounded-xl bg-sre-surface/20 p-3">
          <div className="flex items-center justify-between mb-2">
            <h4 className="text-sm font-semibold text-sre-text">
              Weight Feedback
            </h4>
            <span className="text-xs text-sre-text-muted">
              updates: {Number(weightsState?.update_count || 0)}
            </span>
          </div>
          <p className="text-xs text-sre-text-muted mb-3">
            Tell the model which signal was helpful for this incident.
          </p>
          <div className="space-y-2">
            {feedbackSignals.map((signal) => (
              <div
                key={signal}
                className="flex items-center justify-between text-xs"
              >
                <span className="text-sre-text">{signal}</span>
                <div className="flex gap-2">
                  <Button
                    size="sm"
                    variant="secondary"
                    loading={loadingSignal === `${signal}:up`}
                    aria-label={`Mark ${signal} as correct`}
                    title="Correct"
                    onClick={() => handleFeedback(signal, true)}
                  >
                    <span className="material-icons text-base leading-none">
                      thumb_up
                    </span>
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    loading={loadingSignal === `${signal}:down`}
                    aria-label={`Mark ${signal} as incorrect`}
                    title="Incorrect"
                    onClick={() => handleFeedback(signal, false)}
                  >
                    <span className="material-icons text-base leading-none">
                      thumb_down
                    </span>
                  </Button>
                </div>
              </div>
            ))}
          </div>
          <div className="mt-3 pt-3 border-t border-sre-border/40 flex justify-end">
            <Button
              size="sm"
              variant="danger"
              loading={resettingWeights}
              onClick={handleReset}
            >
              Reset Weights
            </Button>
          </div>
        </div>

        <TableCard
          title={`Deployment Events (${deploymentItems.length})`}
          columns={["Service", "Version", "Timestamp"]}
          rows={deploymentItems}
          rowKey={(row, index) =>
            `${row.service || "service"}-${row.timestamp || "ts"}-${index}`
          }
          emptyText="No deployment events found for this scope."
          renderRow={(row) => (
            <>
              <td className="px-3 py-2 text-sre-text">{row.service || "-"}</td>
              <td className="px-3 py-2 text-sre-text-muted">
                {row.version || "-"}
              </td>
              <td className="px-3 py-2 text-sre-text-muted font-mono">
                {row.timestamp
                  ? new Date(Number(row.timestamp) * 1000).toLocaleString()
                  : "-"}
              </td>
            </>
          )}
        />
      </div>
      <div className="mt-3 grid grid-cols-1 md:grid-cols-2 gap-3">
        <div className="border border-sre-border rounded-xl bg-sre-surface/20 p-3">
          <h4 className="text-sm font-semibold text-sre-text mb-1">
            Top Correlation Confidence
          </h4>
          <p className="text-xl font-semibold text-sre-text">
            {formatNumber(topCorrelateEvent?.confidence, 4)}
          </p>
        </div>
        <div className="border border-sre-border rounded-xl bg-sre-surface/20 p-3">
          <h4 className="text-sm font-semibold text-sre-text mb-1">
            Log-Metric Links
          </h4>
          <p className="text-xl font-semibold text-sre-text">
            {formatNumber(correlateLinks.length, 0)}
          </p>
        </div>
      </div>
    </>
  );

  if (compact) {
    return <div>{inner}</div>;
  }

  return <Section>{inner}</Section>;
}

RcaCausalPanel.propTypes = {
  correlate: PropTypes.object,
  granger: PropTypes.object,
  bayesian: PropTypes.object,
  mlWeights: PropTypes.object,
  deployments: PropTypes.oneOfType([PropTypes.array, PropTypes.object]),
  compact: PropTypes.bool,
};

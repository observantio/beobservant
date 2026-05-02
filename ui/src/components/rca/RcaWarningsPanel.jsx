import PropTypes from "prop-types";
import Section from "./Section";

export default function RcaWarningsPanel({ report, compact = false }) {
  const warnings = report?.analysis_warnings || [];
  const changePoints = report?.change_points || [];

  const content = (
    <>
      <h3 className="text-lg text-sre-text font-semibold mb-3">
        Warnings and Change Points
      </h3>
      {warnings.length === 0 ? (
        <p className="my-4 text-sm leading-relaxed text-sre-text-subtle dark:text-sre-text-muted">
          No analysis warnings for this report.
        </p>
      ) : (
        <ul className="mb-3 list-none space-y-2.5 p-0">
          {warnings.map((warning, idx) => (
            <li
              key={idx}
              className="border-l-[3px] border-amber-700/85 pl-3 text-sm font-semibold leading-relaxed text-amber-950 dark:border-amber-400/50 dark:text-amber-100"
            >
              {warning}
            </li>
          ))}
        </ul>
      )}
      <div>
        <h4 className="text-sm text-sre-text font-semibold mb-2">
          Change Points ({changePoints.length})
        </h4>
        {changePoints.length === 0 ? (
          <p className="text-sm text-sre-text-subtle dark:text-sre-text-muted">
            No change points detected.
          </p>
        ) : (
          <div className="max-h-48 space-y-1.5 overflow-y-auto rounded border border-sre-border bg-sre-surface/50 p-2">
            {changePoints.slice(0, 30).map((cp, idx) => (
              <p
                key={idx}
                className="text-sm leading-snug text-sre-text dark:text-sre-text-muted"
              >
                {cp.metric_name || cp.metric || "metric"} at{" "}
                {new Date(Number(cp.timestamp || 0) * 1000).toLocaleString()}
              </p>
            ))}
          </div>
        )}
      </div>
    </>
  );

  if (compact) {
    return <div>{content}</div>;
  }

  return <Section>{content}</Section>;
}

RcaWarningsPanel.propTypes = {
  report: PropTypes.object,
  compact: PropTypes.bool,
};

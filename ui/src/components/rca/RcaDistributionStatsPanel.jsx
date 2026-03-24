import PropTypes from "prop-types";
import { useMemo, useState } from "react";
import Section from "./Section";

/**
 * Light panel tints; section/legend titles use darker accent text (500) so labels
 * like “Central & scale” read as deep color, not pale on dark UI.
 */
const GROUPS = {
  central: {
    id: "central",
    legendTitle: "Central & scale",
    legendHint: "Location & dispersion: mean, standard deviation, CV, MAD",
    sectionTitle: "Central & scale",
    bar: "border-l-cyan-400",
    panel: "bg-cyan-500/[0.06] ring-1 ring-inset ring-cyan-500/15",
    heading: "text-cyan-500 font-semibold",
    swatch:
      "h-3 w-3 shrink-0 rounded-full bg-cyan-400 shadow-[0_0_10px_rgba(34,211,238,0.45)]",
  },
  range: {
    id: "range",
    legendTitle: "Range & quartiles",
    legendHint: "Spread: min, max, quartiles, IQR (Q3 − Q1)",
    sectionTitle: "Range & quartiles",
    bar: "border-l-violet-400",
    panel: "bg-violet-500/[0.07] ring-1 ring-inset ring-violet-500/15",
    heading: "text-violet-500 font-semibold",
    swatch:
      "h-3 w-3 shrink-0 rounded-full bg-violet-400 shadow-[0_0_10px_rgba(167,139,250,0.45)]",
  },
  shape: {
    id: "shape",
    legendTitle: "Shape",
    legendHint: "Distribution tails: skewness, excess kurtosis",
    sectionTitle: "Shape",
    bar: "border-l-amber-400",
    panel: "bg-amber-500/[0.07] ring-1 ring-inset ring-amber-500/15",
    heading: "text-amber-500 font-semibold",
    swatch:
      "h-3 w-3 shrink-0 rounded-full bg-amber-400 shadow-[0_0_10px_rgba(251,191,36,0.4)]",
  },
};

function fmt(n) {
  if (n === null || n === undefined || Number.isNaN(Number(n))) return "—";
  const v = Number(n);
  if (!Number.isFinite(v)) return "—";
  const a = Math.abs(v);
  if (a >= 1000 || (a < 0.0001 && a > 0)) return v.toExponential(2);
  return v.toLocaleString(undefined, { maximumFractionDigits: 4 });
}

/** Split `query::metricLabel` from resolver series_key. */
function parseSeriesKey(seriesKey, metricName) {
  const sk = String(seriesKey || "").trim();
  if (!sk) {
    return { query: null, shortLabel: metricName || "—" };
  }
  const idx = sk.indexOf("::");
  if (idx === -1) {
    return { query: null, shortLabel: sk };
  }
  const query = sk.slice(0, idx).trim();
  const rest = sk.slice(idx + 2).trim();
  return {
    query: query || null,
    shortLabel: rest || metricName || "—",
  };
}

function Stat({ label, value, mono = true }) {
  return (
    <div className="min-w-0">
      <div className="text-[10px] uppercase tracking-wide text-sre-text-muted/90">
        {label}
      </div>
      <div
        className={`text-sm text-sre-text tabular-nums ${mono ? "font-mono" : ""}`}
      >
        {value}
      </div>
    </div>
  );
}

function StatSection({ groupKey, children }) {
  const g = GROUPS[groupKey];
  return (
    <div
      role="group"
      aria-label={g.sectionTitle}
      className={`rounded-lg pl-3 pr-3 pt-3 pb-3 border-l-[3px] ${g.bar} ${g.panel}`}
    >
      <p
        className={`text-[11px] tracking-wide uppercase mb-2.5 ${g.heading}`}
      >
        {g.sectionTitle}
      </p>
      {children}
    </div>
  );
}

StatSection.propTypes = {
  groupKey: PropTypes.oneOf(["central", "range", "shape"]).isRequired,
  children: PropTypes.node.isRequired,
};

function ColorLegend() {
  const items = [GROUPS.central, GROUPS.range, GROUPS.shape];
  return (
    <div
      className="mt-4 rounded-xl border border-sre-border/80 bg-sre-surface/40 p-3 sm:p-4"
      aria-label="Color legend for statistic groups"
    >
      <p className="text-xs font-semibold text-sre-text mb-3">Legend</p>
      <ul className="grid gap-3 sm:grid-cols-3 sm:gap-4">
        {items.map((g) => (
          <li key={g.id} className="flex gap-2.5 min-w-0">
            <span className={`mt-0.5 ${g.swatch}`} aria-hidden />
            <div className="min-w-0">
              <p className={`text-xs ${g.heading}`}>{g.legendTitle}</p>
              <p className="text-[11px] text-sre-text-muted leading-snug mt-0.5">
                {g.legendHint}
              </p>
            </div>
          </li>
        ))}
      </ul>
      <p className="mt-3 pt-3 border-t border-sre-border/50 text-[11px] text-sre-text-muted leading-relaxed">
        <span className="font-medium text-sre-text-muted">IQR</span> = Q3 − Q1 ·{" "}
        <span className="font-medium text-sre-text-muted">MAD</span> = median absolute
        deviation · <span className="font-medium text-sre-text-muted">CV</span> = σ/μ
        (when μ ≠ 0)
      </p>
    </div>
  );
}

function SeriesCard({ row, index }) {
  const { query, shortLabel } = parseSeriesKey(row.series_key, row.metric_name);
  const displayTitle = shortLabel || row.metric_name || "—";
  const showQuery = query && query.length > 0;
  const duplicateLabel =
    row.metric_name &&
    String(row.metric_name).trim() === String(shortLabel).trim();

  return (
    <article
      className="rounded-xl border border-sre-border/80 bg-sre-surface/25 p-4 shadow-sm"
      aria-labelledby={`dist-stat-title-${index}`}
    >
      <div className="flex flex-wrap items-start justify-between gap-2 border-b border-sre-border/50 pb-3 mb-4">
        <div className="min-w-0 flex-1">
          <h4
            id={`dist-stat-title-${index}`}
            className="text-sm font-semibold text-sre-text leading-snug break-words"
            title={duplicateLabel ? displayTitle : `${displayTitle}`}
          >
            {displayTitle}
          </h4>
          {!duplicateLabel && row.metric_name && (
            <p
              className="mt-1 text-xs text-sre-text-muted line-clamp-2 break-all"
              title={row.metric_name}
            >
              {row.metric_name}
            </p>
          )}
          {showQuery && (
            <p
              className="mt-1.5 text-[11px] leading-relaxed font-mono text-sre-text-muted/90 line-clamp-3 break-all"
              title={query}
            >
              <span className="text-sre-text-muted not-italic font-sans mr-1.5">
                Query
              </span>
              {query}
            </p>
          )}
        </div>
        <span className="shrink-0 rounded-md bg-sre-primary/15 px-2 py-0.5 text-xs font-mono text-sre-primary ring-1 ring-sre-primary/25">
          n={row.sample_count ?? "—"}
        </span>
      </div>

      <div className="space-y-3">
        <StatSection groupKey="central">
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <Stat label="Mean" value={fmt(row.mean)} />
            <Stat label="Std dev" value={fmt(row.std)} />
            <Stat label="CV (σ/μ)" value={fmt(row.coefficient_of_variation)} />
            <Stat label="MAD" value={fmt(row.mad)} />
          </div>
        </StatSection>

        <StatSection groupKey="range">
          <div className="grid grid-cols-2 sm:grid-cols-5 gap-3">
            <Stat label="Min" value={fmt(row.min)} />
            <Stat label="Q1" value={fmt(row.q1)} />
            <Stat label="Median" value={fmt(row.median)} />
            <Stat label="Q3" value={fmt(row.q3)} />
            <Stat label="Max" value={fmt(row.max)} />
          </div>
          <div className="mt-3 grid grid-cols-2 sm:grid-cols-3 gap-3">
            <Stat label="IQR (Q3−Q1)" value={fmt(row.iqr)} />
          </div>
        </StatSection>

        <StatSection groupKey="shape">
          <div className="grid grid-cols-2 gap-3">
            <Stat label="Skewness" value={fmt(row.skewness)} />
            <Stat label="Kurtosis (excess)" value={fmt(row.kurtosis)} />
          </div>
        </StatSection>
      </div>
    </article>
  );
}

export default function RcaDistributionStatsPanel({ report, compact = false }) {
  const allRows = (report?.metric_series_statistics || []).slice(0, 200);
  const [filter, setFilter] = useState("");

  const rows = useMemo(() => {
    const q = filter.trim().toLowerCase();
    if (!q) return allRows;
    return allRows.filter((row) => {
      const sk = String(row.series_key || "").toLowerCase();
      const mn = String(row.metric_name || "").toLowerCase();
      return sk.includes(q) || mn.includes(q);
    });
  }, [allRows, filter]);

  const inner = (
    <div className="space-y-4">
      <div>
        <h3 className="text-lg text-sre-text font-semibold">
          Metric distribution statistics
        </h3>
        <p className="mt-1 text-sm text-sre-text-muted max-w-3xl">
          Each card groups numbers by role. Colored section titles match the legend
          (cyan = central, violet = spread, amber = shape).
        </p>
        <ColorLegend />
      </div>

      {allRows.length === 0 ? (
        <p className="text-sm text-sre-text-muted">
          No statistics for this report (not enough samples or no metric series).
        </p>
      ) : (
        <>
          <div className="flex flex-col sm:flex-row sm:items-center gap-2 sm:justify-between">
            <label className="sr-only" htmlFor="dist-stat-filter">
              Filter series
            </label>
            <input
              id="dist-stat-filter"
              type="search"
              placeholder="Filter by metric or query…"
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
              className="w-full sm:max-w-md rounded-lg border border-sre-border bg-sre-bg-card px-3 py-2 text-sm text-sre-text placeholder:text-sre-text-muted/70 focus:outline-none focus:ring-2 focus:ring-sre-primary/40"
            />
            <p className="text-xs text-sre-text-muted shrink-0">
              Showing {rows.length} of {allRows.length} series
            </p>
          </div>

          <div className="max-h-[min(70vh,560px)] overflow-y-auto pr-1 space-y-4 scrollbar-thin scrollbar-thumb-sre-border scrollbar-track-transparent">
            {rows.length === 0 ? (
              <p className="text-sm text-sre-text-muted py-6 text-center">
                No series match your filter.
              </p>
            ) : (
              rows.map((row, index) => (
                <SeriesCard
                  key={`${row.series_key || row.metric_name}-${index}`}
                  row={row}
                  index={index}
                />
              ))
            )}
          </div>
        </>
      )}
    </div>
  );

  if (compact) {
    return <div>{inner}</div>;
  }

  return <Section>{inner}</Section>;
}

RcaDistributionStatsPanel.propTypes = {
  report: PropTypes.object,
  compact: PropTypes.bool,
};

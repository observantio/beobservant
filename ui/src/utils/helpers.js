`
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
`;
/**
 * Get log display information from explicit structured severity fields.
 * @param {string|object} line - Log line or parsed payload to analyze
 * @param {object} metadata - Optional stream or label metadata for explicit severity hints
 * @returns {{text: string, color: string, bgClass: string}} Log display info
 */

const LOG_LEVEL_STYLES = {
  ERROR: {
    text: "ERROR",
    color: "text-rose-700 dark:text-rose-300",
    bgClass:
      "bg-rose-50 text-rose-700 border-rose-200 dark:bg-rose-500/10 dark:text-rose-300 dark:border-rose-500/30",
  },
  WARN: {
    text: "WARN",
    color: "text-amber-800 dark:text-amber-300",
    bgClass:
      "bg-amber-50 text-amber-800 border-amber-200 dark:bg-amber-500/10 dark:text-amber-300 dark:border-amber-500/30",
  },
  INFO: {
    text: "INFO",
    color: "text-sky-700 dark:text-sky-300",
    bgClass:
      "bg-sky-50 text-sky-700 border-sky-200 dark:bg-sky-500/10 dark:text-sky-300 dark:border-sky-500/30",
  },
  DEBUG: {
    text: "DEBUG",
    color: "text-violet-700 dark:text-violet-300",
    bgClass:
      "bg-violet-50 text-violet-700 border-violet-200 dark:bg-violet-500/10 dark:text-violet-300 dark:border-violet-500/30",
  },
  LOG: {
    text: "LOG",
    color: "text-sre-text",
    bgClass: "bg-sre-surface text-sre-text-muted border-sre-border",
  },
};

const LOG_LEVEL_KEYS = [
  "detected_level",
  "detectedLevel",
  "severity_text",
  "severityText",
  "level",
  "log_level",
  "logLevel",
  "severity",
];

function normalizeLogLevel(value) {
  if (value == null) return null;
  const normalized = String(value).trim().toUpperCase();
  if (!normalized) return null;

  if (normalized === "WARNING") return "WARN";
  if (normalized === "INFORMATION") return "INFO";
  if (normalized === "ERR" || normalized === "ERROR" || normalized === "FATAL" || normalized === "CRITICAL") {
    return "ERROR";
  }
  if (normalized === "WARN" || normalized === "INFO" || normalized === "DEBUG") {
    return normalized;
  }
  if (normalized === "TRACE") return "DEBUG";

  return null;
}

function severityNumberToLevel(value) {
  const numericValue =
    typeof value === "number" ? value : Number.parseInt(String(value), 10);
  if (!Number.isFinite(numericValue)) return null;

  if (numericValue >= 17) return "ERROR";
  if (numericValue >= 13) return "WARN";
  if (numericValue >= 9) return "INFO";
  if (numericValue >= 1) return "DEBUG";

  return null;
}

function readExplicitLogLevel(source) {
  if (!source || typeof source !== "object") return null;

  for (const key of LOG_LEVEL_KEYS) {
    const level = normalizeLogLevel(source[key]);
    if (level) return level;
  }

  const severityNumber = source.severity_number ?? source.severityNumber;
  const levelFromNumber = severityNumberToLevel(severityNumber);
  if (levelFromNumber) return levelFromNumber;

  return null;
}

export function getLogLevel(line, metadata) {
  const level = readExplicitLogLevel(line) || readExplicitLogLevel(metadata) || "LOG";

  return LOG_LEVEL_STYLES[level];
}

/**
 * Extract service name from span
 * @param {object} span - Span object
 * @returns {string} Service name
 */
export function getServiceName(span) {
  if (!span) return "unknown";
  if (span.serviceName) return span.serviceName;
  if (span.process?.serviceName) return span.process.serviceName;

  const tagKey = ["service.name", "service", "service_name"];
  const tagVal = getSpanAttribute(span, tagKey);
  if (tagVal != null) return String(tagVal);

  return "unknown";
}

/**
 * Get span attribute value
 * @param {object} span - Span object
 * @param {string} keys - Attribute key to look for
 * @returns {any} Attribute value or null
 */
function getFromAttributes(attrs, keys) {
  if (!attrs || typeof attrs !== "object") return null;
  for (const key of keys) {
    const val = attrs[key];
    if (val != null) return val;
  }
  return null;
}

function getFromTags(tags, keys) {
  if (Array.isArray(tags)) {
    for (const key of keys) {
      const tag = tags.find((t) => t?.key === key);
      if (tag?.value != null) return tag.value;
    }
    return null;
  }
  if (typeof tags === "object" && tags) {
    for (const key of keys) {
      const val = tags[key];
      if (val != null) return val;
    }
  }
  return null;
}

export function getSpanAttribute(span, keys) {
  if (!span || !keys) return null;
  const keyList = Array.isArray(keys) ? keys : [keys];

  const attrVal = getFromAttributes(span.attributes, keyList);
  if (attrVal != null) return attrVal;

  return getFromTags(span.tags, keyList);
}

/**
 * Calculate percentile of an array
 * @param {number[]} arr - Array of numbers
 * @param {number} p - Percentile (0-1)
 * @returns {number} Percentile value
 */
export function percentile(arr, p) {
  if (!arr.length) return 0;
  const sorted = [...arr].sort((a, b) => a - b);
  const idx = Math.min(
    sorted.length - 1,
    Math.max(0, Math.floor(sorted.length * p)),
  );
  return sorted[idx];
}

/**
 * Check if a trace span has an error status
 * @param {object} span - Span object
 * @returns {boolean} True if the span has an error
 */
export function hasSpanError(span) {
  return Boolean(
    span?.status?.code === "ERROR" ||
    (Array.isArray(span?.tags)
      ? span.tags.some((t) => t.key === "error" && t.value === true)
      : span?.tags?.error === true),
  );
}

/**
 * Deterministic color for a service name (hash-based)
 * @param {string} name - Service name
 * @param {boolean} hasError - Whether the span errored
 * @returns {string} Tailwind background class
 */
export function getSpanColorClass(name, hasError = false) {
  if (hasError) return "bg-red-500";
  const SERVICE_COLORS = [
    "bg-blue-500",
    "bg-green-500",
    "bg-purple-500",
    "bg-amber-500",
    "bg-cyan-500",
    "bg-pink-500",
    "bg-indigo-500",
    "bg-teal-500",
    "bg-orange-500",
    "bg-lime-500",
  ];
  let hash = 0;
  for (let i = 0; i < (name || "").length; i++) {
    hash = Math.trunc((hash << 5) - hash + name.codePointAt(i));
  }
  return SERVICE_COLORS[Math.abs(hash) % SERVICE_COLORS.length];
}

/**
 * Copy text to clipboard
 * @param {string} text - Text to copy
 * @returns {Promise<void>}
 */
export async function copyToClipboard(text) {
  try {
    if (typeof navigator !== "undefined" && navigator?.clipboard?.writeText) {
      await navigator.clipboard.writeText(text);
      return true;
    }
  } catch {
    // Fall through to legacy copy path below.
  }

  try {
    const textarea = document.createElement("textarea");
    textarea.value = String(text ?? "");
    textarea.setAttribute("readonly", "");
    textarea.style.position = "fixed";
    textarea.style.opacity = "0";
    document.body.appendChild(textarea);
    textarea.select();
    textarea.setSelectionRange(0, textarea.value.length);
    const ok = document.execCommand("copy");
    textarea.remove();
    return Boolean(ok);
  } catch {
    return false;
  }
}

/**
 * Download data as JSON file
 * @param {any} data - Data to download
 * @param {string} filename - File name
 */
export function downloadJSON(data, filename = "data.json") {
  const blob = new Blob([JSON.stringify(data, null, 2)], {
    type: "application/json",
  });
  if (typeof URL?.createObjectURL !== "function") return;
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  if (typeof URL?.revokeObjectURL === "function") {
    URL.revokeObjectURL(url);
  }
}

/**
 * Download arbitrary text/binary as a file
 * @param {string|Blob} content
 * @param {string} filename
 * @param {string} type
 */
export function downloadFile(
  content,
  filename = "file.txt",
  type = "text/plain",
) {
  const blob =
    content instanceof Blob ? content : new Blob([content], { type });
  if (typeof URL?.createObjectURL !== "function") return;
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  if (typeof URL?.revokeObjectURL === "function") {
    URL.revokeObjectURL(url);
  }
}

/**
 * Copy an image blob to the clipboard.
 * @param {Blob} blob - Image blob to copy.
 * @returns {Promise<boolean>} True when copied successfully.
 */
export async function copyBlobToClipboard(blob) {
  try {
    if (
      typeof navigator !== "undefined" &&
      navigator.clipboard?.write &&
      typeof ClipboardItem !== "undefined"
    ) {
      const item = new ClipboardItem({ [blob.type || "image/png"]: blob });
      await navigator.clipboard.write([item]);
      return true;
    }
  } catch {
    return false;
  }
  return false;
}

/**
 * Debounce function
 * @param {Function} func - Function to debounce
 * @param {number} wait - Wait time in ms
 * @returns {Function} Debounced function
 */
export function debounce(func, wait) {
  let timeout;
  return function executedFunction(...args) {
    const later = () => {
      clearTimeout(timeout);
      func(...args);
    };
    clearTimeout(timeout);
    timeout = setTimeout(later, wait);
  };
}

/**
 * Deep clone an object
 * @param {any} obj - Object to clone
 * @returns {any} Cloned object
 */
export function deepClone(obj) {
  try {
    return structuredClone(obj);
  } catch {
    return obj;
  }
}

/**
 * Check if value is empty
 * @param {any} value - Value to check
 * @returns {boolean} True if empty
 */
export function isEmpty(value) {
  if (value === null || value === undefined) return true;
  if (typeof value === "string") return value.trim() === "";
  if (Array.isArray(value)) return value.length === 0;
  if (typeof value === "object") return Object.keys(value).length === 0;
  return false;
}

/**
 * Generate unique ID
 * @returns {string} Unique ID
 */
export function generateId() {
  return `${Date.now()}-${Math.random().toString(36).substring(2, 11)}`;
}

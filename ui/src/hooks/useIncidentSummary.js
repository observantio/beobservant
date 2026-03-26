import { useState, useEffect, useRef } from "react";
import { useAuth } from "../contexts/AuthContext";
import * as api from "../api";

/**
 * Polls incident summary for nav badges (assigned to me).
 */
export function useIncidentSummary() {
  const { hasPermission } = useAuth();
  const [incidentSummary, setIncidentSummary] = useState(null);
  const inFlightRef = useRef(false);
  const timerRef = useRef(null);

  useEffect(() => {
    let alive = true;
    const controller = new AbortController();
    const POLL_MS = 30000;

    const clearTimer = () => {
      if (timerRef.current) {
        clearTimeout(timerRef.current);
        timerRef.current = null;
      }
    };

    const scheduleNext = (delayMs = POLL_MS) => {
      if (!alive) return;
      clearTimer();
      timerRef.current = setTimeout(loadSummary, delayMs);
    };

    if (!hasPermission("read:incidents")) {
      setIncidentSummary(null);
      return () => {
        alive = false;
        controller.abort();
        clearTimer();
      };
    }

    async function loadSummary() {
      if (!alive) return;
      if (inFlightRef.current) return;
      if (typeof document !== "undefined" && document.hidden) {
        scheduleNext();
        return;
      }
      inFlightRef.current = true;
      try {
        const data = await api.getIncidentsSummary({
          signal: controller.signal,
          maxRetries: 0,
        });
        if (!alive) return;
        setIncidentSummary(data || null);
      } catch {
        if (!alive) return;
        setIncidentSummary(null);
      } finally {
        inFlightRef.current = false;
        scheduleNext();
      }
    }

    const onVisibilityChange = () => {
      if (
        typeof document !== "undefined" &&
        document.visibilityState === "visible" &&
        !inFlightRef.current
      ) {
        clearTimer();
        void loadSummary();
      }
    };

    if (typeof document !== "undefined") {
      document.addEventListener("visibilitychange", onVisibilityChange);
    }

    loadSummary();
    return () => {
      alive = false;
      controller.abort();
      clearTimer();
      if (typeof document !== "undefined") {
        document.removeEventListener("visibilitychange", onVisibilityChange);
      }
    };
  }, [hasPermission]);

  return incidentSummary;
}

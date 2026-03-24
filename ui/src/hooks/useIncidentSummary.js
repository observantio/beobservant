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
    if (!hasPermission("read:incidents")) {
      setIncidentSummary(null);
      return () => {
        alive = false;
        controller.abort();
        if (timerRef.current) clearTimeout(timerRef.current);
      };
    }
    const loadSummary = async () => {
      if (inFlightRef.current) return;
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
        if (alive) {
          timerRef.current = setTimeout(loadSummary, 30000);
        }
      }
    };
    loadSummary();
    return () => {
      alive = false;
      controller.abort();
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, [hasPermission]);

  return incidentSummary;
}

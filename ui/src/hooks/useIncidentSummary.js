import { useState, useEffect } from "react";
import { useAuth } from "../contexts/AuthContext";
import * as api from "../api";

/**
 * Polls incident summary for nav badges (assigned to me).
 */
export function useIncidentSummary() {
  const { hasPermission } = useAuth();
  const [incidentSummary, setIncidentSummary] = useState(null);

  useEffect(() => {
    let alive = true;
    if (!hasPermission("read:incidents")) {
      setIncidentSummary(null);
      return () => {
        alive = false;
      };
    }
    const loadSummary = async () => {
      try {
        const data = await api.getIncidentsSummary();
        if (!alive) return;
        setIncidentSummary(data || null);
      } catch {
        if (!alive) return;
        setIncidentSummary(null);
      }
    };
    loadSummary();
    const timer = setInterval(loadSummary, 30000);
    return () => {
      alive = false;
      clearInterval(timer);
    };
  }, [hasPermission]);

  return incidentSummary;
}

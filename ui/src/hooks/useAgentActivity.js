import { useEffect, useState } from "react";
import { getActiveAgents } from "../api";

export function useAgentActivity() {
  const [agentActivity, setAgentActivity] = useState([]);
  const [loadingAgents, setLoadingAgents] = useState(true);

  useEffect(() => {
    let active = true;
    const controller = new AbortController();

    (async () => {
      try {
        if (active) setLoadingAgents(true);
        const res = await getActiveAgents({
          signal: controller.signal,
          maxRetries: 0,
        });
        if (active) setAgentActivity(Array.isArray(res) ? res : []);
      } catch (e) {
        void e;
        if (active) setAgentActivity([]);
      } finally {
        if (active) setLoadingAgents(false);
      }
    })();

    return () => {
      active = false;
      controller.abort();
    };
  }, []);

  return {
    agentActivity,
    loadingAgents,
  };
}

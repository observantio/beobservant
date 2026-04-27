import { useEffect, useState } from "react";
import { getActiveAgents } from "../api";
import { useAuth } from "../contexts/AuthContext";

export function useAgentActivity() {
  const { user } = useAuth();
  const [agentActivity, setAgentActivity] = useState([]);
  const [loadingAgents, setLoadingAgents] = useState(true);
  const keys = user?.api_keys || [];
  const activeKey = keys.find((k) => k.is_enabled) || keys.find((k) => k.is_default);
  const activeApiKeyId = activeKey?.id || activeKey?.key || user?.org_id || "";

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
  }, [activeApiKeyId]);

  return {
    agentActivity,
    loadingAgents,
  };
}

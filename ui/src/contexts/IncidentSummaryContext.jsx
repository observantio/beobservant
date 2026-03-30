import { createContext, useContext } from "react";
import PropTypes from "prop-types";
import { useIncidentSummary } from "../hooks/useIncidentSummary";

const IncidentSummaryContext = createContext(null);

export function IncidentSummaryProvider({ children }) {
  const incidentSummary = useIncidentSummary();
  return (
    <IncidentSummaryContext.Provider value={incidentSummary}>
      {children}
    </IncidentSummaryContext.Provider>
  );
}

IncidentSummaryProvider.propTypes = { children: PropTypes.node };

export function useSharedIncidentSummary() {
  return useContext(IncidentSummaryContext);
}

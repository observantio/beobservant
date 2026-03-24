import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";
import PropTypes from "prop-types";

const STORAGE_KEY = "observantio-ui-sidebar-layout";

const LayoutModeContext = createContext(null);

export function LayoutModeProvider({ children }) {
  const [sidebarMode, setSidebarMode] = useState(() => {
    try {
      return globalThis.localStorage?.getItem(STORAGE_KEY) === "1";
    } catch {
      return false;
    }
  });

  useEffect(() => {
    try {
      globalThis.localStorage?.setItem(STORAGE_KEY, sidebarMode ? "1" : "0");
    } catch {
      /* ignore */
    }
  }, [sidebarMode]);

  const toggleSidebarMode = useCallback(() => {
    setSidebarMode((v) => !v);
  }, []);

  const value = useMemo(
    () => ({ sidebarMode, toggleSidebarMode }),
    [sidebarMode, toggleSidebarMode],
  );

  return (
    <LayoutModeContext.Provider value={value}>
      {children}
    </LayoutModeContext.Provider>
  );
}

LayoutModeProvider.propTypes = { children: PropTypes.node };

export function useLayoutMode() {
  const ctx = useContext(LayoutModeContext);
  return (
    ctx ?? {
      sidebarMode: false,
      toggleSidebarMode: () => {},
    }
  );
}

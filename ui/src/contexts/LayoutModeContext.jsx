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
      const saved = globalThis.localStorage?.getItem(STORAGE_KEY);
      if (saved === "1") return true;
      if (saved === "0") return false;
      return true;
    } catch {
      return true;
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
      sidebarMode: true,
      toggleSidebarMode: () => {},
    }
  );
}

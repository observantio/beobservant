import { NavLink } from "react-router-dom";
import { useAuth } from "../contexts/AuthContext";
import { useLayoutMode } from "../contexts/LayoutModeContext";
import { NAV_ITEMS, SIDEBAR_EXTRA_NAV } from "../utils/constants";
import { NavItem } from "./Header";
import { useSharedIncidentSummary } from "../contexts/IncidentSummaryContext";

const NAV_ITEM_LIST = Object.values(NAV_ITEMS);

/**
 * Full-viewport-height left rail (md+): layout toggle + nav. Dashed rule on the right only.
 */
export default function AppSidebar() {
  const { toggleSidebarMode } = useLayoutMode();
  const { hasPermission, user } = useAuth();
  const incidentSummary = useSharedIncidentSummary();

  const visibleNavItems = NAV_ITEM_LIST.filter(
    (item) => !item.permission || hasPermission(item.permission),
  );

  const visibleExtraNav = SIDEBAR_EXTRA_NAV.filter((item) => {
    if (item.permission && !hasPermission(item.permission)) return false;
    if (item.adminOnly && user?.role !== "admin") return false;
    return true;
  });
  const visibleDocumentationNav = visibleExtraNav.filter((item) =>
    item.path.startsWith("/docs"),
  );
  const docsRootItem = visibleDocumentationNav.find((item) => item.path === "/docs");
  const docsTopicNav = visibleDocumentationNav.filter((item) => item.path !== "/docs");
  const visibleManagementNav = visibleExtraNav.filter(
    (item) => !item.path.startsWith("/docs"),
  );

  return (
    <aside
      className="fixed left-0 top-0 z-30 hidden h-screen w-60 shrink-0 flex-col overflow-hidden border-r-2 border-dashed border-sre-border bg-gradient-to-b from-sre-bg via-sre-bg-alt to-sre-bg md:flex"
      aria-label="App sidebar"
    >
      <div className="flex shrink-0 px-2.5 pb-3 pt-3.5">
        <button
          type="button"
          onClick={toggleSidebarMode}
          className="flex w-full items-center gap-3 rounded-lg px-3 py-3 text-sre-text-muted transition-colors hover:bg-sre-surface-light/80 hover:text-sre-text"
          aria-pressed="true"
          aria-label="Switch to Top Nav"
          title="Switch to Top Nav"
        >
          <span className="material-icons text-[22px] leading-none" aria-hidden>
            view_headline
          </span>
          <span className="text-xs font-semibold tracking-wide uppercase">
            Switch to Top Nav
          </span>
        </button>
      </div>

      <nav
        className="flex min-h-0 flex-1 flex-col gap-1 overflow-y-auto overscroll-contain px-2.5 pb-8 pt-2 scrollbar-thin scrollbar-thumb-sre-border scrollbar-track-transparent"
        aria-label="Main navigation"
      >
        {visibleNavItems.length > 0 && (
          <>
            <div className="px-3 pb-1 pt-0.5 text-[11px] font-semibold uppercase tracking-wide text-sre-text-muted/80">
              Observability
            </div>
            {visibleNavItems.map((item) => (
              <NavItem
                key={item.path}
                item={item}
                variant="sidebar"
                incidentSummary={incidentSummary}
              />
            ))}
          </>
        )}

        {visibleExtraNav.length > 0 && (
          <>
            <div
              className="my-3 border-t border-dashed border-sre-border/80"
              role="presentation"
            />
            {visibleManagementNav.length > 0 && (
              <>
                <div className="px-3 pb-1 pt-0.5 text-[11px] font-semibold uppercase tracking-wide text-sre-text-muted/80">
                  Management
                </div>
                {visibleManagementNav.map((item) => (
                  <NavItem
                    key={item.path}
                    item={item}
                    variant="sidebar"
                    incidentSummary={incidentSummary}
                  />
                ))}
              </>
            )}

            {visibleDocumentationNav.length > 0 && (
              <>
                <div
                  className="my-3 border-t border-dashed border-sre-border/80"
                  role="presentation"
                />
                <div className="px-3 pb-1 pt-0.5 text-[11px] font-semibold uppercase tracking-wide text-sre-text-muted/80">
                  Documentation
                </div>
                {docsRootItem && (
                  <NavItem
                    key={docsRootItem.path}
                    item={docsRootItem}
                    variant="sidebar"
                    incidentSummary={incidentSummary}
                  />
                )}
                {docsTopicNav.length > 0 && (
                  <div className="mt-0.5 space-y-0.5 pl-3">
                    {docsTopicNav.map((item) => (
                      <NavLink
                        key={item.path}
                        to={item.path}
                        className={({ isActive }) =>
                          `block rounded-md px-2.5 py-1.5 text-xs leading-5 transition-colors ${
                            isActive
                              ? "bg-sre-primary/10 text-sre-primary dark:bg-sre-success/10 dark:text-sre-success"
                              : "text-sre-text-muted/80 hover:bg-sre-surface-light/60 hover:text-sre-text"
                          }`
                        }
                      >
                        {item.label}
                      </NavLink>
                    ))}
                  </div>
                )}
              </>
            )}
          </>
        )}
      </nav>
    </aside>
  );
}

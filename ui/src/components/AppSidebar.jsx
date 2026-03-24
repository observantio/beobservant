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

  return (
    <aside
      className="fixed left-0 top-0 z-30 hidden h-screen w-56 shrink-0 flex-col border-r-2 border-dashed border-sre-border bg-gradient-to-b from-sre-bg via-sre-bg-alt to-sre-bg md:flex"
      aria-label="App sidebar"
    >
      <div className="flex shrink-0 px-2.5 pb-3 pt-3.5">
        <button
          type="button"
          onClick={toggleSidebarMode}
          className="flex w-full items-center gap-3 rounded-lg px-3 py-3 text-sre-text-muted transition-colors hover:bg-sre-surface-light/80 hover:text-sre-text"
          aria-pressed="true"
          aria-label="Use top navigation layout"
          title="Top navigation"
        >
          <span className="material-icons text-[22px] leading-none" aria-hidden>
            view_headline
          </span>
        </button>
      </div>

      <nav
        className="flex min-h-0 flex-1 flex-col gap-1 overflow-y-auto overscroll-contain px-2.5 pb-6 pt-2"
        aria-label="Main navigation"
      >
        {visibleNavItems.map((item) => (
          <NavItem
            key={item.path}
            item={item}
            variant="sidebar"
            incidentSummary={incidentSummary}
          />
        ))}

        {visibleExtraNav.length > 0 && (
          <>
            <div
              className="my-3 border-t border-dashed border-sre-border/80"
              role="presentation"
            />
            {visibleExtraNav.map((item) => (
              <NavItem
                key={item.path}
                item={item}
                variant="sidebar"
                incidentSummary={incidentSummary}
              />
            ))}
          </>
        )}
      </nav>
    </aside>
  );
}

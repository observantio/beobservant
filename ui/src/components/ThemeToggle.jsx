import PropTypes from "prop-types";
import { useTheme } from "../contexts/ThemeContext";

export default function ThemeToggle({ className = "" }) {
  const { theme, toggleTheme } = useTheme();

  return (
    <button
      type="button"
      onClick={toggleTheme}
      className={`group rounded-2xl border border-sre-border/45 bg-sre-surface-light/50 p-2 shadow-sm backdrop-blur-xl backdrop-saturate-150 transition-[background-color,border-color,transform,box-shadow] duration-300 ease-smooth motion-reduce:transition-none
        hover:border-sre-primary/35 hover:bg-sre-surface-light/70 hover:shadow-md active:scale-[0.94] motion-reduce:active:scale-100
        dark:border-white/12 dark:bg-sre-surface/35 dark:shadow-[inset_0_1px_0_0_rgba(255,255,255,0.06)] dark:hover:border-white/22 dark:hover:bg-sre-surface/50
        focus:outline-none focus-visible:ring-2 focus-visible:ring-sre-primary focus-visible:ring-offset-2 focus-visible:ring-offset-sre-bg motion-reduce:focus-visible:ring-0
        ${className}`}
      title={`Switch to ${theme === "dark" ? "light" : "dark"} mode`}
      aria-label={`Switch to ${theme === "dark" ? "light" : "dark"} mode`}
    >
      {theme === "dark" ? (
        <svg
          className="h-5 w-5 text-sre-text-muted transition-colors duration-300 ease-smooth group-hover:text-sre-text"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M12 3v1m0 16v1m9-9h-1M4 12H3m15.364 6.364l-.707-.707M6.343 6.343l-.707-.707m12.728 0l-.707.707M6.343 17.657l-.707.707M16 12a4 4 0 11-8 0 4 4 0 018 0z"
          />
        </svg>
      ) : (
        <svg
          className="h-5 w-5 text-sre-text-muted transition-colors duration-300 ease-smooth group-hover:text-sre-text"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M20.354 15.354A9 9 0 018.646 3.646 9.003 9.003 0 0012 21a9.003 9.003 0 008.354-5.646z"
          />
        </svg>
      )}
    </button>
  );
}

ThemeToggle.propTypes = {
  className: PropTypes.string,
};

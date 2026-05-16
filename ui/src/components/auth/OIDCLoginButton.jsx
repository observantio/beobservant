import PropTypes from "prop-types";

export default function OIDCLoginButton({
  loading,
  onClick,
  providerLabel = "Single Sign-On",
}) {
  return (
    <button
      type="button"
      className="auth-sso-cartoon-button w-full"
      disabled={loading}
      onClick={onClick}
    >
      {loading && (
        <svg
          className="motion-reduce:animate-none -ml-1 mr-2 h-5 w-5 shrink-0 animate-spin text-white"
          xmlns="http://www.w3.org/2000/svg"
          fill="none"
          viewBox="0 0 24 24"
          aria-hidden
        >
          <circle
            className="opacity-25"
            cx="12"
            cy="12"
            r="10"
            stroke="currentColor"
            strokeWidth="4"
          />
          <path
            className="opacity-75"
            fill="currentColor"
            d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
          />
        </svg>
      )}
      {loading ? "Redirecting..." : `Continue with ${providerLabel}`}
    </button>
  );
}

OIDCLoginButton.propTypes = {
  loading: PropTypes.bool,
  onClick: PropTypes.func.isRequired,
  providerLabel: PropTypes.string,
};

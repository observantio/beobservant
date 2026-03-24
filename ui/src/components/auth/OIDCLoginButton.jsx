import PropTypes from "prop-types";
import { Button } from "../ui";

export default function OIDCLoginButton({
  loading,
  onClick,
  providerLabel = "Single Sign-On",
}) {
  return (
    <Button
      type="button"
      variant="primary"
      className="w-full bg-gradient-to-r from-sre-primary via-sre-primary-light to-sre-success text-white shadow-lg border border-black dark:bg-none dark:bg-sre-bg-alt dark:text-sre-success dark:border-sre-success/60 dark:shadow-none"
      loading={loading}
      onClick={onClick}
    >
      {loading ? "Redirecting..." : `Continue with ${providerLabel}`}
    </Button>
  );
}

OIDCLoginButton.propTypes = {
  loading: PropTypes.bool,
  onClick: PropTypes.func.isRequired,
  providerLabel: PropTypes.string,
};

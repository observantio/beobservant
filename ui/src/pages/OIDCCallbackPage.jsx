import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../contexts/AuthContext";
import { Spinner } from "../components/ui";
import * as api from "../api";

const readParams = () => {
  const url = new URL(globalThis.location.href);
  const search = url.searchParams;
  return {
    code: search.get("code") || "",
    state: search.get("state") || "",
    oidcError: search.get("error") || "",
    errorDescription: search.get("error_description") || "",
  };
};

const extractChallenge = (error) => {
  const detail = error?.body?.detail;
  if (detail && typeof detail === "object") return detail;
  if (error?.body && typeof error.body === "object") return error.body;
  return null;
};

const formatError = (error) => {
  const raw = error?.body?.detail || error?.body?.message || error?.message || error;
  if (raw == null) return "OIDC login failed";
  if (typeof raw === "string") return raw;
  if (typeof raw === "number" || typeof raw === "boolean") return String(raw);
  if (raw && typeof raw === "object") {
    if (raw.mfa_setup_required === true) {
      return "Multi-factor setup is required before you can finish sign in.";
    }
    try {
      return JSON.stringify(raw);
    } catch {
      return "OIDC login failed";
    }
  }
  return "OIDC login failed";
};

export default function OIDCCallbackPage() {
  const navigate = useNavigate();
  const { finishOIDCLogin } = useAuth();
  const [error, setError] = useState("");
  const [mfaRequired, setMfaRequired] = useState(false);
  const [mfaCode, setMfaCode] = useState("");
  const [mfaChallengeId, setMfaChallengeId] = useState("");
  const [mfaSubmitting, setMfaSubmitting] = useState(false);

  const params = useMemo(() => readParams(), []);
  const isMfaRequiredError = (e) => {
    if (e?.status !== 401) return false;
    if (e?.body?.detail === "MFA required" || e?.message === "MFA required") return true;
    if (e?.body?.detail && typeof e.body.detail === "object" && e.body.detail.mfa_required === true) return true;
    if (e?.body && typeof e.body === "object" && e.body.mfa_required === true) return true;
    return false;
  };

  useEffect(() => {
    let alive = true;

    const run = async () => {
      if (params.oidcError) {
        if (alive) setError(params.errorDescription || params.oidcError);
        return;
      }

      if (!params.code || !params.state) {
        if (alive) setError("Missing OIDC callback parameters");
        return;
      }

      try {
        await finishOIDCLogin({ code: params.code, state: params.state });
        if (!alive) return;
        globalThis.history.replaceState({}, "", "/");
        navigate("/", { replace: true });
      } catch (e) {
        if (isMfaRequiredError(e)) {
          if (!alive) return;
          const challenge = extractChallenge(e);
          const challengeId = challenge?.mfa_challenge_id || "";
          if (!challengeId) {
            setError("MFA session expired. Please sign in with Single Sign-On again.");
            return;
          }
          setMfaChallengeId(challengeId);
          setMfaRequired(true);
          setError("");
          return;
        }
        const challenge = extractChallenge(e);
        if (challenge?.mfa_setup_required) {
          try {
            if (challenge.setup_token) api.setSetupToken(challenge.setup_token);
          } catch (_) {
            /* ignore */
          }
          if (!alive) return;
          navigate("/login?mfa_setup=required", { replace: true });
          return;
        }
        if (alive) setError(formatError(e));
      }
    };

    run();
    return () => {
      alive = false;
    };
  }, [finishOIDCLogin, navigate, params]);

  const verifyOidcMfa = async (ev) => {
    ev.preventDefault();
    if (!mfaCode.trim()) {
      setError("Enter your authenticator or recovery code to continue.");
      return;
    }
    setError("");
    setMfaSubmitting(true);
    try {
      await finishOIDCLogin({
        code: params.code,
        state: params.state,
        mfaCode: mfaCode.trim(),
        mfaChallengeId,
      });
      globalThis.history.replaceState({}, "", "/");
      navigate("/", { replace: true });
    } catch (e) {
      setError(formatError(e));
    } finally {
      setMfaSubmitting(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-sre-bg p-4">
      <div className="w-full max-w-md rounded-2xl bg-white/90 p-6 backdrop-blur-sm dark:bg-transparent dark:p-0 dark:shadow-none dark:backdrop-blur-none">
        {!error && !mfaRequired ? (
          <div className="flex flex-col items-center gap-3 text-center">
            <Spinner size="lg" />
            <h1 className="text-xl font-semibold text-sre-text">
              Signing you in
            </h1>
            <p className="text-sre-text-muted text-sm">
              Completing secure OIDC authentication…
            </p>
            <button
              type="button"
              className="text-xs text-sre-primary hover:text-sre-primary-light"
              onClick={() => globalThis.location.reload()}
            >
              Refresh page
            </button>
          </div>
        ) : mfaRequired ? (
          <form className="space-y-4" onSubmit={verifyOidcMfa}>
            <h1 className="text-xl font-semibold text-sre-text text-center">
              Verify MFA
            </h1>
            <p className="text-sre-text-muted text-sm text-center">
              Enter your authenticator code (or recovery code) to finish sign in.
            </p>
            <div>
              <label
                htmlFor="oidcMfaCode"
                className="block text-sm font-medium text-sre-text mb-1"
              >
                MFA code
              </label>
              <input
                id="oidcMfaCode"
                type="text"
                autoFocus
                value={mfaCode}
                onChange={(e) => setMfaCode(e.target.value)}
                placeholder="Enter code"
                className="w-full px-3 py-2 bg-sre-bg rounded text-sre-text dark:bg-transparent"
              />
            </div>
            {error ? (
              <p className="text-red-500 text-sm text-center">{error}</p>
            ) : null}
            <div className="flex items-center justify-between">
              <button
                type="button"
                className="text-sre-primary hover:text-sre-primary-light text-sm"
                onClick={() => navigate("/login", { replace: true })}
              >
                Back to login
              </button>
              <button
                type="submit"
                className="px-4 py-2 bg-sre-primary text-white rounded"
                disabled={mfaSubmitting}
              >
                {mfaSubmitting ? "Verifying..." : "Verify and continue"}
              </button>
            </div>
          </form>
        ) : (
          <div className="text-center">
            <h1 className="text-xl font-semibold text-red-500 mb-2">
              Unable to sign in
            </h1>
            <p className="text-sre-text-muted text-sm mb-4">{error}</p>
            <button
              type="button"
              className="text-sre-primary hover:text-sre-primary-light"
              onClick={() => navigate("/login", { replace: true })}
            >
              Back to login
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

import { useState } from "react";

import { Field } from "../components/ui";

export function SignInPage() {
  const [token, setToken] = useState("");
  return (
    <div className="signin">
      <form
        className="card"
        onSubmit={(event) => {
          event.preventDefault();
          window.location.href = `/auth/login?token=${encodeURIComponent(token.trim())}`;
        }}
      >
        <h1>Sign in</h1>
        <p className="muted">
          Open the sign-in link <code>workspace serve</code> printed, or paste your owner token here. It stays on this machine.
        </p>
        <Field label="Token">
          <input type="password" autoComplete="off" value={token} onChange={(e) => setToken(e.target.value)} />
        </Field>
        <button type="submit" className="primary" disabled={!token.trim()}>
          Sign in
        </button>
      </form>
    </div>
  );
}

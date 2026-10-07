// Policies: how the Brain is governed. How often each area or kind of entry is checked, what
// applies without review, how much one conversation may propose, how long the detail of each
// handout is kept, and who answers for entries that name nobody. Saving is one undo point.

import { type FormEvent, useEffect, useState } from "react";
import { Link } from "react-router";

import { useBrainPolicies, useSetBrainPolicies } from "../../api/hooks";
import type { BrainPolicies } from "../../api/types";
import { ErrorNote, Field, Loading, Section } from "../../components/ui";
import { label } from "../../lib/format";
import { ownerName } from "./shared";

type Form = {
  review_days: Record<string, string>;
  default_owner: string;
  auto_apply_own_scope: boolean;
  auto_apply_scopes: string;
  max_proposals_per_session: string;
  retention_days: string;
};

function formOf(policy: BrainPolicies): Form {
  return {
    review_days: Object.fromEntries(Object.entries(policy.review_days).map(([k, v]) => [k, String(v)])),
    default_owner: policy.default_owner === policy.approver ? "" : policy.default_owner,
    auto_apply_own_scope: policy.auto_apply_own_scope,
    auto_apply_scopes: policy.auto_apply_scopes.join(", "),
    max_proposals_per_session: String(policy.max_proposals_per_session),
    retention_days: String(policy.retention_days),
  };
}

export function PoliciesPage() {
  const { data: policy, isLoading, error } = useBrainPolicies();
  const save = useSetBrainPolicies();
  const [form, setForm] = useState<Form | null>(null);
  const [saved, setSaved] = useState(false);
  useEffect(() => {
    if (policy && !form) setForm(formOf(policy));
  }, [policy, form]);
  if (isLoading) return <Loading />;
  if (!policy || !form) return <ErrorNote error={error} />;
  const set = <K extends keyof Form>(key: K, value: Form[K]) => {
    setSaved(false);
    setForm((now) => (now ? { ...now, [key]: value } : now));
  };
  const cadence = (name: string, value: string) => set("review_days", { ...form.review_days, [name]: value });

  function submit(event: FormEvent) {
    event.preventDefault();
    if (!policy || !form) return;
    const before = formOf(policy);
    const changes: Partial<BrainPolicies> = {};
    const days = Object.fromEntries(
      Object.entries(form.review_days)
        .filter(([, v]) => v.trim())
        .map(([k, v]) => [k, Number(v)]),
    );
    if (JSON.stringify(days) !== JSON.stringify(policy.review_days)) changes.review_days = days;
    if (form.default_owner !== before.default_owner) changes.default_owner = form.default_owner;
    if (form.auto_apply_own_scope !== before.auto_apply_own_scope) changes.auto_apply_own_scope = form.auto_apply_own_scope;
    if (form.auto_apply_scopes !== before.auto_apply_scopes) {
      changes.auto_apply_scopes = form.auto_apply_scopes
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean);
    }
    if (form.max_proposals_per_session !== before.max_proposals_per_session) {
      changes.max_proposals_per_session = Number(form.max_proposals_per_session);
    }
    if (form.retention_days !== before.retention_days) changes.retention_days = Number(form.retention_days);
    if (!Object.keys(changes).length) {
      setSaved(true);
      return;
    }
    save.mutate(changes, {
      onSuccess: (result) => {
        setForm(formOf(result.policy));
        setSaved(true);
      },
    });
  }

  const rows: [string, string, string][] = [
    ...policy.areas.map((key) => ["area", key, label(key)] as [string, string, string]),
    ...policy.kinds.map((key) => ["kind", key, label(key)] as [string, string, string]),
  ];
  return (
    <form className="policies" onSubmit={submit} aria-label="How the Brain is governed">
      <p className="section-lede">
        How the Brain is governed. Saving is one undo point; every change is in the Brain's <Link to="/brain/history">history</Link>.
        Approvals are yours: {ownerName(policy.approver, policy.approver)} ({policy.approver}).
      </p>
      <Section title="How often entries are checked">
        <p className="muted small">
          An entry is due for a check this many days after it was last confirmed, and ranks lower until it is. Between an entry's
          area and its kind, the shorter cadence wins; an entry's own cadence wins over both. Empty: no cadence.
        </p>
        <table className="table cadence-table">
          <thead>
            <tr>
              <th>For</th>
              <th className="num">Every (days)</th>
            </tr>
          </thead>
          <tbody>
            {rows.map(([group, key, name]) => (
              <tr key={`${group}:${key}`}>
                <td>
                  {name} <span className="muted small">{group}</span>
                </td>
                <td className="num">
                  <input
                    aria-label={`Check ${name} every how many days`}
                    inputMode="numeric"
                    value={form.review_days[key] ?? ""}
                    onChange={(event) => cadence(key, event.target.value)}
                  />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Section>
      <Section title="Who answers for entries">
        <Field label="Default owner" hint="For entries that name no owner of their own.">
          <select value={form.default_owner} onChange={(event) => set("default_owner", event.target.value)}>
            <option value="">You ({policy.approver})</option>
            {policy.scopes
              .filter((scope) => scope !== policy.approver)
              .map((scope) => (
                <option key={scope} value={scope}>
                  {ownerName(scope)} ({scope})
                </option>
              ))}
          </select>
        </Field>
      </Section>
      <Section title="What applies without review">
        <label className="check">
          <input
            type="checkbox"
            checked={form.auto_apply_own_scope}
            onChange={(event) => set("auto_apply_own_scope", event.target.checked)}
          />{" "}
          A change inside the proposer's own person scope (their preferences) applies at once
        </label>
        <Field label="Other scopes that apply at once" hint="Comma-separated patterns, like person:*. Empty: everything else waits for you.">
          <input value={form.auto_apply_scopes} onChange={(event) => set("auto_apply_scopes", event.target.value)} />
        </Field>
        <Field label="Proposals one conversation may make" hint="Keeps the review a place you can get through.">
          <input inputMode="numeric" value={form.max_proposals_per_session} onChange={(event) => set("max_proposals_per_session", event.target.value)} />
        </Field>
      </Section>
      <Section title="What is kept about use">
        <Field
          label="Keep the detail of each handout for (days)"
          hint="Which conversation got which version, why, and what it asked. Daily counts are kept for good."
        >
          <input inputMode="numeric" value={form.retention_days} onChange={(event) => set("retention_days", event.target.value)} />
        </Field>
      </Section>
      <div className="row">
        <button type="submit" className="primary" disabled={save.isPending}>
          Save the policy
        </button>
        {saved && !save.isPending ? <span className="muted small" role="status">Saved.</span> : null}
      </div>
      <ErrorNote error={save.error} />
    </form>
  );
}

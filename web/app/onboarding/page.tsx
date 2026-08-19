"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { api, setSession, ApiError, type SignupResult } from "@/lib/api";
import { useApp } from "@/components/providers";
import { Share2, Copy, Check, ArrowRight } from "lucide-react";

// Real signup: creates user, org, project, and a development API key on the
// server (persisted). The key secret is shown exactly once. The first memory
// is written into the user's OWN project through the live API.
export default function Onboarding() {
  const router = useRouter();
  const { setProject } = useApp();
  const [step, setStep] = useState(0);
  const [email, setEmail] = useState("");
  const [org, setOrg] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [acct, setAcct] = useState<SignupResult | null>(null);
  const [copied, setCopied] = useState(false);
  const [memoryDone, setMemoryDone] = useState<string | null>(null);

  async function doSignup() {
    setBusy(true); setErr(null);
    try {
      const res = await api.signup({ email, org: org || undefined, project: "My first project" });
      setSession(res.token);
      setAcct(res);
      if (res.project) setProject(res.project.id);
      setStep(res.existing ? 3 : 1);
    } catch (e) { setErr((e as ApiError).message); }
    setBusy(false);
  }

  async function firstMemory() {
    if (!acct?.project) return;
    setBusy(true); setErr(null);
    const pid = acct.project.id;
    try {
      await api.createEntity(pid, { id: "customer:first", type: "person", label: "Your first customer" });
      await api.createAgent(pid, { id: "my-agent@v1", kind: "system", label: "Your first agent" });
      await api.createEvent(pid, { id: "note:welcome", kind: "note", event_time: "now", label: "Onboarding note" });
      const b = await api.remember(pid, {
        agent: "my-agent@v1", subjects: ["customer:first"],
        proposition: "prefers_annual_billing", because: ["note:welcome"],
        label: "Customer prefers annual billing",
      });
      const st = await api.propositionState(pid, { subjects: ["customer:first"], proposition: "prefers_annual_billing" });
      setMemoryDone(`${b.id} → ${st.state}`);
      setStep(3);
    } catch (e) { setErr((e as ApiError).message); }
    setBusy(false);
  }

  return (
    <div className="mx-auto max-w-lg px-6 py-16">
      <Link href="/" className="mb-10 flex items-center gap-2">
        <span className="grid h-6 w-6 place-items-center rounded-pill bg-accent text-white">
          <Share2 className="h-3 w-3" />
        </span>
        <span className="text-[15px] font-bold tracking-tight">OMEM</span>
      </Link>

      {step === 0 && (
        <div className="panel p-6">
          <h1 className="display text-[22px]">Create your workspace</h1>
          <p className="mt-1.5 text-[13px] text-muted">An organization, a project, and a development API key. Stored on your local OMEM server.</p>
          <label className="mt-5 block text-2xs text-muted">Email</label>
          <input value={email} onChange={e => setEmail(e.target.value)} placeholder="you@company.com" type="email"
            className="mt-1 w-full rounded-md border bg-panel px-3 py-2 text-sm outline-none focus:border-accent" />
          <label className="mt-3 block text-2xs text-muted">Organization (optional)</label>
          <input value={org} onChange={e => setOrg(e.target.value)} placeholder="Acme"
            className="mt-1 w-full rounded-md border bg-panel px-3 py-2 text-sm outline-none focus:border-accent" />
          {err && <div className="mt-3 rounded-md border border-conflict/40 bg-conflictBg px-3 py-2 text-2xs text-conflict">{err}</div>}
          <button onClick={doSignup} disabled={busy || !email.includes("@")}
            className="mt-5 inline-flex w-full items-center justify-center gap-2 rounded-md bg-accent px-4 py-2.5 text-[14px] font-semibold text-white transition-opacity hover:opacity-[0.88] disabled:opacity-40">
            {busy ? "Creating…" : "Continue"} <ArrowRight className="h-4 w-4" />
          </button>
        </div>
      )}

      {step === 1 && acct?.api_key && (
        <div className="panel p-6">
          <h1 className="display text-[22px]">Your development API key</h1>
          <p className="mt-1.5 text-[13px] text-muted">
            This secret is shown once. It is stored hashed; if you lose it, create a new key in Developers.
          </p>
          <div className="mt-4 flex items-center gap-2 rounded-md border bg-raised px-3 py-2.5">
            <code className="mono min-w-0 flex-1 truncate text-xs">{acct.api_key.secret}</code>
            <button onClick={() => { navigator.clipboard.writeText(acct.api_key!.secret!); setCopied(true); setTimeout(() => setCopied(false), 1200); }}
              className="p-1 text-muted hover:text-fg" aria-label="Copy">
              {copied ? <Check className="h-3.5 w-3.5 text-believed" /> : <Copy className="h-3.5 w-3.5" />}
            </button>
          </div>
          <button onClick={() => setStep(2)}
            className="mt-5 w-full rounded-md bg-accent px-4 py-2.5 text-[14px] font-semibold text-white transition-opacity hover:opacity-[0.88]">
            I saved it
          </button>
        </div>
      )}

      {step === 2 && (
        <div className="panel p-6">
          <h1 className="display text-[22px]">Store your first memory</h1>
          <p className="mt-1.5 text-[13px] text-muted">
            Runs against your project <span className="font-medium text-fg">{acct?.project?.name}</span> through the live API:
            an entity, an agent, an evidence event, then a grounded belief.
          </p>
          {err && <div className="mt-3 rounded-md border border-conflict/40 bg-conflictBg px-3 py-2 text-2xs text-conflict">{err}</div>}
          <button onClick={firstMemory} disabled={busy}
            className="mt-5 w-full rounded-md bg-accent px-4 py-2.5 text-[14px] font-semibold text-white transition-opacity hover:opacity-[0.88] disabled:opacity-40">
            {busy ? "Writing…" : "Store it"}
          </button>
        </div>
      )}

      {step === 3 && (
        <div className="panel p-6">
          <h1 className="display text-[22px]">{acct?.existing ? "Welcome back" : "You have memory"}</h1>
          {memoryDone && <p className="mono mt-2 text-xs text-believed">{memoryDone}</p>}
          <p className="mt-1.5 text-[13px] text-muted">
            {acct?.existing ? "Signed in. Your projects are ready." : "Your belief is stored, grounded, and queryable. Open the dashboard to inspect it."}
          </p>
          <button onClick={() => router.push("/overview")}
            className="mt-5 inline-flex w-full items-center justify-center gap-2 rounded-md bg-accent px-4 py-2.5 text-[14px] font-semibold text-white transition-opacity hover:opacity-[0.88]">
            Open dashboard <ArrowRight className="h-4 w-4" />
          </button>
        </div>
      )}
    </div>
  );
}

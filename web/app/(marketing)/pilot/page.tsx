"use client";
import { useState } from "react";
import { MarketingShell } from "@/components/marketing/chrome";
import { Section, Eyebrow } from "@/components/marketing/ui";

/* The design-partner pilot request form. Replaces a mailto, which silently
 * fails for anyone without a desktop mail client set up (most people). The
 * product site is a static export with no backend, so the form posts to
 * Web3Forms, a free form-to-email relay. Set ACCESS_KEY below to your own key:
 * go to web3forms.com, enter your email, and it sends you the key. No account,
 * no dashboard. Submissions arrive in that inbox, with the sender's address as
 * the reply-to, so you just hit reply. To use a different service or a hosted
 * form instead, swap the fetch in submit(). No em dashes anywhere here. */

const ACCESS_KEY = "284a7bb5-610e-4b05-8e13-7f62af452796";

type Status = "idle" | "sending" | "sent" | "error";

export default function Pilot() {
  const [status, setStatus] = useState<Status>("idle");
  const [err, setErr] = useState("");

  async function submit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setStatus("sending");
    setErr("");
    const form = e.currentTarget;
    const fd = new FormData(form);
    // Honeypot: a real person leaves this empty; a bot fills every field.
    if (fd.get("botcheck")) { setStatus("sent"); return; }
    try {
      const res = await fetch("https://api.web3forms.com/submit", {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({
          access_key: ACCESS_KEY,
          subject: "OMEM design-partner pilot request",
          from_name: "OMEM pilot form",
          replyto: fd.get("email"),
          name: fd.get("name"),
          email: fd.get("email"),
          company: fd.get("company"),
          message: fd.get("message"),
        }),
      });
      const data = await res.json();
      if (data.success) {
        setStatus("sent");
        form.reset();
      } else {
        setStatus("error");
        setErr(data.message || "The form could not be sent.");
      }
    } catch {
      setStatus("error");
      setErr("The form could not be sent. Check your connection and try again.");
    }
  }

  return (
    <MarketingShell>
      <Section className="hero-y">
        <Eyebrow>Design-partner pilot</Eyebrow>
        <h1 className="display mt-3 max-w-[24ch] text-3xl sm:text-4xl">
          Tell me what your agent does, and where it gets asked to explain itself.
        </h1>
        <p className="lede mt-6 max-w-[52ch]">
          OMEM itself is free and open source, and always will be. The pilot is
          my time, not a license: over a couple of weeks I put the approval gate
          and the provenance trail into your agent, and you walk away with a
          record you can show a client&rsquo;s compliance team. $1,500, small on
          purpose, and if the pilot does not produce a review-ready artifact,
          you do not pay. Fill this in and I will reply personally.
        </p>

        <div className="mt-10 max-w-xl rounded-lg border bg-panel p-6 sm:p-8">
          {status === "sent" ? (
            <div role="status" aria-live="polite">
              <h2 className="display text-xl">Got it. Thank you.</h2>
              <p className="mt-3 text-note text-muted">
                Your request is in. I read these myself and will reply to the
                email you gave, usually within a day or two. If it is urgent, the
                fastest backup is opening an issue on{" "}
                <a href="https://github.com/troybrandonc-bit/Omem/issues" rel="noreferrer"
                  className="text-accent hover:underline">GitHub</a>.
              </p>
            </div>
          ) : (
            <form onSubmit={submit} className="space-y-5">
              {/* Honeypot, visually hidden and off the tab order. */}
              <input type="checkbox" name="botcheck" tabIndex={-1} autoComplete="off"
                className="hidden" aria-hidden="true" />

              <div>
                <label htmlFor="name" className="mb-1.5 block text-note font-medium">Your name</label>
                <input id="name" name="name" type="text" required autoComplete="name" className="field" />
              </div>
              <div>
                <label htmlFor="email" className="mb-1.5 block text-note font-medium">Email</label>
                <input id="email" name="email" type="email" required autoComplete="email" className="field" />
              </div>
              <div>
                <label htmlFor="company" className="mb-1.5 block text-note font-medium">
                  Company, or what you are building
                </label>
                <input id="company" name="company" type="text" className="field" />
              </div>
              <div>
                <label htmlFor="message" className="mb-1.5 block text-note font-medium">
                  What does your agent do, and where does accountability come up?
                </label>
                <textarea id="message" name="message" rows={5} className="field"
                  placeholder="For example: we ship a support agent to clients, and their security review asks how we prove why it did something." />
              </div>

              {status === "error" && (
                <p role="alert" className="rounded-md border border-[color:var(--conflict)]/40 bg-conflictBg px-3 py-2.5 text-note text-conflict">
                  {err}
                </p>
              )}

              <button type="submit" disabled={status === "sending"}
                className="on-accent inline-flex h-control-lg items-center justify-center rounded-md bg-accent px-6 text-note font-medium text-accentFg transition-[background-color,transform] duration-1 ease-out hover:bg-accentHover active:scale-[0.98] disabled:opacity-50 disabled:active:scale-100">
                {status === "sending" ? "Sending" : "Request a pilot"}
              </button>
            </form>
          )}
        </div>
      </Section>
    </MarketingShell>
  );
}

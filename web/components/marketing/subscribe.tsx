"use client";
import { useState } from "react";

/* Release-notes subscription. The first owned-channel brick: an email capture
 * that costs no new account. It posts to the same Web3Forms relay as /pilot,
 * so each subscriber arrives in the inbox with subject "OMEM subscribe" and the
 * address as reply-to; keep them in a list (or move to a real list tool like
 * Buttondown once volume justifies it; swap the fetch here when so). */

const ACCESS_KEY = "284a7bb5-610e-4b05-8e13-7f62af452796";

export function Subscribe() {
  const [status, setStatus] = useState<"idle" | "sending" | "sent" | "error">("idle");

  async function submit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setStatus("sending");
    const fd = new FormData(e.currentTarget);
    if (fd.get("botcheck")) { setStatus("sent"); return; }
    try {
      const res = await fetch("https://api.web3forms.com/submit", {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({
          access_key: ACCESS_KEY,
          subject: "OMEM subscribe",
          from_name: "OMEM release notes",
          replyto: fd.get("email"),
          email: fd.get("email"),
          message: "New release-notes subscriber.",
        }),
      });
      setStatus((await res.json()).success ? "sent" : "error");
    } catch {
      setStatus("error");
    }
  }

  if (status === "sent") {
    return (
      <p role="status" className="text-note text-muted">
        You&rsquo;re on the list. Releases only, no other mail.
      </p>
    );
  }
  return (
    <form onSubmit={submit} className="flex max-w-md flex-wrap items-center gap-2">
      <input type="checkbox" name="botcheck" tabIndex={-1} autoComplete="off"
        className="hidden" aria-hidden="true" />
      <label htmlFor="sub-email" className="sr-only">Email address</label>
      <input id="sub-email" name="email" type="email" required placeholder="you@company.com"
        autoComplete="email" className="field min-w-0 flex-1" />
      <button type="submit" disabled={status === "sending"}
        className="on-accent inline-flex h-control-lg items-center justify-center rounded-md bg-accent px-4 text-sm font-medium leading-none text-accentFg transition-[background-color,transform] duration-1 ease-out hover:bg-accentHover active:scale-[0.98] disabled:opacity-50">
        {status === "sending" ? "Sending" : "Get release notes"}
      </button>
      {status === "error" && (
        <p role="alert" className="w-full text-caption text-conflict">
          That did not send. Check the address and try again.
        </p>
      )}
    </form>
  );
}

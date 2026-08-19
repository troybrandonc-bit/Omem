"use client";
import { useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { api } from "@/lib/api";
import { useApp } from "@/components/providers";
import { CheckCircle2, AlertCircle, RefreshCw } from "lucide-react";

// Google redirects the browser here when GOOGLE_REDIRECT_URI points at the
// frontend (port 3000). The API also serves this path directly (port 8787), so
// either redirect URI works. This page hands code+state to the API, which
// verifies the signed single-use state and performs the real token exchange.
export default function GmailCallback() {
  const params = useSearchParams();
  const router = useRouter();
  const { project } = useApp();
  const [state, setState] = useState<"working" | "done" | "error">("working");
  const [message, setMessage] = useState("Completing the Gmail connection…");

  useEffect(() => {
    const code = params.get("code");
    const oauthState = params.get("state");
    const denied = params.get("error");

    if (denied) {
      setState("error");
      setMessage(`Google returned "${denied}". The mailbox was not connected.`);
      return;
    }
    if (!code || !oauthState) {
      setState("error");
      setMessage("Missing authorisation code or state in the redirect.");
      return;
    }
    (async () => {
      try {
        await api.gmailCallback(project, undefined, undefined, { code, state: oauthState });
        setState("done");
        setMessage("Gmail connected. Redirecting to Sources…");
        setTimeout(() => router.push("/sources"), 1200);
      } catch (e) {
        setState("error");
        setMessage((e as Error).message);
      }
    })();
    // run once on mount: the state value is single-use
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const Icon = state === "done" ? CheckCircle2 : state === "error" ? AlertCircle : RefreshCw;

  return (
    <div className="mx-auto max-w-lg py-20">
      <section className="panel px-6 py-8 text-center">
        <Icon
          className={
            "mx-auto h-6 w-6 " +
            (state === "done" ? "text-believed" : state === "error" ? "text-conflict" : "animate-spin text-muted")
          }
        />
        <h1 className="display mt-4 text-[19px]">
          {state === "done" ? "Connected" : state === "error" ? "Connection failed" : "Connecting Gmail"}
        </h1>
        <p className="mt-2 text-[13px] text-muted">{message}</p>
        {state === "error" && (
          <button
            onClick={() => router.push("/sources")}
            className="mt-5 rounded-md border px-3 py-1.5 text-[13px] font-medium text-muted hover:border-line-strong"
          >
            Back to Sources
          </button>
        )}
      </section>
    </div>
  );
}

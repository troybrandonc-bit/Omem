"use client";

import { useEffect, useState } from "react";

/* The live numbers, read from the collector rather than typed into the page.
 *
 * The honest states are the point. The bank starts empty, and a page that
 * hides that until it looks impressive would be the same kind of lie the rest
 * of this project refuses. So zero says zero, an unreachable collector says
 * so rather than showing a stale number, and nothing here is ever rounded up. */

const ENDPOINT = "https://commons.omem-cloud.com/v1/commons/public";

type Stats = { contributors: number; patterns: number; stances: number };

export function CommonsLive() {
  const [stats, setStats] = useState<Stats | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let live = true;
    fetch(ENDPOINT, { cache: "no-store" })
      .then(r => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
      .then(b => { if (live) setStats(b?.stats ?? null); })
      .catch(() => { if (live) setFailed(true); });
    return () => { live = false; };
  }, []);

  if (failed) {
    return (
      <p className="mt-8 text-note text-muted">
        The collector did not answer just now. Rather than show you a number we
        cannot check, here is nothing: the live figures are at{" "}
        <a className="link" href={ENDPOINT}>{ENDPOINT}</a>.
      </p>
    );
  }

  const cells: [string, string][] = [
    ["installations contributing", stats ? String(stats.contributors) : "—"],
    ["patterns in the bank", stats ? String(stats.patterns) : "—"],
    ["stances behind them", stats ? String(stats.stances) : "—"],
  ];

  return (
    <div className="mt-10">
      <dl className="grid gap-6 sm:grid-cols-3">
        {cells.map(([label, value]) => (
          <div key={label}>
            <dd className="text-hero font-semibold tabular-nums">{value}</dd>
            <dt className="mt-1 text-note text-muted">{label}</dt>
          </div>
        ))}
      </dl>
      {stats && stats.contributors === 0 && (
        <p className="mt-6 max-w-read text-note text-muted">
          Nobody has contributed yet. That is the true state of it today, and
          the reason it is on the page: a bank that reports its own emptiness
          is one you can believe later, when it does not.
        </p>
      )}
      {stats && stats.contributors === 1 && (
        <p className="mt-6 max-w-read text-note text-muted">
          One installation. A pattern needs two separate ones before it returns
          to anybody, so nothing is flowing back yet.
        </p>
      )}
    </div>
  );
}

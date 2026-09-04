"use client";
import { useEffect, useState } from "react";

/* What is actually in the commons, fetched live, including when the answer is
 * nothing.
 *
 * The commons page described the bank in the abstract, which is the wrong way
 * round for something people are being asked to join. Somebody deciding
 * whether to contribute is owed its real size rather than its ambition, and a
 * counter reading zero is better than a paragraph, because zero is legible and
 * a paragraph is not.
 *
 * Every state here is stated plainly. Not yet collecting is a fact and reads
 * as one. An empty bank is a fact. A bank that cannot be reached says so
 * rather than rendering nothing and letting the page imply the numbers are
 * being withheld.
 *
 * No em dashes. */

const ENDPOINT = "https://commons.omem-cloud.com/v1/commons/public";

type Stats = {
  contributors: number;
  patterns: number;
  stances: number;
  strong: number;
};

type State =
  | { kind: "loading" }
  | { kind: "live"; stats: Stats; datasetPublic: boolean }
  | { kind: "not-collecting" }
  | { kind: "unreachable" };

const FIGURES: [keyof Stats, string, string][] = [
  ["contributors", "contributing installs", "Each one a uuid minted on a machine, carrying nothing about it or its owner."],
  ["patterns", "regularities", "A pair of behaviour tokens, with how often the second followed the first and how often it did not."],
  ["stances", "observations behind them", "Every individual support or refutation counted, which is the number the rates are computed from."],
  ["strong", "holding at 0.8 or better", "Reported separately because a regularity that holds four times in five is a different object from one that holds half the time."],
];

export function CommonsState() {
  const [state, setState] = useState<State>({ kind: "loading" });

  useEffect(() => {
    let live = true;
    const timer = setTimeout(() => {
      if (live) setState((s) => (s.kind === "loading" ? { kind: "unreachable" } : s));
    }, 8000);

    fetch(ENDPOINT, { headers: { Accept: "application/json" } })
      .then(async (r) => {
        if (r.status === 404) return { notCollecting: true } as const;
        if (!r.ok) throw new Error(String(r.status));
        return r.json();
      })
      .then((d) => {
        if (!live) return;
        if ("notCollecting" in d) return setState({ kind: "not-collecting" });
        setState({
          kind: "live",
          stats: d.stats as Stats,
          datasetPublic: Boolean(d.dataset_public),
        });
      })
      .catch(() => live && setState({ kind: "unreachable" }))
      .finally(() => clearTimeout(timer));

    return () => {
      live = false;
      clearTimeout(timer);
    };
  }, []);

  if (state.kind === "loading") {
    return <p className="mt-6 text-note text-muted">Reading the bank...</p>;
  }

  if (state.kind === "not-collecting" || state.kind === "unreachable") {
    return (
      <div className="mt-6 max-w-2xl">
        <p className="text-note leading-relaxed text-muted">
          {state.kind === "not-collecting"
            ? "The collector is not accepting contributions yet, so the bank is empty. That is the honest state of it today and this line will change when it is not."
            : "The collector could not be reached just now, so what follows would be a guess. Rather than show a number that might be wrong, here is nothing."}
        </p>
        <p className="mt-3 text-note leading-relaxed text-muted">
          The format is published regardless, and does not depend on any
          particular software:{" "}
          <a href="/spec/commons-contribution" className="underline hover:text-fg">
            contributing counts
          </a>
          .
        </p>
      </div>
    );
  }

  const { stats, datasetPublic } = state;
  const empty = stats.patterns === 0 && stats.contributors === 0;

  return (
    <div className="mt-6 max-w-2xl">
      {empty ? (
        <p className="text-note leading-relaxed text-muted">
          Nothing in it yet. The collector is running and has received no
          contributions, which is what a commons looks like on its first day and
          is worth saying plainly rather than describing what it will hold.
        </p>
      ) : (
        <dl className="grid gap-x-12 gap-y-6 sm:grid-cols-2">
          {FIGURES.map(([key, label, note]) => (
            <div key={key}>
              <dt className="display text-2xl tabular-nums">
                {stats[key].toLocaleString("en-GB")}
              </dt>
              <dd className="mt-0.5 text-note font-semibold">{label}</dd>
              <dd className="mt-1 text-caption leading-relaxed text-muted">{note}</dd>
            </div>
          ))}
        </dl>
      )}

      <p className="mt-6 text-caption leading-relaxed text-muted">
        Read live from the collector as this page loaded, not written by hand.
        {datasetPublic
          ? " The corpus itself is published and downloadable."
          : " The counts are public; the corpus is not published yet, which is a deliberate decision rather than an oversight."}
      </p>
    </div>
  );
}

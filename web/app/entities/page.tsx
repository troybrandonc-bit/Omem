"use client";
import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { api, type Entity, type Assertion } from "@/lib/api";
import { useApp } from "@/components/providers";
import { Skeleton, EmptyState, ErrorState } from "@/components/ui/primitives";
import { Building2, User, Box } from "lucide-react";

// Entities, read as two things a person actually asks about: the companies you
// keep memory on, and the people you deal with at them. Type + id-prefix decide
// which is which; the works_at relation says which company a contact belongs to.

function humanize(id: string): string {
  const rest = id.includes(":") ? id.slice(id.indexOf(":") + 1) : id;
  return rest.split("@")[0].replace(/[-_.]/g, " ").replace(/\b\w/g, c => c.toUpperCase());
}
function labelOf(e: Entity): string {
  return e.label || humanize(e.id);
}
type Kind = "company" | "contact" | "other";
function kindOf(e: Entity): Kind {
  const t = (e.type || "").toLowerCase();
  const prefix = e.id.includes(":") ? e.id.slice(0, e.id.indexOf(":")).toLowerCase() : "";
  if (["organization", "organisation", "company", "org", "vendor", "account", "business"].includes(t)
      || ["company", "org", "vendor", "account"].includes(prefix)) return "company";
  if (["person", "contact", "people", "customer", "user", "employee"].includes(t)
      || ["person", "contact", "customer", "people"].includes(prefix)) return "contact";
  return "other";
}

export default function Entities() {
  const { project } = useApp();
  const ents = useQuery({
    queryKey: ["entities", project], queryFn: () => api.entities(project), enabled: !!project });
  // Relations + beliefs let us say who a contact is and how much is on file for
  // a company, without a second round-trip per entity.
  const asserts = useQuery({
    queryKey: ["entity-assertions", project],
    queryFn: () => api.assertions(project, { as_of: "now" }), enabled: !!project });

  const model = useMemo(() => {
    const entities = (ents.data?.data ?? []).filter(e => !e.id.startsWith("cohort:"));
    const rows = asserts.data?.data ?? [];
    const label = new Map(entities.map(e => [e.id, labelOf(e)]));

    // person -> company, from the works_at relation.
    const employer = new Map<string, string>();
    // company -> count of (non-relation) beliefs held about it.
    const factsOn = new Map<string, number>();
    for (const a of rows) {
      if (a.is_retraction) continue;
      const isRel = a.proposition.startsWith("rel_");
      if (isRel && a.proposition.includes("works_at") && a.subjects.length >= 2) {
        const person = a.subjects.find(s => s.startsWith("person:")) ?? a.subjects[0];
        const company = a.subjects.find(s => s.startsWith("company:"))
          ?? a.subjects.find(s => s !== person);
        if (person && company) employer.set(person, company);
      }
      if (!isRel) {
        const subj = a.subjects[0];
        if (subj) factsOn.set(subj, (factsOn.get(subj) ?? 0) + 1);
      }
    }

    const companies = entities.filter(e => kindOf(e) === "company")
      .sort((a, b) => labelOf(a).localeCompare(labelOf(b)));
    const contacts = entities.filter(e => kindOf(e) === "contact")
      .sort((a, b) => labelOf(a).localeCompare(labelOf(b)));
    const other = entities.filter(e => kindOf(e) === "other");

    const peopleAt = new Map<string, string[]>();
    for (const c of contacts) {
      const emp = employer.get(c.id);
      if (emp) peopleAt.set(emp, [...(peopleAt.get(emp) ?? []), c.id]);
    }
    return { companies, contacts, other, label, employer, factsOn, peopleAt };
  }, [ents.data, asserts.data]);

  const loading = ents.isLoading || asserts.isLoading;
  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <div>
        <h1 className="display text-lg">Entities</h1>
        <p className="mt-1 max-w-2xl text-sm text-muted">
          Everyone and everything OMEM holds memory about, split into the
          companies you track and the people you deal with at them.
        </p>
      </div>

      {loading ? <Skeleton className="h-64" /> :
        ents.isError || !ents.data ? <ErrorState title="Could not read entities" onRetry={() => ents.refetch()} /> :
        model.companies.length + model.contacts.length + model.other.length === 0 ?
          <EmptyState icon={Box} title="No entities yet"
            body="Observe an interaction or connect a source, and the people and companies it mentions show up here." /> :
        <>
          {model.companies.length > 0 && (
            <section>
              <SectionHead icon={Building2} title="Companies" count={model.companies.length} />
              <div className="grid gap-2 sm:grid-cols-2">
                {model.companies.map(c => {
                  const people = model.peopleAt.get(c.id) ?? [];
                  const facts = model.factsOn.get(c.id) ?? 0;
                  return (
                    <Link key={c.id} href={`/entity?id=${encodeURIComponent(c.id)}`}
                      className="panel group block px-4 py-3 hover:border-accent">
                      <div className="flex items-center gap-2">
                        <Building2 className="h-4 w-4 text-muted" />
                        <span className="text-sm font-semibold group-hover:text-accent">{model.label.get(c.id)}</span>
                      </div>
                      <div className="mt-1 text-2xs text-muted">
                        {facts > 0 ? `${facts} ${facts === 1 ? "fact" : "facts"} on record` : "no facts yet"}
                        {people.length > 0 && ` · ${people.length} ${people.length === 1 ? "contact" : "contacts"}`}
                      </div>
                      {people.length > 0 && (
                        <div className="mt-1.5 flex flex-wrap gap-1">
                          {people.map(p => (
                            <span key={p} className="rounded-sm border bg-raised/60 px-1.5 py-0.5 text-2xs text-ink">
                              {model.label.get(p)}
                            </span>
                          ))}
                        </div>
                      )}
                    </Link>
                  );
                })}
              </div>
            </section>
          )}

          {model.contacts.length > 0 && (
            <section>
              <SectionHead icon={User} title="Contacts" count={model.contacts.length} />
              <div className="panel divide-y overflow-hidden">
                {model.contacts.map(p => {
                  const emp = model.employer.get(p.id);
                  return (
                    <Link key={p.id} href={`/entity?id=${encodeURIComponent(p.id)}`}
                      className="group flex items-center justify-between gap-3 px-4 py-2.5 hover:bg-[color:var(--border)]/20">
                      <div className="flex items-center gap-2.5">
                        <User className="h-4 w-4 shrink-0 text-muted" />
                        <span className="text-sm font-medium group-hover:text-accent">{model.label.get(p.id)}</span>
                      </div>
                      <span className="text-2xs text-muted">
                        {emp ? <>Works at <span className="font-semibold text-ink">{model.label.get(emp)}</span></>
                             : "No company on record"}
                      </span>
                    </Link>
                  );
                })}
              </div>
            </section>
          )}

          {model.other.length > 0 && (
            <section>
              <SectionHead icon={Box} title="Other" count={model.other.length} />
              <div className="panel divide-y overflow-hidden">
                {model.other.map(e => (
                  <Link key={e.id} href={`/entity?id=${encodeURIComponent(e.id)}`}
                    className="group flex items-center justify-between gap-3 px-4 py-2.5 hover:bg-[color:var(--border)]/20">
                    <span className="text-sm font-medium group-hover:text-accent">{model.label.get(e.id)}</span>
                    <span className="text-2xs text-faint">{e.type || "entity"}</span>
                  </Link>
                ))}
              </div>
            </section>
          )}
        </>}
    </div>
  );
}

function SectionHead({ icon: Icon, title, count }:
  { icon: typeof Building2; title: string; count: number }) {
  return (
    <div className="mb-1.5 flex items-baseline gap-2 px-1">
      <Icon className="h-4 w-4 self-center text-faint" />
      <h2 className="text-sm font-semibold">{title}</h2>
      <span className="text-2xs text-faint">{count}</span>
    </div>
  );
}

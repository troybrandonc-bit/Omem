import { CodeBlock, ButtonLink } from "@/components/marketing/ui";

export const metadata = {
  title: "Installing a licence",
  description:
    "How to install and verify an OMEM enterprise licence. Verification is offline: no callback, no telemetry, nothing to phone home. An expired licence stops unlocking paid components and never stops the server.",
};

/* Written for two readers who arrive at once: the engineer installing the
 * token, and the security reviewer standing behind them asking what it talks
 * to. The second one is the reason the "what it does not do" section is near
 * the top rather than buried at the bottom. No em dashes. */

const INSTALL = `# as an environment variable
export OMEM_LICENCE="eyJjdXN0b21lciI6...Ijp9.Xk3v..."

# or from a file, which is easier to rotate
export OMEM_LICENCE_FILE=/etc/omem/licence.token

omem-server`;

const VERIFY = `curl -H "Authorization: Bearer $OMEM_API_KEY" \
  http://127.0.0.1:8787/v1/licence

{
  "licensed": true,
  "customer": "Acme Ltd",
  "expires": 1790000000,
  "features": ["approval_policy"],
  "catalogue": { "approval_policy": "Policy over who may approve which risk class" }
}`;

const POLICY = `curl -X POST -H "Authorization: Bearer $OMEM_OWNER_KEY" \
  -H "Content-Type: application/json" \
  "http://127.0.0.1:8787/v1/healing/policy?project=$PROJECT" -d '{
    "default": "allow",
    "rules": [
      {"action_type": "issue_refund", "approvers": ["key:key_finance"]},
      {"risk_class": "high", "approvers": ["user:usr_head_of_ops"]}
    ]
  }'`;

export default function LicenceDocs() {
  return (
    <article className="prose-omem max-w-3xl">
      <div className="tech-label mb-3">Documentation</div>
      <h1 className="display text-3xl">Installing a licence</h1>

      <p className="lede">
        A licence unlocks the components in <span className="mono">server/ee/</span>.
        Everything else in OMEM works without one and always will.
      </p>

      <h2>What it does not do</h2>
      <p>
        Worth stating before the instructions, because it is the first question
        a security reviewer asks. Verification is a signature check against a
        public key compiled into the server. It opens no connection, sends
        nothing anywhere, and reports no usage to us. There is no callback to
        fail, no endpoint to allowlist, and no telemetry to turn off. An OMEM
        server with a licence installed reaches the network exactly as often as
        one without: never, unless you connected something to it yourself.
      </p>
      <p>
        The server also cannot issue a licence. It holds the public half of the
        signing key, which can check a token and cannot produce one, so a
        complete read of the software you are running reveals no way to mint a
        licence for it.
      </p>

      <h2>Install it</h2>
      <CodeBlock single={INSTALL} filename="shell"
        label="Either form works. The file is easier to rotate" />
      <p>
        Nothing else changes. If the token is missing or invalid, the server
        starts normally and the paid components stay off.
      </p>

      <h2>Check it took</h2>
      <CodeBlock single={VERIFY} filename="terminal"
        label="Any authenticated caller may read this" />
      <p>
        Readable by anyone with a key on purpose, because the person asked to
        prove the install is licensed is usually not the person who bought it.
        It names the customer and the expiry and nothing else: no secret, and
        nothing about your data.
      </p>

      <h2>Use it: an approval policy</h2>
      <p>
        The free gate already refuses to let an agent approve its own action,
        and records every refusal. A policy narrows it further, so that the
        person who may clear a cache is not automatically the person who may
        move money.
      </p>
      <CodeBlock single={POLICY} filename="terminal"
        label="The first matching rule decides" />
      <p>
        Approvers are matched against the principal your authentication layer
        resolved, and then against the name the caller supplied. A policy written
        in terms of principals is the stronger one, because a name in a request
        body is written by whoever sent the request. Anything no rule covers
        falls to <span className="mono">default</span>, which is{" "}
        <span className="mono">allow</span> unless you say otherwise, so adding a
        rule about refunds does not silently freeze everything else.
      </p>
      <p>
        A refusal names the rule that refused it rather than saying
        &ldquo;denied by policy&rdquo;, so whoever is looking at the record can
        go and read the line responsible.
      </p>

      <h2>When it expires</h2>
      <p>
        Paid components stop unlocking. The server keeps running, the free gate
        keeps refusing agent self-approval, and every refusal is still recorded.
        An unpaid invoice should not become an outage, and a product that
        behaves otherwise teaches people not to buy infrastructure from a small
        company.
      </p>

      <h2>If you would rather not</h2>
      <p>
        Delete <span className="mono">server/ee/</span>. OMEM behaves exactly as
        the open version does, because the core does not depend on it. That is
        not a loophole, it is the design: the MIT core is MIT permanently and the
        paid parts are separate components rather than a relicensing of anything
        you already had.
      </p>

      <div className="mt-10 flex flex-wrap gap-3">
        <ButtonLink href="/pricing">What a licence costs</ButtonLink>
        <ButtonLink href="/pilot" variant="secondary">Talk about one</ButtonLink>
      </div>
    </article>
  );
}

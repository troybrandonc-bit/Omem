import type {
	IExecuteFunctions,
	INodeExecutionData,
	INodeType,
	INodeTypeDescription,
	IHttpRequestOptions,
} from 'n8n-workflow';
import { NodeOperationError } from 'n8n-workflow';

/* OMEM for n8n: belief-revision memory for agents in a workflow.
 *
 * Every operation is a thin call onto the self-hosted OMEM HTTP API. The
 * design mirrors what a workflow actually needs from trustworthy memory:
 * write a belief (Remember / Observe / Learn), read the current state
 * (Believes / Recall / Conflicts), and prove it afterwards (Why). Believes is
 * the branch primitive: an IF node downstream can route on BELIEVED_TRUE /
 * CONTRADICTED / UNKNOWN instead of trusting the latest write. */

export class Omem implements INodeType {
	description: INodeTypeDescription = {
		displayName: 'OMEM',
		name: 'omem',
		icon: 'file:omem.svg',
		group: ['transform'],
		version: 1,
		subtitle: '={{$parameter["operation"]}}',
		description:
			'The record of what an AI agent believed and did: keeps contradictions, proves why, self-hosted',
		defaults: { name: 'OMEM' },
		// String literal keeps compatibility across n8n-workflow versions where
		// NodeConnectionType is a type-only export.
		inputs: ['main'] as never,
		outputs: ['main'] as never,
		credentials: [{ name: 'omemApi', required: true }],
		properties: [
			{
				displayName: 'Operation',
				name: 'operation',
				type: 'options',
				noDataExpression: true,
				default: 'recall',
				options: [
					{ name: 'Believes', value: 'believes', action: 'Get the belief state of a claim', description: 'The four-valued state of a claim right now (BELIEVED_TRUE, BELIEVED_FALSE, CONTRADICTED, UNKNOWN)' },
					{ name: 'Conflicts', value: 'conflicts', action: 'List open contradictions', description: 'Every proposition where open assertions disagree, both sides included' },
					{ name: 'Learn', value: 'learn', action: 'Learn from free text', description: 'Extract candidate facts from text; the engine decides what becomes memory' },
					{ name: 'Observe', value: 'observe', action: 'Observe an interaction', description: 'Feed a raw interaction; OMEM decides what becomes memory' },
					{ name: 'Recall', value: 'recall', action: 'Recall relevant memory', description: 'Retrieve what is relevant, with belief state and conflicts attached' },
					{ name: 'Remember', value: 'remember', action: 'Record a belief', description: 'Record a claim as a belief with provenance' },
					{ name: 'Why', value: 'why', action: 'Get the provenance of a belief', description: 'Evidence, sources, interval, and contradictions behind one assertion' },
				],
			},
			// -- shared: agent --
			{
				displayName: 'Agent',
				name: 'agent',
				type: 'string',
				default: 'n8n',
				description: 'The agent this memory belongs to (created on first use)',
				displayOptions: { show: { operation: ['remember', 'observe', 'learn'] } },
			},
			// -- remember --
			{
				displayName: 'About',
				name: 'about',
				type: 'string',
				default: '',
				required: true,
				placeholder: 'customer:alice',
				description: 'The entity the claim is about',
				displayOptions: { show: { operation: ['remember', 'believes'] } },
			},
			{
				displayName: 'Claim',
				name: 'claim',
				type: 'string',
				default: '',
				required: true,
				placeholder: 'prefers_annual_billing',
				description: 'The proposition. Use not:claim to assert the opposite.',
				displayOptions: { show: { operation: ['remember', 'believes'] } },
			},
			{
				displayName: 'Evidence Note',
				name: 'evidenceNote',
				type: 'string',
				default: '',
				description: 'Optional human note recorded with the belief (the API label field)',
				displayOptions: { show: { operation: ['remember'] } },
			},
			// -- recall --
			{
				displayName: 'About',
				name: 'recallAbout',
				type: 'string',
				default: '',
				placeholder: 'customer:alice',
				description: 'Entity to recall about (leave empty to recall by context)',
				displayOptions: { show: { operation: ['recall'] } },
			},
			{
				displayName: 'As Of',
				name: 'asOf',
				type: 'string',
				default: '',
				placeholder: '2026-08-25T14:00:00Z',
				description: 'Reconstruct what was believed at this moment (ISO time). Empty means now.',
				displayOptions: { show: { operation: ['recall'] } },
			},
			{
				displayName: 'Limit',
				name: 'limit',
				type: 'number',
				default: 10,
				displayOptions: { show: { operation: ['recall'] } },
			},
			// -- why --
			{
				displayName: 'Assertion ID',
				name: 'assertionId',
				type: 'string',
				default: '',
				required: true,
				description: 'The assertion to explain (returned by Remember, Learn, and Recall)',
				displayOptions: { show: { operation: ['why'] } },
			},
			// -- observe / learn --
			{
				displayName: 'Text',
				name: 'text',
				type: 'string',
				typeOptions: { rows: 3 },
				default: '',
				required: true,
				description: 'The interaction or free text to process',
				displayOptions: { show: { operation: ['observe', 'learn'] } },
			},
			{
				displayName: 'About',
				name: 'learnAbout',
				type: 'string',
				default: '',
				description: 'Optional entity the text is about',
				displayOptions: { show: { operation: ['learn'] } },
			},
			{
				displayName: 'Source',
				name: 'source',
				type: 'string',
				default: 'n8n',
				description: 'Where this information came from',
				displayOptions: { show: { operation: ['observe', 'learn'] } },
			},
		],
	};

	async execute(this: IExecuteFunctions): Promise<INodeExecutionData[][]> {
		const items = this.getInputData();
		const out: INodeExecutionData[] = [];
		const creds = await this.getCredentials('omemApi');
		const baseUrl = String(creds.baseUrl).replace(/\/+$/, '');
		const project = String(creds.project || '');

		const call = async (method: 'GET' | 'POST', path: string, body?: object) => {
			const options: IHttpRequestOptions = {
				method,
				url: `${baseUrl}${path}`,
				headers: {
					Authorization: `Bearer ${creds.apiKey}`,
					'Content-Type': 'application/json',
				},
				qs: project ? { project } : undefined,
				body,
				json: true,
			};
			return this.helpers.httpRequest(options);
		};

		for (let i = 0; i < items.length; i++) {
			try {
				const op = this.getNodeParameter('operation', i) as string;
				let res;
				if (op === 'remember') {
					const agent = this.getNodeParameter('agent', i) as string;
					const about = this.getNodeParameter('about', i) as string;
					// Auto-create the agent and subject entity, mirroring the Python
					// SDK's auto_create so a first-time remember works out of the box.
					// Failures here mean "already exists" and are safely ignored.
					try { await call('POST', '/v1/agents', { id: agent, kind: 'system' }); } catch {}
					try { await call('POST', '/v1/entities', { id: about, type: 'thing' }); } catch {}
					const body: Record<string, unknown> = {
						agent,
						subjects: [about],
						proposition: this.getNodeParameter('claim', i),
						assertion_time: 'now',
						because: [],
					};
					const note = this.getNodeParameter('evidenceNote', i) as string;
					if (note) body.label = note;
					res = await call('POST', '/v1/assertions', body);
				} else if (op === 'believes') {
					res = await call('POST', '/v1/queries/proposition-state', {
						subjects: [this.getNodeParameter('about', i)],
						proposition: this.getNodeParameter('claim', i),
					});
				} else if (op === 'recall') {
					const body: Record<string, unknown> = {
						limit: this.getNodeParameter('limit', i),
					};
					const about = this.getNodeParameter('recallAbout', i) as string;
					const asOf = this.getNodeParameter('asOf', i) as string;
					if (about) body.about = about;
					if (asOf) body.as_of = asOf;
					res = await call('POST', '/v1/recall', body);
				} else if (op === 'why') {
					const id = encodeURIComponent(this.getNodeParameter('assertionId', i) as string);
					res = await call('GET', `/v1/assertions/${id}/why`);
				} else if (op === 'observe') {
					res = await call('POST', '/v1/observe', {
						agent: this.getNodeParameter('agent', i),
						interaction: { text: this.getNodeParameter('text', i) },
						source: this.getNodeParameter('source', i),
					});
				} else if (op === 'learn') {
					const body: Record<string, unknown> = {
						agent: this.getNodeParameter('agent', i),
						text: this.getNodeParameter('text', i),
						source: this.getNodeParameter('source', i),
					};
					const about = this.getNodeParameter('learnAbout', i) as string;
					if (about) body.about = about;
					res = await call('POST', '/v1/learn', body);
				} else if (op === 'conflicts') {
					res = await call('GET', '/v1/memory/conflicts');
				} else {
					throw new NodeOperationError(this.getNode(), `Unknown operation: ${op}`);
				}
				out.push({ json: res as never, pairedItem: { item: i } });
			} catch (error) {
				if (this.continueOnFail()) {
					out.push({ json: { error: (error as Error).message }, pairedItem: { item: i } });
					continue;
				}
				throw error;
			}
		}
		return [out];
	}
}

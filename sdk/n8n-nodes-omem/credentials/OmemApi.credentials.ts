import type { ICredentialType, INodeProperties } from 'n8n-workflow';

// OMEM is self-hosted: the base URL points at the user's own omem-server.
// The API key and project id are printed on the server's first run.
export class OmemApi implements ICredentialType {
	name = 'omemApi';
	displayName = 'OMEM API';
	documentationUrl = 'https://infrastructure.omem-cloud.com/docs/quickstart/';
	properties: INodeProperties[] = [
		{
			displayName: 'Base URL',
			name: 'baseUrl',
			type: 'string',
			default: 'http://127.0.0.1:8787',
			description: 'URL of your self-hosted omem-server',
		},
		{
			displayName: 'API Key',
			name: 'apiKey',
			type: 'string',
			typeOptions: { password: true },
			default: '',
			description: 'Printed on first run of omem-server (starts with omem_sk_)',
		},
		{
			displayName: 'Project',
			name: 'project',
			type: 'string',
			default: '',
			description: 'Project id to read and write memory in (starts with proj_)',
		},
	];
}

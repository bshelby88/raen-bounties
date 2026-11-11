import test from 'node:test';
import assert from 'node:assert/strict';
import { createRaenMcpPlugin, DEFAULT_RAEN_MCP_URL } from '../src/index.js';

test('RAEN MCP ElizaOS plugin exposes all 5 required actions and validates API key', async () => {
  const plugin = createRaenMcpPlugin({ apiKey: 'test-bearer-token' });
  assert.equal(plugin.name, 'raen-mcp-gateway');
  const names = plugin.actions.map((a) => a.name);
  assert.deepEqual(names, [
    'LAW_LOOKUP',
    'DISPUTE_LETTER',
    'IMAGE_GENERATE',
    'CONTRACT_ANALYZE',
    'TOOL_FINDER',
  ]);

  for (const act of plugin.actions) {
    assert.equal(await act.validate({ getSetting: () => 'test-bearer-token' }), true);
  }

  const unauthPlugin = createRaenMcpPlugin({ apiKey: '' });
  delete process.env.RAEN_MCP_API_KEY;
  assert.equal(await unauthPlugin.actions[0].validate({ getSetting: () => '' }), false);
});

test('LAW_LOOKUP action sends Streamable HTTP JSON-RPC 2.0 request with Bearer auth and returns answer', async () => {
  let capturedUrl = '';
  let capturedHeaders = {};
  let capturedBody = null;

  const mockFetch = async (url, init) => {
    capturedUrl = url;
    capturedHeaders = init.headers;
    capturedBody = JSON.parse(init.body);
    return {
      ok: true,
      status: 200,
      headers: { get: () => 'text/event-stream' },
      text: async () =>
        'event: message\ndata: {"jsonrpc":"2.0","id":"1","result":{"content":[{"type":"text","text":"15 U.S.C. § 1681i mandates a 30-day reinvestigation window."}]}}\n\n',
    };
  };

  const plugin = createRaenMcpPlugin({ apiKey: 'raen-secret-test', fetchImpl: mockFetch });
  const lawAction = plugin.actions.find((a) => a.name === 'LAW_LOOKUP');
  let callbackPayload = null;

  const result = await lawAction.handler(
    {},
    { content: { text: 'Check FCRA 611 deadline' } },
    {},
    {},
    async (msg) => {
      callbackPayload = msg;
    }
  );

  assert.equal(capturedUrl, DEFAULT_RAEN_MCP_URL);
  assert.equal(capturedHeaders.Authorization, 'Bearer raen-secret-test');
  assert.equal(capturedBody.method, 'tools/call');
  assert.equal(capturedBody.params.name, 'law_lookup');
  assert.match(result.text, /30-day reinvestigation window/);
  assert.equal(callbackPayload.action, 'LAW_LOOKUP');
});

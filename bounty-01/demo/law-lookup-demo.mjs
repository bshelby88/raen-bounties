import { createRaenMcpPlugin } from '../src/index.js';

async function runLawLookupDemo() {
  const mockFetch = async (_url, init) => {
    const req = JSON.parse(init.body);
    return {
      ok: true,
      status: 200,
      headers: { get: () => 'application/json' },
      text: async () =>
        JSON.stringify({
          jsonrpc: '2.0',
          id: req.id,
          result: {
            content: [
              {
                type: 'text',
                text: '15 U.S.C. § 1681i (FCRA Section 611): Consumer reporting agencies must conduct a reasonable reinvestigation within 30 days of receiving notice of a consumer dispute.',
              },
            ],
          },
        }),
    };
  };

  const plugin = createRaenMcpPlugin({
    apiKey: process.env.RAEN_MCP_API_KEY || 'demo-raen-bearer-key',
    fetchImpl: mockFetch,
  });

  const lawAction = plugin.actions.find((a) => a.name === 'LAW_LOOKUP');
  const transcript = [];
  await lawAction.handler(
    { getSetting: () => 'demo-raen-bearer-key' },
    {
      content: {
        text: 'What is the statutory reinvestigation deadline under FCRA 15 U.S.C. § 1681i?',
        arguments: { jurisdiction: 'US-Federal', query: '15 U.S.C. 1681i reinvestigation deadline' },
      },
    },
    {},
    {},
    async (reply) => {
      transcript.push(reply);
    }
  );

  console.log(JSON.stringify({ demo: 'LAW_LOOKUP', transcript }, null, 2));
}

runLawLookupDemo();

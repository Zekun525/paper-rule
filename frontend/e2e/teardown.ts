export default async function teardown() {
  const response = await fetch('http://127.0.0.1:18765/__e2e/shutdown', {
    method: 'POST',
    headers: { 'X-Test-Token': process.env.PAPERRULE_E2E_TOKEN ?? '' },
    signal: AbortSignal.timeout(5000),
  });
  if (!response.ok) throw new Error('Test server failed to shut down cleanly');
}

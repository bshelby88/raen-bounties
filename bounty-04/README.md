# x402 Manifest Drift Watcher GitHub Action (BOUNTY-04)

Reusable GitHub Action (`bounty-04/action.yml`) and standalone CLI (`watch_x402_drift.py`) that polls `/.well-known/x402.json` across an x402 fleet on a cron schedule and fails with a markdown diff table whenever `scheme`, `network`, or `payTo` drifts from expected values.

## Features

- **Fleet-Wide Drift Detection**: Inspects all 12 services in the RAEN fleet against expected manifest configurations.
- **Multiple `accepts` Matching**: Traverses all `accepts` items to match the targeted payment scheme/network.
- **Case-Insensitive Address Comparison**: Normalizes EIP-55 checksum addresses against lowercase strings to eliminate false positives.
- **GitHub Step Summary**: Automatically renders rich markdown diff tables directly to `$GITHUB_STEP_SUMMARY` in CI runs.
- **Production Config Included**: Ready-to-use `bounty-04/x402-expected.json` pre-configured for the entire RAEN fleet on Base mainnet.

## Usage in `.github/workflows/x402-drift.yml`

```yaml
name: 'x402 Manifest Drift Watcher'

on:
  schedule:
    - cron: '0 0,12 * * *'
  workflow_dispatch:

jobs:
  watch-x402:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: ./bounty-04
        with:
          config-path: 'bounty-04/x402-expected.json'
          timeout-seconds: '15'
```

## Running Locally

```bash
# Check fleet against config
python bounty-04/watch_x402_drift.py --config bounty-04/x402-expected.json

# Run unit tests
python -m pytest -v bounty-04/tests/
```

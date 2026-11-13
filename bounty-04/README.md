# x402 Manifest Drift Watcher GitHub Action (BOUNTY-04)

Reusable GitHub Action (`bounty-04/action.yml`) and CLI (`watch_x402_drift.py`) that polls `/.well-known/x402.json` across an x402 fleet on a cron schedule and fails with a markdown diff table whenever `scheme`, `network`, or `payTo` drifts from expected values.

## Usage in `.github/workflows/x402-drift.yml`

```yaml
on:
  schedule:
    - cron: '0 */6 * * *'
  workflow_dispatch:

jobs:
  watch-x402:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: satoshinakamoto666666/raen-bounties/bounty-04@main
        with:
          config-path: 'x402-expected.json'
```

# x402 manifest drift watch

A reusable GitHub Action for RAEN bounty 4. It fetches the public payment manifests for all 12 fleet services and compares every payment option's `scheme`, `network` and `payTo` against checked-in expectations. It supports RAEN's `endpoints.<path>.accepts` objects, accepts arrays, and top-level x402 accepts arrays.

On drift or an unreadable/invalid manifest, the Action fails and posts the diff to a configured issue or PR. Later runs update the same GitHub Actions bot comment; identical reports do not create additional comments, and a healthy run clears the previous failure report. Address casing alone does not count as a destination change.

## Use from another repository

This composite Action requires Python 3, available on GitHub-hosted Ubuntu runners. It has no Python package dependencies.

Create an issue in the calling repository for reports, then set its number below. The token needs permission to write comments in that repository. For a pull-request workflow, omit `issue-number` to use the triggering PR. Without an issue/PR, the report is still written to the job log and step summary.

```yaml
name: Watch payment manifests
on:
  schedule:
    - cron: '17 */6 * * *'
  workflow_dispatch:
permissions:
  contents: read
  issues: write
jobs:
  watch:
    runs-on: ubuntu-latest
    steps:
      - uses: soundcake/raen-bounty-4-20261110/integrations/x402-manifest-watch@bounty-4-manifest-drift
        with:
          issue-number: '1' # An existing issue in this calling repository
          github-token: ${{ secrets.GITHUB_TOKEN }}
```

Pin the `uses` reference to a reviewed commit when adopting it. The bundled `fleet.json` contains the 12 endpoints from the RAEN directory and explicit expected payment fields. The checker never learns its expected destination from the response being checked.

For custom expectations, check out the calling repository and pass `config: path/to/fleet.json`. The format is:

```json
{
  "expected": {
    "scheme": "exact",
    "network": "eip155:8453",
    "payTo": "0x1111111111111111111111111111111111111111"
  },
  "services": [
    {
      "name": "example",
      "url": "https://example.com/.well-known/x402.json"
    }
  ]
}
```

Each service may override individual expected fields with its own `expected` object. All configured services are checked even when an earlier service fails. Empty options, missing payment fields, malformed JSON, HTTP failures and oversized responses fail the check. Exit codes are 0 for a match, 1 for manifest drift/availability failure and 2 for configuration or comment-publication errors.

## Run and validate

```sh
python3 integrations/x402-manifest-watch/watch.py
python3 -m unittest discover -s integrations/x402-manifest-watch/tests -v
python3 integrations/x402-manifest-watch/tests/demo.py
```

The checker reads only public metadata endpoints; it does not perform paid service requests or sign payments. The reproducible demo serves a deliberately incorrect `payTo` and a GitHub-comments API fixture on localhost. It verifies exit code 1 and a diff comment, with no external write. Its captured output is in [sample-run.log](sample-run.log). Tests also cover healthy recovery, comment pagination and deduplication, all three drift fields, multiple endpoints/payment options, unavailable manifests and missing fields.

For a real cron run, grant `issues: write` and set an existing report issue. If repository policy prevents comments, the Action reports the publication error and fails; the full manifest report remains in the job log and summary.

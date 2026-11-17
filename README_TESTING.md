## Testing the Claim Flow

The `settlement-collector` includes a comprehensive test suite to ensure the security and reliability of the claim-code issuance and redemption process (the `RAEN-8922B9225B` pattern).

### Prerequisites
- Python 3.9+
- `pip install -r requirements-test.txt`

### Running Tests
To execute the test suite:
```bash
pytest tests/test_claim_flow.py
```

### Coverage
The test suite covers:
- **Issuance Logic:** Ensures codes follow the `RAEN-[12 hex chars]` format.
- **Happy Path:** Full flow from settlement to successful redemption.
- **Security Checks:** 
    - Replay protection (prevents double spending).
    - Malformed code detection.
    - Unknown code handling.
- **Temporal Logic:** Expiration of claim codes.
- **Concurrency:** Basic simulation of race conditions during redemption.
- **Idempotency:** Verification of system state after repeated requests.

*Note: Tests use a mock layer for blockchain and HTTP calls to ensure no live funds are spent during CI/CD.*

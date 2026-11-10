#!/usr/bin/env python3
"""Read public payment manifests and compare them with committed expectations."""
import argparse
import difflib
import json
import os
from pathlib import Path
import re
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

FIELDS = ("scheme", "network", "payTo")
MARKER = "<!-- raen-x402-manifest-watch -->"
MAX_BYTES = 1024 * 1024


def read_json(url, *, method="GET", token=None, payload=None):
    headers = {"Accept": "application/json", "User-Agent": "raen-manifest-watch"}
    if token:
        headers["Authorization"] = "Bearer " + token
    data = None
    if payload is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(payload).encode()
    with urlopen(Request(url, data=data, headers=headers, method=method), timeout=15) as response:
        raw = response.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValueError("response exceeds 1 MiB")
    return json.loads(raw)


def normalize(fields):
    if not isinstance(fields, dict):
        raise ValueError("payment fields must be an object")
    result = {}
    for key in FIELDS:
        value = fields.get(key)
        if not isinstance(value, str) or not value.strip():
            raise ValueError("missing or invalid " + key)
        if key == "payTo":
            if not re.fullmatch(r"0x[0-9a-fA-F]{40}", value):
                raise ValueError("payTo must be a 20-byte EVM address")
            value = value.lower()
        result[key] = value
    return result


def payment_options(manifest):
    """Support RAEN endpoints.*.accepts plus top-level x402 accepts arrays."""
    if not isinstance(manifest, dict):
        raise ValueError("manifest must be an object")
    groups = []
    if "endpoints" in manifest:
        endpoints = manifest["endpoints"]
        if not isinstance(endpoints, dict) or not endpoints:
            raise ValueError("endpoints must be a nonempty object")
        for path, endpoint in sorted(endpoints.items()):
            if not isinstance(endpoint, dict) or "accepts" not in endpoint:
                raise ValueError("endpoint " + path + " is missing accepts")
            groups.append((path, endpoint["accepts"]))
    if "accepts" in manifest:
        groups.append(("$", manifest["accepts"]))
    if isinstance(manifest.get("error"), dict) and "accepts" in manifest["error"]:
        groups.append(("$.error", manifest["error"]["accepts"]))
    if not groups:
        raise ValueError("manifest contains no payment options")
    options = {}
    for path, accepts in groups:
        if isinstance(accepts, dict):
            accepts = [accepts]
        if not isinstance(accepts, list) or not accepts:
            raise ValueError("empty or invalid accepts at " + path)
        for index, option in enumerate(accepts):
            options[f"{path}/accepts/{index}"] = normalize(option)
    return options


def config_services(config, allow_local_http=False):
    if not isinstance(config, dict):
        raise ValueError("config must be an object")
    defaults = normalize(config.get("expected"))
    services = config.get("services")
    if not isinstance(services, list) or not services:
        raise ValueError("config services must be a nonempty list")
    seen = set()
    result = []
    for service in services:
        if not isinstance(service, dict):
            raise ValueError("each service must be an object")
        name, url = service.get("name"), service.get("url")
        if not isinstance(name, str) or not name or name in seen:
            raise ValueError("service names must be nonempty and unique")
        seen.add(name)
        if not isinstance(url, str):
            raise ValueError("service URL must be a string")
        parsed = urlsplit(url)
        local = allow_local_http and parsed.scheme == "http" and parsed.hostname in {"127.0.0.1", "localhost", "::1"}
        if not parsed.hostname or (parsed.scheme != "https" and not local) or parsed.username or parsed.password or parsed.fragment:
            raise ValueError("service URLs must use HTTPS without credentials or fragments")
        expected = normalize({**defaults, **service.get("expected", {})})
        result.append((name, url, expected))
    return result


def check_services(services, fetch=read_json):
    failures, checked = [], 0
    for name, url, expected in services:
        try:
            actual = payment_options(fetch(url))
            wanted = {path: expected for path in actual}
            if wanted != actual:
                before = json.dumps(wanted, indent=2, sort_keys=True).splitlines()
                after = json.dumps(actual, indent=2, sort_keys=True).splitlines()
                diff = "\n".join(difflib.unified_diff(before, after, fromfile=name + "/expected", tofile=name + "/actual", lineterm=""))
                failures.append(diff)
            else:
                checked += 1
        except (HTTPError, URLError, OSError, ValueError, TypeError) as error:
            failures.append(f"{name}: manifest unavailable or invalid: {error}")
    return checked, failures


def report_text(checked, total, failures):
    heading = f"x402 manifest watch: {checked}/{total} services match expected payment fields."
    if not failures:
        return MARKER + "\n" + heading
    content = "\n\n".join(failures)
    # Keep untrusted manifest strings inside one literal code block.
    longest = max((len(x) for x in re.findall(r"`+", content)), default=0)
    fence = "`" * max(3, longest + 1)
    return MARKER + "\n" + heading + "\n\n" + fence + "diff\n" + content[:55000] + "\n" + fence


def sync_comment(repository, issue, token, body, failed, api=None, request=read_json):
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
        raise ValueError("GITHUB_REPOSITORY must identify the caller repository")
    if not str(issue).isdigit() or int(issue) < 1:
        raise ValueError("issue-number must be a positive integer")
    if not token:
        raise ValueError("github-token is required to publish the requested diff comment")
    base = (api or os.environ.get("GITHUB_API_URL", "https://api.github.com")).rstrip("/")
    endpoint = f"{base}/repos/{repository}/issues/{issue}/comments"
    page = 1
    while True:
        comments = request(f"{endpoint}?per_page=100&page={page}", token=token)
        for comment in comments:
            if comment.get("user", {}).get("login") == "github-actions[bot]" and comment.get("body", "").startswith(MARKER):
                if comment["body"] != body:
                    request(f"{base}/repos/{repository}/issues/comments/{comment['id']}", method="PATCH", token=token, payload={"body": body})
                return
        if len(comments) < 100:
            break
        page += 1
    if failed:
        request(endpoint, method="POST", token=token, payload={"body": body})


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=os.environ.get("X402_CONFIG") or str(Path(__file__).with_name("fleet.json")))
    parser.add_argument("--allow-local-http", action="store_true", help="allow a localhost fixture server for tests")
    args = parser.parse_args(argv)
    try:
        services = config_services(json.loads(Path(args.config).read_text()), args.allow_local_http)
        checked, failures = check_services(services)
    except (OSError, ValueError, TypeError) as error:
        print("Configuration error: " + str(error), file=sys.stderr)
        return 2
    body = report_text(checked, len(services), failures)
    print(body)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as summary:
            summary.write(body + "\n")
    issue = os.environ.get("X402_ISSUE")
    if not issue and os.environ.get("GITHUB_EVENT_PATH"):
        event = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text())
        issue = event.get("pull_request", {}).get("number")
    if issue:
        try:
            sync_comment(os.environ.get("GITHUB_REPOSITORY", ""), issue, os.environ.get("X402_TOKEN", ""), body, bool(failures))
        except (HTTPError, URLError, OSError, ValueError, TypeError) as error:
            print("Comment publication failed: " + str(error), file=sys.stderr)
            return 2
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())

"""Reproduce a bad payTo and a GitHub comment against local HTTP fixtures."""
from test_watch import FixtureServer

with FixtureServer() as server:
    server.payment["payTo"] = "0x" + "bb" * 20
    result = server.run()
    print("Local fixture: manifest payTo changed from expected a1... to bb...")
    print(result.stdout.strip())
    print("Checker exit code:", result.returncode)
    print("GitHub API fixture comments:", len(server.comments))
    print("Comment contains diff:", "payTo" in server.comments[0]["body"])
    assert result.returncode == 1 and len(server.comments) == 1

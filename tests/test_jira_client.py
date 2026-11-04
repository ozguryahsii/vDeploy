import httpx
import pytest

from vdeploy.jira_client import JiraClient, describe_error


def _client(handler):
    return JiraClient("https://jira.example/", "token", transport=httpx.MockTransport(handler))


def test_bad_jql_message_is_shown():
    def handler(request):
        return httpx.Response(400, json={"errorMessages": ["Field 'Talep Tipi' does not exist."], "errors": {}})

    with pytest.raises(httpx.HTTPStatusError) as exc:
        _client(handler).count('project = SAY AND "Talep Tipi" = "X"')
    msg = describe_error(exc.value)
    assert "400" in msg and "Talep Tipi" in msg


def test_search_pages_and_sends_bearer_token():
    seen = []

    def handler(request):
        assert request.headers["Authorization"] == "Bearer token"
        start = int(request.url.params["startAt"])
        seen.append(start)
        issues = [{"key": f"SAY-{start + i}", "fields": {}} for i in range(100 if start == 0 else 20)]
        return httpx.Response(200, json={"total": 120, "issues": issues, "names": {}})

    keys = [i["key"] for i, _ in _client(handler).search("project = SAY")]
    assert len(keys) == 120 and seen == [0, 100]

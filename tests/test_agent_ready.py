"""Judges for agent-facing files: pure functions of one response, no network."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engines.agent_ready import (
    Probe,
    judge_agent_card,
    judge_agents_txt,
    judge_api_catalog,
    judge_ard_catalog,
)

HTML = Probe(200, "text/html; charset=utf-8", "<!DOCTYPE html><html><body>404</body></html>")
NOT_FOUND = Probe(404, "text/html", "<html>nope</html>")
DOWN = Probe(None, "", "")

CARD = {
    "name": "x", "description": "d", "url": "https://x/mcp", "version": "1",
    "capabilities": {}, "defaultInputModes": ["application/json"],
    "defaultOutputModes": ["text/markdown"],
    "skills": [{"id": "s", "name": "S", "description": "d"}],
}
MCP = "application/mcp-server-card+json"
SKILL = 'text/markdown; profile="urn:air:agent-skills"'


def js(obj, ctype="application/json", status=200):
    return Probe(status, ctype, json.dumps(obj))


def entry(i, t=MCP):
    return {"identifier": f"urn:{i}", "url": f"https://x/{i}", "type": t}


# agents.txt
def test_agents_txt_good():
    assert judge_agents_txt(Probe(200, "text/plain", "# c\nUser-agent: *\nAllow: /\n"))[0]


def test_agents_txt_bad():
    assert not judge_agents_txt(HTML)[0]
    assert not judge_agents_txt(NOT_FOUND)[0]
    assert not judge_agents_txt(DOWN)[0]
    assert not judge_agents_txt(Probe(200, "text/plain", "# only a comment\n"))[0]
    assert not judge_agents_txt(Probe(200, "text/plain", "free prose, no directives"))[0]


# agent card
def test_agent_card_good():
    assert judge_agent_card(js(CARD)) == (True, "1 skills")


def test_agent_card_missing_field_named():
    ok, why = judge_agent_card(js({k: v for k, v in CARD.items() if k != "version"}))
    assert not ok and "version" in why


def test_agent_card_bad_shapes():
    assert not judge_agent_card(HTML)[0]
    assert not judge_agent_card(Probe(200, "application/json", "{nope"))[0]
    assert not judge_agent_card(js([1]))[0]
    assert not judge_agent_card(js({**CARD, "skills": [{"id": "s"}]}))[0]
    assert not judge_agent_card(js({**CARD, "skills": "x"}))[0]


# ARD
def test_ard_good_with_profile_spacing_variants():
    es = [entry(1), entry(2, SKILL), entry(3, 'text/markdown;profile="urn:air:agent-skills"')]
    assert judge_ard_catalog(js({"entries": es}))[0]


def test_ard_non_agentic_type_fails():
    ok, why = judge_ard_catalog(js({"entries": [entry(1), entry(2, "text/html")]}))
    assert not ok and "text/html" in why


def test_ard_duplicate_skill_fails():
    ok, why = judge_ard_catalog(js({"entries": [entry(1, SKILL), entry(1, SKILL)]}))
    assert not ok and "duplicate" in why


def test_ard_empty_missing_html():
    assert not judge_ard_catalog(js({"entries": []}))[0]
    assert not judge_ard_catalog(js({}))[0]
    assert not judge_ard_catalog(HTML)[0]
    assert not judge_ard_catalog(NOT_FOUND)[0]


# api-catalog
LINKSET = {"linkset": [{"anchor": "https://x/", "item": [{"href": "https://x/mcp"}]}]}


def test_api_catalog_good():
    assert judge_api_catalog(js(LINKSET, 'application/linkset+json; profile="x"'))[0]


def test_api_catalog_wrong_content_type():
    ok, why = judge_api_catalog(js(LINKSET, "application/json"))
    assert not ok and "linkset+json" in why


def test_api_catalog_bad():
    assert not judge_api_catalog(HTML)[0]
    assert not judge_api_catalog(NOT_FOUND)[0]
    assert not judge_api_catalog(js({"linkset": []}, "application/linkset+json"))[0]
    assert not judge_api_catalog(js({"x": 1}, "application/linkset+json"))[0]

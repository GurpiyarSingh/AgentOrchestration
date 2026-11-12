"""Click through every page of Codeloom in a real browser (installed Microsoft Edge via Playwright).

    uv run python tests/e2e/ui_walkthrough.py --url http://127.0.0.1:8768 --out <screenshot dir>

Run against tests/e2e/demo_server.py. Fails on JS errors, failed API calls, or broken flows.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from playwright.sync_api import Page, expect, sync_playwright

problems: list[str] = []


def check(cond: bool, msg: str) -> None:
    print(("  ok   " if cond else "  FAIL ") + msg)
    if not cond:
        problems.append(msg)


def shot(page: Page, out: Path, name: str) -> None:
    page.wait_for_timeout(350)  # let enter animations finish
    page.screenshot(path=str(out / f"{name}.png"), full_page=False)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8768")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    base = args.url.rstrip("/")

    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="msedge", headless=True)
        page = browser.new_page(viewport={"width": 1600, "height": 1000})
        page.set_default_timeout(15000)
        page.on("console", lambda m: m.type == "error" and problems.append(f"console error: {m.text}"))
        page.on("pageerror", lambda e: problems.append(f"page error: {e}"))
        page.on(
            "response",
            lambda r: (
                (r.status >= 500 and "/api/" in r.url)
                and problems.append(f"HTTP {r.status} {r.request.method} {r.url}")
            ),
        )

        # ---- onboarding -----------------------------------------------------------------
        print("Onboarding")
        page.goto(base + "/")
        expect(page.get_by_text("Connect your OpenAI account to start")).to_be_visible()
        check(page.get_by_role("button", name="Start build").is_disabled(), "Start build disabled without key")
        shot(page, out, "01-home-no-key")

        # ---- settings: key + model ---------------------------------------------------------
        print("Settings")
        page.get_by_role("link", name="Settings").first.click()
        page.get_by_placeholder("sk-…").fill("bad-key")
        page.get_by_role("button", name="Verify & save").click()
        expect(page.locator(".callout.err")).to_be_visible()
        check(True, "bad key rejected with an error")
        page.get_by_placeholder("sk-…").fill("sk-test-codeloom-1234")
        page.get_by_role("button", name="Verify & save").click()
        expect(page.get_by_text("Connected", exact=True)).to_be_visible()
        check(page.get_by_text("Connect your OpenAI account to start").count() == 0, "banner gone after saving key")
        page.locator("select").first.select_option("openai:gpt-5.4-mini")
        page.get_by_role("button", name="Save", exact=True).first.click()
        page.wait_for_timeout(600)
        check("gpt-5.4-mini" in page.locator(".sidebar").inner_text(), "default model shown in sidebar")
        shot(page, out, "02-settings-connected")

        # ---- new project modal ----------------------------------------------------------------
        print("New project")
        page.get_by_role("link", name="Build").first.click()
        page.get_by_title("New project").click()
        modal = page.locator(".modal")
        expect(modal).to_be_visible()
        # the modal must be on top: the element at its centre must belong to the modal
        box = modal.bounding_box()
        assert box
        on_top = page.evaluate(
            "([x,y]) => !!document.elementFromPoint(x,y)?.closest('.modal')",
            [box["x"] + box["width"] / 2, box["y"] + box["height"] / 2],
        )
        check(on_top, "modal is on top of the page (not clipped/covered)")
        page.locator(".modal input").first.fill("Test Repo")
        expect(page.get_by_text("no spaces")).to_be_visible()
        check(page.get_by_role("button", name="Create project").is_disabled(), "invalid name blocks create")
        shot(page, out, "03-new-project-invalid")
        page.get_by_role("button", name=re.compile('Use "test-repo"')).click()
        page.get_by_role("button", name="Create project").click()
        expect(page.locator(".toast", has_text="test-repo").first).to_be_visible()
        check(page.locator("select").first.input_value() != "", "new project selected in Build form")
        page.keyboard.press("Escape")

        # ---- existing repo via the in-app folder browser --------------------------------------
        print("Existing folder (plain, no git)")
        import tempfile

        parent = Path(tempfile.mkdtemp(prefix="cl-e2e-"))
        repo = parent / "My Existing Repo"
        repo.mkdir()
        (repo / "README.md").write_text("hi\n")
        page.get_by_title("New project").click()
        page.get_by_role("button", name="Existing folder").click()
        page.locator(".modal input.mono").first.fill(str(parent))
        page.get_by_role("button", name="Browse here").click()
        browser_modal = page.locator(".modal").last
        expect(browser_modal.locator(".file-item", has_text="My Existing Repo")).to_be_visible()
        shot(page, out, "03b-folder-browser")
        browser_modal.locator(".file-item", has_text="My Existing Repo").click()
        browser_modal.get_by_role("button", name="Select this folder").click()
        check(page.locator(".modal input").nth(1).input_value() == "my-existing-repo", "name auto-filled from folder")
        page.get_by_role("button", name="Add folder").click()
        expect(page.locator(".toast", has_text="my-existing-repo").first).to_be_visible()
        check(True, "plain folder added via folder browser")
        page.keyboard.press("Escape")
        page.locator("select").first.select_option(label="test-repo · Python")

        # ---- build ----------------------------------------------------------------------------
        print("Build")
        page.get_by_role("button", name="Slugify").click()
        page.get_by_role("button", name="Start build").click()
        page.wait_for_url(re.compile(r"/builds/"))
        expect(page.locator(".step").first).to_be_visible()
        shot(page, out, "04-build-running")
        expect(page.locator(".build-head .badge").first).to_contain_text(
            re.compile("Done|Needs attention"), timeout=60000
        )
        check("Done" in page.locator(".build-head .badge").first.inner_text(), "build finished Done")
        shot(page, out, "05-build-done")
        for tab in ["Requirements", "Design", "Files", "Tests", "Review", "Diff"]:
            page.locator(".tab", has_text=tab).click()
            page.wait_for_timeout(400)
            shot(page, out, f"06-tab-{tab.lower()}")
        check(page.locator(".code").count() > 0, "diff rendered")
        page.locator(".tab", has_text="Files").click()
        expect(page.locator(".code")).to_contain_text("format_thousands")
        check(True, "generated file content visible")
        check(page.get_by_role("button", name="Merge").count() == 0, "no merge step (written directly)")
        check("The files are in" in page.locator(".build-head").inner_text(), "build says where the files are")

        # ---- projects -----------------------------------------------------------------------
        print("Projects")
        page.get_by_role("link", name="Projects").first.click()
        page.locator(".list-item", has_text="test-repo").click()
        expect(page.locator(".file-item", has_text=re.compile(r"^numfmt.py")).first).to_be_visible()
        check(True, "generated file in project folder")
        shot(page, out, "08-projects")

        # ---- agents -----------------------------------------------------------------------
        print("Agents")
        page.get_by_role("link", name="Agents").first.click()
        page.locator(".list-item", has_text="code_generator").click()
        expect(page.locator(".card-head h2", has_text="code_generator")).to_be_visible()
        page.locator("input[type=number]").nth(1).fill("45")
        page.get_by_role("button", name="Save").click()
        expect(page.locator(".toast", has_text="Saved").first).to_be_visible()
        page.locator(".list-item", has_text="code_runner").click()
        expect(page.get_by_text("Deterministic step, no AI model")).to_be_visible()
        page.get_by_role("button", name="New").click()
        page.locator("input.mono").first.fill("summarizer")
        page.get_by_role("button", name="Save").click()
        expect(page.locator(".list-item", has_text="summarizer")).to_be_visible()
        check(True, "agent edited, step agent shown, new agent created")
        shot(page, out, "09-agents")

        # ---- MCP servers ----------------------------------------------------------------------
        print("MCP")
        echo = str(Path(__file__).resolve().parents[1] / "fixtures" / "mcp_echo_server.py")
        page.get_by_role("link", name="MCP servers").first.click()
        expect(page.get_by_text("Quick start")).to_be_visible()
        shot(page, out, "13-mcp-empty")
        page.get_by_role("button", name="Add manually").click()
        m = page.locator(".modal")
        m.locator("input").first.fill("echo")
        m.get_by_placeholder("npx").fill(sys.executable)
        m.locator("textarea").fill(echo)
        m.get_by_role("button", name="Add").click()
        m.get_by_placeholder("API_KEY").fill("ECHO_TOKEN")
        m.get_by_placeholder("value").fill("very-secret")
        shot(page, out, "14-mcp-add")
        m.get_by_role("button", name="Save & connect").click()
        expect(page.locator(".card", has_text="echo").get_by_text("connected", exact=True)).to_be_visible(timeout=60000)
        check(
            page.locator(".card", has_text="echo").get_by_text("2 tools").count() == 1,
            "manual MCP server connected with 2 tools",
        )
        page.get_by_role("button", name="Show tools").click()
        expect(page.get_by_text("needs approval")).to_be_visible()
        check(True, "destructive MCP tool flagged for approval")
        page.get_by_role("button", name="Browse registry").click()
        reg = page.locator(".modal")
        expect(reg.get_by_text("Echo Math")).to_be_visible()
        reg.get_by_role("button", name="Use").first.click()
        expect(page.locator(".modal").get_by_text("io.codeloom/echo-math")).to_be_visible()
        page.locator(".modal").get_by_role("button", name="Save & connect").click()
        expect(page.locator(".card", has_text="echo-math").get_by_text("connected", exact=True)).to_be_visible(
            timeout=60000
        )
        check(True, "server added from the registry and connected")
        page.get_by_role("button", name="Import JSON").click()
        import json as _json

        page.locator(".modal textarea").fill(
            _json.dumps({"mcpServers": {"echo-json": {"command": sys.executable, "args": [echo]}}})
        )
        page.locator(".modal").get_by_role("button", name="Import & connect").click()
        expect(page.locator(".card", has_text="echo-json").get_by_text("connected", exact=True)).to_be_visible(
            timeout=60000
        )
        check(True, "server imported from mcp.json and connected")
        shot(page, out, "15-mcp-servers")

        # ---- skills ---------------------------------------------------------------------------
        print("Skills")
        page.get_by_role("link", name="Skills").first.click()
        expect(page.locator(".list-item", has_text="test-design")).to_be_visible()
        page.get_by_role("button", name="New").click()
        page.get_by_placeholder("api-design").fill("api-style")
        page.get_by_placeholder("REST API design conventions").fill(
            "REST API conventions. Use when designing endpoints."
        )
        page.get_by_role("button", name="Save").click()
        expect(page.locator(".list-item", has_text="api-style")).to_be_visible()
        check(True, "skill created")
        shot(page, out, "16-skills")
        page.get_by_role("link", name="Agents").first.click()
        page.locator(".list-item", has_text="assistant").click()
        page.locator(".chip", has_text="api-style").click()
        page.get_by_role("button", name="Save").click()
        expect(page.locator(".toast", has_text="Saved assistant").first).to_be_visible()
        page.get_by_role("link", name="Skills").first.click()
        page.locator(".list-item", has_text="api-style").click()
        expect(page.locator(".badge", has_text="assistant")).to_be_visible()
        check(True, "skill assigned to an agent (shown as Used by)")

        # ---- tools --------------------------------------------------------------------------
        print("Tools")
        page.get_by_role("link", name="Tools").first.click()
        page.locator(".list-item", has_text="builtin__calculator").click()
        page.get_by_placeholder("string").first.fill("6*7")
        page.get_by_role("button", name="Run").click()
        expect(page.locator(".code pre").last).to_have_text("42")
        check(True, "calculator Try-it returns 42")
        page.locator(".list-item", has_text="echo__add").first.click()
        tool_card = page.locator("div", has=page.locator(".list-item", has_text="echo__add")).last
        tool_card.get_by_placeholder("integer").nth(0).fill("40")
        tool_card.get_by_placeholder("integer").nth(1).fill("2")
        tool_card.get_by_role("button", name="Run").click()
        expect(tool_card.locator(".code pre").last).to_have_text("42")
        check(True, "MCP tool callable from the Tools page")
        shot(page, out, "10-tools")

        # ---- chat ---------------------------------------------------------------------------
        print("Chat")
        page.get_by_role("link", name="Chat").first.click()
        page.locator("textarea").fill("What is 17.5% of 2340?")
        page.keyboard.press("Enter")
        expect(page.get_by_text("17.5% of 2,340 is 409.5.")).to_be_visible(timeout=20000)
        check(page.locator(".tool-call").count() > 0, "agent tool call shown in chat")
        page.get_by_role("button", name="Model").click()
        page.locator("textarea").fill("hi")
        page.keyboard.press("Enter")
        expect(page.get_by_text("Hello from the scripted model.")).to_be_visible(timeout=20000)
        check(True, "model chat works")
        shot(page, out, "11-chat")

        # ---- runs ---------------------------------------------------------------------------
        print("Runs")
        page.get_by_role("link", name="Runs & traces").first.click()
        page.locator("tr.click").first.click()
        expect(page.locator(".span-row").first).to_be_visible()
        page.locator(".span-row").first.click()
        check(page.locator(".sticky .code").count() > 0, "span details shown")
        usage = page.locator(".usage").inner_text()
        check(bool(re.search(r"Model calls\s*[1-9]", usage)), f"usage header counts calls ({usage.splitlines()[:3]})")
        shot(page, out, "12-runs")

        # ---- deep link + reload ------------------------------------------------------------
        page.reload()
        expect(page.locator(".span-row").first).to_be_visible()
        check(True, "deep link survives reload")

        # ---- themes -------------------------------------------------------------------------
        print("Themes")
        html = page.locator("html")
        check(html.get_attribute("data-theme") == "dark", "dark theme by default")
        page.get_by_label("Switch to light theme").click()
        check(html.get_attribute("data-theme") == "light", "toggle switches to light")
        page.reload()
        expect(page.locator(".span-row").first).to_be_visible()
        check(html.get_attribute("data-theme") == "light", "light theme survives reload")
        page.get_by_role("link", name="Settings").first.click()
        page.get_by_role("button", name="Dark", exact=True).click()
        check(html.get_attribute("data-theme") == "dark", "Settings > Appearance switches back to dark")
        page.get_by_role("button", name="System", exact=True).click()
        check(html.get_attribute("data-theme") in {"light", "dark"}, "System theme resolves")
        page.get_by_role("button", name="Light", exact=True).click()
        for name, url in [
            ("home", "/"),
            ("build", None),
            ("agents", "/agents"),
            ("settings", "/settings"),
            ("chat", "/chat"),
            ("runs", "/runs"),
            ("projects", "/projects"),
            ("tools", "/tools"),
        ]:
            if url is None:
                page.goto(base + "/")
                page.locator(".list-item").first.click()
                page.wait_for_url(re.compile(r"/builds/"))
                expect(page.locator(".build-head")).to_be_visible()
            else:
                page.goto(base + url)
            shot(page, out, f"20-light-{name}")
        check(True, "light-theme screenshots captured")

        browser.close()

    print("\nPROBLEMS:" if problems else "\nNo problems found.")
    for p in problems:
        print(" -", p)
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()

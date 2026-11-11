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
        page.on("response", lambda r: (r.status >= 500 and "/api/" in r.url)
                and problems.append(f"HTTP {r.status} {r.request.method} {r.url}"))

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
        print("Existing repo")
        import subprocess
        import tempfile

        parent = Path(tempfile.mkdtemp(prefix="cl-e2e-"))
        repo = parent / "My Existing Repo"
        repo.mkdir()
        subprocess.run(["git", "init", "-q", "-b", "main"], cwd=repo, check=True)
        (repo / "README.md").write_text("hi\n")
        subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "add", "-A"], cwd=repo, check=True)
        subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "init"], cwd=repo, check=True)
        page.get_by_title("New project").click()
        page.get_by_role("button", name="Existing local repo").click()
        page.locator(".modal input.mono").first.fill(str(parent))
        page.get_by_role("button", name="Browse here").click()
        browser_modal = page.locator(".modal").last
        expect(browser_modal.locator(".file-item", has_text="My Existing Repo")).to_be_visible()
        check(browser_modal.locator(".file-item", has_text="My Existing Repo").locator(".badge").count() == 1,
              "in-app browser flags the git repo")
        shot(page, out, "03b-folder-browser")
        browser_modal.locator(".file-item", has_text="My Existing Repo").click()
        expect(browser_modal.locator(".badge", has_text="git repository")).to_be_visible()
        browser_modal.get_by_role("button", name="Select this folder").click()
        check(page.locator(".modal input").nth(1).input_value() == "my-existing-repo", "name auto-filled from folder")
        page.get_by_role("button", name="Add repository").click()
        expect(page.locator(".toast", has_text="my-existing-repo").first).to_be_visible()
        check(True, "existing repo added via folder browser")
        page.keyboard.press("Escape")
        page.locator("select").first.select_option(label="test-repo · Python")

        # ---- build ----------------------------------------------------------------------------
        print("Build")
        page.get_by_role("button", name="Slugify").click()
        page.get_by_role("button", name="Start build").click()
        page.wait_for_url(re.compile(r"/builds/"))
        expect(page.locator(".step").first).to_be_visible()
        shot(page, out, "04-build-running")
        expect(page.locator(".build-head .badge").first).to_contain_text(re.compile("Done|Needs attention"), timeout=60000)
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
        page.get_by_role("button", name="Merge").click()
        expect(page.locator(".modal")).to_be_visible()
        page.locator(".modal").get_by_role("button", name="Merge").click()
        expect(page.locator(".build-head")).to_contain_text("Merged")
        check(page.get_by_role("button", name="Merge").count() == 0, "finish actions hidden after merge")
        shot(page, out, "07-build-merged")

        # ---- projects -----------------------------------------------------------------------
        print("Projects")
        page.get_by_role("link", name="Projects").first.click()
        page.locator(".list-item", has_text="test-repo").click()
        expect(page.locator(".file-item", has_text=re.compile(r"^numfmt.py")).first).to_be_visible()
        check(True, "merged file in project tree")
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

        # ---- tools --------------------------------------------------------------------------
        print("Tools")
        page.get_by_role("link", name="Tools").first.click()
        page.locator(".list-item", has_text="builtin__calculator").click()
        page.get_by_placeholder("string").first.fill("6*7")
        page.get_by_role("button", name="Run").click()
        expect(page.locator(".code pre").last).to_have_text("42")
        check(True, "calculator Try-it returns 42")
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

        browser.close()

    print("\nPROBLEMS:" if problems else "\nNo problems found.")
    for p in problems:
        print(" -", p)
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()

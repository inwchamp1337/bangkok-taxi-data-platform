"""
Automated screenshot capture script using Playwright.
Captures Control Center, Grafana dashboards, and interactive modals.
"""

from __future__ import annotations
import os
from pathlib import Path
import time
from playwright.sync_api import sync_playwright

OUTPUT_DIR = Path("docs/images")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def capture_all():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1600, "height": 1000})

        # -------------------------------------------------------------
        # 1. FastAPI Control Center UI
        # -------------------------------------------------------------
        page = context.new_page()
        print("Navigating to Control Center UI (http://127.0.0.1:5000)...")
        page.goto("http://127.0.0.1:5000", wait_until="networkidle")
        time.sleep(1.5)
        page.screenshot(path=str(OUTPUT_DIR / "control_panel.png"))
        print("Saved docs/images/control_panel.png")

        # Open Advanced Modal if available
        try:
            adv_btn = page.locator("button:has-text('Advanced Simulation'), button:has-text('Custom Simulation'), #advSimBtn, button.btn-secondary")
            if adv_btn.count() > 0:
                adv_btn.first.click()
                time.sleep(0.8)
                page.screenshot(path=str(OUTPUT_DIR / "simulation_modal.png"))
                print("Saved docs/images/simulation_modal.png")
        except Exception as e:
            print("Modal capture note:", e)

        # -------------------------------------------------------------
        # 2. Grafana Dashboards (Login first)
        # -------------------------------------------------------------
        gf_page = context.new_page()
        print("Logging into Grafana (http://127.0.0.1:3000)...")
        gf_page.goto("http://127.0.0.1:3000/login", wait_until="networkidle")
        try:
            gf_page.fill("input[name='user']", "admin")
            gf_page.fill("input[name='password']", "grafana_secret")
            gf_page.click("button[type='submit']")
            time.sleep(2)
        except Exception as e:
            print("Grafana login note:", e)

        # Capture Dashboard 1: Taxi Overview
        print("Capturing Taxi Overview Dashboard...")
        gf_page.goto("http://127.0.0.1:3000/d/taxi-overview?kiosk=tv", wait_until="networkidle")
        time.sleep(3)
        gf_page.screenshot(path=str(OUTPUT_DIR / "grafana_overview.png"))
        print("Saved docs/images/grafana_overview.png")

        # Capture Dashboard 2: Hotspot Analysis
        print("Capturing Hotspot Analysis Dashboard...")
        gf_page.goto("http://127.0.0.1:3000/d/taxi-hotspot?kiosk=tv", wait_until="networkidle")
        time.sleep(3)
        gf_page.screenshot(path=str(OUTPUT_DIR / "grafana_hotspots.png"))
        print("Saved docs/images/grafana_hotspots.png")

        # Capture Dashboard 3: Trip Analytics
        print("Capturing Trip Analytics Dashboard...")
        gf_page.goto("http://127.0.0.1:3000/d/taxi-trips?kiosk=tv", wait_until="networkidle")
        time.sleep(3)
        gf_page.screenshot(path=str(OUTPUT_DIR / "grafana_trips.png"))
        print("Saved docs/images/grafana_trips.png")

        browser.close()
        print("Screenshot capture workflow finished successfully!")


if __name__ == "__main__":
    capture_all()

import os
import sys
import io
import json
import queue
import threading
import asyncio
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List

import uvicorn
from fastapi import FastAPI, BackgroundTasks, Request
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from config import (
    BASE_DIR,
    DEFAULT_RESTAURANT_NAME,
    DEFAULT_RESTAURANT_ID,
    DEFAULT_WORKSHEET_NAME,
    GOOGLE_SHEET_URL,
    ZOMATO_LOGIN_URL,
)
from scrapers.browser_manager import BrowserManager
from scrapers.zomato_scraper import ZomatoScraper
from processors.metric_calculator import MetricCalculator
from exporters.google_sheets_generator import GoogleSheetsReportGenerator
from exporters.excel_generator import ExcelReportGenerator
from main import get_weekly_date_ranges, get_custom_dates, format_date_range_label

app = FastAPI(title="Report Automation Web UI")

STATIC_DIR = BASE_DIR / "static"
STATIC_DIR.mkdir(parents=True, exist_ok=True)
OUTLETS_FILE = BASE_DIR / "outlets.json"

# Thread-safe log queue for SSE
log_queue: queue.Queue = queue.Queue()
active_job = {
    "is_running": False,
    "status": "Ready",
    "outlet": "",
    "sheet_url": None,
    "error": None,
}


def load_outlets() -> List[Dict[str, Any]]:
    if not OUTLETS_FILE.exists():
        default_outlets = [
            {"id": "1", "name": "The Paneer Story", "zomato_id": "22749423", "swiggy_id": "1394282"},
            {"id": "2", "name": "The Spice Meridian", "zomato_id": "22663260", "swiggy_id": "1363315"},
            {"id": "3", "name": "Babbu Hotel", "zomato_id": "3300011", "swiggy_id": ""},
            {"id": "4", "name": "Biryani Lovers", "zomato_id": "22317789", "swiggy_id": ""},
        ]
        with open(OUTLETS_FILE, "w", encoding="utf-8") as f:
            json.dump(default_outlets, f, indent=2)
        return default_outlets
    try:
        with open(OUTLETS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def save_outlets(outlets: List[Dict[str, Any]]):
    with open(OUTLETS_FILE, "w", encoding="utf-8") as f:
        json.dump(outlets, f, indent=2)


class QueueWriter(io.TextIOBase):
    """Intercepts stdout / print statements and pushes them to log_queue."""
    def __init__(self, original_stdout):
        self.original_stdout = original_stdout

    def write(self, s):
        if self.original_stdout:
            self.original_stdout.write(s)
            self.original_stdout.flush()
        if s.strip():
            log_queue.put({"type": "log", "text": s.strip()})
        return len(s)

    def flush(self):
        if self.original_stdout:
            self.original_stdout.flush()


def run_automation_worker(
    ranges: List[tuple],
    restaurant_name: Optional[str],
    restaurant_id: Optional[str],
    worksheet_name: str,
    export_excel: bool = False,
    export_sheets: bool = True,
):
    global active_job
    active_job["is_running"] = True
    active_job["status"] = "Running"
    active_job["error"] = None
    active_job["sheet_url"] = None

    old_stdout = sys.stdout
    sys.stdout = QueueWriter(old_stdout)

    try:
        target_display_name = restaurant_name or (f"ID: {restaurant_id}" if restaurant_id else DEFAULT_RESTAURANT_NAME)
        target_display_id = restaurant_id or (DEFAULT_RESTAURANT_ID if not restaurant_name else "")

        print("=" * 55)
        print(f"[*] Starting Automation: {len(ranges)} report(s)")
        print(f"[*] Target Outlet: {target_display_name} (ZID: {target_display_id})")
        print(f"[*] Destination Tab: '{worksheet_name}'")
        print("=" * 55)

        with BrowserManager(headless=False) as bm:
            page = bm.get_page()
            scraper = ZomatoScraper(page)

            print("[*] Validating session cookies...")
            is_logged_in = scraper.check_login_status()
            if not is_logged_in:
                print("[!] Notice: If not logged in, please complete sign-in in browser window.")

            total_reports = len(ranges)
            last_sheet_url = None

            for idx, (s_date, e_date, d_label) in enumerate(ranges, 1):
                print(f"\n[REPORT {idx}/{total_reports}] Date Range: {d_label}")
                log_queue.put({"type": "step", "step": idx, "total": total_reports, "label": d_label})

                extracted_data = scraper.scrape_all(
                    s_date,
                    e_date,
                    d_label,
                    restaurant_name=restaurant_name,
                    restaurant_id=restaurant_id,
                )

                res_name = extracted_data.get("restaurant_name") or restaurant_name or (f"Restaurant_{restaurant_id}" if restaurant_id else DEFAULT_RESTAURANT_NAME)
                res_id = extracted_data.get("restaurant_id") or restaurant_id or DEFAULT_RESTAURANT_ID

                print(f"[✓] Calculating derived formulas for {d_label}...")
                metrics = MetricCalculator.calculate_zomato_metrics(extracted_data)

                if export_excel:
                    excel_gen = ExcelReportGenerator()
                    excel_gen.generate_report(
                        zomato_metrics=metrics,
                        restaurant_name=res_name,
                        restaurant_id=res_id,
                        date_range_label=d_label,
                        report_title="Weekly Report",
                    )

                if export_sheets:
                    sheets_gen = GoogleSheetsReportGenerator()
                    last_sheet_url = sheets_gen.generate_report(
                        zomato_metrics=metrics,
                        restaurant_name=res_name,
                        restaurant_id=res_id,
                        date_range_label=d_label,
                        report_title="Weekly Report",
                        worksheet_name=worksheet_name,
                    )
                    active_job["sheet_url"] = last_sheet_url
                    log_queue.put({"type": "sheet_ready", "url": last_sheet_url})

            print("\n" + "=" * 55)
            print("[✓] ALL REPORTS SYNCED SUCCESSFULLY!")
            if last_sheet_url:
                print(f"[🔗] Live Sheet: {last_sheet_url}")
            print("=" * 55)

            active_job["status"] = "Completed"
            log_queue.put({"type": "done", "sheet_url": last_sheet_url})

    except Exception as e:
        err_msg = str(e)
        print(f"\n[!] Automation Error: {err_msg}")
        active_job["status"] = "Error"
        active_job["error"] = err_msg
        log_queue.put({"type": "error", "message": err_msg})
    finally:
        sys.stdout = old_stdout
        active_job["is_running"] = False


class RunRequest(BaseModel):
    outlet_name: Optional[str] = None
    zomato_id: Optional[str] = None
    swiggy_id: Optional[str] = None
    range_type: str = "1"  # "1", "2", "3", "custom"
    weeks: int = 1
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    platform: str = "both"  # "both", "z", "s"
    worksheet_name: str = DEFAULT_WORKSHEET_NAME
    export_excel: bool = False


class OutletModel(BaseModel):
    name: str
    zomato_id: str
    swiggy_id: Optional[str] = ""


@app.get("/api/outlets")
def api_get_outlets():
    return load_outlets()


@app.post("/api/outlets")
def api_add_outlet(outlet: OutletModel):
    outlets = load_outlets()
    new_id = str(len(outlets) + 1)
    new_item = {
        "id": new_id,
        "name": outlet.name.strip(),
        "zomato_id": outlet.zomato_id.strip(),
        "swiggy_id": (outlet.swiggy_id or "").strip(),
    }
    # Check if already exists by zomato_id
    existing = next((o for o in outlets if o["zomato_id"] == new_item["zomato_id"]), None)
    if existing:
        existing.update(new_item)
    else:
        outlets.append(new_item)
    save_outlets(outlets)
    return {"status": "ok", "outlets": outlets, "selected": new_item}


@app.get("/api/status")
def api_get_status():
    return active_job


@app.post("/api/run")
def api_run_automation(req: RunRequest, background_tasks: BackgroundTasks):
    global active_job
    if active_job["is_running"]:
        return JSONResponse(status_code=400, content={"error": "An automation job is already running."})

    # Determine date ranges
    if req.range_type == "custom" and req.start_date and req.end_date:
        s_date, e_date, d_label = get_custom_dates(req.start_date, req.end_date)
        ranges = [(s_date, e_date, d_label)]
    else:
        try:
            num_w = int(req.range_type) if req.range_type.isdigit() else req.weeks
        except Exception:
            num_w = 1
        ranges = get_weekly_date_ranges(num_w)

    active_job["outlet"] = req.outlet_name or req.zomato_id or DEFAULT_RESTAURANT_NAME

    # Clear queue
    while not log_queue.empty():
        try:
            log_queue.get_nowait()
        except Exception:
            break

    # Spawn thread
    t = threading.Thread(
        target=run_automation_worker,
        kwargs={
            "ranges": ranges,
            "restaurant_name": req.outlet_name,
            "restaurant_id": req.zomato_id,
            "worksheet_name": req.worksheet_name or DEFAULT_WORKSHEET_NAME,
            "export_excel": req.export_excel,
            "export_sheets": True,
        },
        daemon=True,
    )
    t.start()

    return {"status": "started", "ranges_count": len(ranges)}


@app.get("/api/stream")
async def api_stream_logs(request: Request):
    """Server-Sent Events streaming real-time log lines to the client."""
    async def event_generator():
        while True:
            if await request.is_disconnected():
                break
            try:
                # Non-blocking get
                data = log_queue.get_nowait()
                yield f"data: {json.dumps(data)}\n\n"
            except queue.Empty:
                await asyncio.sleep(0.2)
                yield ": keepalive\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.post("/api/setup-login")
def api_setup_login():
    def worker():
        old_stdout = sys.stdout
        sys.stdout = QueueWriter(old_stdout)
        try:
            print("[*] Launching browser for Google Login setup...")
            with BrowserManager(headless=False) as bm:
                bm.interactive_login(ZOMATO_LOGIN_URL)
            print("[+] Login setup complete. Profile session saved.")
        finally:
            sys.stdout = old_stdout

    threading.Thread(target=worker, daemon=True).start()
    return {"status": "launched"}


# Serve static frontend
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/", response_class=HTMLResponse)
def serve_index():
    index_file = STATIC_DIR / "index.html"
    if index_file.exists():
        with open(index_file, "r", encoding="utf-8") as f:
            return f.read()
    return "<h1>Web UI is loading...</h1>"


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8501))
    print(f"\n🚀 Launching Report Automation Web UI on: http://localhost:{port}\n")
    uvicorn.run(app, host="0.0.0.0", port=port)

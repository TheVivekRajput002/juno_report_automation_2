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
    DEFAULT_SWIGGY_ID,
    DEFAULT_WORKSHEET_NAME,
    GOOGLE_SHEET_URL,
    ZOMATO_LOGIN_URL,
    SWIGGY_LOGIN_URL,
)
from scrapers.browser_manager import BrowserManager
from scrapers.zomato_scraper import ZomatoScraper
from scrapers.swiggy_scraper import SwiggyScraper
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
            {"id": "3", "name": "Babbu Hotel", "zomato_id": "3300011", "swiggy_id": "215500"},
            {"id": "4", "name": "Biryani Lovers", "zomato_id": "22317789", "swiggy_id": "1263351"},
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


class JobCardModel(BaseModel):
    outlet_name: Optional[str] = None
    zomato_id: Optional[str] = None
    swiggy_id: Optional[str] = None
    range_type: str = "1"  # "1", "2", "3", "custom"
    weeks: int = 1
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    platform: str = "both"  # "both", "z", "s"


def run_automation_worker(
    jobs: List[Dict[str, Any]],
    worksheet_name: str = DEFAULT_WORKSHEET_NAME,
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
        total_jobs = len(jobs)
        total_reports_all = sum(len(j.get("ranges", [])) for j in jobs)

        # Check which platforms are needed across all jobs
        needs_zomato = any((j.get("platform") or "both").lower() in ["both", "all", "zs", "zomato", "z"] for j in jobs)
        needs_swiggy = any((j.get("platform") or "both").lower() in ["both", "all", "zs", "swiggy", "s"] for j in jobs)

        print("=" * 60)
        print(f"[*] Starting Multi-Card Automation Execution ({total_jobs} Card(s), {total_reports_all} Total Report(s))")
        for i, j in enumerate(jobs, 1):
            plat_str = (j.get("platform") or "both").upper()
            ranges_str = f"{len(j.get('ranges', []))} range(s)"
            print(f"  [{i}/{total_jobs}] {j.get('outlet_name')} | Platform: {plat_str} | {ranges_str}")
        print(f"[*] Destination Tab: '{worksheet_name}'")
        print("=" * 60)

        with BrowserManager(headless=False) as bm:
            z_page = bm.get_named_page("zomato") if needs_zomato else None
            s_page = bm.get_named_page("swiggy") if needs_swiggy else None

            z_scraper = ZomatoScraper(z_page) if z_page else None
            s_scraper = SwiggyScraper(s_page) if s_page else None

            if z_scraper:
                print("[*] Validating Zomato session...")
                if not z_scraper.check_login_status():
                    print("[!] Notice: Zomato session not detected. Please complete Google sign-in in the opened browser window...")
                    if not z_scraper.auth.wait_for_login(timeout_sec=60):
                        print("[!] Warning: Proceeding, but Zomato session may not be authenticated.")

            if s_scraper:
                print("[*] Validating Swiggy session...")
                if not s_scraper.check_login_status():
                    print("[!] Notice: Swiggy session not detected. Please enter your mobile number & OTP in the opened browser window...")
                    if not s_scraper.auth.wait_for_login(timeout_sec=60):
                        print("[!] Warning: Proceeding, but Swiggy session may not be authenticated.")

            last_sheet_url = None
            completed_jobs = 0
            overall_report_counter = 0

            for job_idx, job in enumerate(jobs, 1):
                res_name = job.get("outlet_name") or DEFAULT_RESTAURANT_NAME
                z_id = str(job.get("zomato_id") or "")
                s_id = str(job.get("swiggy_id") or "")
                job_ranges = job.get("ranges") or []
                job_platform = (job.get("platform") or "both").lower().strip()

                run_zomato = job_platform in ["both", "all", "zs", "zomato", "z"]
                run_swiggy = job_platform in ["both", "all", "zs", "swiggy", "s"]

                target_display = res_name
                if z_id:
                    target_display += f" (ZID: {z_id})"
                if s_id:
                    target_display += f" (SID: {s_id})"

                print("\n" + "=" * 60)
                print(f"[CARD {job_idx}/{total_jobs}] Running: {target_display} [{job_platform.upper()}] ({len(job_ranges)} Report(s))")
                print("=" * 60)

                log_queue.put({
                    "type": "card_start",
                    "card_index": job_idx,
                    "total_cards": total_jobs,
                    "outlet_name": res_name,
                    "platform": job_platform,
                    "ranges_count": len(job_ranges),
                })

                for idx, (s_date, e_date, d_label) in enumerate(job_ranges, 1):
                    overall_report_counter += 1
                    print(f"\n[{res_name} - REPORT {idx}/{len(job_ranges)}] Date Range: {d_label}")
                    log_queue.put({
                        "type": "step",
                        "card_index": job_idx,
                        "total_cards": total_jobs,
                        "step": idx,
                        "total": len(job_ranges),
                        "overall_step": overall_report_counter,
                        "total_overall": total_reports_all,
                        "label": d_label,
                        "outlet_name": res_name,
                    })

                    z_metrics = None
                    s_metrics = None

                    # 1. Scrape Zomato if enabled for this card
                    if run_zomato and z_scraper:
                        print(f"[*] Extracting Zomato data for {d_label}...")
                        try:
                            z_extracted = z_scraper.scrape_all(
                                s_date,
                                e_date,
                                d_label,
                                restaurant_name=res_name,
                                restaurant_id=z_id,
                            )
                            z_metrics = MetricCalculator.calculate_zomato_metrics(z_extracted)
                            print(f"[✓] Zomato: Orders={z_metrics.orders}, Sales={z_metrics.sales_after_discount}, Payout={z_metrics.cash_in_bank}")
                        except Exception as ze:
                            print(f"[!] Zomato extraction error for {res_name}: {ze}")

                    # 2. Scrape Swiggy if enabled for this card
                    if run_swiggy and s_scraper:
                        print(f"[*] Extracting Swiggy data for {d_label}...")
                        try:
                            s_extracted = s_scraper.scrape_all(
                                s_date,
                                e_date,
                                d_label,
                                restaurant_name=res_name,
                                restaurant_id=s_id,
                            )
                            s_metrics = MetricCalculator.calculate_swiggy_metrics(s_extracted)
                            print(f"[✓] Swiggy: Orders={s_metrics.orders}, Sales={s_metrics.sales_after_discount}, Payout={s_metrics.cash_in_bank}")
                        except Exception as se:
                            print(f"[!] Swiggy extraction error for {res_name}: {se}")

                    final_res_name = res_name or (z_scraper.extracted_restaurant_name if z_scraper else None) or (s_scraper.extracted_restaurant_name if s_scraper else None) or DEFAULT_RESTAURANT_NAME
                    final_res_id = (z_id if z_id else None) or (s_id if run_swiggy and not run_zomato else None) or DEFAULT_RESTAURANT_ID

                    if export_excel:
                        try:
                            excel_gen = ExcelReportGenerator()
                            excel_gen.generate_report(
                                zomato_metrics=z_metrics,
                                swiggy_metrics=s_metrics,
                                restaurant_name=final_res_name,
                                restaurant_id=final_res_id,
                                date_range_label=d_label,
                                report_title="Weekly Report",
                            )
                        except Exception as ee:
                            print(f"[!] Excel export error: {ee}")

                    if export_sheets:
                        try:
                            sheets_gen = GoogleSheetsReportGenerator()
                            last_sheet_url = sheets_gen.generate_report(
                                zomato_metrics=z_metrics,
                                swiggy_metrics=s_metrics,
                                restaurant_name=final_res_name,
                                restaurant_id=final_res_id,
                                date_range_label=d_label,
                                report_title="Weekly Report",
                                worksheet_name=worksheet_name,
                            )
                            active_job["sheet_url"] = last_sheet_url
                            log_queue.put({"type": "sheet_ready", "url": last_sheet_url})
                        except Exception as se:
                            print(f"[!] Google Sheets sync error: {se}")

                completed_jobs += 1
                print(f"\n[✓] Card [{job_idx}/{total_jobs}] '{res_name}' completed successfully!")

            print("\n" + "=" * 60)
            print(f"[✓] ALL {completed_jobs}/{total_jobs} CARDS PROCESSED SUCCESSFULLY!")
            if last_sheet_url:
                print(f"[🔗] Live Sheet: {last_sheet_url}")
            print("=" * 60)

            active_job["status"] = "Completed"
            log_queue.put({"type": "done", "sheet_url": last_sheet_url, "total_cards": completed_jobs})

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
    cards: Optional[List[JobCardModel]] = None
    # Backward-compatible single/batch fields
    outlet_name: Optional[str] = None
    zomato_id: Optional[str] = None
    swiggy_id: Optional[str] = None
    outlets: Optional[List[Dict[str, Any]]] = None
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
    swiggy_account: Optional[str] = ""


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

    jobs_to_run = []

    if req.cards and len(req.cards) > 0:
        for card in req.cards:
            res_name = (card.outlet_name or "").strip()
            z_id = str(card.zomato_id or "").strip()
            s_id = str(card.swiggy_id or "").strip()

            if card.range_type == "custom" and card.start_date and card.end_date:
                s_date, e_date, d_label = get_custom_dates(card.start_date, card.end_date)
                ranges = [(s_date, e_date, d_label)]
            else:
                try:
                    num_w = int(card.range_type) if str(card.range_type).isdigit() else card.weeks
                except Exception:
                    num_w = 1
                ranges = get_weekly_date_ranges(num_w)

            jobs_to_run.append({
                "outlet_name": res_name or (f"ID: {z_id}" if z_id else DEFAULT_RESTAURANT_NAME),
                "zomato_id": z_id,
                "swiggy_id": s_id,
                "ranges": ranges,
                "platform": card.platform or "both",
            })
    elif req.outlets and len(req.outlets) > 0:
        if req.range_type == "custom" and req.start_date and req.end_date:
            s_date, e_date, d_label = get_custom_dates(req.start_date, req.end_date)
            ranges = [(s_date, e_date, d_label)]
        else:
            try:
                num_w = int(req.range_type) if str(req.range_type).isdigit() else req.weeks
            except Exception:
                num_w = 1
            ranges = get_weekly_date_ranges(num_w)

        for o in req.outlets:
            res_name = (o.get("name") or "").strip()
            z_id = str(o.get("zomato_id") or "").strip()
            s_id = str(o.get("swiggy_id") or "").strip()
            if res_name or z_id or s_id:
                jobs_to_run.append({
                    "outlet_name": res_name or (f"ID: {z_id}" if z_id else DEFAULT_RESTAURANT_NAME),
                    "zomato_id": z_id,
                    "swiggy_id": s_id,
                    "ranges": ranges,
                    "platform": req.platform or "both",
                })
    else:
        if req.range_type == "custom" and req.start_date and req.end_date:
            s_date, e_date, d_label = get_custom_dates(req.start_date, req.end_date)
            ranges = [(s_date, e_date, d_label)]
        else:
            try:
                num_w = int(req.range_type) if str(req.range_type).isdigit() else req.weeks
            except Exception:
                num_w = 1
            ranges = get_weekly_date_ranges(num_w)

        jobs_to_run.append({
            "outlet_name": req.outlet_name or DEFAULT_RESTAURANT_NAME,
            "zomato_id": req.zomato_id or DEFAULT_RESTAURANT_ID,
            "swiggy_id": req.swiggy_id or DEFAULT_SWIGGY_ID,
            "ranges": ranges,
            "platform": req.platform or "both",
        })

    active_job["outlet"] = ", ".join([j["outlet_name"] for j in jobs_to_run[:3]]) + (f" (+{len(jobs_to_run)-3} more)" if len(jobs_to_run) > 3 else "")

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
            "jobs": jobs_to_run,
            "worksheet_name": req.worksheet_name or DEFAULT_WORKSHEET_NAME,
            "export_excel": req.export_excel,
            "export_sheets": True,
        },
        daemon=True,
    )
    t.start()

    total_ranges_count = sum(len(j.get("ranges", [])) for j in jobs_to_run)
    return {"status": "started", "jobs_count": len(jobs_to_run), "ranges_count": total_ranges_count}


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
            print("[*] Launching browser for Zomato Google Login setup...")
            with BrowserManager(headless=False) as bm:
                bm.interactive_login(ZOMATO_LOGIN_URL)
            print("[+] Zomato login setup complete. Profile session saved.")
        finally:
            sys.stdout = old_stdout

    threading.Thread(target=worker, daemon=True).start()
    return {"status": "launched"}


@app.post("/api/setup-login-swiggy")
def api_setup_login_swiggy():
    def worker():
        old_stdout = sys.stdout
        sys.stdout = QueueWriter(old_stdout)
        try:
            print("[*] Launching browser for Swiggy Partner Login setup...")
            with BrowserManager(headless=False) as bm:
                bm.interactive_login(SWIGGY_LOGIN_URL)
            print("[+] Swiggy login setup complete. Profile session saved.")
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

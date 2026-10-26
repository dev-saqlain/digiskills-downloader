import csv
import io
import os
import re
import shutil
import subprocess
import threading
import time
import uuid
import zipfile
from pathlib import Path
from urllib.parse import urlparse

from flask import Flask, render_template, request, redirect, url_for, flash, send_file, jsonify

APP_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.environ.get("DATA_DIR", APP_DIR / "data"))
JOBS_DIR = DATA_DIR / "jobs"
JOBS_DIR.mkdir(parents=True, exist_ok=True)

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "change-this-secret-before-deploying")

jobs = {}
jobs_lock = threading.Lock()

def valid_youtube_url(value):
    try:
        parsed = urlparse(value.strip())
        host = (parsed.hostname or "").lower()
        return parsed.scheme in ("http", "https") and (
            host == "youtube.com" or host.endswith(".youtube.com") or
            host == "youtu.be" or host.endswith(".youtu.be")
        )
    except Exception:
        return False

def clean_urls(lines):
    seen, result = set(), []
    for line in lines:
        url = (line or "").strip().strip('"').strip("'")
        if not url or url.lower() in ("url", "video_url", "youtube_url", "link"):
            continue
        if not valid_youtube_url(url):
            continue
        # Normalize watch URLs and short links via yt-dlp itself; retain original URL.
        if url not in seen:
            seen.add(url)
            result.append(url)
    return result

def read_csv_urls(file_storage):
    raw = file_storage.read().decode("utf-8-sig", errors="replace")
    rows = list(csv.reader(io.StringIO(raw)))
    found = []
    for row in rows:
        for cell in row:
            if "youtube.com/" in cell.lower() or "youtu.be/" in cell.lower():
                found.append(cell.strip())
    return clean_urls(found)

def run_job(job_id, urls, quality):
    job_dir = JOBS_DIR / job_id
    video_dir = job_dir / "videos"
    video_dir.mkdir(parents=True, exist_ok=True)
    success, failed = [], []
    with jobs_lock:
        jobs[job_id]["status"] = "running"
        jobs[job_id]["message"] = "Download started."
    try:
        total = len(urls)
        for index, url in enumerate(urls, 1):
            with jobs_lock:
                jobs[job_id]["current"] = index
                jobs[job_id]["current_url"] = url
                jobs[job_id]["message"] = f"Processing video {index} of {total}"
                jobs[job_id]["logs"].append(f"[{index}/{total}] {url}")
            if quality == "1080":
                fmt = "bestvideo[height<=1080][height>=720][vcodec^=avc1]+bestaudio/best[height<=1080]"
            elif quality == "720":
                fmt = "bestvideo[height<=720][vcodec^=avc1]+bestaudio/best[height<=720]"
            else:
                fmt = "bestvideo[vcodec^=avc1]+bestaudio/best/best"
            cmd = [
                "python", "-m", "yt_dlp",
                "--no-playlist",
                "--no-warnings",
                "--newline",
                "--restrict-filenames",
                "-f", fmt,
                "--merge-output-format", "mp4",
                "-o", str(video_dir / "%(title).120s-%(id)s.%(ext)s"),
                url,
            ]
            try:
                proc = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
                out = (proc.stdout or "") + "\n" + (proc.stderr or "")
                if proc.returncode == 0:
                    produced = [p for p in video_dir.iterdir() if p.is_file()]
                    if produced:
                        success.append(url)
                        with jobs_lock:
                            jobs[job_id]["logs"].append(f"SUCCESS: video {index} processed.")
                    else:
                        failed.append((url, "yt-dlp exited successfully but no output file was found"))
                        with jobs_lock:
                            jobs[job_id]["logs"].append(f"FAILED: no output file for video {index}.")
                else:
                    err = "\n".join([x for x in out.splitlines() if "ERROR:" in x or "WARNING:" in x][-4:])
                    failed.append((url, err or f"yt-dlp exit code {proc.returncode}"))
                    with jobs_lock:
                        jobs[job_id]["logs"].append(f"FAILED: {err or 'yt-dlp error'}")
            except subprocess.TimeoutExpired:
                failed.append((url, "Timed out after 15 minutes"))
                with jobs_lock:
                    jobs[job_id]["logs"].append("FAILED: timed out after 15 minutes.")
        zip_path = job_dir / "videos.zip"
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for p in video_dir.iterdir():
                if p.is_file() and p.stat().st_size:
                    zf.write(p, arcname=p.name)
        report = job_dir / "download_report.csv"
        with report.open("w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            writer.writerow(["URL", "Status", "Details"])
            ok_set = set(success)
            fail_map = {u: e for u, e in failed}
            for url in urls:
                writer.writerow([url, "Success" if url in ok_set else "Failed", fail_map.get(url, "")])
        with jobs_lock:
            jobs[job_id]["status"] = "done"
            jobs[job_id]["success"] = len(success)
            jobs[job_id]["failed"] = len(failed)
            jobs[job_id]["message"] = f"Finished: {len(success)} succeeded, {len(failed)} failed."
            jobs[job_id]["zip_ready"] = zip_path.exists() and zip_path.stat().st_size > 0
    except Exception as exc:
        with jobs_lock:
            jobs[job_id]["status"] = "error"
            jobs[job_id]["message"] = str(exc)
            jobs[job_id]["logs"].append(f"FATAL: {exc}")

@app.get("/")
def index():
    return render_template("index.html")

@app.post("/start")
def start():
    pasted = request.form.get("urls", "")
    urls = clean_urls(pasted.splitlines())
    uploaded = request.files.get("csv_file")
    if uploaded and uploaded.filename:
        if not uploaded.filename.lower().endswith(".csv"):
            flash("Please upload a .csv file.")
            return redirect(url_for("index"))
        urls.extend(read_csv_urls(uploaded))
        urls = list(dict.fromkeys(urls))
    try:
        max_count = int(request.form.get("max_count", "12"))
    except ValueError:
        max_count = 12
    max_count = max(1, min(max_count, 30))
    urls = urls[:max_count]
    if not urls:
        flash("No valid YouTube URLs found. Paste URLs or upload the CSV produced by your scanner.")
        return redirect(url_for("index"))
    quality = request.form.get("quality", "1080")
    if quality not in ("1080", "720", "best"):
        quality = "1080"
    job_id = uuid.uuid4().hex[:12]
    with jobs_lock:
        jobs[job_id] = {
            "status": "queued", "message": "Queued.", "current": 0,
            "total": len(urls), "current_url": "", "logs": [],
            "success": 0, "failed": 0, "zip_ready": False
        }
    thread = threading.Thread(target=run_job, args=(job_id, urls, quality), daemon=True)
    thread.start()
    return redirect(url_for("job_page", job_id=job_id))

@app.get("/job/<job_id>")
def job_page(job_id):
    with jobs_lock:
        job = jobs.get(job_id)
    if not job:
        flash("Job not found. Free hosting may restart and clear temporary jobs.")
        return redirect(url_for("index"))
    return render_template("job.html", job_id=job_id, job=job)

@app.get("/api/job/<job_id>")
def job_api(job_id):
    with jobs_lock:
        job = jobs.get(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404
    return jsonify(job)

@app.get("/download/<job_id>")
def download(job_id):
    with jobs_lock:
        job = jobs.get(job_id)
    if not job or job.get("status") != "done":
        flash("This job is not ready.")
        return redirect(url_for("job_page", job_id=job_id))
    path = JOBS_DIR / job_id / "videos.zip"
    if not path.exists() or path.stat().st_size == 0:
        flash("No video files were successfully downloaded.")
        return redirect(url_for("job_page", job_id=job_id))
    return send_file(path, as_attachment=True, download_name=f"digiskills_videos_{job_id}.zip")

@app.get("/report/<job_id>")
def report(job_id):
    path = JOBS_DIR / job_id / "download_report.csv"
    if not path.exists():
        flash("Report is not ready.")
        return redirect(url_for("job_page", job_id=job_id))
    return send_file(path, as_attachment=True, download_name=f"download_report_{job_id}.csv")

@app.get("/health")
def health():
    return {"status": "ok"}

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "5000")), debug=False)

DigiSkills Video Helper — Render starter project
=================================================

WHAT THIS PROJECT DOES
- Runs as a separate Flask website.
- Accepts YouTube video URLs pasted into the form or found in a CSV file.
- Lets you choose 1080p preference, 720p, or best available.
- Processes URLs one at a time, then offers a ZIP and a CSV report.
- Shows real success/failure counts instead of assuming a download succeeded.

IMPORTANT LIMITATIONS
- This is a CSV/URL-based web app. It does NOT automatically log in to DigiSkills LMS or control the office PC's Chrome.
- Only use URLs and downloads you are authorized to access/save. It does not bypass LMS restrictions or protected streams.
- Render Free services have limited memory, ephemeral disk, inactivity sleep, request/runtime constraints and may restart. Large batches or long lectures may fail; start with ONE short test video.
- Files stored on the free instance are temporary. Download the ZIP as soon as the job finishes.
- The job is kept in server memory, so a restart loses its status. This is a starter version, not production-grade persistent job storage.
- Never put LMS passwords, browser cookies, or session tokens into this website.
- YouTube may return 429/bot verification/PO-token errors. Deno helps with JS challenges but does not guarantee that every URL can be downloaded.

LOCAL TEST (optional)
1. Install Python and FFmpeg/Deno locally if needed.
2. In this folder run:
   pip install -r requirements.txt
   python app.py
3. Open http://127.0.0.1:5000

RENDER DEPLOYMENT
1. Create a new GitHub repository for this project. Keep it separate from the old PythonAnywhere ERP converter.
2. Upload all files from this folder to the repository (app.py, requirements.txt, Dockerfile, render.yaml, templates/).
3. Sign in at https://render.com/ and choose New > Blueprint.
4. Connect the new GitHub repository and deploy the blueprint. Alternatively create a new Web Service using the Docker runtime.
5. Wait for the build/deploy to finish, then open the Render URL.
6. Test with ONE short video URL that you are authorized to download. Do not begin with a whole week of lectures.
7. If Render logs show a build error or the service restarts, inspect Logs. Free-tier resource/time limits may make long videos unsuitable.

QUALITY
- 1080p setting prefers H.264 video up to 1080p plus audio and merges to MP4 when compatible.
- If 1080p/H.264 is unavailable, yt-dlp may fall back to a lower available format.
- Resolution cannot exceed the source quality.
- FFmpeg is included in the Docker image to merge separate streams.

This project is independent of your PythonAnywhere project.

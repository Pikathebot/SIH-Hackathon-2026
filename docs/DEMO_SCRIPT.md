# SatQuery AI — Demo Script

A 10-minute live walkthrough on the real GPU engine, plus the setup that has to happen first.
Every step below was rehearsed on the RTX 5070 machine; times are what it actually took.

---

## 1. Before the audience arrives (T−15 min)

**Free the GPU.** The hybrid engine peaks at about 11.8 of 12.2 GB.
- Quit **LM Studio** and **ComfyUI** (tray icons too). Close games, Wallpaper Engine and anything else using the GPU.
- Check: `nvidia-smi` should show under 2.5 GB used before you start.

**Start the stack** from the repo root in PowerShell:
```powershell
# .env must contain AI_SERVICE_MODE=real and AI_ENGINE=hybrid
.\start_dev.ps1
```
This starts llama-server (Qwen3-VL-8B, :8080), the backend (:8000) and the frontend (:3000).
llama-server takes about 30–60 s to load.

**Pre-flight checks** (all must pass):
```powershell
curl http://localhost:8000/api/v1/ready      # 200 {"status":"ready","checks":{"database":true,"engine":true}}
curl http://localhost:8000/api/v1/health     # "mode":"real", "vlm_available":true, "rsunivlm_loaded":true
```
Then open http://localhost:3000. The top bar must say **AI Online**.

**Warm up** (so the first on-stage answer is not the slow one): sign in with a throwaway account,
run Sample Questions → *Scene Description* and *Water & Land Cover Highlight* once, then sign out.

**Browser:** one window, zoom 100 %, dark theme (sun/moon button top right), notifications off.
If Chrome shows an error page for `localhost`, pause Cloudflare WARP or any VPN.

---

## 2. The walkthrough (≈10 min)

All six scenarios are in **Sample Questions** (top right). Each one uploads a bundled sample image
exactly like a user's file, so answers, overlays and coordinates are real.

### Step 1 — Sign up (30 s)
Create an account (any email, 10+ character password).
> "Every analysis is stored per user. Uploads, history and results are private to this account."

### Step 2 — Scene description on real Sentinel-2 (≈2–4 s)
Sample Questions → **Scene Description** → **Analyze**.
- Read the first sentence of the answer aloud.
- Hover the image: the read-out shows **real latitude/longitude** from the GeoTIFF, and the badge shows the ground **extent** (10 × 10 km for this tile).
- Open **Analysis Details & Technical Summary**: the task the system chose (*Image Captioning*), latency, and where the confidence comes from. Hover the tool name to show the exact model tool (`qwen_vl_cap`).
> "No task picker. The system reads the question and routes it."

### Step 3 — Ask a yes/no question (≈2–3 s)
Re-open **Scene Description**, replace the question with **"Is there a river in this image?"**, Analyze.
Expected: a direct **"No, …"** with a reason.
> "Same image, different intent: a yes/no question goes to question answering, not to segmentation."

### Step 4 — Question answering on a real port (≈1 s)
**Visual Question Answering** ("Is there a ship berthed at the terminal?"), on a real 0.6 m NAIP image of the Port of Long Beach.
Expected: **"Yes"**, with evidence: the vessel alongside the quay and the gantry crane over it.

### Step 5 — Localization with map coordinates (≈2 s)
**Object & Facility Localization** ("Locate all aircraft."), on a real 0.3 m NAIP image of the Davis-Monthan aircraft storage yard.
Expected: **13 boxes**, one on each clearly visible aircraft (the small airframe parts near the bottom are not boxed).
- Optional: re-run the VQA preset's port image with **"Locate the ship and the gantry cranes."**: 1 ship + 4 cranes.
- Toggle **Boxes** off and on.
- Click **GeoJSON**: each box exported as a WGS84 polygon, ready for QGIS.

### Step 6 — Water segmentation from JPEG 2000 (≈5–9 s)
**Water & Land Cover Highlight**.
Expected: the lake polygon is masked. The amber "Band Order Unverified" notice is expected and honest:
the file carries no band metadata.
> "Masks come from RSUniVLM, a remote-sensing model; boxes and language come from Qwen3-VL. That is the hybrid engine."

### Step 7 — Change detection (≈5 s)
**Temporal Change Detection** (2021 vs 2024).
- Drag the **split slider** between before and after.
- The answer lists the new structures by quadrant; the change mask is shown below.

### Step 8 — Optical + radar fusion through cloud (≈1 s)
**Optical + Radar (SAR) Fusion**.
Expected: about **52 % water, 48 % built-up**, and the answer states that **43 % of the optical image is cloud-covered** and the water beneath it was identified from radar.
> "Optical can't see through cloud; radar can. The fused map shows the water under the clouds, and the ships under them stay as strong radar targets."

### Step 9 — It remembers (30 s)
Reload the page (F5). You stay signed in; the conversation and every result are still there.
Click **PDF Report** on any result for a printable mission report.

### Step 10 — Guardrails (30 s)
Attach two radar images (or switch both images to *Radar (SAR)*).
Expected: a warning explains the supported combinations and **Analyze is disabled**.

**Close:** everything ran locally on one 12 GB consumer GPU. No image or question left the machine.

---

## 3. Things not to do on stage

| Avoid | Why |
|---|---|
| Asking for **counts** ("How many aircraft…?") | Counting in free text is unreliable (it says 11, then 14, for 13 aircraft; 3 cranes for 4). Use **Locate…** and count the boxes. |
| The `real_sentinel2_change_*` pair | It is open sea; the honest answer is "no concrete changes". |
| Radar questions on `real_sentinel1_sar_grd_vv.tif` as a highlight | At this resolution the model correctly says it cannot identify targets: honest, but not impressive. |
| Opening LM Studio, ComfyUI or a game mid-demo | Out of GPU memory → failed queries. |
| Firing many queries at once | One GPU job at a time; the queue holds 4 more, then "queue is full" (503). |

---

## 4. If something goes wrong

| Symptom | Fix |
|---|---|
| Top bar shows AI offline / `/ready` is 503 | Backend not up. Check its window for errors; restart `.\start_dev.ps1`. |
| `/health` shows `"vlm_available": false` | llama-server is down. Restart it with `scripts\start_vlm_server.ps1`, then restart the backend (it picks the engine at startup; without llama-server it falls back to RSUniVLM only). |
| "The analysis queue is full. Please try again shortly." (503) | Wait a few seconds and re-run. |
| "The analysis took longer than 300 s and was abandoned." (504) | Usually another GPU app. Check `nvidia-smi`, close it, re-run. |
| A preset shows "Sample image … is missing" | Run `.venv\Scripts\python scripts\build_demo_samples.py`, then reload. |
| No GPU at all (laptop, venue machine) | Set `AI_SERVICE_MODE=mock` in `.env` and restart. The UI works end to end with canned answers. **Say so** to the audience. |

**Reset between runs:** sidebar → **Clear All History**, or sign up with a fresh account.

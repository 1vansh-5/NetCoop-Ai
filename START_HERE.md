# NetCoop — Groq update

## Install / replace
1. Stop your running NetCoop server. Keep a backup of the existing folder.
2. Extract this ZIP. Copy everything INSIDE its T2 folder into your existing T2 folder and replace matching files. Include the complete static folder and new groq_decision.py.
3. Copy .env.example to .env beside server.py (if you already have .env, add these settings to it instead).
4. Set GROQ_API_KEY=your_actual_key in .env. Keep GROQ_MODEL=llama-3.3-70b-versatile, or use another Groq model supporting JSON object responses.
5. Run run.bat. Open http://127.0.0.1:8000 and hard-refresh your browser (Ctrl+F5).

## Use
Click Diagnose / Operations on the campus page. It opens the full operations dashboard in the same tab, with agent operations, evidence, AI decision, downloads and incident history together.
Select Normal, Latency spike or Hardware failure from the telemetry provider list. Choose Groq AI and click Run investigation. Each investigation executes telemetry_provider.py again; a preview is a separate sample, so its random values can differ from the final run.
The supplied provider generates fresh RANDOM SIMULATION data; it is not a collector connected to real network equipment. The 3D campus is also illustrative and is not the provider's measured topology.
Groq chooses the final probable cause, confidence and alternatives. The matching runbook supplies recommended actions. The original specialist scores are retained under specialist_baseline. The dashboard labels fallback decisions if the key is missing, the API fails or the response is invalid. Stale or very incomplete data cannot become a definitive AI diagnosis. No repairs run automatically.

Your key stays on the server. Groq mode sends the normalized telemetry and specialist findings to Groq. Never put the key in JavaScript or share your .env.

## Files changed
engine.py, server.py, provider.py, telemetry_provider.py, cli.py, static/index.html, static/campus.html, static/campus-netcoop.js, static/netcoop.html, static/app.js, README.md.
New: groq_decision.py, .env.example, START_HERE.md, tests/test_groq.py.
The ZIP includes the whole source project and existing assets/tests/samples. It excludes API keys, old incident history, .git, virtual environments and generated caches. Existing .env and data are not replaced.

## Validation
Run python -m pytest -q from T2 after installing requirements.txt. Groq tests use mocked API responses, including AI overriding specialist results, invalid responses, missing-key fallback and stale-data protection. A real Groq request requires your key and has not been tested with your account.

API integration references: https://console.groq.com/docs/api-reference and https://console.groq.com/docs/structured-outputs

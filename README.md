# AgriMarket AI — Telangana farm planning assistant

AgriMarket AI is a Python + Streamlit prototype for helping farmers compare crop options before sowing. It has a welcome page, local user accounts, English/Hindi/Telugu interface labels, saved farm profiles, a Telangana district selector, soil/month/water inputs, an optional soil-test section, live district-level weather context, crop suitability rankings, fertilizer notes, editable investment/profit scenarios, and a thank-you page after sign-out.

The login and planning screens include agriculture photography served from Unsplash, so those images need an internet connection to display.

## Run on Windows

Use a project virtual environment so the app does not inherit a mismatched NumPy/pandas installation from Anaconda:

```powershell
cd "C:\Users\srima\OneDrive\Desktop\sp1"
python -m venv .venv-fieldwise
.\.venv-fieldwise\Scripts\python.exe -m pip install --upgrade pip
.\.venv-fieldwise\Scripts\python.exe -m pip install -r requirements.txt
.\.venv-fieldwise\Scripts\python.exe -m streamlit run app.py
```

Open the local URL Streamlit prints, normally `http://localhost:8501`. Keep that terminal open while using the app. Register a user ID and password on the first screen, then sign in.

## Live internet data

- The app requests a 7-day forecast and 10 completed years of monthly rainfall history from Open-Meteo for the selected district headquarters. Its forecast and historical weather APIs use numerical weather models and reanalysis; these are district-level estimates, not measurements from the farmer's field.
- With a data.gov.in API key, the app fetches reported district modal prices from the Government of India's AGMARKNET mandi price feed. The quote date and mandi names are shown; confirm the rate with the buyer because availability and freshness vary. If there is no key or quote, enter a current local price yourself.
- Crop calendars and fertilizer notes link to public ICAR and CICR advisories. Soil type remains farmer-entered (and can be supplemented with a Soil Health Card). SoilGrids currently reports that its point REST API is paused, so this version does not pretend to fetch live soil measurements.

### Enable live mandi prices

1. Register on [data.gov.in](https://www.data.gov.in/) and generate an API key for the current daily mandi prices resource.
2. Copy `.streamlit/secrets.toml.example` to `.streamlit/secrets.toml`.
3. Replace the placeholder with your key. Do not share or commit `secrets.toml`.
4. Restart Streamlit and run a new farm analysis.

## How recommendations and estimates work

Crop rankings use an explainable suitability score from the chosen sowing month, farmer-entered soil type, water availability, near-term rainfall, and the 10-year rainfall history for that sowing month. This prototype does **not** contain a trained machine-learning model. The score is a screening aid, not a prediction of yield or a guarantee that a crop will be profitable.

The budget section displays an editable sample scenario immediately, so investment and return details are visible without first filling every field. Sample price, yield and cost values are illustrative only, not verified current local data or field-specific predictions. Replace them with a current mandi/buyer quote, your farm's yield history and actual input costs. If the mandi feed is configured, its reported modal quote pre-fills the price; verify it locally before relying on it. The displayed range is a simple sensitivity scenario around the shown inputs, not a forecast. No available public feed in this prototype supplies reliable field-specific yield, farm-specific costs, or a guaranteed profit prediction. Fertilizer guidance is crop-level reference material; the final dose must come from a current Soil Health Card/lab test and local KVK or agriculture officer.

## Accounts and local data

New accounts are stored in `%LOCALAPPDATA%\Fieldwise\farmers.db` on Windows. Passwords are stored as salted PBKDF2 hashes. The app saves district, area, soil, water, sowing month, and language for each account. This local sign-in is for a classroom/local prototype, not production identity management. Do not expose this Streamlit server to the public internet without adding production authentication, HTTPS, backups, rate limiting, and a reviewed privacy/security design.

## Project files

- `app.py` — Streamlit UI, local authentication, district forecast request, crop ranking, fertilizer notes, and scenario calculations.
- `.streamlit/config.toml` — AgriMarket AI visual theme.
- `.streamlit/secrets.toml.example` — Template for the optional data.gov.in API key.
- `requirements.txt` — Python dependencies, including a compatible NumPy/pandas pair for a fresh environment.
- `.gitignore` — Keeps local accounts, virtual environments, and secrets out of source control.

"""AgriMarket AI — Telangana crop planning assistant (Streamlit prototype).

This app combines farmer-entered field details, a transparent crop suitability
score, live Open-Meteo weather context, and source-linked agronomy notes. The
cost/yield figures are editable planning assumptions, not guarantees.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import sqlite3
import statistics
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen
import json

import streamlit as st


st.set_page_config(
    page_title="AgriMarket AI | Farm planning",
    page_icon=":material/energy_savings_leaf:",
    layout="wide",
    initial_sidebar_state="expanded",
)

ROOT = Path(__file__).resolve().parent
LOCAL_DATA_DIR = Path(os.environ.get("LOCALAPPDATA", str(ROOT / ".fieldwise"))) / "Fieldwise"
DB_PATH = Path(os.environ.get("FIELDWISE_DB", str(LOCAL_DATA_DIR / "farmers.db")))
PASSWORD_ROUNDS = 310_000
MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]
LANGUAGES = {"en": "English", "hi": "हिन्दी", "te": "తెలుగు"}
FARM_PHOTOS = {
    "telangana": "https://images.unsplash.com/photo-1666545743813-e692fb2b2430?auto=format&fit=crop&w=1600&q=80",
    "farmer": "https://images.unsplash.com/photo-1627475320102-d73fcb4eb427?auto=format&fit=crop&w=1200&q=75",
    "fields": "https://images.unsplash.com/photo-1505590309800-8b20b8ba273b?auto=format&fit=crop&w=1200&q=75",
}

# Approximate district-headquarter coordinates, used only to fetch broad
# district-level weather context. They are not field-level measurements.
DISTRICTS = {
    "Adilabad": (19.664, 78.532),
    "Bhadradri Kothagudem": (17.556, 80.619),
    "Hanumakonda": (18.000, 79.580),
    "Hyderabad": (17.385, 78.487),
    "Jangaon": (17.722, 79.152),
    "Jayashankar Bhupalpally": (18.435, 79.110),
    "Jagtial": (18.794, 78.917),
    "Jogulamba Gadwal": (16.235, 77.803),
    "Kamareddy": (18.321, 78.335),
    "Karimnagar": (18.438, 79.128),
    "Khammam": (17.247, 80.151),
    "Komaram Bheem Asifabad": (19.362, 79.287),
    "Mahabubabad": (17.597, 80.003),
    "Mahabubnagar": (16.737, 78.009),
    "Mancherial": (18.870, 79.444),
    "Medak": (18.045, 78.261),
    "Medchal-Malkajgiri": (17.606, 78.485),
    "Mulugu": (18.191, 79.942),
    "Nagarkurnool": (16.483, 78.324),
    "Nalgonda": (17.057, 79.268),
    "Narayanpet": (16.744, 77.496),
    "Nirmal": (19.097, 78.344),
    "Nizamabad": (18.672, 78.094),
    "Peddapalli": (18.614, 79.379),
    "Rajanna Sircilla": (18.386, 78.802),
    "Rangareddy": (17.320, 78.128),
    "Sangareddy": (17.619, 78.082),
    "Siddipet": (18.101, 78.852),
    "Suryapet": (17.140, 79.623),
    "Vikarabad": (17.336, 77.905),
    "Wanaparthy": (16.362, 78.063),
    "Warangal": (17.968, 79.594),
    "Yadadri Bhuvanagiri": (17.515, 78.886),
}

I18N = {
    "en": {
        "tagline": "FARM PLANNING, GROUNDED IN YOUR FIELD",
        "title": "Plan your next crop with confidence",
        "subtitle": "Tell us about your land. AgriMarket AI combines your field conditions with current weather context to compare crop options.",
        "language": "Language", "login": "Sign in", "register": "Create account", "user_id": "User ID",
        "welcome_heading": "Welcome to AgriMarket AI", "welcome_text": "Plan your next crop with Telangana-focused weather context, crop guidance, fertilizer notes, and an editable farm budget.",
        "welcome_start": "Get started", "thanks_heading": "Thank you for using AgriMarket AI", "thanks_text": "Your session has ended. We hope the crop and budget planner was helpful.", "back_welcome": "Back to welcome page",
        "password": "Password", "name": "Your name", "login_help": "New to AgriMarket AI? Create an account to save your farm profile.",
        "account_created": "Account created. Sign in with your new User ID.", "bad_login": "That User ID or password did not match.",
        "user_exists": "That User ID is already in use.", "bad_user": "Use 3–32 letters, numbers, dots, dashes, or underscores for your User ID.",
        "bad_password": "Password must be 8–128 characters.", "logged_in": "Signed in as", "logout": "Sign out",
        "farm_inputs": "Your farm conditions", "district": "District (weather location)", "area": "Farm area (acres)",
        "soil": "Soil type", "month": "Planned sowing month", "water": "Water level / availability for this crop",
        "soil_test": "Soil test (optional)", "ph": "Soil pH", "nitrogen": "Available nitrogen (kg/ha)",
        "phosphorus": "Available phosphorus (kg/ha)", "potassium": "Available potassium (kg/ha)",
        "analyze": "Find suitable crops", "saving": "Analyzing field and checking district weather…",
        "recommendation": "Crop recommendations", "top_crop": "Best match for the conditions entered", "selected_crop": "Selected crop plan", "open_crop": "View this crop plan",
        "score": "Field suitability", "score_note": "An explainable screening score, not a yield guarantee or trained prediction model.",
        "why": "Why it matches", "risks": "Things to check", "weather": "Live weather context",
        "weather_failed": "Live weather is temporarily unavailable. Crop ranking still uses the field details you entered.",
        "weather_source": "7-day district forecast from Open-Meteo; a district-centre estimate, not a field sensor.",
        "weather_rain": "Forecast rainfall (7 days)", "weather_temp": "Average daytime high", "weather_risk": "Planning note",
        "budget": "Farm budget and return scenario", "budget_note": "Editable sample scenario in INR per acre. Replace sample figures with local quotes and your own farm records for a farm-specific estimate.",
        "expected_price": "Expected selling price (₹/quintal)", "expected_yield": "Expected yield (quintals/acre)",
        "costs": "Estimated input costs per acre", "seed_cost": "Seed", "land_cost": "Land preparation & labour",
        "fert_cost": "Fertilizer & soil inputs", "water_cost": "Irrigation / water", "crop_cost": "Crop protection",
        "other_cost": "Other costs", "total_investment": "Estimated total investment", "gross_return": "Estimated gross return",
        "profit_range": "Indicative net return range", "central_return": "At the entered yield and price",
        "profit_warning": "This is a scenario estimate. Actual yields, prices, costs, weather and losses can differ materially.",
        "fertilizer": "Fertilizer and soil plan", "npk": "Advisory nutrient rate", "fert_note": "Use your Soil Health Card / lab report to set the final dose. Do not apply micronutrients or pesticides unless a deficiency or pest is confirmed.",
        "crop_calendar": "Sowing window", "water_plan": "Water guidance", "harvest": "Typical crop duration",
        "sources": "Sources and method", "source_weather": "Open-Meteo live forecast", "source_crop": "ICAR crop advisories",
        "source_cotton": "CICR Telangana cotton package", "method_note": "Crop ranking is a transparent rule-based suitability screen using month, soil, water availability and (when available) near-term rainfall. It does not use a trained machine-learning model.",
        "sample_notice": "Prototype estimates only. Confirm the crop, variety and input dose with your local KVK / agriculture officer and current soil test before investing.",
        "no_plan": "Enter your farm details and select Find suitable crops to build a plan.", "soil_red": "Red soil", "soil_black": "Black cotton soil",
        "soil_loam": "Loamy soil", "soil_sandy": "Sandy soil", "soil_alluvial": "Alluvial soil",
        "water_low": "Rain-fed / limited", "water_mid": "Supplemental irrigation", "water_high": "Assured irrigation",
        "soil_unavailable": "Not tested", "month_warning": "The selected month is outside the main sowing window in the reference crop calendar.",
        "weather_caution": "Check actual field moisture before sowing; a district forecast cannot confirm rainfall in your plot.",
        "water_caution": "This crop generally needs more reliable water than the availability you selected.",
        "profile_saved": "Farm profile saved for this account.", "save_profile": "Save farm profile", "profile": "Farm profile",
        "no_weather": "No forecast returned for this district.", "score_limited": "Limited match", "score_good": "Good match",
        "score_strong": "Strong match", "range_low": "Lower scenario", "range_high": "Upper scenario",
        "crop_rice": "Paddy / rice", "crop_maize": "Maize", "crop_cotton": "Cotton", "crop_pigeon": "Red gram / pigeon pea",
        "crop_soy": "Soybean", "crop_groundnut": "Groundnut", "crop_chickpea": "Bengal gram / chickpea",
        "sow_month_help": "Select the month you plan to sow, not the harvest month.",
        "price_help": "Use the official mandi quote shown when available, or enter a current local buyer quote.",
        "price_assumption": "Sample price, yield and cost values are illustrative only, not current local quotes or a yield forecast. Replace them with verified local figures.",
        "forecast_dry": "The near-term forecast is dry for rain-fed sowing. Recheck the forecast and field moisture before sowing.",
        "district_location": "Location: district-centre estimate.", "days": "days", "other_options": "Other crop options",
        "local_account_note": "Local prototype account · password stored as a salted PBKDF2 hash on this computer.",
        "market_data": "Live mandi data", "market_setup": "For current prices, add a data.gov.in API key in .streamlit/secrets.toml. Until then, enter a current local quote.",
        "latest_market": "Latest modal price", "history_rain": "Historical rain for sowing month", "history_note": "10-year median rainfall for this calendar month (district-level reanalysis; not a forecast).", "market_basis": "District median of reported modal prices",
        "market_missing": "No recent mandi quote found for this crop in the selected district. Enter a local buyer/mandi quote below.",
        "market_error": "Live mandi prices could not be loaded. You can still enter a local quote.", "stale_price": "The latest available mandi quote is over 7 days old; confirm today’s rate locally.",
        "profit_inputs_needed": "Enter a sale price, expected yield, and per-acre costs to see the return scenario.",
        "yield_help": "This is not fetched from the internet or predicted by a trained AI model. Use your farm history or a local agriculture adviser.",
        "welcome_heading": "Welcome to AgriMarket AI",
        "welcome_text": "Plan your next crop with Telangana weather context, crop guidance, fertilizer notes, and an editable farm budget.",
        "welcome_start": "Get started",
        "thanks_heading": "Thank you for using AgriMarket AI",
        "thanks_text": "Your session has ended. We hope the crop and budget planner was helpful.",
        "back_welcome": "Back to welcome page",
        "profit_inputs_needed": "Enter a sale price, expected yield, and per-acre costs to see the return scenario.",
        "yield_help": "This is not fetched from the internet or predicted by a trained AI model. Use your farm history or a local agriculture adviser.",
        "api_enabled": "AGMARKNET mandi price service enabled",
        "get_api_key": "Get a data.gov.in API key",
        "photography_note": "Farm photography via Unsplash. Images need an internet connection.",
        "telangana": "Telangana",
        "weather_service": "Weather service",
        "soil_test_entered": "Soil test entered",
        "source_history_note": "Historical reanalysis used for monthly rainfall context.",
        "source_market_note": "Latest reported modal prices when an API key is configured.",
        "source_crop_note": "Telangana crop calendar and crop advisories.",
        "source_cotton_note": "Telangana cotton package of practices.",
        "source_soil_note": "SoilGrids REST API is currently unavailable, so farmers enter soil values in this version.",
        "source_market_label": "Government of India AGMARKNET mandi price dataset",
        "source_weather_note": "7-day district-centre forecast estimate.",
        "month_names": ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"],
    },
    "hi": {
        "tagline": "आपके खेत की जानकारी पर आधारित खेती की योजना",
        "title": "अगली फसल की योजना सोच-समझकर बनाएं",
        "subtitle": "अपने खेत की जानकारी दें। AgriMarket AI खेत की स्थितियों और मौजूदा मौसम की जानकारी से फसलों की तुलना करता है।",
        "language": "भाषा", "login": "लॉग इन", "register": "खाता बनाएं", "user_id": "यूज़र आईडी",
        "password": "पासवर्ड", "name": "आपका नाम", "login_help": "नए किसान हैं? खेत की जानकारी सहेजने के लिए खाता बनाएं।",
        "account_created": "खाता बन गया। नई यूज़र आईडी से लॉग इन करें।", "bad_login": "यूज़र आईडी या पासवर्ड सही नहीं है।",
        "user_exists": "यह यूज़र आईडी पहले से मौजूद है।", "bad_user": "यूज़र आईडी में 3–32 अक्षर, अंक, डॉट, डैश या अंडरस्कोर रखें।",
        "bad_password": "पासवर्ड 8–128 अक्षरों का होना चाहिए।", "logged_in": "लॉग इन हैं:", "logout": "लॉग आउट",
        "farm_inputs": "आपके खेत की जानकारी", "district": "ज़िला (मौसम स्थान)", "area": "खेत का क्षेत्रफल (एकड़)",
        "soil": "मिट्टी का प्रकार", "month": "बुवाई का महीना", "water": "इस फसल के लिए पानी का स्तर / उपलब्धता",
        "soil_test": "मिट्टी की जांच (वैकल्पिक)", "ph": "मिट्टी का pH", "nitrogen": "उपलब्ध नाइट्रोजन (kg/ha)",
        "phosphorus": "उपलब्ध फॉस्फोरस (kg/ha)", "potassium": "उपलब्ध पोटाश (kg/ha)",
        "analyze": "उपयुक्त फसलें देखें", "saving": "खेत की जानकारी और ज़िले का मौसम देखा जा रहा है…",
        "recommendation": "फसल सुझाव", "top_crop": "दी गई जानकारी के लिए सबसे उपयुक्त", "selected_crop": "चुनी हुई फसल की योजना", "open_crop": "इस फसल की योजना देखें",
        "score": "खेत के अनुकूलता अंक", "score_note": "यह समझने योग्य शुरुआती अंक है; उपज की गारंटी या प्रशिक्षित AI मॉडल नहीं।",
        "why": "क्यों उपयुक्त है", "risks": "क्या जांचें", "weather": "मौसम की ताज़ा जानकारी",
        "weather_failed": "अभी मौसम की जानकारी उपलब्ध नहीं है। फसल क्रम आपके खेत की जानकारी पर आधारित रहेगा।",
        "weather_source": "Open-Meteo से 7 दिन का ज़िला पूर्वानुमान; यह खेत के सेंसर का माप नहीं है।",
        "weather_rain": "अगले 7 दिन की वर्षा", "weather_temp": "औसत अधिकतम तापमान", "weather_risk": "योजना संबंधी सलाह",
        "budget": "लागत और आमदनी का अनुमान", "budget_note": "बदलने योग्य योजना अनुमान · रुपये · प्रति एकड़, जब तक अलग न लिखा हो",
        "expected_price": "अपेक्षित बिक्री मूल्य (₹/क्विंटल)", "expected_yield": "अपेक्षित उपज (क्विंटल/एकड़)",
        "costs": "प्रति एकड़ अनुमानित लागत", "seed_cost": "बीज", "land_cost": "खेत तैयारी और मजदूरी",
        "fert_cost": "खाद और मिट्टी के इनपुट", "water_cost": "सिंचाई / पानी", "crop_cost": "फसल सुरक्षा",
        "other_cost": "अन्य खर्च", "total_investment": "कुल निवेश का अनुमान", "gross_return": "कुल आमदनी का अनुमान",
        "profit_range": "संभावित शुद्ध आमदनी की सीमा", "central_return": "दिए गए उपज और मूल्य पर",
        "profit_warning": "यह केवल परिस्थिति-आधारित अनुमान है। असली उपज, भाव, खर्च, मौसम और नुकसान अलग हो सकते हैं।",
        "fertilizer": "खाद और मिट्टी की योजना", "npk": "सलाहकार पोषक तत्व मात्रा", "fert_note": "अंतिम मात्रा Soil Health Card / प्रयोगशाला जांच के अनुसार रखें। कमी या कीट की पुष्टि के बिना सूक्ष्म पोषक या कीटनाशक न डालें।",
        "crop_calendar": "बुवाई का समय", "water_plan": "पानी की सलाह", "harvest": "फसल की सामान्य अवधि",
        "sources": "स्रोत और तरीका", "source_weather": "Open-Meteo मौसम पूर्वानुमान", "source_crop": "ICAR फसल सलाह",
        "source_cotton": "CICR तेलंगाना कपास पैकेज", "method_note": "फसल क्रम महीने, मिट्टी, पानी और उपलब्ध होने पर निकट अवधि की वर्षा पर आधारित स्पष्ट नियमों से बनता है। इसमें प्रशिक्षित मशीन-लर्निंग मॉडल नहीं है।",
        "sample_notice": "प्रोटोटाइप अनुमान। निवेश से पहले स्थानीय KVK / कृषि अधिकारी और मिट्टी जांच से फसल, किस्म व मात्रा की पुष्टि करें।",
        "no_plan": "खेत की जानकारी भरें और योजना देखने के लिए उपयुक्त फसलें देखें दबाएं।", "soil_red": "लाल मिट्टी", "soil_black": "काली कपास मिट्टी",
        "soil_loam": "दोमट मिट्टी", "soil_sandy": "रेतीली मिट्टी", "soil_alluvial": "जलोढ़ मिट्टी",
        "water_low": "वर्षा पर निर्भर / सीमित", "water_mid": "पूरक सिंचाई", "water_high": "निश्चित सिंचाई",
        "soil_unavailable": "जांच नहीं हुई", "month_warning": "चुना महीना संदर्भ फसल कैलेंडर के मुख्य बुवाई समय से बाहर है।",
        "weather_caution": "बुवाई से पहले खेत की नमी जांचें; ज़िले का पूर्वानुमान आपके खेत की वर्षा की पुष्टि नहीं करता।",
        "water_caution": "इस फसल को आपके चुने पानी से अधिक भरोसेमंद सिंचाई की जरूरत हो सकती है।",
        "profile_saved": "खेत की जानकारी खाते में सहेजी गई।", "save_profile": "खेत की जानकारी सहेजें", "profile": "खेत की जानकारी",
        "no_weather": "इस ज़िले का पूर्वानुमान नहीं मिला।", "score_limited": "सीमित मेल", "score_good": "अच्छा मेल",
        "score_strong": "बेहतर मेल", "range_low": "कम अनुमान", "range_high": "अधिक अनुमान",
        "crop_rice": "धान", "crop_maize": "मक्का", "crop_cotton": "कपास", "crop_pigeon": "अरहर / तुअर",
        "crop_soy": "सोयाबीन", "crop_groundnut": "मूंगफली", "crop_chickpea": "चना",
        "sow_month_help": "बुवाई का महीना चुनें, कटाई का महीना नहीं।",
        "price_help": "दिए मूल्य को स्थानीय खरीदार/मंडी के मौजूदा भाव से बदलें।",
        "price_assumption": "मूल्य और उपज के डिफ़ॉल्ट उदाहरण हैं; ये लाइव भाव या AI उपज पूर्वानुमान नहीं हैं।",
        "forecast_dry": "वर्षा आधारित बुवाई के लिए निकट अवधि का पूर्वानुमान सूखा है। बुवाई से पहले मौसम और खेत की नमी फिर जांचें।",
        "district_location": "स्थान: ज़िला मुख्यालय का अनुमान।", "days": "दिन", "other_options": "अन्य फसल विकल्प",
        "local_account_note": "स्थानीय प्रोटोटाइप खाता · पासवर्ड इस कंप्यूटर पर salted PBKDF2 hash के रूप में सहेजा जाता है।",
        "market_data": "मंडी का ताज़ा डेटा", "market_setup": "मौजूदा भाव के लिए .streamlit/secrets.toml में मुफ्त data.gov.in API key जोड़ें। इसके बिना मूल्य फ़ील्ड बदलने योग्य योजना अनुमान है।",
        "latest_market": "नवीनतम मंडी भाव", "history_rain": "बुवाई महीने की पिछली वर्षा", "history_note": "इस महीने की 10-वर्षीय मध्य वर्षा (ज़िला स्तर का पुनर्विश्लेषण; पूर्वानुमान नहीं)।", "market_basis": "रिपोर्ट किए गए मंडी भावों का ज़िला मध्यक",
        "market_missing": "इस ज़िले में इस फसल का हाल का मंडी भाव नहीं मिला। नीचे स्थानीय खरीदार/मंडी का भाव भरें।",
        "market_error": "मंडी भाव नहीं मिल पाए। आप स्थानीय भाव भर सकते हैं।", "stale_price": "मंडी का नवीनतम भाव 7 दिन से पुराना है; आज का भाव स्थानीय स्तर पर जांचें।",
        "month_names": ["जनवरी", "फ़रवरी", "मार्च", "अप्रैल", "मई", "जून", "जुलाई", "अगस्त", "सितंबर", "अक्टूबर", "नवंबर", "दिसंबर"],
    },
    "te": {
        "tagline": "మీ పొలం పరిస్థితుల ఆధారంగా సాగు ప్రణాళిక",
        "title": "తదుపరి పంటను నమ్మకంగా ప్లాన్ చేయండి",
        "subtitle": "మీ భూమి వివరాలు ఇవ్వండి. AgriMarket AI పొలం పరిస్థితులు, తాజా వాతావరణ సమాచారంతో పంటలను పోలుస్తుంది.",
        "language": "భాష", "login": "లాగిన్", "register": "ఖాతా సృష్టించండి", "user_id": "యూజర్ ఐడి",
        "password": "పాస్‌వర్డ్", "name": "మీ పేరు", "login_help": "AgriMarket AI కొత్తదా? మీ పొలం వివరాలు సేవ్ చేయడానికి ఖాతా సృష్టించండి.",
        "account_created": "ఖాతా సృష్టించబడింది. కొత్త యూజర్ ఐడితో లాగిన్ అవ్వండి.", "bad_login": "యూజర్ ఐడి లేదా పాస్‌వర్డ్ సరిపోలలేదు.",
        "user_exists": "ఈ యూజర్ ఐడి ఇప్పటికే వాడుకలో ఉంది.", "bad_user": "యూజర్ ఐడి 3–32 అక్షరాలు, సంఖ్యలు, డాట్, డాష్ లేదా అండర్‌స్కోర్‌తో ఉండాలి.",
        "bad_password": "పాస్‌వర్డ్ 8–128 అక్షరాలు ఉండాలి.", "logged_in": "లాగిన్ అయ్యారు:", "logout": "లాగ్ అవుట్",
        "farm_inputs": "మీ పొలం పరిస్థితులు", "district": "జిల్లా (వాతావరణ స్థానం)", "area": "పొలం విస్తీర్ణం (ఎకరాలు)",
        "soil": "నేల రకం", "month": "విత్తే నెల", "water": "ఈ పంటకు నీటి స్థాయి / లభ్యత",
        "soil_test": "నేల పరీక్ష (ఐచ్ఛికం)", "ph": "నేల pH", "nitrogen": "అందుబాటులో ఉన్న నత్రజని (kg/ha)",
        "phosphorus": "అందుబాటులో ఉన్న భాస్వరం (kg/ha)", "potassium": "అందుబాటులో ఉన్న పొటాష్ (kg/ha)",
        "analyze": "అనుకూల పంటలను చూడండి", "saving": "పొలం వివరాలు, జిల్లా వాతావరణం పరిశీలిస్తున్నాం…",
        "recommendation": "పంట సూచనలు", "top_crop": "ఇచ్చిన వివరాలకు అత్యంత అనుకూలమైనది", "selected_crop": "ఎంచుకున్న పంట ప్రణాళిక", "open_crop": "ఈ పంట ప్రణాళిక చూడండి",
        "score": "పొలానికి అనుకూలత", "score_note": "ఇది వివరించగలిగే ప్రాథమిక స్కోరు మాత్రమే; దిగుబడి హామీ లేదా శిక్షణ పొందిన AI మోడల్ కాదు.",
        "why": "ఎందుకు సరిపోతుంది", "risks": "తనిఖీ చేయాల్సినవి", "weather": "తాజా వాతావరణ సమాచారం",
        "weather_failed": "ప్రస్తుతం వాతావరణ సమాచారం అందుబాటులో లేదు. పంట క్రమం మీరు ఇచ్చిన పొలం వివరాలపై ఆధారపడి ఉంటుంది.",
        "weather_source": "Open-Meteo 7 రోజుల జిల్లా అంచనా; ఇది పొలంలో అమర్చిన సెన్సార్ కొలత కాదు.",
        "weather_rain": "తదుపరి 7 రోజుల వర్షం", "weather_temp": "సగటు గరిష్ఠ ఉష్ణోగ్రత", "weather_risk": "ప్రణాళిక సూచన",
        "budget": "పెట్టుబడి, ఆదాయ అంచనా", "budget_note": "మార్చుకోగల ప్రణాళిక అంచనాలు · రూపాయలు · పేర్కొనకపోతే ఎకరానికి",
        "expected_price": "అంచనా అమ్మకపు ధర (₹/క్వింటాల్)", "expected_yield": "అంచనా దిగుబడి (క్వింటాళ్లు/ఎకరం)",
        "costs": "ఎకరానికి అంచనా ఖర్చులు", "seed_cost": "విత్తనాలు", "land_cost": "భూమి తయారీ, కూలీ",
        "fert_cost": "ఎరువులు, నేల ఇన్‌పుట్లు", "water_cost": "నీటిపారుదల / నీరు", "crop_cost": "పంట రక్షణ",
        "other_cost": "ఇతర ఖర్చులు", "total_investment": "మొత్తం పెట్టుబడి అంచనా", "gross_return": "మొత్తం ఆదాయ అంచనా",
        "profit_range": "సంభావ్య నికర ఆదాయ పరిధి", "central_return": "మీరు ఇచ్చిన దిగుబడి, ధరతో",
        "profit_warning": "ఇది ఒక పరిస్థితి ఆధారిత అంచనా మాత్రమే. వాస్తవ దిగుబడి, ధర, ఖర్చు, వాతావరణం, నష్టాలు మారవచ్చు.",
        "fertilizer": "ఎరువులు, నేల ప్రణాళిక", "npk": "సూచించిన పోషక మోతాదు", "fert_note": "చివరి మోతాదును Soil Health Card / ప్రయోగశాల పరీక్ష ఆధారంగా నిర్ణయించండి. లోపం లేదా పురుగు నిర్ధారణ లేకుండా సూక్ష్మపోషకాలు లేదా పురుగుమందులు వాడకండి.",
        "crop_calendar": "విత్తే సమయం", "water_plan": "నీటి సూచన", "harvest": "సాధారణ పంట కాలం",
        "sources": "మూలాలు, విధానం", "source_weather": "Open-Meteo ప్రత్యక్ష వాతావరణం", "source_crop": "ICAR పంట సూచనలు",
        "source_cotton": "CICR తెలంగాణ పత్తి ప్యాకేజ్", "method_note": "పంట క్రమం నెల, నేల, నీటి లభ్యత, అందుబాటులో ఉంటే సమీప వర్షపాతంపై ఆధారమైన స్పష్టమైన నియమాలతో రూపొందుతుంది. శిక్షణ పొందిన మెషిన్ లెర్నింగ్ మోడల్ ఉపయోగించదు.",
        "sample_notice": "ప్రోటోటైప్ అంచనాలు మాత్రమే. పెట్టుబడికి ముందు స్థానిక KVK / వ్యవసాయ అధికారి, తాజా నేల పరీక్షతో పంట, రకం, మోతాదు నిర్ధారించండి.",
        "no_plan": "పొలం వివరాలు నమోదు చేసి, పంట ప్రణాళిక కోసం అనుకూల పంటలను చూడండి ఎంచుకోండి.", "soil_red": "ఎర్ర నేల", "soil_black": "నల్ల రేగడి నేల",
        "soil_loam": "లోమీ నేల", "soil_sandy": "ఇసుక నేల", "soil_alluvial": "ఒండ్రు నేల",
        "water_low": "వర్షాధారం / పరిమితం", "water_mid": "అదనపు నీటిపారుదల", "water_high": "నిర్ధారిత నీటిపారుదల",
        "soil_unavailable": "పరీక్షించలేదు", "month_warning": "ఎంచుకున్న నెల సూచన క్యాలెండర్‌లోని ప్రధాన విత్తే సమయం వెలుపల ఉంది.",
        "weather_caution": "విత్తే ముందు పొలంలోని తేమను తనిఖీ చేయండి; జిల్లా అంచనా మీ పొలంలో వర్షాన్ని నిర్ధారించదు.",
        "water_caution": "ఈ పంటకు మీరు ఎంచుకున్న దానికంటే స్థిరమైన నీటి వనరు అవసరం కావచ్చు.",
        "profile_saved": "పొలం వివరాలు ఈ ఖాతాలో సేవ్ అయ్యాయి.", "save_profile": "పొలం వివరాలు సేవ్ చేయండి", "profile": "పొలం ప్రొఫైల్",
        "no_weather": "ఈ జిల్లాకు వాతావరణ అంచనా రాలేదు.", "score_limited": "పరిమిత అనుకూలత", "score_good": "మంచి అనుకూలత",
        "score_strong": "బలమైన అనుకూలత", "range_low": "తక్కువ అంచనా", "range_high": "ఎక్కువ అంచనా",
        "crop_rice": "వరి", "crop_maize": "మొక్కజొన్న", "crop_cotton": "పత్తి", "crop_pigeon": "కంది",
        "crop_soy": "సోయాబీన్", "crop_groundnut": "వేరుశెనగ", "crop_chickpea": "శనగ",
        "sow_month_help": "కోత నెలను కాదు, విత్తే నెలను ఎంచుకోండి.",
        "price_help": "డిఫాల్ట్ అంచనాను స్థానిక కొనుగోలుదారు/మార్కెట్ ప్రస్తుత ధరతో మార్చండి.",
        "price_assumption": "డిఫాల్ట్ ధర, దిగుబడి ఉదాహరణలు మాత్రమే; ప్రత్యక్ష ధరలు లేదా AI దిగుబడి అంచనా కాదు.",
        "forecast_dry": "వర్షాధార విత్తనానికి సమీప వాతావరణం పొడిగా ఉంది. విత్తే ముందు వాతావరణం, పొలం తేమ మళ్లీ చూడండి.",
        "district_location": "స్థానం: జిల్లా కేంద్రం ఆధారిత అంచనా.", "days": "రోజులు", "other_options": "ఇతర పంట ఎంపికలు",
        "local_account_note": "స్థానిక ప్రోటోటైప్ ఖాతా · పాస్‌వర్డ్ ఈ కంప్యూటర్‌లో salted PBKDF2 hash గా నిల్వ ఉంటుంది.",
        "market_data": "ప్రత్యక్ష మార్కెట్ డేటా", "market_setup": "ప్రస్తుత ధరల కోసం .streamlit/secrets.toml లో ఉచిత data.gov.in API కీ జోడించండి. లేకపోతే ధర ఫీల్డ్ మార్చగల ప్రణాళిక అంచనా.",
        "latest_market": "తాజా మోడల్ ధర", "history_rain": "విత్తే నెల గత వర్షపాతం", "history_note": "ఈ నెలకు 10 సంవత్సరాల మధ్యస్థ వర్షపాతం (జిల్లా స్థాయి రీఅనాలిసిస్; వాతావరణ అంచనా కాదు).", "market_basis": "నివేదించిన మార్కెట్ మోడల్ ధరల జిల్లా మధ్యస్థం",
        "market_missing": "ఎంచుకున్న జిల్లాలో ఈ పంటకు తాజా మార్కెట్ ధర దొరకలేదు. కింద స్థానిక కొనుగోలుదారు/మార్కెట్ ధర నమోదు చేయండి.",
        "market_error": "ప్రత్యక్ష మార్కెట్ ధరలు లోడ్ కాలేదు. స్థానిక ధరను నమోదు చేయవచ్చు.", "stale_price": "తాజా మార్కెట్ ధర 7 రోజుల కంటే పాతది; ఈరోజు ధరను స్థానికంగా నిర్ధారించండి.",
        "welcome_heading": "AgriMarket AI \u0c15\u0c3f \u0c38\u0c4d\u0c35\u0c3e\u0c17\u0c24\u0c02",
        "welcome_text": "\u0c24\u0c46\u0c32\u0c02\u0c17\u0c3e\u0c23 \u0c35\u0c3e\u0c24\u0c3e\u0c35\u0c30\u0c23 \u0c38\u0c2e\u0c3e\u0c1a\u0c3e\u0c30\u0c02, \u0c2a\u0c02\u0c1f \u0c2e\u0c3e\u0c30\u0c4d\u0c17\u0c26\u0c30\u0c4d\u0c36\u0c15\u0c02, \u0c0e\u0c30\u0c41\u0c35\u0c41\u0c32 \u0c38\u0c42\u0c1a\u0c28\u0c32\u0c41, \u0c2e\u0c3e\u0c30\u0c4d\u0c1a\u0c17\u0c32 \u0c35\u0c4d\u0c2f\u0c35\u0c38\u0c3e\u0c2f \u0c2c\u0c21\u0c4d\u0c1c\u0c46\u0c1f\u0c4d\u200c\u0c24\u0c4b \u0c2e\u0c40 \u0c24\u0c26\u0c41\u0c2a\u0c30\u0c3f \u0c2a\u0c02\u0c1f\u0c28\u0c41 \u0c2a\u0c4d\u0c30\u0c23\u0c3e\u0c33\u0c3f\u0c15 \u0c1a\u0c47\u0c2f\u0c02\u0c21\u0c3f.",
        "welcome_start": "\u0c2a\u0c4d\u0c30\u0c3e\u0c30\u0c02\u0c2d\u0c3f\u0c02\u0c1a\u0c02\u0c21\u0c3f",
        "thanks_heading": "AgriMarket AI \u0c09\u0c2a\u0c2f\u0c4b\u0c17\u0c3f\u0c02\u0c1a\u0c3f\u0c28\u0c02\u0c26\u0c41\u0c15\u0c41 \u0c27\u0c28\u0c4d\u0c2f\u0c35\u0c3e\u0c26\u0c3e\u0c32\u0c41",
        "thanks_text": "\u0c2e\u0c40 \u0c38\u0c46\u0c37\u0c28\u0c4d \u0c2e\u0c41\u0c17\u0c3f\u0c38\u0c3f\u0c02\u0c26\u0c3f. \u0c2a\u0c02\u0c1f \u0c2e\u0c30\u0c3f\u0c2f\u0c41 \u0c2c\u0c21\u0c4d\u0c1c\u0c46\u0c1f\u0c4d \u0c2a\u0c4d\u0c30\u0c23\u0c3e\u0c33\u0c3f\u0c15 \u0c2e\u0c40\u0c15\u0c41 \u0c09\u0c2a\u0c2f\u0c4b\u0c17\u0c2a\u0c21\u0c3f\u0c02\u0c26\u0c28\u0c3f \u0c06\u0c36\u0c3f\u0c38\u0c4d\u0c24\u0c41\u0c28\u0c4d\u0c28\u0c3e\u0c2e\u0c41.",
        "back_welcome": "\u0c38\u0c4d\u0c35\u0c3e\u0c17\u0c24 \u0c2a\u0c47\u0c1c\u0c40\u0c15\u0c3f \u0c24\u0c3f\u0c30\u0c3f\u0c17\u0c3f \u0c35\u0c46\u0c33\u0c4d\u0c32\u0c02\u0c21\u0c3f",
        "profit_inputs_needed": "\u0c06\u0c26\u0c3e\u0c2f \u0c05\u0c02\u0c1a\u0c28\u0c3e\u0c28\u0c41 \u0c1a\u0c42\u0c21\u0c1f\u0c3e\u0c28\u0c3f\u0c15\u0c3f \u0c05\u0c2e\u0c4d\u0c2e\u0c15\u0c2a\u0c41 \u0c27\u0c30, \u0c06\u0c36\u0c3f\u0c02\u0c1a\u0c3f\u0c28 \u0c26\u0c3f\u0c17\u0c41\u0c2c\u0c21\u0c3f, \u0c0e\u0c15\u0c30\u0c3e\u0c15\u0c41 \u0c16\u0c30\u0c4d\u0c1a\u0c41\u0c32\u0c28\u0c41 \u0c28\u0c2e\u0c4b\u0c26\u0c41 \u0c1a\u0c47\u0c2f\u0c02\u0c21\u0c3f.",
        "yield_help": "\u0c08 \u0c38\u0c2e\u0c3e\u0c1a\u0c3e\u0c30\u0c02 \u0c07\u0c02\u0c1f\u0c30\u0c4d\u0c28\u0c46\u0c1f\u0c4d \u0c28\u0c41\u0c02\u0c1a\u0c3f \u0c2a\u0c4a\u0c02\u0c26\u0c2c\u0c21\u0c26\u0c41; \u0c36\u0c3f\u0c15\u0c4d\u0c37\u0c23 \u0c2a\u0c4a\u0c02\u0c26\u0c3f\u0c28 AI \u0c2e\u0c4b\u0c21\u0c32\u0c4d \u0c15\u0c42\u0c21\u0c3e \u0c05\u0c02\u0c1a\u0c28\u0c3e \u0c35\u0c47\u0c2f\u0c26\u0c41. \u0c2e\u0c40 \u0c2a\u0c4a\u0c32\u0c02 \u0c30\u0c3f\u0c15\u0c3e\u0c30\u0c4d\u0c21\u0c41\u0c32\u0c41 \u0c32\u0c47\u0c26\u0c3e \u0c38\u0c4d\u0c25\u0c3e\u0c28\u0c3f\u0c15 \u0c35\u0c4d\u0c2f\u0c35\u0c38\u0c3e\u0c2f \u0c38\u0c32\u0c39\u0c3e\u0c26\u0c3e\u0c30\u0c41\u0c28\u0c3f \u0c38\u0c02\u0c2a\u0c4d\u0c30\u0c26\u0c3f\u0c02\u0c1a\u0c02\u0c21\u0c3f.",
        "api_enabled": "AGMARKNET \u0c2e\u0c3e\u0c30\u0c4d\u0c15\u0c46\u0c1f\u0c4d \u0c27\u0c30\u0c32 \u0c38\u0c47\u0c35 \u0c2a\u0c4d\u0c30\u0c3e\u0c30\u0c02\u0c2d\u0c3f\u0c02\u0c1a\u0c2c\u0c21\u0c3f\u0c02\u0c26\u0c3f",
        "get_api_key": "data.gov.in API \u0c15\u0c40 \u0c2a\u0c4a\u0c02\u0c26\u0c02\u0c21\u0c3f",
        "photography_note": "\u0c2a\u0c4a\u0c32\u0c3e\u0c32 \u0c1a\u0c3f\u0c24\u0c4d\u0c30\u0c3e\u0c32\u0c41 Unsplash \u0c28\u0c41\u0c02\u0c1a\u0c3f. \u0c1a\u0c3f\u0c24\u0c4d\u0c30\u0c3e\u0c32\u0c41 \u0c1a\u0c42\u0c2a\u0c3f\u0c02\u0c1a\u0c21\u0c3e\u0c28\u0c3f\u0c15\u0c3f \u0c07\u0c02\u0c1f\u0c30\u0c4d\u0c28\u0c46\u0c1f\u0c4d \u0c05\u0c35\u0c38\u0c30\u0c02.",
        "telangana": "\u0c24\u0c46\u0c32\u0c02\u0c17\u0c3e\u0c23",
        "weather_service": "\u0c35\u0c3e\u0c24\u0c3e\u0c35\u0c30\u0c23 \u0c38\u0c47\u0c35",
        "soil_test_entered": "\u0c2e\u0c1f\u0c4d\u0c1f\u0c3f \u0c2a\u0c30\u0c40\u0c15\u0c4d\u0c37 \u0c35\u0c3f\u0c35\u0c30\u0c3e\u0c32\u0c41 \u0c28\u0c2e\u0c4b\u0c26\u0c41 \u0c1a\u0c47\u0c36\u0c3e\u0c30\u0c41",
        "source_history_note": "\u0c17\u0c24 \u0c35\u0c3e\u0c24\u0c3e\u0c35\u0c30\u0c23 \u0c2a\u0c41\u0c28\u0c30\u0c4d\u0c35\u0c3f\u0c36\u0c4d\u0c32\u0c47\u0c37\u0c23 \u0c06\u0c27\u0c3e\u0c30\u0c02\u0c17\u0c3e \u0c35\u0c3f\u0c24\u0c4d\u0c24\u0c47 \u0c28\u0c46\u0c32 \u0c35\u0c30\u0c4d\u0c37\u0c2a\u0c3e\u0c24\u0c02 \u0c38\u0c2e\u0c3e\u0c1a\u0c3e\u0c30\u0c02.",
        "source_market_note": "API \u0c15\u0c40 \u0c09\u0c28\u0c4d\u0c28\u0c2a\u0c4d\u0c2a\u0c41\u0c21\u0c41 \u0c05\u0c02\u0c26\u0c41\u0c2c\u0c3e\u0c1f\u0c41\u0c32\u0c4b \u0c09\u0c02\u0c21\u0c47 \u0c24\u0c3e\u0c1c\u0c3e \u0c28\u0c3f\u0c35\u0c47\u0c26\u0c3f\u0c24 \u0c2e\u0c3e\u0c30\u0c4d\u0c15\u0c46\u0c1f\u0c4d \u0c27\u0c30\u0c32\u0c41.",
        "source_crop_note": "\u0c24\u0c46\u0c32\u0c02\u0c17\u0c3e\u0c23 \u0c2a\u0c02\u0c1f \u0c15\u0c3e\u0c32\u0c2a\u0c1f\u0c4d\u0c1f\u0c3f\u0c15 \u0c2e\u0c30\u0c3f\u0c2f\u0c41 \u0c2a\u0c02\u0c1f \u0c38\u0c32\u0c39\u0c3e\u0c32\u0c41.",
        "source_cotton_note": "\u0c24\u0c46\u0c32\u0c02\u0c17\u0c3e\u0c23 \u0c2a\u0c24\u0c4d\u0c24\u0c3f \u0c38\u0c3e\u0c17\u0c41 \u0c2a\u0c26\u0c4d\u0c27\u0c24\u0c41\u0c32\u0c41.",
        "source_soil_note": "SoilGrids REST API \u0c2a\u0c4d\u0c30\u0c38\u0c4d\u0c24\u0c41\u0c24\u0c02 \u0c05\u0c02\u0c26\u0c41\u0c2c\u0c3e\u0c1f\u0c41\u0c32\u0c4b \u0c32\u0c47\u0c26\u0c41; \u0c08 \u0c38\u0c02\u0c1a\u0c3f\u0c15\u0c32\u0c4b \u0c2e\u0c1f\u0c4d\u0c1f\u0c3f \u0c35\u0c3f\u0c35\u0c30\u0c3e\u0c32\u0c28\u0c41 \u0c30\u0c48\u0c24\u0c47 \u0c28\u0c2e\u0c4b\u0c26\u0c41 \u0c1a\u0c47\u0c38\u0c4d\u0c24\u0c3e\u0c30\u0c41.",
        "source_market_label": "\u0c2d\u0c3e\u0c30\u0c24 \u0c2a\u0c4d\u0c30\u0c2d\u0c41\u0c24\u0c4d\u0c35 AGMARKNET \u0c2e\u0c3e\u0c30\u0c4d\u0c15\u0c46\u0c1f\u0c4d \u0c27\u0c30\u0c32 \u0c21\u0c47\u0c1f\u0c3e",
        "source_weather_note": "7 \u0c30\u0c4b\u0c1c\u0c41\u0c32 \u0c1c\u0c3f\u0c32\u0c4d\u0c32\u0c3e \u0c15\u0c47\u0c02\u0c26\u0c4d\u0c30 \u0c35\u0c3e\u0c24\u0c3e\u0c35\u0c30\u0c23 \u0c05\u0c02\u0c1a\u0c28\u0c3e.",
        "month_names": ["జనవరి", "ఫిబ్రవరి", "మార్చి", "ఏప్రిల్", "మే", "జూన్", "జూలై", "ఆగస్టు", "సెప్టెంబర్", "అక్టోబర్", "నవంబర్", "డిసెంబర్"],
    },
}


def tr(key: str, lang: str | None = None) -> str:
    lang = lang or st.session_state.get("language", "en")
    return I18N.get(lang, I18N["en"]).get(key, I18N["en"].get(key, key))


def init_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DB_PATH, timeout=10) as db:
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("""CREATE TABLE IF NOT EXISTS users (
            user_id TEXT PRIMARY KEY, display_name TEXT NOT NULL,
            password_salt BLOB NOT NULL, password_hash BLOB NOT NULL,
            created_at TEXT NOT NULL
        )""")
        db.execute("""CREATE TABLE IF NOT EXISTS farm_profiles (
            user_id TEXT PRIMARY KEY REFERENCES users(user_id) ON DELETE CASCADE,
            district TEXT NOT NULL, area_acres REAL NOT NULL,
            soil TEXT NOT NULL, water TEXT NOT NULL, sow_month INTEGER NOT NULL,
            language TEXT NOT NULL
        )""")


def password_digest(password: str, salt: bytes) -> bytes:
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PASSWORD_ROUNDS)


def register_user(user_id: str, display_name: str, password: str) -> str | None:
    normalized = user_id.strip().casefold()
    if len(normalized) < 3 or len(normalized) > 32 or not all(ch.isalnum() or ch in "._-" for ch in normalized):
        return "bad_user"
    if not 8 <= len(password) <= 128:
        return "bad_password"
    salt = secrets.token_bytes(16)
    try:
        with sqlite3.connect(DB_PATH, timeout=10) as db:
            db.execute(
                "INSERT INTO users (user_id, display_name, password_salt, password_hash, created_at) VALUES (?, ?, ?, ?, ?)",
                (normalized, display_name.strip()[:80], salt, password_digest(password, salt), datetime.now().isoformat(timespec="seconds")),
            )
        return None
    except sqlite3.IntegrityError:
        return "user_exists"


def authenticate(user_id: str, password: str) -> tuple[str, str] | None:
    normalized = user_id.strip().casefold()
    with sqlite3.connect(DB_PATH, timeout=10) as db:
        row = db.execute("SELECT user_id, display_name, password_salt, password_hash FROM users WHERE user_id = ?", (normalized,)).fetchone()
    if row and hmac.compare_digest(password_digest(password, row[2]), row[3]):
        return row[0], row[1]
    return None


def load_profile(user_id: str) -> dict[str, object]:
    with sqlite3.connect(DB_PATH, timeout=10) as db:
        row = db.execute("SELECT district, area_acres, soil, water, sow_month, language FROM farm_profiles WHERE user_id = ?", (user_id,)).fetchone()
    if not row:
        return {}
    return dict(zip(("district", "area", "soil", "water", "month", "language"), row))


def save_profile(user_id: str, profile: dict[str, object]) -> None:
    with sqlite3.connect(DB_PATH, timeout=10) as db:
        db.execute(
            """INSERT INTO farm_profiles (user_id, district, area_acres, soil, water, sow_month, language)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(user_id) DO UPDATE SET district=excluded.district,
               area_acres=excluded.area_acres, soil=excluded.soil, water=excluded.water,
               sow_month=excluded.sow_month, language=excluded.language""",
            (user_id, profile["district"], profile["area"], profile["soil"], profile["water"], profile["month"], profile["language"]),
        )


@st.cache_data(ttl=1800, show_spinner=False)
def get_weather(latitude: float, longitude: float) -> dict[str, object] | None:
    """Fetch a small district-centre forecast from Open-Meteo (no API key)."""
    query = urlencode({
        "latitude": latitude,
        "longitude": longitude,
        "daily": "precipitation_sum,temperature_2m_max",
        "forecast_days": 7,
        "timezone": "Asia/Kolkata",
    })
    url = f"https://api.open-meteo.com/v1/forecast?{query}"
    request = Request(url, headers={"User-Agent": "FieldwiseFarmPlanner/1.0"})
    try:
        with urlopen(request, timeout=8) as response:
            payload = json.loads(response.read().decode("utf-8"))
        daily = payload.get("daily", {})
        rains = [value for value in daily.get("precipitation_sum", []) if isinstance(value, (int, float))]
        temps = [value for value in daily.get("temperature_2m_max", []) if isinstance(value, (int, float))]
        return {
            "rain_mm": round(sum(rains), 1) if rains else None,
            "high_c": round(sum(temps) / len(temps), 1) if temps else None,
            "dates": daily.get("time", []),
        }
    except (OSError, ValueError, KeyError, TimeoutError):
        return None


@st.cache_data(ttl=86400, show_spinner=False)
def get_monthly_rain_history(latitude: float, longitude: float) -> dict[int, list[float]] | None:
    """Return ten completed years of monthly precipitation totals by month."""
    last_year = date.today().year - 1
    query = urlencode({
        "latitude": latitude,
        "longitude": longitude,
        "start_date": f"{last_year - 9}-01-01",
        "end_date": f"{last_year}-12-31",
        "daily": "precipitation_sum",
        "timezone": "Asia/Kolkata",
    })
    request = Request(f"https://archive-api.open-meteo.com/v1/archive?{query}", headers={"User-Agent": "FieldwiseFarmPlanner/1.0"})
    try:
        with urlopen(request, timeout=12) as response:
            payload = json.loads(response.read().decode("utf-8"))
        dates = payload.get("daily", {}).get("time", [])
        rain = payload.get("daily", {}).get("precipitation_sum", [])
        by_month: dict[int, dict[int, float]] = {}
        for day_text, amount in zip(dates, rain):
            if amount is None:
                continue
            day = date.fromisoformat(day_text)
            by_month.setdefault(day.month, {}).setdefault(day.year, 0.0)
            by_month[day.month][day.year] += float(amount)
        return {month: list(year_totals.values()) for month, year_totals in by_month.items()}
    except (OSError, ValueError, KeyError, TimeoutError):
        return None


PRICE_RESOURCE_ID = "9ef84268-d588-465a-a308-a864a43d0070"
PRICE_COMMODITIES = {
    "rice": ("Paddy(Dhan)(Common)", "Paddy"),
    "maize": ("Maize",),
    "cotton": ("Cotton",),
    "pigeon": ("Arhar (Tur/Red Gram)", "Arhar (Tur)", "Red Gram"),
    "soy": ("Soyabean", "Soybean"),
    "groundnut": ("Groundnut",),
    "chickpea": ("Bengal Gram(Gram)", "Bengal Gram"),
}


def get_data_gov_api_key() -> str:
    key = os.environ.get("FIELDWISE_DATA_GOV_API_KEY", "").strip()
    if key:
        return key
    if not (ROOT / ".streamlit" / "secrets.toml").exists():
        return ""
    try:
        return str(st.secrets.get("DATA_GOV_IN_API_KEY", "")).strip()
    except (FileNotFoundError, KeyError, RuntimeError):
        return ""


@st.cache_data(ttl=1800, show_spinner=False)
def get_live_mandi_prices(district: str, api_key: str) -> dict[str, dict[str, object]] | None:
    """Fetch current district modal prices from the official OGD mandi feed."""
    if not api_key:
        return None
    params = {
        "api-key": api_key,
        "format": "json",
        "limit": 1000,
        "filters[state.keyword]": "Telangana",
        "filters[district]": district,
    }
    url = f"https://api.data.gov.in/resource/{PRICE_RESOURCE_ID}?{urlencode(params)}"
    request = Request(url, headers={"User-Agent": "FieldwiseFarmPlanner/1.0"})
    try:
        with urlopen(request, timeout=12) as response:
            payload = json.loads(response.read().decode("utf-8"))
        records = payload.get("records", [])
        result: dict[str, dict[str, object]] = {}
        for crop_id, aliases in PRICE_COMMODITIES.items():
            alias_keys = ["".join(ch for ch in alias.casefold() if ch.isalnum()) for alias in aliases]
            crop_rows = []
            for row in records:
                if str(row.get("district", "")).strip().casefold() != district.casefold():
                    continue
                commodity_key = "".join(ch for ch in str(row.get("commodity", "")).casefold() if ch.isalnum())
                if not any(alias in commodity_key or commodity_key in alias for alias in alias_keys):
                    continue
                price_text = str(row.get("modal_price", "")).replace(",", "")
                try:
                    modal_price = float(price_text)
                except ValueError:
                    continue
                date_text = str(row.get("arrival_date", ""))
                parsed_date = None
                for date_format in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d %b %Y"):
                    try:
                        parsed_date = datetime.strptime(date_text, date_format).date()
                        break
                    except ValueError:
                        pass
                if parsed_date:
                    crop_rows.append((parsed_date, modal_price, row))
            if not crop_rows:
                continue
            latest_date = max(item[0] for item in crop_rows)
            latest_rows = [item for item in crop_rows if item[0] == latest_date]
            prices = [item[1] for item in latest_rows]
            markets = sorted({str(item[2].get("market", "")) for item in latest_rows if item[2].get("market")})
            result[crop_id] = {
                "price": statistics.median(prices),
                "arrival_date": latest_date.isoformat(),
                "markets": markets,
                "market_count": len(latest_rows),
                "commodity": str(latest_rows[0][2].get("commodity", "")),
                "source": "data.gov.in / AGMARKNET",
            }
        return result
    except (OSError, ValueError, KeyError, TimeoutError):
        return {}


# Sowing windows and soil/water fit form the explainable prototype ranking.
CROPS = {
    "rice": {
        "label": "crop_rice", "months": {6, 7}, "soils": {"black", "loam", "alluvial"}, "water": {2},
        "duration": (120, 145),
        "fertilizer": "40–48 kg N, 20 kg P and 16 kg K per acre for Vanakalam (ICAR Telangana advisory, 2025). Split N; apply zinc only if deficiency is confirmed.",
        "calendar": "Nursery timing varies by variety: long duration May 20–June 20; medium/short duration from June 20. Direct seeding can start from late June.",
        "water_note": "Choose only with assured irrigation or a dependable canal/tank supply. Consider alternate wetting and drying where suitable.",
        "reason": "Best suited to heavier, moisture-retentive soils and assured irrigation.",
        "risk": "Confirm reliable irrigation, variety-specific nursery dates and field drainage before committing.",
    },
    "maize": {
        "label": "crop_maize", "months": {6, 7, 10, 11}, "soils": {"red", "black", "loam"}, "water": {0, 1, 2},
        "duration": (90, 120),
        "fertilizer": "ICAR Telangana Kharif guide: irrigated 150:65:65 kg N:P₂O₅:K₂O/ha + 25 kg zinc sulphate/ha; dryland 100:50:25 + 10 kg zinc sulphate/ha. Top-dress urea around 45 DAS per local advice.",
        "calendar": "Kharif sowing window is June 15–July 15; delayed monsoon sowing may extend to July-end. Other seasons need local confirmation.",
        "water_note": "Rainfed sowing should wait for adequate field moisture; the ICAR advisory uses 50–60 mm accumulated rainfall as a guide.",
        "reason": "A flexible cereal option for red, black or loamy soils; irrigation choice changes its nutrient plan.",
        "risk": "Check monsoon onset, drainage and fall-armyworm monitoring plans.",
    },
    "cotton": {
        "label": "crop_cotton", "months": {6, 7}, "soils": {"red", "black"}, "water": {0, 1, 2},
        "duration": (150, 180),
        "fertilizer": "CICR Telangana package: for hybrids, 120–150:60:60 kg N:P₂O₅:K₂O/ha; varieties 90:45:45. Base the final dose on the Soil Health Card. Apply N and K in splits as advised.",
        "calendar": "Target early sowing in June after sufficient rain; avoid delayed rainfed sowing after July 20 according to the ICAR Telangana advisory.",
        "water_note": "Use ridge/furrow on medium soils and broad-bed furrow on black soils to manage moisture and excess rain.",
        "reason": "Matches the main Telangana cotton season and is compatible with red or black soils.",
        "risk": "Cotton is input-intensive and price-sensitive. Check seed authenticity, pink bollworm history and local market access.",
    },
    "pigeon": {
        "label": "crop_pigeon", "months": {6, 7}, "soils": {"red", "black", "loam"}, "water": {0, 1},
        "duration": (155, 180),
        "fertilizer": "ICAR general pulse guidance: basal N:P₂O₅:K₂O around 25–30:40–50:30 kg/ha, plus soil-test-based sulphur where indicated. Use Rhizobium/PSB seed inoculation per local package.",
        "calendar": "Telangana advisory: sow June 15–July 15 after about 60 mm rain; spacing differs for red and black soils.",
        "water_note": "Deep-rooted and relatively drought-tolerant, but protect flowering/pod-fill during prolonged dry spells.",
        "reason": "A rainfed pulse option that can fit red and black soils when sowing rain arrives.",
        "risk": "Ensure drainage after heavy rain; confirm a wilt-tolerant variety for the district.",
    },
    "soy": {
        "label": "crop_soy", "months": {6, 7}, "soils": {"red", "black", "loam"}, "water": {0, 1},
        "duration": (90, 110),
        "fertilizer": "ICAR Telangana advisory: 50 kg DAP + 26 kg MOP per acre at sowing; top-dress 25–30 kg urea/acre at 30 DAS. Soil test and current university guidance take priority.",
        "calendar": "Sow June 15–early July. Broad-bed furrow or raised beds can help handle heavy rain and moisture stress.",
        "water_note": "Avoid waterlogging; conserve moisture and plan protective irrigation if a dry spell occurs.",
        "reason": "Fits the Telangana Kharif window and commonly suits red/black soils with drainage.",
        "risk": "Use a locally adapted, certified variety and confirm seed availability before purchase.",
    },
    "groundnut": {
        "label": "crop_groundnut", "months": {6, 7}, "soils": {"red", "loam", "sandy"}, "water": {0, 1, 2},
        "duration": (100, 125),
        "fertilizer": "ICAR advisory lists gypsum at pegging (500 kg/ha) and emphasizes seed treatment. Verify the cultivar, soil test and Telangana KVK package before applying; the dose is not inferred from soil type alone.",
        "calendar": "Usually a Kharif option; sow with dependable onset rain and a well-prepared, well-drained seedbed.",
        "water_note": "Needs moisture at establishment and pegging/pod development; avoid standing water.",
        "reason": "Light, well-drained red or sandy loams can suit groundnut when moisture is adequate.",
        "risk": "Seed cost is relatively high; confirm seed rate, gypsum need and groundnut market access locally.",
    },
    "chickpea": {
        "label": "crop_chickpea", "months": {10, 11}, "soils": {"black", "loam"}, "water": {0, 1},
        "duration": (100, 120),
        "fertilizer": "ICAR Bengal gram advisory: basal 20 kg N + 50 kg P₂O₅ + 40 kg sulphur/ha. Use a locally released wilt-resistant variety and soil-test guidance.",
        "calendar": "Rabi sowing window: October 15–November 15 in the ICAR advisory.",
        "water_note": "Generally suited to residual moisture; a light irrigation around 30–35 DAS may help if locally appropriate.",
        "reason": "A Rabi pulse option for heavier soils where residual moisture is available.",
        "risk": "Avoid waterlogging and check wilt history, residual moisture and harvest-market timing.",
    },
}

# Editable demo baselines so the budget panel is useful before a farmer has
# entered their own figures. These are illustrative planning values, not live
# market quotes or field-specific yield predictions.
BUDGET_DEFAULTS = {
    "rice": (2300, 27, (1800, 7000, 5200, 6500, 2200, 1800)),
    "maize": (2200, 24, (1800, 6500, 4300, 2500, 2400, 1600)),
    "cotton": (7200, 9.5, (2200, 8500, 5200, 1800, 3600, 2200)),
    "pigeon": (7800, 6, (1200, 5500, 3000, 900, 1800, 1300)),
    "soy": (4700, 9.5, (1800, 5500, 4200, 900, 2200, 1500)),
    "groundnut": (6500, 9.5, (4500, 7000, 4200, 2600, 2600, 1700)),
    "chickpea": (6000, 7, (2600, 5000, 3500, 900, 1700, 1500)),
}

# Human-readable agronomy notes are translated separately from widget labels;
# numeric rates remain in their source units in every language.
CROP_COPY = {
    "hi": {
        "rice": {
            "fertilizer": "ICAR तेलंगाना सलाह (2025): वानाकालम में प्रति एकड़ 40–48 kg N, 20 kg P और 16 kg K। N को भागों में दें; जिंक केवल कमी की पुष्टि होने पर दें।",
            "calendar": "किस्म के अनुसार नर्सरी समय: लंबी अवधि 20 मई–20 जून; मध्यम/कम अवधि 20 जून से। सीधी बुवाई जून के अंत से।",
            "water_note": "केवल भरोसेमंद सिंचाई या निश्चित नहर/टैंक पानी होने पर चुनें। उपयुक्त जगहों पर alternate wetting and drying अपनाएं।",
            "reason": "भारी, नमी रोकने वाली मिट्टी और निश्चित सिंचाई के लिए बेहतर मेल।",
            "risk": "बुवाई से पहले पानी, किस्म के अनुसार नर्सरी समय और खेत की जल निकासी की पुष्टि करें।",
        },
        "maize": {
            "fertilizer": "ICAR तेलंगाना खरीफ सलाह: सिंचित में 150:65:65 kg N:P₂O₅:K₂O/ha + 25 kg जिंक सल्फेट/ha; वर्षा आधारित में 100:50:25 + 10 kg जिंक सल्फेट/ha। यूरिया की टॉप ड्रेसिंग स्थानीय सलाह से करें।",
            "calendar": "खरीफ बुवाई 15 जून–15 जुलाई; मानसून देर से आए तो जुलाई अंत तक बढ़ सकती है। अन्य मौसम के लिए स्थानीय सलाह लें।",
            "water_note": "वर्षा आधारित बुवाई से पहले खेत में पर्याप्त नमी होनी चाहिए; ICAR 50–60 mm संचित वर्षा को मार्गदर्शक मानता है।",
            "reason": "लाल, काली या दोमट मिट्टी में उगने वाला विकल्प; पानी के अनुसार खाद योजना बदलती है।",
            "risk": "मानसून, जल निकासी और फॉल आर्मीवर्म निगरानी की योजना जांचें।",
        },
        "cotton": {
            "fertilizer": "CICR तेलंगाना पैकेज: हाइब्रिड के लिए 120–150:60:60 kg N:P₂O₅:K₂O/ha; किस्मों के लिए 90:45:45। Soil Health Card के अनुसार अंतिम मात्रा तय करें।",
            "calendar": "पर्याप्त बारिश के बाद जून में जल्दी बुवाई करें; ICAR तेलंगाना सलाह वर्षा आधारित कपास को 20 जुलाई के बाद न बोने की सलाह देती है।",
            "water_note": "मध्यम मिट्टी में ridge/furrow और काली मिट्टी में broad-bed furrow से नमी व अतिरिक्त पानी संभालें।",
            "reason": "तेलंगाना खरीफ के मुख्य मौसम और लाल/काली मिट्टी से मेल खाता है।",
            "risk": "कपास में शुरुआती लागत और भाव का जोखिम अधिक है। प्रमाणित बीज, गुलाबी सुंडी का इतिहास और मंडी पहुंच जांचें।",
        },
        "pigeon": {
            "fertilizer": "ICAR दलहन मार्गदर्शन: बुवाई पर लगभग 25–30:40–50:30 kg N:P₂O₅:K₂O/ha; सल्फर मिट्टी जांच के आधार पर दें। स्थानीय पैकेज के अनुसार Rhizobium/PSB बीज उपचार करें।",
            "calendar": "तेलंगाना सलाह: लगभग 60 mm बारिश के बाद 15 जून–15 जुलाई बुवाई; दूरी मिट्टी के प्रकार पर निर्भर है।",
            "water_note": "गहरी जड़ वाली और सूखा सहन करने वाली फसल; लंबे सूखे में फूल/फली बनते समय बचाव करें।",
            "reason": "बारिश आने पर लाल या काली मिट्टी में वर्षा आधारित दलहन का विकल्प।",
            "risk": "भारी बारिश के बाद जल निकासी रखें और जिले के लिए wilt-resistant किस्म चुनें।",
        },
        "soy": {
            "fertilizer": "ICAR तेलंगाना सलाह: बुवाई पर प्रति एकड़ 50 kg DAP + 26 kg MOP; 30 दिन बाद 25–30 kg यूरिया/एकड़। मिट्टी जांच और ताज़ा विश्वविद्यालय सलाह को प्राथमिकता दें।",
            "calendar": "15 जून–जुलाई के पहले सप्ताह तक बुवाई। भारी बारिश और नमी तनाव में broad-bed furrow उपयोगी हो सकता है।",
            "water_note": "जलभराव से बचाएं और सूखे अंतराल की स्थिति में पूरक सिंचाई की योजना रखें।",
            "reason": "तेलंगाना खरीफ मौसम और जल निकासी वाली लाल/काली मिट्टी से मेल खाता है।",
            "risk": "स्थानीय प्रमाणित किस्म चुनें और बीज खरीदने से पहले उपलब्धता जांचें।",
        },
        "groundnut": {
            "fertilizer": "ICAR सलाह में फली बनते समय pegging क्षेत्र के पास 500 kg gypsum/ha दिया गया है। किस्म और Soil Health Card के आधार पर स्थानीय KVK से मात्रा की पुष्टि करें।",
            "calendar": "आमतौर पर खरीफ विकल्प; भरोसेमंद शुरुआती बारिश और अच्छी जल निकासी वाली तैयार क्यारी में बोएं।",
            "water_note": "अंकुरण और फली बनने पर नमी जरूरी; खेत में पानी जमा न होने दें।",
            "reason": "नमी और जल निकासी सही हो तो हल्की लाल/रेतीली दोमट मिट्टी में अच्छा मेल।",
            "risk": "बीज लागत अधिक हो सकती है; बीज दर, gypsum जरूरत और स्थानीय बाजार पहले जांचें।",
        },
        "chickpea": {
            "fertilizer": "ICAR बंगाल ग्राम सलाह: बुवाई पर 20 kg N + 50 kg P₂O₅ + 40 kg सल्फर/ha। स्थानीय wilt-resistant किस्म और मिट्टी जांच के अनुसार मात्रा लें।",
            "calendar": "रबी बुवाई का समय: 15 अक्टूबर–15 नवंबर (ICAR सलाह)।",
            "water_note": "आमतौर पर बची हुई मिट्टी की नमी पर उगती है; स्थानीय परिस्थिति में 30–35 दिन पर हल्की सिंचाई लाभकारी हो सकती है।",
            "reason": "जहाँ मिट्टी भारी और पिछली फसल की नमी बची हो, वहाँ रबी दलहन का विकल्प।",
            "risk": "जलभराव से बचें; wilt का इतिहास, बची नमी और बिक्री समय देखें।",
        },
    },
    "te": {
        "rice": {
            "fertilizer": "ICAR తెలంగాణ సలహా (2025): వానాకాలంలో ఎకరానికి 40–48 kg N, 20 kg P, 16 kg K. N ను విడతలుగా ఇవ్వండి; జింక్ లోపం నిర్ధారణ అయితేనే వాడండి.",
            "calendar": "నారు సమయం రకాన్ని బట్టి ఉంటుంది: దీర్ఘకాలికం మే 20–జూన్ 20; మధ్య/స్వల్పకాలికం జూన్ 20 నుంచి. నేరుగా విత్తడం జూన్ చివరి నుంచి.",
            "water_note": "నమ్మదగిన నీటిపారుదల లేదా కాలువ/చెరువు నీరు ఉన్నప్పుడే ఎంచుకోండి. సాధ్యమైన చోట alternate wetting and drying పాటించండి.",
            "reason": "నీటిని నిలుపుకునే బరువైన నేల, నిర్ధారిత నీటిపారుదల ఉంటే మంచి ఎంపిక.",
            "risk": "విత్తే ముందు నీటి వనరు, రకానుసార నారు సమయం, పొలం డ్రైనేజీ నిర్ధారించండి.",
        },
        "maize": {
            "fertilizer": "ICAR తెలంగాణ ఖరీఫ్ సలహా: నీటిపారుదలలో 150:65:65 kg N:P₂O₅:K₂O/ha + 25 kg జింక్ సల్ఫేట్/ha; వర్షాధారంలో 100:50:25 + 10 kg జింక్ సల్ఫేట్/ha. యూరియా టాప్‌డ్రెస్సింగ్ స్థానిక సలహాతో చేయండి.",
            "calendar": "ఖరీఫ్ విత్తే సమయం జూన్ 15–జూలై 15; వర్షాలు ఆలస్యమైతే జూలై చివరి వరకు పొడిగించవచ్చు. ఇతర సీజన్లకు స్థానిక సలహా తీసుకోండి.",
            "water_note": "వర్షాధార విత్తనానికి పొలంలో తగిన తేమ ఉండాలి; ICAR మార్గదర్శకంగా 50–60 mm కూడిన వర్షాన్ని సూచిస్తుంది.",
            "reason": "ఎర్ర, నల్ల లేదా లోమీ నేలలో పండే పంట; నీటి స్థితిని బట్టి ఎరువు ప్రణాళిక మారుతుంది.",
            "risk": "వర్షాకాల ప్రారంభం, డ్రైనేజీ, ఫాల్ ఆర్మీవార్మ్ పర్యవేక్షణ ప్రణాళిక చూడండి.",
        },
        "cotton": {
            "fertilizer": "CICR తెలంగాణ ప్యాకేజ్: హైబ్రిడ్‌కు 120–150:60:60 kg N:P₂O₅:K₂O/ha; రకాలకు 90:45:45. Soil Health Card ఆధారంగా తుది మోతాదు నిర్ణయించండి.",
            "calendar": "తగిన వర్షం తర్వాత జూన్‌లో ముందుగా విత్తండి; వర్షాధార పత్తిని జూలై 20 తర్వాత విత్తవద్దని ICAR తెలంగాణ సలహా చెబుతుంది.",
            "water_note": "మధ్యస్థ నేలలో ridge/furrow, నల్ల నేలలో broad-bed furrow పద్ధతులతో తేమ, అదనపు నీరు నిర్వహించండి.",
            "reason": "తెలంగాణ ఖరీఫ్ ప్రధాన సీజన్, ఎర్ర/నల్ల నేలలకు సరిపోతుంది.",
            "risk": "పత్తికి ప్రారంభ పెట్టుబడి, ధరల ప్రమాదం ఎక్కువ. ధృవీకరించిన విత్తనం, పింక్ బోల్‌వార్మ్ చరిత్ర, మార్కెట్‌ను చూడండి.",
        },
        "pigeon": {
            "fertilizer": "ICAR పప్పుధాన్య మార్గదర్శకం: విత్తేటప్పుడు సుమారు 25–30:40–50:30 kg N:P₂O₅:K₂O/ha; సల్ఫర్‌ను నేల పరీక్ష ఆధారంగా ఇవ్వండి. స్థానిక ప్యాకేజ్ ప్రకారం Rhizobium/PSB విత్తన శుద్ధి చేయండి.",
            "calendar": "తెలంగాణ సలహా: సుమారు 60 mm వర్షం తర్వాత జూన్ 15–జూలై 15 విత్తండి; మొక్కల దూరం నేల రకంపై ఆధారపడి ఉంటుంది.",
            "water_note": "లోతైన వేరు, కరువును తట్టుకునే పంట; దీర్ఘకాల పొడి పరిస్థితిలో పూత/కాయ దశకు రక్షణ ఇవ్వండి.",
            "reason": "వర్షం వచ్చినప్పుడు ఎర్ర లేదా నల్ల నేలలో వర్షాధార పప్పుధాన్య ఎంపిక.",
            "risk": "భారీ వర్షం తర్వాత డ్రైనేజీ ఉంచండి; జిల్లాకు సరిపోయే wilt-resistant రకం ఎంచుకోండి.",
        },
        "soy": {
            "fertilizer": "ICAR తెలంగాణ సలహా: విత్తేటప్పుడు ఎకరానికి 50 kg DAP + 26 kg MOP; 30 రోజుల తర్వాత 25–30 kg యూరియా/ఎకరం. నేల పరీక్ష, తాజా విశ్వవిద్యాలయ సలహాకు ప్రాధాన్యం ఇవ్వండి.",
            "calendar": "జూన్ 15–జూలై మొదటి వారం విత్తండి. అధిక వర్షం లేదా తేమ ఒత్తిడిని ఎదుర్కోవడానికి broad-bed furrow ఉపయోగపడుతుంది.",
            "water_note": "నీరు నిల్వ ఉండనివ్వకండి; పొడి విరామం వస్తే అదనపు నీటిపారుదల ప్లాన్ చేయండి.",
            "reason": "తెలంగాణ ఖరీఫ్ సీజన్, నీరు నిల్వ ఉండని ఎర్ర/నల్ల నేలలకు సరిపోతుంది.",
            "risk": "స్థానికంగా విడుదలైన ధృవీకరించిన రకాన్ని ఎంచుకుని విత్తనం ముందుగా అందుబాటులో ఉందో చూడండి.",
        },
        "groundnut": {
            "fertilizer": "ICAR సలహాలో కాయ ఏర్పడే సమయంలో pegging ప్రాంతం దగ్గర 500 kg gypsum/ha సూచించింది. రకం, Soil Health Card ఆధారంగా స్థానిక KVK వద్ద మోతాదు నిర్ధారించండి.",
            "calendar": "సాధారణంగా ఖరీఫ్ పంట; నమ్మదగిన ప్రారంభ వర్షం, మంచి డ్రైనేజీ ఉన్న పొలంలో విత్తండి.",
            "water_note": "మొలక, కాయ ఏర్పడే దశలో తేమ అవసరం; పొలంలో నీరు నిలవనివ్వకండి.",
            "reason": "తేమ, డ్రైనేజీ సరిగా ఉంటే తేలికపాటి ఎర్ర/ఇసుక లోమీ నేలలో అనుకూలం.",
            "risk": "విత్తన ఖర్చు ఎక్కువ కావచ్చు; విత్తన పరిమాణం, gypsum అవసరం, స్థానిక మార్కెట్ నిర్ధారించండి.",
        },
        "chickpea": {
            "fertilizer": "ICAR బెంగాల్ గ్రాము సలహా: విత్తేటప్పుడు 20 kg N + 50 kg P₂O₅ + 40 kg సల్ఫర్/ha. స్థానిక wilt-resistant రకం, నేల పరీక్ష ప్రకారం వాడండి.",
            "calendar": "రబీ విత్తే సమయం: అక్టోబర్ 15–నవంబర్ 15 (ICAR సలహా).",
            "water_note": "మిగిలిన నేల తేమతో పెరుగుతుంది; స్థానిక పరిస్థితులకు సరిపోతే 30–35 రోజులకు తేలికపాటి నీరు ఉపయోగపడవచ్చు.",
            "reason": "భారీ నేల, మునుపటి పంట నుంచి తేమ మిగిలిన చోట రబీ పప్పుధాన్య ఎంపిక.",
            "risk": "నీరు నిలవనివ్వకండి; wilt చరిత్ర, మిగిలిన తేమ, అమ్మకపు సమయం చూడండి.",
        },
    },
}

SOILS = {"red": "soil_red", "black": "soil_black", "loam": "soil_loam", "sandy": "soil_sandy", "alluvial": "soil_alluvial"}
WATER_LEVELS = {0: "water_low", 1: "water_mid", 2: "water_high"}


def score_crop(crop: dict[str, object], month: int, soil: str, water: int, forecast: dict[str, object] | None, historical_rain: float | None, current_month: int) -> tuple[int, list[str], list[str]]:
    score = 0
    reasons: list[str] = []
    risks: list[str] = [str(crop["risk"])]
    months = crop["months"]
    soils = crop["soils"]
    water_fit = crop["water"]
    if month in months:
        score += 40
        reasons.append(str(crop["calendar"]))
    else:
        score -= 25
        risks.append(tr("month_warning"))
    if soil in soils:
        score += 25
        reasons.append(str(crop["reason"]))
    else:
        score += 5
        risks.append("Soil texture is not in the main reference match; confirm drainage and soil depth locally.")
    if water in water_fit:
        score += 20
    else:
        score -= 15
        risks.append(tr("water_caution"))
    if water == 2 and "rice" in crop["label"]:
        score += 10
    if historical_rain is not None and month in {6, 7} and crop["label"] != "crop_rice":
        if historical_rain >= 100:
            score += 5
            reasons.append(f"10-year median rainfall for this sowing month is {historical_rain:.0f} mm at the district location.")
        elif historical_rain < 50 and water == 0:
            score -= 8
            risks.append(f"Historical median rainfall for this month is only {historical_rain:.0f} mm; rain-fed establishment may be difficult.")
    if forecast and month == current_month and forecast.get("rain_mm") is not None:
        rain = float(forecast["rain_mm"])
        if month in {6, 7} and crop["label"] != "crop_rice":
            if rain >= 50:
                score += 5
                reasons.append(f"The next 7-day district forecast totals {rain:.0f} mm rain; verify field moisture before sowing.")
            elif water == 0:
                score -= 8
                risks.append("The near-term district forecast is below the 50 mm sowing rainfall guide; wait for adequate field moisture.")
    score = max(0, min(100, score))
    if forecast and month == current_month and month in {6, 7} and water == 0 and forecast.get("rain_mm") is not None:
        risks.append(tr("weather_caution"))
    return score, reasons[:2], risks[:3]


def money(amount: float) -> str:
    return f"₹{amount:,.0f}"


def render_welcome() -> None:
    lang = st.selectbox(tr("language"), list(LANGUAGES), format_func=lambda code: LANGUAGES[code], key="login_language")
    st.session_state["language"] = lang
    left, right = st.columns([1.1, 1], gap="large", vertical_alignment="center")
    with left:
        st.markdown(":green[:material/energy_savings_leaf: AGRIMARKET AI]")
        st.title(tr("welcome_heading"))
        st.write(tr("welcome_text"))
        if st.button(tr("welcome_start"), type="primary", width="stretch", key="welcome_start"):
            st.session_state["welcome_done"] = True
            st.rerun()
    with right:
        st.image(FARM_PHOTOS["telangana"], caption="Telangana agriculture", width="stretch")


def render_thankyou() -> None:
    st.markdown(":green[:material/energy_savings_leaf: AGRIMARKET AI]")
    st.title(tr("thanks_heading"))
    st.write(tr("thanks_text"))
    if st.button(tr("back_welcome"), type="primary", width="stretch", key="back_welcome"):
        st.session_state["show_thankyou"] = False
        st.session_state["welcome_done"] = False
        st.rerun()


def render_login() -> None:
    left, right = st.columns([1.25, 1], gap="large", vertical_alignment="center")
    with left:
        st.markdown(f"### :green[:material/energy_savings_leaf: AGRIMARKET AI]  ·  {tr('tagline')}")
        st.title(tr("title"))
        st.write(tr("subtitle"))
        st.image(FARM_PHOTOS["telangana"], caption="Growing with the land · Telangana", width="stretch")
        st.markdown(f"- :material/thermostat: {tr('weather')}\n- :material/compost: {tr('fertilizer')}\n- :material/account_balance: {tr('budget')}")
    with right:
        with st.container(border=True):
            st.subheader(tr("login"))
            st.caption(tr("login_help"))
            login_tab, register_tab = st.tabs([tr("login"), tr("register")])
            with login_tab:
                with st.form("login_form"):
                    user_id = st.text_input(tr("user_id"), autocomplete="username")
                    password = st.text_input(tr("password"), type="password", autocomplete="current-password")
                    submitted = st.form_submit_button(tr("login"), type="primary", width="stretch")
                if submitted:
                    user = authenticate(user_id, password)
                    if user:
                        st.session_state["user_id"], st.session_state["display_name"] = user
                        st.rerun()
                    st.error(tr("bad_login"))
            with register_tab:
                with st.form("register_form"):
                    display_name = st.text_input(tr("name"))
                    new_user_id = st.text_input(tr("user_id"), autocomplete="username")
                    new_password = st.text_input(tr("password"), type="password", autocomplete="new-password")
                    created = st.form_submit_button(tr("register"), type="primary", width="stretch")
                if created:
                    error = register_user(new_user_id, display_name or new_user_id, new_password)
                    if error:
                        st.error(tr(error))
                    else:
                        st.success(tr("account_created"))
        st.caption(tr("local_account_note"))


def render_plan(user_id: str, display_name: str) -> None:
    profile = load_profile(user_id)
    with st.sidebar:
        st.markdown("## :green[:material/energy_savings_leaf: AgriMarket AI]")
        st.caption(tr("logged_in") + " " + display_name)
        st.markdown("---")
        if not get_data_gov_api_key():
            st.caption(tr("market_setup"))
            st.markdown(f"[{tr('get_api_key')}](https://www.data.gov.in/help)")
        else:
            st.caption(tr("api_enabled"))
        st.markdown("---")
        if st.button(tr("logout"), width="stretch"):
            for key in ("user_id", "display_name", "plan"):
                st.session_state.pop(key, None)
            st.session_state["show_thankyou"] = True
            st.rerun()

    lang = st.session_state["language"]
    month_names = tr("month_names", lang)
    month_index = int(profile.get("month", date.today().month)) - 1
    default_district = str(profile.get("district", "Warangal"))
    default_district_index = list(DISTRICTS).index(default_district) if default_district in DISTRICTS else 0
    soil_keys = list(SOILS)
    soil_index = soil_keys.index(profile.get("soil", "red")) if profile.get("soil") in SOILS else 0
    water_keys = list(WATER_LEVELS)
    water_index = water_keys.index(profile.get("water", 0)) if profile.get("water") in WATER_LEVELS else 0

    st.markdown(f"#### :green[:material/energy_savings_leaf: AGRIMARKET AI]  ·  {tr('tagline')}")
    header_left, header_right = st.columns([3, 1], vertical_alignment="bottom")
    with header_left:
        st.title(tr("title"))
        st.caption(tr("subtitle"))
    with header_right:
        today = date.today()
        st.badge(f"{tr('telangana')} - {today.day} {tr('month_names')[today.month - 1]} {today.year}", color="green")

    photo_columns = st.columns(3, gap="small")
    photo_items = [
        ("telangana", "Telangana fields"),
        ("farmer", "Farmer in the paddy"),
        ("fields", "Patterns of cultivation"),
    ]
    for column, (photo_key, caption) in zip(photo_columns, photo_items):
        with column:
            st.image(FARM_PHOTOS[photo_key], caption=caption, width="stretch")
    st.caption(f"[{tr('photography_note')}](https://unsplash.com/)")

    with st.container(border=True):
        st.subheader(tr("farm_inputs"), anchor=False)
        with st.form("farm_planning_form"):
            col1, col2, col3 = st.columns(3)
            with col1:
                district = st.selectbox(tr("district"), list(DISTRICTS), index=default_district_index)
                area = st.number_input(tr("area"), min_value=0.1, max_value=10_000.0, value=float(profile.get("area", 2.0)), step=0.5)
            with col2:
                soil = st.selectbox(tr("soil"), soil_keys, index=soil_index, format_func=lambda key: tr(SOILS[key]))
                month = st.selectbox(tr("month"), range(1, 13), index=month_index, format_func=lambda value: month_names[value - 1])
            with col3:
                water = st.selectbox(tr("water"), water_keys, index=water_index, format_func=lambda key: tr(WATER_LEVELS[key]))
                st.caption(tr("sow_month_help"))
            with st.expander(tr("soil_test")):
                test_col1, test_col2, test_col3, test_col4 = st.columns(4)
                soil_ph = test_col1.number_input(tr("ph"), min_value=0.0, max_value=14.0, value=0.0, step=0.1, help="Enter 0 if not known.")
                soil_n = test_col2.number_input(tr("nitrogen"), min_value=0.0, value=0.0, step=1.0)
                soil_p = test_col3.number_input(tr("phosphorus"), min_value=0.0, value=0.0, step=1.0)
                soil_k = test_col4.number_input(tr("potassium"), min_value=0.0, value=0.0, step=1.0)
            run_plan = st.form_submit_button(tr("analyze"), type="primary", width="stretch")

    if run_plan:
        chosen_profile = {"district": district, "area": area, "soil": soil, "water": water, "month": month, "language": lang}
        save_profile(user_id, chosen_profile)
        latitude, longitude = DISTRICTS[district]
        with st.spinner(tr("saving")):
            forecast = get_weather(latitude, longitude)
            rainfall_history = get_monthly_rain_history(latitude, longitude)
            api_key = get_data_gov_api_key()
            market_prices = get_live_mandi_prices(district, api_key) if api_key else None
        month_rain_values = (rainfall_history or {}).get(month, [])
        historical_rain = statistics.median(month_rain_values) if month_rain_values else None
        results = []
        for crop_id, crop in CROPS.items():
            score, reasons, risks = score_crop(crop, month, soil, water, forecast, historical_rain, date.today().month)
            results.append({"id": crop_id, "crop": crop, "score": score, "reasons": reasons, "risks": risks})
        results.sort(key=lambda result: result["score"], reverse=True)
        st.session_state.pop("selected_crop_id", None)
        st.session_state["plan"] = {
            "profile": chosen_profile, "forecast": forecast, "rainfall_history": rainfall_history,
            "historical_rain": historical_rain, "market_prices": market_prices, "market_api_enabled": bool(api_key),
            "results": results, "soil_test": {"ph": soil_ph, "n": soil_n, "p": soil_p, "k": soil_k},
        }

    plan = st.session_state.get("plan")
    if not plan:
        st.info(tr("no_plan"), icon=":material/info:")
        return
    show_results(plan)


def show_results(plan: dict[str, object]) -> None:
    forecast = plan["forecast"]
    historical_rain = plan.get("historical_rain")
    market_prices = plan.get("market_prices") or {}
    results = plan["results"]
    farm = plan["profile"]
    area = float(farm["area"])
    selected_crop_id = st.session_state.get("selected_crop_id", results[0]["id"])
    crop_result = next((item for item in results if item["id"] == selected_crop_id), results[0])
    crop_id = crop_result["id"]
    crop = crop_result["crop"]
    crop_name = tr(crop["label"])
    live_quote = market_prices.get(crop_id) if isinstance(market_prices, dict) else None
    localized_copy = CROP_COPY.get(st.session_state.get("language", "en"), {}).get(crop_id, crop)

    st.markdown(f"### {tr('recommendation')}")
    top_col, weather_col = st.columns([1.35, 1], gap="large")
    with top_col:
        with st.container(border=True):
            selected_label = "top_crop" if crop_result["id"] == results[0]["id"] else "selected_crop"
            st.badge(tr(selected_label), icon=":material/auto_awesome:", color="green")
            st.subheader(crop_name, anchor=False)
            score_label = tr("score_strong") if crop_result["score"] >= 75 else tr("score_good") if crop_result["score"] >= 50 else tr("score_limited")
            st.metric(tr("score"), f"{crop_result['score']} / 100", score_label)
            st.progress(crop_result["score"])
            st.caption(tr("score_note"))
            st.markdown(f"**{tr('why')}**")
            st.markdown(f"- {localized_copy['reason']}")
            for reason in crop_result["reasons"]:
                if "forecast" in reason:
                    st.markdown(f"- {reason}")
            st.markdown(f"**{tr('risks')}**")
            st.markdown(f"- {localized_copy['risk']}")
            if crop_id == "rice" and farm["water"] < 2:
                st.markdown(f"- {tr('water_caution')}")
            st.markdown(f"**{tr('crop_calendar')}:** {localized_copy['calendar']}")
            st.markdown(f"**{tr('harvest')}:** {crop['duration'][0]}–{crop['duration'][1]} days")
    with weather_col:
        with st.container(border=True):
            st.subheader(tr("weather"), anchor=False)
            if forecast:
                rain = forecast.get("rain_mm")
                high = forecast.get("high_c")
                metric1, metric2, metric3 = st.columns(3)
                metric1.metric(tr("weather_rain"), f"{rain:.1f} mm" if rain is not None else "—")
                metric2.metric(tr("weather_temp"), f"{high:.1f} °C" if high is not None else "—")
                metric3.metric(tr("history_rain"), f"{historical_rain:.0f} mm" if historical_rain is not None else "—")
                st.caption(f"{tr('weather_source')} {tr('district_location')} {farm['district']}.")
                if historical_rain is not None:
                    st.caption(tr("history_note"))
                if rain is not None and farm["month"] in {6, 7} and rain < 50 and farm["water"] == 0:
                    st.warning(tr("forecast_dry"), icon=":material/water_drop:")
                else:
                    st.caption(tr("weather_caution"))
            else:
                st.warning(tr("weather_failed"))
                st.caption(f"{tr('weather_service')}: https://open-meteo.com/")
            st.markdown(f"**{tr('water_plan')}:** {localized_copy['water_note']}")

    st.markdown(f"### {tr('budget')}")
    st.caption(tr("budget_note"))
    with st.container(border=True):
        price_yield_col, cost_col = st.columns([1, 1.5], gap="large")
        with price_yield_col:
            sample_price, sample_yield, sample_costs = BUDGET_DEFAULTS[crop_id]
            default_price = float(live_quote["price"]) if live_quote else float(sample_price)
            price_token = str(live_quote.get("arrival_date", "sample-v2")) if live_quote else "sample-v2"
            price = st.number_input(tr("expected_price"), min_value=0.0, value=default_price, step=100.0, key=f"price_{crop_id}_{price_token}", help=tr("price_help"))
            expected_yield = st.number_input(tr("expected_yield"), min_value=0.0, value=float(sample_yield), step=0.5, key=f"yield_{crop_id}_v2", help=tr("yield_help"))
            if live_quote:
                markets_text = ", ".join(live_quote["markets"][:3]) or str(farm["district"])
                st.success(f"{tr('latest_market')}: {money(default_price)}/qtl · {tr('market_basis')} · {markets_text} · {live_quote['arrival_date']} · {live_quote['source']}")
                try:
                    quote_age = (date.today() - date.fromisoformat(str(live_quote["arrival_date"]))).days
                    if quote_age > 7:
                        st.warning(tr("stale_price"))
                except ValueError:
                    pass
            elif plan.get("market_api_enabled"):
                st.warning(tr("market_missing") if market_prices else tr("market_error"))
            else:
                st.info(tr("market_setup"))
                st.caption(tr("price_assumption"))
            if not live_quote:
                st.caption(tr("price_assumption"))
        with cost_col:
            st.markdown(f"**{tr('costs')}**")
            cost_labels = ["seed_cost", "land_cost", "fert_cost", "water_cost", "crop_cost", "other_cost"]
            costs = []
            cost_columns = st.columns(3)
            for index, (key, default) in enumerate(zip(cost_labels, sample_costs)):
                with cost_columns[index % 3]:
                    costs.append(st.number_input(tr(key), min_value=0.0, value=float(default), step=500.0, key=f"{crop_id}_{key}_v2"))
            total_per_acre = sum(costs)
            st.metric(tr("total_investment"), money(total_per_acre * area), f"{money(total_per_acre)} / acre")

        if price > 0 and expected_yield > 0 and total_per_acre > 0:
            total_cost = total_per_acre * area
            lower_yield = expected_yield * 0.8
            upper_yield = expected_yield * 1.2
            low_revenue = lower_yield * area * price * 0.9
            high_revenue = upper_yield * area * price * 1.1
            central_revenue = expected_yield * area * price
            low_profit, high_profit = low_revenue - total_cost, high_revenue - total_cost
            metric_a, metric_b, metric_c = st.columns(3)
            metric_a.metric(tr("gross_return"), money(central_revenue))
            metric_b.metric(tr("central_return"), money(central_revenue - total_cost))
            metric_c.metric(tr("profit_range"), f"{money(low_profit)} – {money(high_profit)}")
            st.caption(tr("profit_warning"))
        else:
            st.info(tr("profit_inputs_needed"))

    with st.container(border=True):
        st.subheader(tr("fertilizer"), anchor=False)
        st.write(localized_copy["fertilizer"])
        st.caption(tr("fert_note"))
        soil_test = plan["soil_test"]
        known = [f"{tr('ph')}: {soil_test['ph']:.1f}"] if soil_test["ph"] else []
        known += [f"{label}: {soil_test[field]:.0f} kg/ha" for field, label in (("n", tr("nitrogen")), ("p", tr("phosphorus")), ("k", tr("potassium"))) if soil_test[field] > 0]
        if known:
            st.caption(tr("soil_test_entered") + " ? " + " ? ".join(known))

    st.markdown(f"### {tr('recommendation')} · {tr('other_options')}")
    alternatives = [item for item in results if item["id"] != crop_id][:3]
    cols = st.columns(len(alternatives))
    for col, item in zip(cols, alternatives):
        with col:
            with st.container(border=True):
                st.markdown(f"**{tr(item['crop']['label'])}**")
                st.metric(tr("score"), f"{item['score']} / 100")
                other_copy = CROP_COPY.get(st.session_state.get("language", "en"), {}).get(item["id"], item["crop"])
                st.caption(other_copy["reason"] if item["score"] >= 50 else other_copy["risk"])
                if st.button(tr("open_crop"), key=f"open_crop_{item['id']}", width="stretch"):
                    st.session_state["selected_crop_id"] = item["id"]
                    st.rerun()

    with st.expander(tr("sources")):
        st.markdown(f"- [{tr('source_weather')}](https://open-meteo.com/en/docs) - {tr('source_weather_note')}")
        st.markdown(f"- [Open-Meteo Historical Weather API](https://open-meteo.com/en/docs/historical-weather-api) - {tr('source_history_note')}")
        st.markdown(f"- [{tr('source_market_label')}](https://data.gov.in/catalog/current-daily-price-various-commodities-various-markets-mandi) - {tr('source_market_note')}")
        st.markdown(f"- [{tr('source_crop')}](https://icar.org.in/sites/default/files/Circulars/ICAR-En-Kharif-Agro-Advisories-for-Farmers-2025.pdf) - {tr('source_crop_note')}")
        st.markdown(f"- [{tr('source_cotton')}](https://www.cicr.org.in/wp-content/uploads/POP-TS-Adil.pdf) - {tr('source_cotton_note')}")
        st.markdown(f"- [SoilGrids service status](https://docs.isric.org/globaldata/soilgrids/) - {tr('source_soil_note')}")
        st.write(tr("method_note"))
    st.warning(tr("sample_notice"), icon=":material/health_and_safety:")


def main() -> None:
    init_db()
    st.session_state.setdefault("language", "en")
    if "user_id" not in st.session_state:
        if st.session_state.get("show_thankyou"):
            render_thankyou()
            return
        if not st.session_state.get("welcome_done"):
            render_welcome()
            return
        render_login()
        return
    render_plan(st.session_state["user_id"], st.session_state["display_name"])


if __name__ == "__main__":
    main()

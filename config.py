import os
from dotenv import load_dotenv

load_dotenv()

def _setup_ca_bundle():
    """Norton Antivirus MITM-proxies HTTPS and re-signs certs with its own CA,
    which Python/curl don't trust — every yfinance/requests call fails with
    CERTIFICATE_VERIFY_FAILED. Build a bundle of certifi + Norton CA and point
    all HTTP clients at it."""
    norton_ca = r"C:\ProgramData\Norton\Antivirus\wscert.pem"
    if not os.path.exists(norton_ca):
        return
    try:
        import certifi, shutil
        os.makedirs("output", exist_ok=True)
        bundle = os.path.abspath("output/ca_bundle.pem")
        shutil.copyfile(certifi.where(), bundle)
        with open(norton_ca, "rb") as f:
            norton = f.read()
        with open(bundle, "ab") as f:
            f.write(b"\n" + norton)
        os.environ.setdefault("SSL_CERT_FILE", bundle)
        os.environ.setdefault("REQUESTS_CA_BUNDLE", bundle)
        os.environ.setdefault("CURL_CA_BUNDLE", bundle)
    except Exception:
        pass

_setup_ca_bundle()

FMP_API_KEY = os.getenv("FMP_API_KEY")
WATCHLIST = ["KGC", "GOLD", "NEM", "AEM"]
OUTPUT_PATH = "output/analysis.json"
NEWS_PATH = "output/news.json"
WATCHLIST_PATH = "watchlist.json"
LOG_FILE = "logs/app.log"
FOLLOWUP_PATH = "output/followup.json"
FRED_API_KEY = os.getenv("FRED_API_KEY")
NEWSAPI_KEY  = os.getenv("NEWSAPI_KEY")
MACRO_PATH   = "output/macro.json"
TRADES_PATH  = "output/trades.json"
TRADE_CANDIDATES_PATH = "output/trade_candidates.json"
TRADES_AI_PATH = "output/trades_ai.json"
TRADE_AI_CANDIDATES_PATH = "output/trade_ai_candidates.json"
OLLAMA_URL   = "http://localhost:11434"
# OLLAMA_MODEL = "gemma2:9b"
OLLAMA_MODEL = "phi3:mini"
GEMINI_API_KEY  = os.getenv("GEMINI_API_KEY")
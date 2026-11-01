import sys
from pathlib import Path

# Ensure backend root is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from google_auth_oauthlib.flow import InstalledAppFlow
from app.config import settings
from app.services.gmail import SCOPES, _token_path, get_profile

def authenticate():
    creds_file = settings.gmail_credentials_file
    if not Path(creds_file).exists():
        print(f"Error: Credentials file not found at {creds_file}", flush=True)
        sys.exit(1)

    print("Initializing OAuth flow...", flush=True)
    flow = InstalledAppFlow.from_client_secrets_file(creds_file, SCOPES)
    
    # We run local server on a fixed port and print the URL directly
    print("\n" + "="*70, flush=True)
    print("CLICK THE LINK BELOW TO AUTHORIZE GMAIL:", flush=True)
    print("="*70, flush=True)
    
    print("Opening browser for authorization...", flush=True)
    creds = flow.run_local_server(port=8080, open_browser=True)
    
    token_path = _token_path()
    token_path.write_text(creds.to_json())
    print(f"\nSUCCESS! Token saved to {token_path}", flush=True)
    
    profile = get_profile()
    print(f"Authenticated as: {profile.get('emailAddress')}", flush=True)

if __name__ == "__main__":
    authenticate()

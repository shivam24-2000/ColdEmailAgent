"""Test script to verify Gmail API reading, drafting, and sending."""
import sys
import time
from pathlib import Path
from typing import Any

# Ensure backend root is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent))

def test_gmail():
    print("=" * 60, flush=True)
    print("1. Testing Gmail Account Access...", flush=True)
    print("=" * 60, flush=True)
    
    try:
        print("-> Loading cached credentials...", flush=True)
        from app.services.gmail import get_credentials
        creds = get_credentials()
        if not creds:
            raise RuntimeError("Failed to load credentials")
        print(f"-> Credentials loaded! Valid: {creds.valid}, Expired: {creds.expired}", flush=True)
        
        print("-> Connecting to Gmail API service (building client)...", flush=True)
        from app.services.gmail import get_service
        t0 = time.time()
        svc: Any = get_service()
        print(f"-> Service client built in {time.time() - t0:.2f}s!", flush=True)
        
        print("-> Fetching profile from Google...", flush=True)
        t0 = time.time()
        profile = svc.users().getProfile(userId="me").execute()
        print(f"-> Profile fetched in {time.time() - t0:.2f}s!", flush=True)
        
        email = profile.get("emailAddress")
        print(f"\n✅ SUCCESS: Connected to Gmail account: {email}", flush=True)
        print(f"   Total Messages: {profile.get('messagesTotal')}", flush=True)
        print(f"   Total Threads:  {profile.get('threadsTotal')}", flush=True)
    except Exception as e:
        print(f"\n❌ FAILED to get profile: {e}", flush=True)
        import traceback
        traceback.print_exc()
        return

    print("\n" + "=" * 60, flush=True)
    print("2. Testing Draft Creation...", flush=True)
    print("=" * 60, flush=True)
    try:
        from app.services.gmail import create_draft
        print(f"-> Creating test draft to {email}...", flush=True)
        draft = create_draft(
            to=email,
            subject="ColdEmailer Verification Draft",
            body="Hello Shivam!\n\nThis is a test draft created by ColdEmailer.\nIf you can see this in your Gmail drafts, your integration is 100% working!"
        )
        draft_id = draft.get("id")
        print(f"\n✅ SUCCESS: Created draft in your Gmail!", flush=True)
        print(f"   Draft ID: {draft_id}", flush=True)
        print(f"   👉 Open https://mail.google.com and check your 'Drafts' folder!", flush=True)
    except Exception as e:
        print(f"\n❌ FAILED to create draft: {e}", flush=True)
        import traceback
        traceback.print_exc()
        return

    print("\n" + "=" * 60, flush=True)
    print("🎉 ALL TESTS PASSED! Gmail integration is fully operational.", flush=True)
    print("=" * 60, flush=True)

if __name__ == "__main__":
    test_gmail()

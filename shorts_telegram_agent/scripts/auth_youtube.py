"""Run locally once to create OAuth token JSON for the Render secret."""
import json
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
flow = InstalledAppFlow.from_client_secrets_file("client_secrets.json", SCOPES)
credentials = flow.run_local_server(port=0)
print("\nCopy the complete JSON below into Render env var YOUTUBE_TOKEN_JSON:\n")
print(credentials.to_json())

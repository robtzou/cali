import os
import datetime
import json
import re

from flask import Flask, redirect, url_for, session, request, render_template_string
from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import google.generativeai as genai

# New imports for OCR and advanced date parsing
import pytesseract
from PIL import Image
from dateutil import parser as date_parser
from dateutil.tz import gettz

app = Flask(__name__)
app.secret_key = 'your-super-secret-key'
# Create an 'uploads' directory if it doesn't exist
if not os.path.exists('uploads'):
    os.makedirs('uploads')
app.config['UPLOAD_FOLDER'] = 'uploads'


os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"
CLIENT_SECRETS_FILE = "client_secrets.json"
SCOPES = ["https://www.googleapis.com/auth/calendar"]

# --- Gemini Configuration ---
# We no longer use a Tool, as we want a flexible JSON object back for multiple events
genai.configure(api_key=os.environ["GOOGLE_API_KEY"])
model = genai.GenerativeModel(model_name='gemini-1.5-flash')

# Adapted from your script to be a system prompt for Gemini
LLM_PROMPT_TEMPLATE = """
You are a calendar event extraction assistant.
Extract all calendar-worthy events from the provided text into a strict JSON object.
Your output must be ONLY the JSON object, with no other text or markdown formatting.

The JSON object must have a single key "events", which is an array of event objects.
Each event object should have:
- "title": (string) A short, human-friendly title.
- "start": (string) The event start time in ISO 8601 format or a clear natural-language datetime.
- "end": (string, optional) The event end time.
- "allday": (boolean) True if it's an all-day event.
- "location": (string, optional) The event location.
- "description": (string, optional) Any notes or description.
- "timezone": (string, optional) The IANA timezone (e.g., "America/New_York").

Resolve relative dates like "tomorrow" or "next Tuesday" relative to the current time: {current_datetime}.
Assume the user is in this timezone unless specified otherwise: {timezone}.
If an end time is not provided for a timed event, infer a 60-minute duration.
"""

# --- OCR and Event Normalization Functions (from your script) ---

def ocr_image_to_text(image_path: str) -> str:
    """Perform OCR on an image and return extracted text."""
    try:
        img = Image.open(image_path)
        text = pytesseract.image_to_string(img)
        return text
    except Exception as e:
        print(f"Error during OCR: {e}")
        return ""

def _parse_datetime_guess(s: str, tz: str) -> datetime.datetime:
    """Parse a datetime string, assigning a timezone if it's naive."""
    dt = date_parser.parse(s, fuzzy=True)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=gettz(tz))
    return dt

def normalize_event_fields(evt: dict, default_tz: str) -> dict:
    """Convert LLM event dict into Google Calendar event body."""
    title = evt.get("title") or "Untitled Event"
    if not evt.get("start"):
        raise ValueError(f"Event '{title}' is missing a 'start' time.")

    allday = bool(evt.get("allday", False))
    tz = evt.get("timezone") or default_tz
    start_dt = _parse_datetime_guess(str(evt["start"]), tz)

    if allday:
        start_date = start_dt.date().isoformat()
        if evt.get("end"):
            end_dt = _parse_datetime_guess(str(evt["end"]), tz)
            end_date = (end_dt.date() + datetime.timedelta(days=1)).isoformat()
        else:
            end_date = (start_dt.date() + datetime.timedelta(days=1)).isoformat()
        body = {"start": {"date": start_date}, "end": {"date": end_date}}
    else:
        if evt.get("end"):
            end_dt = _parse_datetime_guess(str(evt["end"]), tz)
        else:
            end_dt = start_dt + datetime.timedelta(minutes=60)
        body = {
            "start": {"dateTime": start_dt.isoformat(), "timeZone": tz},
            "end": {"dateTime": end_dt.isoformat(), "timeZone": tz},
        }
    
    body["summary"] = title
    if evt.get("location"): body["location"] = evt.get("location")
    if evt.get("description"): body["description"] = evt.get("description")
    
    return body


# --- App Routes ---

@app.route("/")
def index():
    if 'credentials' in session:
        return redirect(url_for('dashboard'))
    return '<a href="/login">Connect to Google Calendar</a>'

@app.route("/login")
def login():
    flow = Flow.from_client_secrets_file(
        CLIENT_SECRETS_FILE,
        scopes=SCOPES,
        redirect_uri=url_for("callback", _external=True)
    )
    authorization_url, state = flow.authorization_url()
    session["state"] = state
    return redirect(authorization_url)

@app.route("/callback")
def callback():
    state = session["state"]
    flow = Flow.from_client_secrets_file(
        CLIENT_SECRETS_FILE, scopes=SCOPES, state=state,
        redirect_uri=url_for("callback", _external=True)
    )
    flow.fetch_token(authorization_response=request.url)
    credentials = flow.credentials
    session['credentials'] = credentials_to_dict(credentials)
    return redirect(url_for("dashboard"))

@app.route("/dashboard", methods=['GET', 'POST'])
def dashboard():
    if 'credentials' not in session:
        return redirect(url_for('login'))

    message = "Enter a command or upload an image to create calendar events."

    if request.method == 'POST':
        creds = Credentials(**session['credentials'])
        service = build("calendar", "v3", credentials=creds)
        raw_text = ""

        # Check for uploaded file
        if 'image_file' in request.files and request.files['image_file'].filename != '':
            file = request.files['image_file']
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], file.filename)
            file.save(filepath)
            raw_text = ocr_image_to_text(filepath)
        # Check for text prompt
        elif request.form.get('prompt'):
            raw_text = request.form['prompt']
        
        if not raw_text:
            message = "Please provide a prompt or upload an image."
        else:
            try:
                # --- New Gemini Logic ---
                now = datetime.datetime.now().astimezone()
                prompt = (
                    LLM_PROMPT_TEMPLATE.format(
                        current_datetime=now.isoformat(),
                        timezone=str(now.tzinfo)
                    )
                    + "\n\nTEXT TO PARSE:\n" + raw_text
                )

                response = model.generate_content(
                    prompt,
                    generation_config={"response_mime_type": "application/json"}
                )
                
                llm_data = json.loads(response.text)
                events_to_create = llm_data.get("events", [])
                
                if not events_to_create:
                    message = "No events found in the text."
                else:
                    created_events_html = []
                    for event_data in events_to_create:
                        normalized_event = normalize_event_fields(event_data, default_tz=str(now.tzinfo))
                        created_event = service.events().insert(calendarId="primary", body=normalized_event).execute()
                        link = f"<a href='{created_event.get('htmlLink')}' target='_blank'>{created_event.get('summary')}</a>"
                        created_events_html.append(f"<li>{link}</li>")
                    
                    message = f"Successfully created {len(created_events_html)} event(s):<ul>{''.join(created_events_html)}</ul>"

            except Exception as e:
                message = f"An error occurred: {e}"

    # Render the dashboard page
    return render_template_string("""
        <!DOCTYPE html>
        <html>
        <head>
            <title>AI Calendar Agent</title>
            <style>
                body { font-family: sans-serif; padding: 2em; }
                form > div { margin-bottom: 1em; }
                input[type=file] { margin-top: 0.5em; }
                .results { margin-top: 1em; padding: 1em; border: 1px solid #ccc; border-radius: 5px; background-color: #f9f9f9; }
            </style>
        </head>
        <body>
            <h1>AI Calendar Agent</h1>
            <div class="results">{{ message | safe }}</div>
            <form method="post" enctype="multipart/form-data">
                <div>
                    <label for="prompt"><b>\nOption 1:</b> Type a command</label><br>
                    <input type="text" id="prompt" name="prompt" size="50">
                </div>
                <div>
                    <label for="image_file"><b>Option 2:</b> Or upload a schedule image</label><br>
                    <input type="file" id="image_file" name="image_file" accept="image/*">
                </div>
                <input type="submit" value="Process and Create Events">
            </form>
            <br><br>
            <a href="/logout">Logout</a>
        </body>
        </html>
    """, message=message)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))

def credentials_to_dict(credentials):
    return {'token': credentials.token, 'refresh_token': credentials.refresh_token,
            'token_uri': credentials.token_uri, 'client_id': credentials.client_id,
            'client_secret': credentials.client_secret, 'scopes': credentials.scopes}

if __name__ == "__main__":
    app.run(debug=True)

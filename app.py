#   pip install google-cloud-vision
#   export GOOGLE_APPLICATION_CREDENTIALS=/absolute/path/to/your-service-account.json

import os
import datetime
import json
import re

from flask import Flask, redirect, url_for, session, request, render_template_string
from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
import google.generativeai as genai
from google.cloud import vision

# New imports for OCR and advanced date parsing
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
    """
    Perform OCR on an image and return extracted text using Google Cloud Vision's
    DOCUMENT_TEXT_DETECTION (more accurate for documents/receipts than basic OCR).

    Requirements:
      - pip install google-cloud-vision
      - Set service account credentials, e.g.:
          export GOOGLE_APPLICATION_CREDENTIALS="/path/to/service-account.json"

    Notes:
      - This replaces the previous Tesseract-based approach, which was more memory intensive.
      - Vision handles a wide variety of file types (JPEG, PNG, WEBP, PDF first page as image, etc.).
    """
    try:
        client = vision.ImageAnnotatorClient()
        with open(image_path, "rb") as f:
            content = f.read()
        image = vision.Image(content=content)

        # Use DOCUMENT_TEXT_DETECTION for structured docs; it's better for forms and receipts.
        response = client.document_text_detection(image=image)
        if response.error.message:
            # Return empty string but log the error for debugging
            print(f"Vision API error: {response.error.message}")
            return ""

        # full_text_annotation aggregates detected text across the whole page
        if response.full_text_annotation and response.full_text_annotation.text:
            return response.full_text_annotation.text

        # Fallback: try reading concatenated block/annotation text
        if response.text_annotations:
            return " ".join([a.description for a in response.text_annotations])

        return ""
    except Exception as e:
        # Keep the interface identical: swallow and return empty string, but print error
        print(f"Error during OCR with Google Vision: {e}")
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

    # This is the crucial change. 
    # access_type='offline' tells Google we need a refresh token to use when the user is not present.
    # prompt='consent' forces the consent screen every time, which is useful for testing to ensure a refresh token is always sent.
    authorization_url, state = flow.authorization_url(
        access_type='offline',
        prompt='consent'
    )
    
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

    results_html = ""

    if request.method == 'POST':
        creds = Credentials(**session['credentials'])
        service = build("calendar", "v3", credentials=creds)
        raw_text = ""

        # Check for uploaded file
        if 'image_file' in request.files and request.files['image_file'].filename != '':
            file = request.files['image_file']
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], file.filename)
            file.save(filepath)
            raw_text = ocr_image_to_text(filepath)  # Uses Google Cloud Vision DOCUMENT_TEXT_DETECTION
        # Check for text prompt
        elif request.form.get('prompt'):
            raw_text = request.form['prompt']
        
        if not raw_text:
            results_html = "Please provide a prompt or upload an image."
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
                    results_html = "No events found in the text."
                else:
                    created_events_html = []
                    for event_data in events_to_create:
                        normalized_event = normalize_event_fields(event_data, default_tz=str(now.tzinfo))
                        created_event = service.events().insert(calendarId="primary", body=normalized_event).execute()
                        link = f"<a href='{created_event.get('htmlLink')}' target='_blank'>{created_event.get('summary')}</a>"
                        created_events_html.append(f"<li>{link}</li>")
                    
                    results_html = f"Successfully created {len(created_events_html)} event(s):<ul>{''.join(created_events_html)}</ul>"

            except Exception as e:
                results_html = f"An error occurred: {e}"

    # Render the dashboard page
    return render_template_string("""
                                  
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>AI Calendar Agent</title>
            <style>
                @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;700&display=swap');
                :root {
                    --bg-color: #f8f9fa;
                    --card-bg: #ffffff;
                    --text-color: #212529;
                    --primary-color: #6d28d9;
                    --primary-hover: #5b21b6;
                    --border-color: #dee2e6;
                    --input-focus-border: #845ef7;
                }
                body {
                    font-family: 'Inter', sans-serif;
                    background-color: var(--bg-color);
                    color: var(--text-color);
                    display: flex;
                    justify-content: center;
                    align-items: center;
                    min-height: 100vh;
                    margin: 0;
                    padding: 1em;
                    box-sizing: border-box;
                }
                .container {
                    width: 100%;
                    max-width: 600px;
                    background: var(--card-bg);
                    padding: 2.5em;
                    border-radius: 16px;
                    box-shadow: 0 8px 32px rgba(0,0,0,0.1);
                }
                h1 {
                    font-weight: 700;
                    color: var(--text-color);
                    margin-bottom: 0.25em;
                    text-align: center;
                }
                .subtitle {
                    text-align: center;
                    color: #6c757d;
                    margin-top: 0;
                    margin-bottom: 2em;
                }
                .logout-link {
                    display: block;
                    margin-top: 2em;
                    font-size: 0.9em;
                    color: #6c757d;
                    text-decoration: none;
                    transition: color 0.2s;
                    text-align: center;
                }
                .logout-link:hover { color: var(--primary-color); }
                .results {
                    margin-bottom: 2em;
                    padding: 1em;
                    border-radius: 8px;
                    background-color: #e9ecef;
                    text-align: left;
                    border: 1px solid var(--border-color);
                    font-size: 0.9em;
                }
                .results a { color: var(--primary-color); font-weight: 500; }
                .results ul { padding-left: 20px; margin-top: 0.5em; margin-bottom: 0; }
                form > div { margin-bottom: 1.5em; text-align: left; }
                label { display: block; font-weight: 500; margin-bottom: 0.5em; }
                input[type=text] {
                    width: 100%;
                    padding: 12px;
                    border: 1px solid var(--border-color);
                    border-radius: 8px;
                    background-color: var(--card-bg);
                    font-size: 1em;
                    box-sizing: border-box;
                    transition: border-color 0.2s, box-shadow 0.2s;
                }
                input[type=text]:focus {
                    outline: none;
                    border-color: var(--input-focus-border);
                    box-shadow: 0 0 0 3px rgba(132, 94, 247, 0.25);
                }
                .file-upload-wrapper { position: relative; overflow: hidden; display: inline-block; width: 100%; }
                .file-upload-btn {
                    border: 1px solid var(--border-color); color: #495057; background-color: #f8f9fa;
                    padding: 12px; border-radius: 8px; cursor: pointer; display: block;
                    text-align: center; transition: background-color 0.2s;
                    white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
                }
                .file-upload-btn:hover { background-color: #e9ecef; }
                input[type=file] {
                    font-size: 100px; position: absolute; left: 0; top: 0; opacity: 0;
                    cursor: pointer; height: 100%; width: 100%;
                }
                .submit-btn {
                    width: 100%; padding: 14px; font-size: 1.1em; font-weight: 700; color: white;
                    background-image: linear-gradient(45deg, #845ef7, #6d28d9);
                    border: none; border-radius: 8px; cursor: pointer; transition: transform 0.2s, box-shadow 0.2s;
                    box-shadow: 0 4px 15px rgba(109, 40, 217, 0.3); margin-top: 1em;
                }
                .submit-btn:hover {
                    transform: translateY(-2px);
                    box-shadow: 0 6px 20px rgba(109, 40, 217, 0.4);
                }
            </style>
        </head>
        <body>
            <div class="container">
                <h1>AI Calendar Agent</h1>
                <p class="subtitle">Type a command or upload an image of a schedule.</p>
                {% if results_html %}
                <div class="results">{{ results_html | safe }}</div>
                {% endif %}
                <form method="post" enctype="multipart/form-data">
                    <div>
                        <label for="prompt"><b>Option 1:</b> Type a command</label>
                        <input type="text" id="prompt" name="prompt" placeholder="e.g., Lunch with Alex tomorrow at 1pm">
                    </div>
                    <div>
                        <label for="image_file"><b>Option 2:</b> Or upload a schedule image</label>
                        <div class="file-upload-wrapper">
                             <span class="file-upload-btn">Click to choose a file</span>
                             <input type="file" id="image_file" name="image_file" accept="image/*">
                        </div>
                    </div>
                    <input type="submit" value="Process and Create Events" class="submit-btn">
                </form>
                <a href="/logout" class="logout-link">Logout</a>
            </div>
            <script>
                document.getElementById('image_file').addEventListener('change', function() {
                    var fileName = this.files[0] ? this.files[0].name : 'Click to choose a file';
                    document.querySelector('.file-upload-btn').textContent = fileName;
                });
            </script>
        </body>
        </html>
    """, results_html=results_html)


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
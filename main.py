import os
import datetime
from flask import Flask, redirect, url_for, session, request, render_template_string
from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
import google.generativeai as genai
from google.ai import generativelanguage as glm

app = Flask(__name__)
app.secret_key = 'your-super-secret-key'

os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"
CLIENT_SECRETS_FILE = "client_secrets.json"
SCOPES = ["https://www.googleapis.com/auth/calendar"]

# --- Gemini Configuration ---
genai.configure(api_key=os.environ["GOOGLE_API_KEY"])
create_calendar_event = glm.Tool(
    function_declarations=[
        glm.FunctionDeclaration(
            name='create_calendar_event',
            description="Creates a new event on Google Calendar.",
            parameters=glm.Schema(
                type=glm.Type.OBJECT,
                properties={
                    'summary': glm.Schema(type=glm.Type.STRING, description="The title or summary of the event."),
                    'start_time': glm.Schema(type=glm.Type.STRING, description="The start time of the event in ISO 8601 format."),
                    'end_time': glm.Schema(type=glm.Type.STRING, description="The end time of the event in ISO 8601 format."),
                },
                required=['summary', 'start_time', 'end_time']
            )
        )
    ]
)
model = genai.GenerativeModel(
    model_name='gemini-1.5-flash',
    tools=[create_calendar_event]
)

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
        CLIENT_SECRETS_FILE,
        scopes=SCOPES,
        state=state,
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

    # Recreate the credentials object from the session data
    creds = Credentials(**session['credentials'])
    
    # Message to display to the user
    message = "Enter a command to create a calendar event."

    if request.method == 'POST':
        try:
            # --- This is where our agent logic now lives ---
            user_prompt = request.form['prompt']
            
            # 1. Add current time context
            now = datetime.datetime.now().strftime("%A, %B %d, %Y at %I:%M %p")
            full_prompt = f"The current time is {now}. With that in mind, please handle the following request: {user_prompt}"
            
            # 2. Call the Gemini model
            chat_session = model.start_chat()
            response = chat_session.send_message(full_prompt)
            function_call = response.candidates[0].content.parts[0].function_call
            
            if function_call.name == "create_calendar_event":
                args = function_call.args
                
                # 3. Build the calendar service
                service = build("calendar", "v3", credentials=creds)
                
                # 4. Create the event
                event_body = {
                    "summary": args["summary"],
                    "start": {"dateTime": args["start_time"], "timeZone": "America/New_York"}, # Adjust timezone as needed
                    "end": {"dateTime": args["end_time"], "timeZone": "America/New_York"},
                }
                event = service.events().insert(calendarId="primary", body=event_body).execute()
                
                # Success message with a link
                message = f"Event created! <a href='{event.get('htmlLink')}' target='_blank'>View it here.</a>"
            else:
                message = "Sorry, I couldn't understand the event details from your prompt."

        except Exception as e:
            message = f"An error occurred: {e}"

    # Render the dashboard page with the message
    return render_template_string("""
        <h1>AI Calendar Agent</h1>
        <p>{{ message | safe }}</p>
        <form method="post">
            <input type="text" id="prompt" name="prompt" size="50" placeholder="e.g., Schedule a dentist appointment for next Tuesday at 3pm"><br><br>
            <input type="submit" value="Create Event">
        </form>
        <br>
        <a href="/logout">Logout</a>
    """, message=message)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))

# Helper function
def credentials_to_dict(credentials):
    return {'token': credentials.token,
            'refresh_token': credentials.refresh_token,
            'token_uri': credentials.token_uri,
            'client_id': credentials.client_id,
            'client_secret': credentials.client_secret,
            'scopes': credentials.scopes}

if __name__ == "__main__":
    app.run(debug=True)
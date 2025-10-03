# Cali - AI Calendar Assistant

An intelligent web application that automatically extracts calendar events from text or images and adds them to your Google Calendar. Simply upload a screenshot of a schedule, paste text, or type a natural language command, and Cali will parse the information and create calendar events for you.

## Features

- **Image Processing**: Upload screenshots, photos, or scanned documents containing schedule information
- **Text Parsing**: Paste text or type natural language commands to create events
- **AI-Powered**: Uses Google's Gemini AI to intelligently extract and parse event information
- **Google Calendar Integration**: Seamlessly adds events to your Google Calendar
- **Web Interface**: Clean, modern web UI for easy interaction
- **Docker Support**: Ready for containerized deployment

## How It Works

1. **OCR Processing**: Uses Google Cloud Vision API to extract text from uploaded images
2. **AI Parsing**: Leverages Google's Gemini 1.5 Flash model to intelligently parse event information
3. **Event Creation**: Automatically formats and adds events to your Google Calendar via the Google Calendar API

## Prerequisites

- Python 3.11+
- Google Cloud Platform account with Vision API enabled
- Google API credentials (OAuth2)
- Google Gemini API key

## Setup

### 1. Clone the Repository

```bash
git clone <repository-url>
cd cali
```

### 2. Install Dependencies

Using pip:
```bash
pip install -r requirements.txt
```

Or using uv (recommended):
```bash
uv sync
```

### 3. Google API Setup

#### Google Cloud Vision API
1. Create a Google Cloud project
2. Enable the Vision API
3. Create a service account and download the JSON key file
4. Set the environment variable:
```bash
export GOOGLE_APPLICATION_CREDENTIALS="/path/to/your-service-account.json"
```

#### Google Calendar API
1. Go to the [Google Cloud Console](https://console.cloud.google.com/)
2. Enable the Google Calendar API
3. Create OAuth 2.0 credentials and download `client_secrets.json`
4. Place the file in your project root

#### Google Gemini API
1. Get your API key from [Google AI Studio](https://aistudio.google.com/app/apikey)
2. Set the environment variable:
```bash
export GOOGLE_API_KEY="your-gemini-api-key"
```

### 4. Run the Application

```bash
python app.py
```

Or with Docker:
```bash
docker build -t cali .
docker run -p 10000:10000 \
  -e GOOGLE_API_KEY=your-api-key \
  -e GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account.json \
  -v /path/to/service-account.json:/path/to/service-account.json \
  cali
```

## Usage

1. **Start the application** and navigate to `http://localhost:5000`
2. **Connect to Google Calendar** by clicking the login link
3. **Create events** using either:
   - **Text input**: Type natural language commands like "Lunch with Alex tomorrow at 1pm"
   - **Image upload**: Upload screenshots of schedules, calendars, or event listings
4. **Review and confirm** the automatically created events in your Google Calendar

### Example Inputs

**Text Commands:**
- "Meeting with the team next Tuesday at 2pm"
- "Doctor appointment on March 15th at 10:30am"
- "Dinner reservation at 7pm on Friday"

**Image Uploads:**
- Screenshots of conference schedules
- Photos of printed calendars
- Scanned documents with event information

## API Integration

The application integrates with:
- **Google Cloud Vision API**: For OCR text extraction from images
- **Google Gemini API**: For intelligent event parsing and extraction
- **Google Calendar API**: For creating and managing calendar events

## Docker Deployment

The application includes a Dockerfile for easy deployment:

```bash
docker build -t cali .
docker run -p 10000:10000 \
  -e GOOGLE_API_KEY=your-api-key \
  -e GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account.json \
  cali
```

## Environment Variables

- `GOOGLE_API_KEY`: Your Google Gemini API key
- `GOOGLE_APPLICATION_CREDENTIALS`: Path to your Google Cloud service account JSON file

## File Structure

```
cali/
├── app.py              # Main Flask application
├── vision.py           # Google Cloud Vision API utilities
├── requirements.txt    # Python dependencies
├── pyproject.toml     # Project configuration
├── Dockerfile         # Docker configuration
├── client_secrets.json # Google OAuth credentials (not in repo)
└── uploads/           # Temporary file storage
```

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Submit a pull request

## License

This project is open source and available under the [MIT License](LICENSE).

## Support

For issues and questions, please open an issue in the GitHub repository.

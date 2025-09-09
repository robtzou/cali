# 1. Start with an official Python base image
FROM python:3.11-slim

# 2. Set the working directory inside the container
WORKDIR /app

# 3. Install system dependencies using apt-get, including Tesseract
RUN apt-get update && apt-get install -y \
    tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*

# 4. Copy your requirements file into the container
COPY requirements.txt .

# 5. Install the Python packages
RUN pip install --no-cache-dir -r requirements.txt

# 6. Copy the rest of your application code into the container
COPY . .

# 7. Expose the port the app will run on
EXPOSE 10000

# 8. Define the command to run your app using Gunicorn
CMD ["gunicorn", "--workers", "1", "--bind", "0.0.0.0:10000", "app:app"]

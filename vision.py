# test_vision.py
from google.cloud import vision
client = vision.ImageAnnotatorClient()
with open("some-image.png", "rb") as f:
    img = vision.Image(content=f.read())
res = client.document_text_detection(image=img)
print(res.full_text_annotation.text if res.full_text_annotation else "(no text)")


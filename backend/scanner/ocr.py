import docx
import pytesseract
from   pdf2image import convert_from_path

def extract_text_from_pdf(pdf_path):
    """Converts a PDF to images and extracts text using Tesseract."""
    # Convert PDF pages to a list of PIL Image objects
    images = convert_from_path(pdf_path)
    full_text = ""

    # Loop through each image (page) and run OCR
    for image in images:
        text = pytesseract.image_to_string(image)
        full_text += text + "\n" # Add a newline to separate pages

        return full_text

def extract_text_from_docx(docx_path):
    """Extracts text directly from a DOCX file."""
    try:
        document = docx.Document(docx_path)
        full_text = []
        for para in document.paragraphs:
            full_text.append(para.text)
        return '\n'.join(full_text)
    except Exception as e:
        # Handle potential errors with corrupted DOCX files
        print(f"Error reading docx file: {e}")
        return
    
def get_text_from_file(file_path):
    """
    Checks file type and calls the appropriate text extraction function.
    """
    if file_path.lower().endswith('.pdf'):
        print(extract_text_from_pdf(file_path))
        return extract_text_from_pdf(file_path)

    elif file_path.lower().endswith('.docx'):
        print(extract_text_from_docx(file_path))
        return extract_text_from_docx(file_path)
    elif file_path.lower().endswith(('.png', '.jpg', '.jpeg')):
        # Handle simple image files directly with Tesseract
        return pytesseract.image_to_string(file_path)
    else:
        print("Unsupported file type")
        return ""
    
if __name__ == "__main__":
    get_text_from_file("uploads/inst326.docx")
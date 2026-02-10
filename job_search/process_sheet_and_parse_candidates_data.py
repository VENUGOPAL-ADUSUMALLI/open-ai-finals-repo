import re
from io import BytesIO
from collections import OrderedDict

import pdfplumber
import requests
from google.oauth2 import service_account
from googleapiclient.discovery import build

# ================= CONSTANTS =================
SERVICE_ACCOUNT_FILE = "/home/nitesh/open-ai-finals-repo/service_account.json"
SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]

SPREADSHEET_ID = "11-uzrMwaD1seWEOiuucp23L1F6ecS2pXpM0X6COpCJ0"
RANGE_NAME = "Sheet1!A1:Z1000"


# ================= HELPERS =================
def _extract_drive_id_helper(url):
    match = re.search(r"/file/d/([a-zA-Z0-9_-]+)", url)
    return match.group(1) if match else None


def _read_public_drive_file_helper(file_id):
    URL = "https://drive.google.com/uc?export=download"
    session = requests.Session()

    response = session.get(URL, params={"id": file_id}, stream=True)

    for k, v in response.cookies.items():
        if k.startswith("download_warning"):
            response = session.get(
                URL,
                params={"id": file_id, "confirm": v},
                stream=True
            )

    content = b""
    for chunk in response.iter_content(32768):
        if chunk:
            content += chunk

    return content


def _extract_pdf_text_helper(file_bytes):
    text = ""
    with pdfplumber.open(BytesIO(file_bytes)) as pdf:
        for page in pdf.pages:
            text += page.extract_text(layout=True) or ""
            text += "\n"
    return text


def _split_into_sections_helper(text):
    SECTION_TITLES = [
        "Quick overview",
        "Education",
        "Experience",
        "Projects",
        "Technical Skills",
        "Involvement",
        "Achievements",
        "Certifications",
        "Languages",
        "Interests"
    ]
    lines = [line.strip() for line in text.split("\n") if line.strip()]

    sections = OrderedDict()
    current_section = None

    for line in lines:
        for title in SECTION_TITLES:
            if line.lower() == title.lower():
                current_section = title
                sections[current_section] = []
                break
        else:
            if current_section:
                sections[current_section].append(line)

    return sections


# ================= GOOGLE SHEET =================
def fetch_rows_from_sheet():
    creds = service_account.Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE,
        scopes=SCOPES
    )

    service = build("sheets", "v4", credentials=creds)

    rows = service.spreadsheets().values().get(
        spreadsheetId=SPREADSHEET_ID,
        range=RANGE_NAME
    ).execute().get("values", [])

    return rows


# ================= RESUME PARSER =================
def parse_resume_from_drive_link(resume_link):
    if not resume_link.startswith("http"):
        raise ValueError("Invalid resume link")

    file_id = _extract_drive_id_helper(resume_link)
    if not file_id:
        raise ValueError("Not a valid Drive link")

    file_bytes = _read_public_drive_file_helper(file_id)
    raw_text = _extract_pdf_text_helper(file_bytes)

    return _split_into_sections_helper(raw_text)


# ================= MAIN LOGIC =================
def process_candidates():
    rows = fetch_rows_from_sheet()

    if not rows:
        print("❌ No data found in Google Sheet")
        return

    header = rows[0]
    resume_index = header.index("Resume Link")

    for row in rows[1:]:
        if len(row) <= resume_index:
            continue

        name = row[1]
        resume_link = row[resume_index]

        print("\n" + "=" * 70)
        print(f"Candidate: {name}")

        try:
            sections = parse_resume_from_drive_link(resume_link)

            print("\nStructured Resume Data:\n")
            for section, content in sections.items():
                print(section.upper())
                print("-" * len(section))
                for line in content:
                    print(line)
                print()

        except Exception as e:
            print("❌ Failed to process resume:", e)


# ================= ENTRY POINT =================
if __name__ == "__main__":
    process_candidates()

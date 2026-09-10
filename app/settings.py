import os

from dotenv import load_dotenv

load_dotenv()

# Absolute base URL of this app, used for links embedded in generated PDFs and
# Excel files (a client opening a quotation needs a full URL, not a relative one).
BASE_URL = os.getenv("BASE_URL", "https://app.candelauae.com").rstrip("/")

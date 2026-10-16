"""Download a datasheet PDF from a brand's link (pasted on the product page).

Only public http(s) addresses are fetched - never the server itself or the
local network - with a size cap and a timeout, and the result must really be
a PDF. Share links from Dropbox / Google Drive / OneDrive are turned into
their direct-download form.
"""
import ipaddress
import os
import re
import socket
import urllib.error
import urllib.parse
import urllib.request

from fastapi import HTTPException

MAX_BYTES = 60 * 1024 * 1024
TIMEOUT = 40
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"


def _bad(msg):
    raise HTTPException(status_code=400, detail=msg)


def _direct(url):
    """Share-page links -> direct download links."""
    m = re.match(r"https://drive\.google\.com/file/d/([^/]+)", url)
    if m:
        return f"https://drive.google.com/uc?export=download&id={m.group(1)}"
    if "dropbox.com" in url:
        return re.sub(r"([?&])dl=0", r"\1dl=1", url) if "dl=0" in url else url + ("&" if "?" in url else "?") + "dl=1"
    if "1drv.ms" in url or "onedrive.live.com" in url:
        return url + ("&" if "?" in url else "?") + "download=1"
    return url


def _check_host(url):
    p = urllib.parse.urlparse(url)
    if p.scheme not in ("http", "https") or not p.hostname:
        _bad("Paste a full link starting with https://")
    try:
        infos = socket.getaddrinfo(p.hostname, p.port or (443 if p.scheme == "https" else 80))
    except socket.gaierror:
        _bad("That website can't be found - check the link")
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast or ip.is_unspecified:
            _bad("That link points to a private address")


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


def fetch_pdf(url: str) -> tuple[bytes, str]:
    """(pdf bytes, file name) from a link, or HTTPException with a plain message."""
    url = _direct((url or "").strip())
    opener = urllib.request.build_opener(_NoRedirect)
    for _ in range(6):  # follow redirects ourselves, checking every hop
        _check_host(url)
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/pdf,*/*"})
        try:
            resp = opener.open(req, timeout=TIMEOUT)
        except urllib.error.HTTPError as e:
            if e.code in (301, 302, 303, 307, 308) and e.headers.get("Location"):
                url = urllib.parse.urljoin(url, e.headers["Location"])
                continue
            _bad(f"The brand's website answered with error {e.code} - check the link")
        except (urllib.error.URLError, TimeoutError, OSError):
            _bad("Couldn't reach that website - check the link or try again")
        with resp:
            data = resp.read(MAX_BYTES + 1)
            if len(data) > MAX_BYTES:
                _bad("That PDF is over 60 MB")
            if not data.lstrip()[:5].startswith(b"%PDF"):
                if b"<html" in data[:2000].lower() or "html" in (resp.headers.get("Content-Type") or ""):
                    _bad("That link opens a web page, not a PDF. On the brand's page, right-click the "
                         "datasheet / PDF button, choose 'Copy link address' and paste that.")
                _bad("That link isn't a PDF file")
            name = ""
            cd = resp.headers.get("Content-Disposition") or ""
            m = re.search(r'filename\*?=(?:UTF-8\'\')?"?([^";]+)', cd)
            if m:
                name = urllib.parse.unquote(m.group(1))
            if not name:
                name = os.path.basename(urllib.parse.urlparse(url).path) or "datasheet.pdf"
            if not name.lower().endswith(".pdf"):
                name += ".pdf"
            return data, name[:200]
    _bad("Too many redirects on that link")

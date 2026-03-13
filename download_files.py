#!/usr/bin/env python3
"""
Download all document folder attachments from RedTeam WO 1940046.
Uses correct zip URL format and individual file downloads as fallback.
"""

import requests
import json
import re
import base64
import os
import time
import urllib.parse

WO_ID = "1940046"
WO_MOD = "00"
NODE = "https://node.flex.redteam.com"
ASP_BASE = "https://flex.redteam.com/rts"
OUTPUT_DIR = "/home/user/RedTeam/wo_data/attachments"

# All document folders
FOLDERS = [
    ("Preconstruction", "VendorQuotes", "Quotes", "vendor_quotes"),
    ("Preconstruction", "CustomerProposals", "Proposal", "proposals"),
    ("Contracting", "ContractDocuments", "Contract", "contracts"),
    ("Contracting", "VendorCommitments", "CommitmentFiles", "vendor_commitments"),
    ("Contracting", "LienLawClaims", "LLDocuments", "lien_law_docs"),
    ("ChangeManagement", "CustomerChangeProposals", "ChangeProposal", "change_proposals"),
    ("ChangeManagement", "CustomerChangeOrders", "RCO", "change_orders"),
    ("SubmittalManagement", "ProjectSubmittals", "Deliverable", "submittals"),
    ("PerformanceManagement", "RequestforInformation", "RFI", "rfis"),
    ("PerformanceManagement", "Correspondence", "FOI_FYI", "correspondence"),
    ("PerformanceManagement", "MeetingMinutesAgendas", "MeetingAgenda", "meeting_agendas"),
    ("PerformanceManagement", "ScheduleUpdates", "Schedule", "schedule_updates"),
    ("JobsiteManagement", "RequestsforCorrection", "Punchlist", "punchlist_docs"),
    ("JobsiteManagement", "Photos", "Progress", "photos"),
    ("FinancialManagement", "CustomerBilling", "Invoice", "invoices"),
    ("FinancialManagement", "TMSheets", "TMSheets", "tm_sheets"),
    ("FinancialManagement", "VendorInvoices", "Disbursements", "vendor_invoices"),
    ("FinancialManagement", "EmployeeExpenses", "EmployeeExpenses", "employee_expenses"),
]


def create_session():
    session = requests.Session()
    r = session.post("https://auth.redteam.com/connect/login",
        json={"email": "bnobile@remnantconstruction.com", "password": "Boca5656**",
              "client_id": "1v7lfl5iq9i0ihdid56llerjf7",
              "redirect_uri": "https://id.redteam.com/callback"},
        timeout=15, allow_redirects=False)
    loc = r.headers["Location"]
    code = re.search(r"code=([^&]+)", loc).group(1)
    session.get(f"https://id.redteam.com/auth/callback?code={code}&state=test",
        timeout=15, allow_redirects=False)
    payload = json.dumps({"username": "bnobile", "password": "Boca5656*",
        "company": "remnantconstruction", "TA_UserID": "", "forzeNewSession": "X",
        "renewalPayLater": "", "attemptsSession": "0"})
    r = session.post(f"{NODE}/security/login", data=payload,
        headers={"Content-Type": "application/json"}, timeout=15)
    login_data = r.json()
    r2 = session.get(login_data["url"], timeout=15)
    data_match = re.search(r'"data":"([^"]+)"', r2.text)
    if data_match:
        session.post(f"{ASP_BASE}/app/asp/rtssessionstart/startapp.asp",
            data={"data": data_match.group(1)}, timeout=15)
    print("[+] Session ready")
    return session


def get_folder_files(session, txt_folder, txt_itemfolder, doctype):
    """Get file listing for a specific folder."""
    param_str = (f"DocumentFolderID=&txt_folder={txt_folder}&txt_itemfolder={txt_itemfolder}"
                 f"&doctype={doctype}&WorkorderID={WO_ID}&WorkorderMod={WO_MOD}"
                 f"&vFiles=&OpenLink=&searchKeyword=")
    encoded = base64.b64encode(param_str.encode()).decode()
    url = f"{ASP_BASE}/app/asp/LinkWorkorderAttachmentsGetFolder.asp?p={encoded}"
    try:
        r = session.post(url, timeout=120)
        if r.status_code != 200:
            return [], ""
        return parse_folder_html(r.text, doctype), r.text
    except Exception as e:
        print(f"    Error: {e}")
        return [], ""


def parse_folder_html(html, doctype):
    """Extract file info from folder HTML, including download URLs."""
    files = []

    # Extract UploadID/FileSize hidden inputs
    upload_ids = re.findall(r'id=["\']UploadID(\d+)["\'][^>]*value=["\'](\d+)["\']', html)
    file_sizes = {}
    for idx, uid in upload_ids:
        size_match = re.search(rf'id=["\']FileSize{idx}["\'][^>]*value=["\']([^"\']+)["\']', html)
        size = size_match.group(1) if size_match else "0"
        file_sizes[idx] = (uid, size)

    # Extract openImage params for file details
    img_calls = re.findall(r"openImage\('([^']+)'\)", html)
    file_details = {}
    for i, call in enumerate(img_calls):
        try:
            padded = call + '=' * (4 - len(call) % 4) if len(call) % 4 else call
            decoded = base64.b64decode(padded).decode()
            params = dict(re.findall(r'([^&=]+)=([^&]*)', decoded))
            file_details[str(i+1)] = params
        except:
            pass

    for idx, (uid, size) in file_sizes.items():
        details = file_details.get(idx, {})
        name = details.get('descAttach', details.get('FileName', f'file_{uid}'))
        filename = details.get('FileName', '')
        uploads_folder = details.get('UploadsFolder', '')
        ext = details.get('FileExtenssion', '')

        files.append({
            "upload_id": uid,
            "size": size,
            "name": name,
            "filename": filename,
            "uploads_folder": uploads_folder,
            "ext": ext,
            "index": idx,
        })

    return files


def download_zip(session, upload_ids, doctype, label, batch_num=1):
    """Create and download zip using correct URL format."""
    items_str = ",".join(upload_ids) + ","

    # Correct URL format matching the JavaScript DownloadSelected function
    zip_url = (
        f"{ASP_BASE}/app/asp/CreateTemporaryZipInS3.asp?"
        f"WorkorderId={WO_ID}&WorkorderMod={WO_MOD}"
        f"&zipfiles=true&zipWorkorderMod={WO_MOD}&woStatus=00"
        f"&docType={urllib.parse.quote(doctype)}&itemsDown={items_str}"
    )

    print(f"  Creating zip: {label} batch {batch_num} ({len(upload_ids)} files)...")
    try:
        r = session.get(zip_url, timeout=120)
        resp_text = r.text.strip()
        print(f"    Response ({r.status_code}): {resp_text[:300]}")

        # Parse response
        destination = ""
        try:
            zip_data = r.json()
            destination = zip_data.get("destination", "")
            if not destination:
                # Check for other fields
                print(f"    JSON keys: {list(zip_data.keys())}")
        except:
            dest_match = re.search(r'"destination"\s*:\s*"([^"]+)"', resp_text)
            if dest_match:
                destination = dest_match.group(1)

        if not destination:
            print(f"    No destination found")
            return False

        # Poll for download
        encoded_dest = urllib.parse.quote(destination, safe="")
        download_url = f"{NODE}/files/specs.redteamsoftware.com/{encoded_dest}"
        print(f"    Polling: {download_url[:100]}...")

        for attempt in range(15):
            time.sleep(5)
            try:
                dr = session.get(download_url, timeout=120, stream=True)
                content_length = int(dr.headers.get('content-length', 0))
                if dr.status_code == 200 and content_length > 100:
                    outpath = os.path.join(OUTPUT_DIR, f"{label}_batch_{batch_num}.zip")
                    with open(outpath, 'wb') as f:
                        for chunk in dr.iter_content(chunk_size=65536):
                            f.write(chunk)
                    size = os.path.getsize(outpath)
                    print(f"    OK: {outpath} ({size:,} bytes)")
                    return True
                elif dr.status_code == 404:
                    print(f"    Attempt {attempt+1}: not ready yet")
                else:
                    # Read content to check
                    content = dr.content
                    if len(content) > 100:
                        outpath = os.path.join(OUTPUT_DIR, f"{label}_batch_{batch_num}.zip")
                        with open(outpath, 'wb') as f:
                            f.write(content)
                        print(f"    OK: {outpath} ({len(content):,} bytes)")
                        return True
                    print(f"    Attempt {attempt+1}: status={dr.status_code}, size={len(content)}")
            except Exception as e:
                print(f"    Attempt {attempt+1}: {e}")

        return False

    except Exception as e:
        print(f"    Error: {e}")
        return False


def download_individual(session, files, label):
    """Download files individually via openImage/direct URL."""
    outdir = os.path.join(OUTPUT_DIR, label)
    os.makedirs(outdir, exist_ok=True)

    downloaded = 0
    for f in files:
        uid = f["upload_id"]
        filename = f.get("filename", "")
        uploads_folder = f.get("uploads_folder", "")
        name = f.get("name", f"file_{uid}")

        if not filename:
            continue

        # Try S3 direct download
        s3_path = f"{uploads_folder}/{filename}" if uploads_folder else filename
        url = f"{NODE}/files/specs.redteamsoftware.com/uploads/{urllib.parse.quote(s3_path)}"

        try:
            r = session.get(url, timeout=60)
            if r.status_code == 200 and len(r.content) > 0:
                safe_name = re.sub(r'[<>:"/\\|?*]', '_', filename)
                outpath = os.path.join(outdir, safe_name)
                with open(outpath, 'wb') as fo:
                    fo.write(r.content)
                downloaded += 1
                if downloaded % 10 == 0:
                    print(f"    Downloaded {downloaded}/{len(files)}")
                continue
        except:
            pass

    print(f"    Individual downloads: {downloaded}/{len(files)}")
    return downloaded


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    session = create_session()

    # First: test zip with a small folder (vendor_quotes - 6 files)
    print("\n=== Testing zip download with vendor_quotes ===")
    test_files, test_html = get_folder_files(session, "Preconstruction", "VendorQuotes", "Quotes")
    print(f"Found {len(test_files)} files")

    if test_files:
        # Save file listing
        with open(os.path.join(OUTPUT_DIR, "folder_vendor_quotes_files.json"), 'w') as f:
            json.dump(test_files, f, indent=2)

        upload_ids = [f["upload_id"] for f in test_files]
        success = download_zip(session, upload_ids, "Quotes", "vendor_quotes")

        if not success:
            print("\n  Zip failed, trying individual downloads...")
            session = create_session()
            download_individual(session, test_files, "vendor_quotes")

    # Now process all remaining folders
    results = {}
    for txt_folder, txt_itemfolder, doctype, label in FOLDERS:
        if label == "vendor_quotes":
            continue  # already done

        print(f"\n=== {label} ({txt_folder}/{txt_itemfolder}) ===")

        # Load file list from cached JSON if available
        cache_file = os.path.join(OUTPUT_DIR, f"folder_{label}_files.json")
        if os.path.exists(cache_file):
            with open(cache_file) as f:
                files = json.load(f)
            print(f"  Loaded {len(files)} files from cache")
        else:
            files, html = get_folder_files(session, txt_folder, txt_itemfolder, doctype)
            print(f"  Found {len(files)} files")
            if files:
                with open(cache_file, 'w') as f:
                    json.dump(files, f, indent=2)
            if html:
                with open(os.path.join(OUTPUT_DIR, f"folder_{label}.html"), 'w') as f:
                    f.write(html)

        if not files:
            results[label] = {"found": 0, "downloaded": 0}
            continue

        # Try zip download first
        upload_ids = [f["upload_id"] for f in files]
        batch_size = 50
        total_downloaded = 0
        zip_worked = True

        for i in range(0, len(upload_ids), batch_size):
            batch = upload_ids[i:i+batch_size]
            batch_num = (i // batch_size) + 1

            if i > 0:
                session = create_session()

            if not download_zip(session, batch, doctype, label, batch_num):
                zip_worked = False
                break

            total_downloaded += len(batch)

        if not zip_worked:
            # Fall back to individual downloads
            print(f"  Zip failed, trying individual downloads for {label}...")
            session = create_session()
            total_downloaded = download_individual(session, files, label)

        results[label] = {"found": len(files), "downloaded": total_downloaded}

    # Summary
    print("\n" + "="*60)
    print("FINAL SUMMARY")
    print("="*60)
    for label, data in results.items():
        print(f"  {label}: {data['found']} found, {data['downloaded']} downloaded")

    # List all files
    print("\nAll downloaded files:")
    for root, dirs, filenames in os.walk(OUTPUT_DIR):
        for fn in sorted(filenames):
            fp = os.path.join(root, fn)
            size = os.path.getsize(fp)
            rel = os.path.relpath(fp, OUTPUT_DIR)
            if size > 0:
                print(f"  {rel}: {size:,} bytes")


if __name__ == "__main__":
    main()

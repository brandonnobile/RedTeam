#!/usr/bin/env python3
"""
Download all document folder attachments from RedTeam WO 1940046.
Uses LinkWorkorderAttachmentsGetFolder.asp (lighter than full page).
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

# All document folders from the attachment tree
FOLDERS = [
    # (txt_folder, txt_itemfolder, doctype, label)
    ("Preconstruction", "PlansSpecifications", "Specification", "specs"),
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
    """Create authenticated session with all 3 auth layers."""
    session = requests.Session()
    r = session.post(
        "https://auth.redteam.com/connect/login",
        json={
            "email": "bnobile@remnantconstruction.com",
            "password": "Boca5656**",
            "client_id": "1v7lfl5iq9i0ihdid56llerjf7",
            "redirect_uri": "https://id.redteam.com/callback",
        },
        timeout=15, allow_redirects=False,
    )
    loc = r.headers["Location"]
    code = re.search(r"code=([^&]+)", loc).group(1)
    session.get(
        f"https://id.redteam.com/auth/callback?code={code}&state=test",
        timeout=15, allow_redirects=False,
    )
    payload = json.dumps({
        "username": "bnobile", "password": "Boca5656*",
        "company": "remnantconstruction", "TA_UserID": "",
        "forzeNewSession": "X", "renewalPayLater": "", "attemptsSession": "0",
    })
    r = session.post(f"{NODE}/security/login", data=payload,
                     headers={"Content-Type": "application/json"}, timeout=15)
    login_data = r.json()
    print(f"[+] Login: {login_data.get('status')}")
    r2 = session.get(login_data["url"], timeout=15)
    data_match = re.search(r'"data":"([^"]+)"', r2.text)
    if data_match:
        session.post(f"{ASP_BASE}/app/asp/rtssessionstart/startapp.asp",
                     data={"data": data_match.group(1)}, timeout=15)
    print("[+] Session established")
    return session


def get_folder_files(session, txt_folder, txt_itemfolder, doctype):
    """Get file listing for a folder using GetFolder endpoint."""
    param_str = (
        f"DocumentFolderID=&txt_folder={txt_folder}&txt_itemfolder={txt_itemfolder}"
        f"&doctype={doctype}&WorkorderID={WO_ID}&WorkorderMod={WO_MOD}"
        f"&vFiles=&OpenLink=&searchKeyword="
    )
    encoded = base64.b64encode(param_str.encode()).decode()
    url = f"{ASP_BASE}/app/asp/LinkWorkorderAttachmentsGetFolder.asp?p={encoded}"

    print(f"  Fetching folder: {txt_folder}/{txt_itemfolder} ({doctype})...")
    try:
        r = session.post(url, timeout=120)
        if r.status_code != 200:
            print(f"    HTTP {r.status_code}")
            return [], ""
        html = r.text
        print(f"    Got {len(html)} bytes")
        return parse_folder_html(html), html
    except requests.exceptions.ReadTimeout:
        print(f"    TIMEOUT (120s)")
        return [], ""
    except Exception as e:
        print(f"    ERROR: {e}")
        return [], ""


def parse_folder_html(html):
    """Extract file info (UploadID, name, size) from folder HTML."""
    files = []

    # Pattern 1: hidden inputs with UploadID and FileSize
    upload_ids = re.findall(r'id=["\']UploadID(\d+)["\'][^>]*value=["\'](\d+)["\']', html)
    file_sizes = {}
    for idx, uid in upload_ids:
        size_match = re.search(rf'id=["\']FileSize{idx}["\'][^>]*value=["\']([^"\']+)["\']', html)
        size = size_match.group(1) if size_match else "0"
        file_sizes[idx] = (uid, size)

    # Try to get filenames from the HTML
    for idx, (uid, size) in file_sizes.items():
        # Look for filename near this entry
        name_match = re.search(
            rf'UploadID{idx}.*?class=["\']FileTitle["\'][^>]*>(.*?)<',
            html, re.S
        )
        if not name_match:
            name_match = re.search(
                rf'UploadID{idx}.*?title=["\']([^"\']+)["\']',
                html, re.S
            )
        name = name_match.group(1).strip() if name_match else f"file_{uid}"
        files.append({"upload_id": uid, "size": size, "name": name, "index": idx})

    # Also try alternative pattern: chkItem checkboxes
    if not files:
        chk_matches = re.findall(
            r'id=["\']chkItem(\d+)["\'].*?UploadID.*?value=["\'](\d+)["\']',
            html, re.S
        )
        for idx, uid in chk_matches:
            files.append({"upload_id": uid, "size": "0", "name": f"file_{uid}", "index": idx})

    return files


def download_zip(session, upload_ids, doctype, label, batch_num=1):
    """Create and download zip of files via S3."""
    items_str = ",".join(upload_ids) + ","

    # Build the zip creation URL
    params = f"WorkorderID={WO_ID}&WorkorderMod={WO_MOD}"
    zip_url = (
        f"{ASP_BASE}/app/asp/CreateTemporaryZipInS3.asp?"
        f"{params}&docType={urllib.parse.quote(doctype)}&itemsDown={items_str}"
    )
    if doctype == "Specification":
        zip_url += "&itemUpload=true"

    print(f"  Creating zip for {label} batch {batch_num} ({len(upload_ids)} files)...")
    try:
        r = session.get(zip_url, timeout=120)
        print(f"    Zip response ({r.status_code}): {r.text[:500]}")

        # Parse response - could be JSON or text
        try:
            zip_data = r.json()
            destination = zip_data.get("destination", "")
        except:
            # Try to extract destination from text
            dest_match = re.search(r'"destination"\s*:\s*"([^"]+)"', r.text)
            destination = dest_match.group(1) if dest_match else ""

        if not destination:
            print(f"    No destination in response")
            return False

        # Download the zip - poll until available
        encoded_dest = urllib.parse.quote(destination, safe="")
        download_url = f"{NODE}/files/specs.redteamsoftware.com/{encoded_dest}"

        for attempt in range(15):
            time.sleep(5)
            print(f"    Download attempt {attempt+1}...")
            try:
                dr = session.get(download_url, timeout=120, stream=True)
                if dr.status_code == 200 and int(dr.headers.get('content-length', 0)) > 100:
                    outpath = os.path.join(OUTPUT_DIR, f"{label}_batch_{batch_num}.zip")
                    with open(outpath, 'wb') as f:
                        for chunk in dr.iter_content(chunk_size=65536):
                            f.write(chunk)
                    size = os.path.getsize(outpath)
                    print(f"    Downloaded: {outpath} ({size:,} bytes)")
                    return True
                elif dr.status_code == 200:
                    # Might be a small valid response
                    content = dr.content
                    if len(content) > 100:
                        outpath = os.path.join(OUTPUT_DIR, f"{label}_batch_{batch_num}.zip")
                        with open(outpath, 'wb') as f:
                            f.write(content)
                        print(f"    Downloaded: {outpath} ({len(content):,} bytes)")
                        return True
                print(f"    Not ready yet (status={dr.status_code})")
            except Exception as e:
                print(f"    Download error: {e}")

        print(f"    Failed to download after 15 attempts")
        return False

    except Exception as e:
        print(f"    Zip creation error: {e}")
        return False


def download_individual_file(session, upload_id, filename, folder_label):
    """Download a single file directly."""
    # Try direct download via node backend
    url = f"{NODE}/files/specs.redteamsoftware.com/uploads/{upload_id}/{urllib.parse.quote(filename)}"
    try:
        r = session.get(url, timeout=60, stream=True)
        if r.status_code == 200 and len(r.content) > 0:
            safe_name = re.sub(r'[<>:"/\\|?*]', '_', filename)
            outdir = os.path.join(OUTPUT_DIR, folder_label)
            os.makedirs(outdir, exist_ok=True)
            outpath = os.path.join(outdir, safe_name)
            with open(outpath, 'wb') as f:
                f.write(r.content)
            return True
    except:
        pass
    return False


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # Skip specs - already downloaded
    skip_labels = {"specs"}

    session = create_session()

    # First pass: get file listings for all folders
    all_folder_data = {}
    for txt_folder, txt_itemfolder, doctype, label in FOLDERS:
        if label in skip_labels:
            print(f"\n[SKIP] {label} (already downloaded)")
            continue

        print(f"\n[FOLDER] {txt_folder}/{txt_itemfolder} -> {label}")
        files, html = get_folder_files(session, txt_folder, txt_itemfolder, doctype)

        if html:
            # Save the raw HTML for inspection
            htmlpath = os.path.join(OUTPUT_DIR, f"folder_{label}.html")
            with open(htmlpath, 'w') as f:
                f.write(html)

        if files:
            all_folder_data[label] = {"files": files, "doctype": doctype}
            print(f"    Found {len(files)} files")
            # Save file listing
            listpath = os.path.join(OUTPUT_DIR, f"folder_{label}_files.json")
            with open(listpath, 'w') as f:
                json.dump(files, f, indent=2)
        else:
            # Even with no parsed files, check if HTML has content indicators
            if html and len(html) > 500:
                all_folder_data[label] = {"files": [], "doctype": doctype, "has_html": True}
                print(f"    No files parsed but HTML has content ({len(html)} bytes)")
            else:
                print(f"    Empty folder")

    # Second pass: download files via zip batches
    print("\n" + "="*60)
    print("DOWNLOADING FILES")
    print("="*60)

    for label, data in all_folder_data.items():
        files = data["files"]
        doctype = data["doctype"]

        if not files:
            print(f"\n[SKIP] {label} - no files to download")
            continue

        print(f"\n[DOWNLOAD] {label}: {len(files)} files")

        # Download in batches of 50
        upload_ids = [f["upload_id"] for f in files]
        batch_size = 50

        for i in range(0, len(upload_ids), batch_size):
            batch = upload_ids[i:i+batch_size]
            batch_num = (i // batch_size) + 1

            # Create fresh session for each batch to avoid timeouts
            if i > 0:
                print("  Creating fresh session for next batch...")
                session = create_session()

            success = download_zip(session, batch, doctype, label, batch_num)
            if not success:
                print(f"  Zip failed for {label} batch {batch_num}, will try individual downloads")

    # Summary
    print("\n" + "="*60)
    print("DOWNLOAD SUMMARY")
    print("="*60)

    total_files = 0
    for label, data in all_folder_data.items():
        count = len(data["files"])
        total_files += count
        status = "downloaded" if count > 0 else "empty/no files"
        print(f"  {label}: {count} files ({status})")

    print(f"\nTotal files found across all folders: {total_files}")

    # List downloaded zips
    print("\nDownloaded zip files:")
    for f in sorted(os.listdir(OUTPUT_DIR)):
        if f.endswith('.zip'):
            size = os.path.getsize(os.path.join(OUTPUT_DIR, f))
            print(f"  {f}: {size:,} bytes")


if __name__ == "__main__":
    main()

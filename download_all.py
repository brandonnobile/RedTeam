#!/usr/bin/env python3
"""
Download ALL document attachments from RedTeam WO 1940046.
Direct file downloads from flex.redteam.com/TS/CompaniesTS/remnantconstruction/Uploads/
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
FILE_BASE = "https://flex.redteam.com/TS/CompaniesTS/remnantconstruction/Uploads"
OUTPUT_DIR = "/home/user/RedTeam/wo_data/attachments"

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
    code = re.search(r"code=([^&]+)", r.headers["Location"]).group(1)
    session.get(f"https://id.redteam.com/auth/callback?code={code}&state=test",
        timeout=15, allow_redirects=False)
    r = session.post(f"{NODE}/security/login",
        data=json.dumps({"username": "bnobile", "password": "Boca5656*",
            "company": "remnantconstruction", "TA_UserID": "", "forzeNewSession": "X",
            "renewalPayLater": "", "attemptsSession": "0"}),
        headers={"Content-Type": "application/json"}, timeout=15)
    login_data = r.json()
    r2 = session.get(login_data["url"], timeout=15)
    m = re.search(r'"data":"([^"]+)"', r2.text)
    if m:
        session.post(f"{ASP_BASE}/app/asp/rtssessionstart/startapp.asp",
            data={"data": m.group(1)}, timeout=15)
    print("[+] Session ready")
    return session


def get_folder_files(session, txt_folder, txt_itemfolder, doctype):
    """Get file listing for a folder via GetFolder endpoint."""
    param_str = (f"DocumentFolderID=&txt_folder={txt_folder}&txt_itemfolder={txt_itemfolder}"
                 f"&doctype={doctype}&WorkorderID={WO_ID}&WorkorderMod={WO_MOD}"
                 f"&vFiles=&OpenLink=&searchKeyword=")
    encoded = base64.b64encode(param_str.encode()).decode()
    url = f"{ASP_BASE}/app/asp/LinkWorkorderAttachmentsGetFolder.asp?p={encoded}"
    try:
        r = session.post(url, timeout=120)
        if r.status_code != 200:
            return []
        return parse_files_from_html(r.text, doctype)
    except Exception as e:
        print(f"    Folder fetch error: {e}")
        return []


def parse_files_from_html(html, doctype):
    """Extract file details from folder HTML using openImage params."""
    files = []
    img_calls = re.findall(r"openImage\('([^']+)'\)", html)

    for call in img_calls:
        try:
            padded = call + '=' * (4 - len(call) % 4) if len(call) % 4 else call
            decoded = base64.b64decode(padded).decode()
            params = dict(re.findall(r'([^&=]+)=([^&]*)', decoded))
            files.append({
                "upload_id": params.get("UploadID", ""),
                "filename": params.get("FileName", ""),
                "uploads_folder": params.get("UploadsFolder", ""),
                "description": params.get("descAttach", ""),
                "ext": params.get("FileExtenssion", ""),
                "doctype": params.get("doctype", doctype),
                "b64_param": call,
            })
        except Exception as e:
            continue

    # Deduplicate by upload_id
    seen = set()
    unique = []
    for f in files:
        uid = f["upload_id"]
        if uid and uid not in seen:
            seen.add(uid)
            unique.append(f)

    return unique


def download_file_direct(session, file_info, outdir):
    """Download a single file directly from the TS uploads directory."""
    folder = file_info["uploads_folder"]
    filename = file_info["filename"]
    if not filename:
        return False

    url = f"{FILE_BASE}/{urllib.parse.quote(folder)}/{urllib.parse.quote(filename)}"
    safe_name = re.sub(r'[<>:"/\\|?*]', '_', filename)
    outpath = os.path.join(outdir, safe_name)

    if os.path.exists(outpath) and os.path.getsize(outpath) > 0:
        return True  # Already downloaded

    try:
        r = session.get(url, timeout=60, stream=True)
        if r.status_code == 200:
            with open(outpath, 'wb') as f:
                for chunk in r.iter_content(chunk_size=65536):
                    f.write(chunk)
            size = os.path.getsize(outpath)
            if size > 0:
                return True
            else:
                os.remove(outpath)
    except Exception as e:
        pass
    return False


def download_file_via_viewer(session, file_info, outdir):
    """Download by loading the viewer page and extracting the direct URL."""
    param = file_info.get("b64_param", "")
    if not param:
        return False

    url = f"{ASP_BASE}/app/asp/LinkWorkorderAttachmentsImages.asp?p={param}"
    try:
        r = session.get(url, timeout=30)
        if r.status_code != 200:
            return False

        # Find download URL in viewer page
        dl_match = re.search(r'href="(https?://[^"]+\?download=true)"', r.text)
        if not dl_match:
            dl_match = re.search(r'object\s+data="(https?://[^"]+)"', r.text)
        if not dl_match:
            dl_match = re.search(r'src="(https?://flex\.redteam\.com/TS/[^"]+)"', r.text)

        if dl_match:
            file_url = dl_match.group(1)
            filename = file_info.get("filename", "") or file_url.split("/")[-1].split("?")[0]
            safe_name = re.sub(r'[<>:"/\\|?*]', '_', filename)
            outpath = os.path.join(outdir, safe_name)

            if os.path.exists(outpath) and os.path.getsize(outpath) > 0:
                return True

            r2 = session.get(file_url, timeout=60, stream=True)
            if r2.status_code == 200:
                with open(outpath, 'wb') as f:
                    for chunk in r2.iter_content(chunk_size=65536):
                        f.write(chunk)
                if os.path.getsize(outpath) > 0:
                    return True
                os.remove(outpath)
    except Exception as e:
        pass
    return False


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    session = create_session()

    total_found = 0
    total_downloaded = 0
    results = {}

    for txt_folder, txt_itemfolder, doctype, label in FOLDERS:
        print(f"\n{'='*60}")
        print(f"[{label}] {txt_folder}/{txt_itemfolder}")
        print(f"{'='*60}")

        outdir = os.path.join(OUTPUT_DIR, label)
        os.makedirs(outdir, exist_ok=True)

        # Check for cached file listing
        cache_file = os.path.join(OUTPUT_DIR, f"folder_{label}_details.json")
        if os.path.exists(cache_file):
            with open(cache_file) as f:
                files = json.load(f)
            print(f"  Loaded {len(files)} files from cache")
        else:
            files = get_folder_files(session, txt_folder, txt_itemfolder, doctype)
            print(f"  Found {len(files)} files")
            if files:
                with open(cache_file, 'w') as f:
                    json.dump(files, f, indent=2)

        total_found += len(files)

        if not files:
            results[label] = {"found": 0, "downloaded": 0}
            continue

        # Download files - try direct first, then viewer
        downloaded = 0
        failed = []
        for i, file_info in enumerate(files):
            if download_file_direct(session, file_info, outdir):
                downloaded += 1
            else:
                failed.append(file_info)

            if (i + 1) % 25 == 0:
                print(f"  Progress: {i+1}/{len(files)} processed, {downloaded} downloaded")

        # Retry failed ones via viewer page (slower but more reliable)
        if failed:
            print(f"  Retrying {len(failed)} files via viewer page...")
            for file_info in failed:
                if download_file_via_viewer(session, file_info, outdir):
                    downloaded += 1

        print(f"  Result: {downloaded}/{len(files)} downloaded")
        total_downloaded += downloaded
        results[label] = {"found": len(files), "downloaded": downloaded}

        # Refresh session every few folders
        if total_downloaded > 0 and total_downloaded % 200 == 0:
            print("  Refreshing session...")
            session = create_session()

    # Final summary
    print(f"\n{'='*60}")
    print("FINAL SUMMARY")
    print(f"{'='*60}")
    for label, data in results.items():
        status = "OK" if data["downloaded"] == data["found"] else f"PARTIAL ({data['downloaded']}/{data['found']})"
        if data["found"] == 0:
            status = "empty"
        print(f"  {label}: {data['found']} files - {status}")

    print(f"\nTotal: {total_downloaded}/{total_found} files downloaded")

    # Disk usage
    total_size = 0
    file_count = 0
    for root, dirs, filenames in os.walk(OUTPUT_DIR):
        for fn in filenames:
            fp = os.path.join(root, fn)
            s = os.path.getsize(fp)
            total_size += s
            file_count += 1
    print(f"Disk: {file_count} files, {total_size/1024/1024:.1f} MB")


if __name__ == "__main__":
    main()

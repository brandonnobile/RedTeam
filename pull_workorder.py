#!/usr/bin/env python3
"""
Pull ALL data from RedTeam Flex work order 1940046.
Authenticates, then scrapes every tab and attachment.
"""

import requests
import json
import re
import base64
import os
from html.parser import HTMLParser

WO_ID = "1940046"
WO_MOD = "00"
WO_STATUS = "InProgress"
FACILITY_ID = "00221"
OUTPUT_DIR = "/home/user/RedTeam/wo_data"

NODE = "https://node.flex.redteam.com"
ASP_BASE = "https://flex.redteam.com/rts"


class TableExtractor(HTMLParser):
    """Extract table data from HTML."""
    def __init__(self):
        super().__init__()
        self.tables = []
        self.current_table = None
        self.current_row = None
        self.current_cell = ""
        self.in_cell = False
        self.in_table = False
        self.cell_tag = None

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            self.in_table = True
            self.current_table = []
        elif tag in ("td", "th") and self.in_table:
            self.in_cell = True
            self.current_cell = ""
            self.cell_tag = tag
        elif tag == "tr" and self.in_table:
            self.current_row = []

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self.in_cell:
            self.in_cell = False
            if self.current_row is not None:
                self.current_row.append(self.current_cell.strip())
        elif tag == "tr" and self.current_row is not None and self.in_table:
            if self.current_row:
                self.current_table.append(self.current_row)
            self.current_row = None
        elif tag == "table" and self.in_table:
            if self.current_table:
                self.tables.append(self.current_table)
            self.current_table = None
            self.in_table = False

    def handle_data(self, data):
        if self.in_cell:
            self.current_cell += data


def extract_tables(html):
    """Extract all tables from HTML as list of list of lists."""
    parser = TableExtractor()
    parser.feed(html)
    return parser.tables


def extract_links(html):
    """Extract all href links from HTML."""
    return re.findall(r'href=["\']([^"\']+)["\']', html)


def extract_img_srcs(html):
    """Extract all image sources from HTML."""
    return re.findall(r'src=["\']([^"\']+\.(?:jpg|jpeg|png|gif|bmp|pdf|doc|docx|xls|xlsx))["\']', html, re.I)


def b64_params(**kwargs):
    """Create base64-encoded parameter string like the SPA does."""
    parts = "&".join(f"{k}={v}" for k, v in kwargs.items())
    return base64.b64encode(parts.encode()).decode()


def create_session():
    """Create authenticated session with all 3 auth layers."""
    session = requests.Session()

    # Step 1: OAuth/Cognito login
    r = session.post(
        "https://auth.redteam.com/connect/login",
        json={
            "email": "bnobile@remnantconstruction.com",
            "password": "Boca5656**",
            "client_id": "1v7lfl5iq9i0ihdid56llerjf7",
            "redirect_uri": "https://id.redteam.com/callback",
        },
        timeout=15,
        allow_redirects=False,
    )
    loc = r.headers["Location"]
    code = re.search(r"code=([^&]+)", loc).group(1)
    session.get(
        f"https://id.redteam.com/auth/callback?code={code}&state=test",
        timeout=15,
        allow_redirects=False,
    )

    # Step 2: Legacy node backend login
    payload = json.dumps({
        "username": "bnobile",
        "password": "Boca5656*",
        "company": "remnantconstruction",
        "TA_UserID": "",
        "forzeNewSession": "X",
        "renewalPayLater": "",
        "attemptsSession": "0",
    })
    r = session.post(
        f"{NODE}/security/login",
        data=payload,
        headers={"Content-Type": "application/json"},
        timeout=15,
    )
    login_data = r.json()
    print(f"[+] Login: {login_data.get('status')}")

    # Step 3: ASP session establishment
    r2 = session.get(login_data["url"], timeout=15)
    data_match = re.search(r'"data":"([^"]+)"', r2.text)
    if data_match:
        session.post(
            f"{ASP_BASE}/app/asp/rtssessionstart/startapp.asp",
            data={"data": data_match.group(1)},
            timeout=15,
        )
    print("[+] Session established")
    return session


def save_json(data, filename):
    """Save data as JSON file."""
    filepath = os.path.join(OUTPUT_DIR, filename)
    with open(filepath, "w") as f:
        json.dump(data, f, indent=2, default=str)
    print(f"  Saved {filepath} ({os.path.getsize(filepath)} bytes)")


def save_html(html, filename):
    """Save raw HTML."""
    filepath = os.path.join(OUTPUT_DIR, filename)
    with open(filepath, "w") as f:
        f.write(html)
    print(f"  Saved {filepath} ({os.path.getsize(filepath)} bytes)")


def save_text(text, filename):
    """Save as text file."""
    filepath = os.path.join(OUTPUT_DIR, filename)
    with open(filepath, "w") as f:
        f.write(text)
    print(f"  Saved {filepath} ({os.path.getsize(filepath)} bytes)")


def pull_node_data(s):
    """Pull data from node backend API endpoints."""
    results = {}

    # Basic WO info (full record from list)
    print("\n[*] Pulling workorder list data...")
    r = s.post(f"{NODE}/workorders", json={"WorkorderMod": "00"}, timeout=15)
    all_wos = r.json()
    for wo in all_wos.get("aaData", []):
        if wo.get("WorkorderID") == WO_ID:
            results["workorder_detail"] = wo
            break
    save_json(results.get("workorder_detail", {}), "01_workorder_detail.json")

    # Basic WO info
    r = s.get(f"{NODE}/workorders/{WO_ID}", timeout=10)
    results["workorder_basic"] = r.json()
    save_json(results["workorder_basic"], "01_workorder_basic.json")

    # Home menu (all available sections)
    print("[*] Pulling home menu...")
    r = s.get(f"{NODE}/workorders/home/id/{WO_ID}/mod/{WO_MOD}", timeout=10)
    results["home_menu"] = r.json()
    save_json(results["home_menu"], "02_home_menu.json")

    # Tabs
    print("[*] Pulling tabs config...")
    r = s.post(
        f"{NODE}/tabs",
        json={
            "TabGroupID": "Workorders",
            "Level": "L1.1.1",
            "UserID": 1,
            "WorkorderID": WO_ID,
            "WorkorderMod": WO_MOD,
        },
        headers={"Content-Type": "application/json"},
        timeout=10,
    )
    results["tabs"] = r.json()
    save_json(results["tabs"], "02_tabs.json")

    # Contacts for this WO
    print("[*] Pulling contacts...")
    r = s.get(f"{NODE}/contacts/{WO_ID}", timeout=10)
    results["contacts"] = r.json()
    save_json(results["contacts"], "03_contacts.json")

    # All contacts
    r = s.post(f"{NODE}/contacts", json={}, timeout=15)
    results["all_contacts"] = r.json()
    save_json(results["all_contacts"], "03_all_contacts.json")

    # Spreadsheets
    r = s.get(f"{NODE}/workorders/id/{WO_ID}/mod/{WO_MOD}/spreadsheets", timeout=10)
    results["spreadsheets"] = r.json()
    save_json(results["spreadsheets"], "04_spreadsheets.json")

    # Session info
    r = s.get(f"{NODE}/security/infoSession", timeout=10)
    results["session_info"] = r.json()
    save_json(results["session_info"], "00_session_info.json")

    # Employee prefs
    r = s.get(f"{NODE}/employees/0", timeout=10)
    results["employee"] = r.json()
    save_json(results["employee"], "00_employee.json")

    # Status/SubStatus dropdowns
    r = s.get(f"{NODE}/workorders/cboStatus", timeout=10)
    results["statuses"] = r.json()

    r = s.get(f"{NODE}/workorders/cboSubStatus", timeout=10)
    results["sub_statuses"] = r.json()

    r = s.get(f"{NODE}/workorders/cboProjectManagers", timeout=10)
    results["project_managers"] = r.json()

    return results


def pull_asp_pages(s):
    """Pull data from ASP pages (the actual tab content)."""

    p = b64_params(
        WorkorderID=WO_ID,
        WorkorderMod=WO_MOD,
        WorkorderStatus=WO_STATUS,
        FacilityID=FACILITY_ID,
    )
    p2 = b64_params(
        WorkorderID=WO_ID,
        WorkorderMod=WO_MOD,
        WorkorderStatus=WO_STATUS,
        CustomerFacilityID=FACILITY_ID,
    )

    asp_pages = {
        "05_dashboard_news": f"app/workorders/activities_/woNews.asp?p={p2}",
        "06_rfi_dialog": "app/workorders/dialog_/Documents.asp?Dashboard=true",
        "07_budget": f"app/workorders/budget_/budget_SPEED.asp?woid={WO_ID}&womod={WO_MOD}&wostatus={WO_STATUS}&facilityID={FACILITY_ID}",
        "08_billing": f"app/workorders/billing_/billing.asp?p={p}",
        "09_buyout": f"app/workorders/buyout_/Buyout.asp?p={p}",
        "10_punchlist": "app/workorders/punchlist_/ManagePunchList.asp?punchType=",
        "11_financial_overview": f"app/workorders/budget_/ViewProjectSum_L_SPEED.asp?workorderID={WO_ID}&workorderMod={WO_MOD}&workorderStatus={WO_STATUS}&activeUser=1&client=remnantconstruction",
        "12_changes_overview": f"app/workorders/changeorder_/views/idxChangesOvw.asp?workorderID={WO_ID}&workorderMod={WO_MOD}&workorderStatus={WO_STATUS}&activeUser=1&client=remnantconstruction",
        "13_rfi_summary": f"app/workorders/dialog_/views/idxRFISummary.asp?workorderID={WO_ID}&workorderMod={WO_MOD}&workorderStatus={WO_STATUS}&activeUser=1&client=remnantconstruction",
        "14_attachments": f"app/asp/LinkWorkorderAttachments.asp?type=Specification&typeorigin=Specification&workorderID={WO_ID}&workorderMod={WO_MOD}&workorderStatus={WO_STATUS}&activeUser=1&client=remnantconstruction",
        "15_photos": "app/workorders/photos_/woPhotos.asp",
    }

    for name, path in asp_pages.items():
        url = f"{ASP_BASE}/{path}"
        print(f"[*] Pulling {name}...")
        try:
            r = s.get(url, timeout=30)
            if r.status_code == 200:
                save_html(r.text, f"{name}.html")

                # If it's a redirect form (like changes overview), follow it
                form_match = re.search(
                    r'action="([^"]+)"', r.text
                )
                if form_match and "submit()" in r.text and len(r.text) < 1000:
                    redirect_url = f"{ASP_BASE}/app/workorders/{form_match.group(1).split('app/workorders/')[-1] if 'app/workorders/' in form_match.group(1) else form_match.group(1)}"
                    # Handle relative URLs
                    if not redirect_url.startswith("http"):
                        base_path = "/".join(url.split("/")[:-1])
                        redirect_url = f"{base_path}/{form_match.group(1)}"

                    # Extract hidden form data
                    textarea_match = re.search(
                        r'<textarea[^>]*name="([^"]+)"[^>]*>([^<]*)</textarea>',
                        r.text,
                    )
                    form_data = {}
                    if textarea_match:
                        form_data[textarea_match.group(1)] = textarea_match.group(2)

                    print(f"  Following redirect to {redirect_url}...")
                    r2 = s.post(redirect_url, data=form_data, timeout=30)
                    if r2.status_code == 200:
                        save_html(r2.text, f"{name}_full.html")

                # Extract tables from HTML
                tables = extract_tables(r.text)
                if tables:
                    table_data = []
                    for i, table in enumerate(tables):
                        if len(table) > 1:
                            headers = table[0]
                            rows = []
                            for row in table[1:]:
                                if len(row) == len(headers):
                                    rows.append(dict(zip(headers, row)))
                                else:
                                    rows.append(row)
                            table_data.append({"headers": headers, "rows": rows})
                    if table_data:
                        save_json(table_data, f"{name}_tables.json")
            else:
                print(f"  [{r.status_code}] Failed")
        except Exception as e:
            print(f"  [ERR] {e}")


def pull_additional_asp_pages(s):
    """Pull additional pages that require form POSTs."""

    # RFI Summary - needs POST with textarea data
    print("[*] Pulling RFI Summary (following redirect)...")
    r = s.get(
        f"{ASP_BASE}/app/workorders/dialog_/views/idxRFISummary.asp?workorderID={WO_ID}&workorderMod={WO_MOD}&workorderStatus={WO_STATUS}&activeUser=1&client=remnantconstruction",
        timeout=15,
    )
    if r.status_code == 200:
        form_match = re.search(r'action="([^"]+)"', r.text)
        textarea_match = re.search(
            r'<textarea[^>]*name="([^"]+)"[^>]*>([^<]*)</textarea>', r.text
        )
        if form_match and textarea_match:
            rfi_url = f"{ASP_BASE}/app/workorders/dialog_/views/{form_match.group(1)}"
            form_data = {textarea_match.group(1): textarea_match.group(2)}
            r2 = s.post(rfi_url, data=form_data, timeout=30)
            if r2.status_code == 200:
                save_html(r2.text, "13_rfi_summary_full.html")
                tables = extract_tables(r2.text)
                if tables:
                    save_json(
                        [
                            {
                                "headers": t[0] if t else [],
                                "rows": t[1:] if len(t) > 1 else [],
                            }
                            for t in tables
                            if len(t) > 1
                        ],
                        "13_rfi_summary_tables.json",
                    )

    # Changes Overview - needs POST redirect
    print("[*] Pulling Changes Overview (following redirect)...")
    r = s.get(
        f"{ASP_BASE}/app/workorders/changeorder_/views/idxChangesOvw.asp?workorderID={WO_ID}&workorderMod={WO_MOD}&workorderStatus={WO_STATUS}&activeUser=1&client=remnantconstruction",
        timeout=15,
    )
    if r.status_code == 200:
        form_match = re.search(r'action="([^"]+)"', r.text)
        if form_match:
            changes_url = f"{ASP_BASE}/app/workorders/changeorder_/views/{form_match.group(1)}"
            r2 = s.post(changes_url, data={}, timeout=30)
            if r2.status_code == 200:
                save_html(r2.text, "12_changes_overview_full.html")
                tables = extract_tables(r2.text)
                if tables:
                    save_json(
                        [
                            {
                                "headers": t[0] if t else [],
                                "rows": t[1:] if len(t) > 1 else [],
                            }
                            for t in tables
                            if len(t) > 1
                        ],
                        "12_changes_overview_tables.json",
                    )


def pull_attachments_list(s):
    """Pull and parse the attachments/documents page."""
    print("\n[*] Pulling full attachments list...")
    r = s.get(
        f"{ASP_BASE}/app/asp/LinkWorkorderAttachments.asp?type=Specification&typeorigin=Specification&workorderID={WO_ID}&workorderMod={WO_MOD}&workorderStatus={WO_STATUS}&activeUser=1&client=remnantconstruction",
        timeout=30,
    )
    if r.status_code == 200:
        html = r.text

        # Extract file links
        file_links = re.findall(
            r'href=["\']([^"\']*(?:download|attach|upload|file|document)[^"\']*)["\']',
            html,
            re.I,
        )
        # Extract document names and IDs
        doc_entries = re.findall(
            r'(?:documentid|attachmentid|fileid|uploadid)\s*=\s*["\']?(\d+)',
            html,
            re.I,
        )

        # Extract all anchors with their text
        anchor_pattern = re.compile(
            r"<a[^>]*href=[\"']([^\"']+)[\"'][^>]*>(.*?)</a>", re.S
        )
        anchors = anchor_pattern.findall(html)
        file_anchors = []
        for href, text in anchors:
            clean_text = re.sub(r"<[^>]+>", "", text).strip()
            if clean_text and any(
                ext in href.lower() or ext in clean_text.lower()
                for ext in [
                    ".pdf", ".doc", ".xls", ".jpg", ".png", ".dwg",
                    ".zip", ".csv", ".txt", ".gif", ".bmp", ".tif",
                    "download", "attach", "upload",
                ]
            ):
                file_anchors.append({"href": href, "text": clean_text})

        attachments_data = {
            "file_links": file_links[:100],
            "document_ids": list(set(doc_entries)),
            "file_anchors": file_anchors[:200],
            "total_html_size": len(html),
        }
        save_json(attachments_data, "20_attachments_list.json")

        # Also extract all links for reference
        all_links = extract_links(html)
        save_json(all_links, "20_all_links.json")

        # Extract tables from attachments page
        tables = extract_tables(html)
        if tables:
            save_json(
                [
                    {
                        "headers": t[0] if t else [],
                        "rows": t[1:] if len(t) > 1 else [],
                        "row_count": len(t) - 1 if len(t) > 1 else 0,
                    }
                    for t in tables
                    if len(t) > 1
                ],
                "20_attachments_tables.json",
            )


def create_summary(s):
    """Create a summary of all pulled data."""
    print("\n[*] Creating summary...")

    summary = {
        "workorder_id": WO_ID,
        "files_pulled": [],
    }

    for f in sorted(os.listdir(OUTPUT_DIR)):
        filepath = os.path.join(OUTPUT_DIR, f)
        size = os.path.getsize(filepath)
        summary["files_pulled"].append({"file": f, "size": size})

    save_json(summary, "00_summary.json")


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    print("=" * 60)
    print(f"Pulling ALL data for Work Order {WO_ID}")
    print("=" * 60)

    s = create_session()

    # Pull node backend data
    print("\n--- Node Backend Data ---")
    pull_node_data(s)

    # Pull ASP page data
    print("\n--- ASP Page Data ---")
    pull_asp_pages(s)

    # Pull additional pages that require redirects
    pull_additional_asp_pages(s)

    # Pull attachments
    pull_attachments_list(s)

    # Create summary
    create_summary(s)

    print("\n" + "=" * 60)
    print(f"Done! All data saved to {OUTPUT_DIR}/")
    print("=" * 60)


if __name__ == "__main__":
    main()

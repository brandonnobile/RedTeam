#!/usr/bin/env python3
"""Upload wo_data/ to Google Drive using user OAuth token via clients6.google.com."""

import os
import sys
import json
import time
import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

TOKEN_FILE = os.path.join(os.path.dirname(__file__), 'gdrive_user_token.json')
CLIENT_ID = '764086051850-6qr4p6gpi6hn506pt8ejuq83di341hur.apps.googleusercontent.com'
CLIENT_SECRET = 'd-FL95Q19q7MQmFpd7hHD0Ty'
PARENT_FOLDER_ID = '1g2UjsH7E7Pu1K1-jtbFkOI2nLMIOT7G3'
API_BASE = 'https://clients6.google.com'
QUOTA_HEADER = {'X-Goog-User-Project': 'api-project-793455338908'}

session = requests.Session()
session.verify = False


def load_tokens():
    with open(TOKEN_FILE) as f:
        return json.load(f)


def save_tokens(tokens):
    with open(TOKEN_FILE, 'w') as f:
        json.dump(tokens, f)


def refresh_access_token(tokens):
    """Refresh the access token using the refresh token."""
    resp = session.post('https://oauth2.googleapis.com/token', data={
        'client_id': CLIENT_ID,
        'client_secret': CLIENT_SECRET,
        'refresh_token': tokens['refresh_token'],
        'grant_type': 'refresh_token'
    })
    if resp.status_code != 200:
        raise Exception(f"Token refresh failed: {resp.text}")
    new_data = resp.json()
    tokens['access_token'] = new_data['access_token']
    save_tokens(tokens)
    return tokens


def get_headers(tokens):
    return {
        'Authorization': f'Bearer {tokens["access_token"]}',
        **QUOTA_HEADER
    }


def find_or_create_folder(tokens, name, parent_id):
    """Find existing folder or create a new one."""
    headers = get_headers(tokens)
    query = f"name='{name}' and '{parent_id}' in parents and mimeType='application/vnd.google-apps.folder' and trashed=false"
    resp = session.get(f'{API_BASE}/drive/v3/files',
                       params={'q': query, 'fields': 'files(id)'},
                       headers=headers)
    if resp.status_code == 401:
        tokens = refresh_access_token(tokens)
        return find_or_create_folder(tokens, name, parent_id)
    files = resp.json().get('files', [])
    if files:
        return tokens, files[0]['id']

    metadata = {
        'name': name,
        'mimeType': 'application/vnd.google-apps.folder',
        'parents': [parent_id]
    }
    resp = session.post(f'{API_BASE}/drive/v3/files',
                        headers={**headers, 'Content-Type': 'application/json'},
                        data=json.dumps(metadata))
    if resp.status_code == 401:
        tokens = refresh_access_token(tokens)
        return find_or_create_folder(tokens, name, parent_id)
    return tokens, resp.json()['id']


def upload_file(tokens, filepath, parent_id, retries=3):
    """Upload a file using resumable upload for large files, multipart for small."""
    filename = os.path.basename(filepath)
    filesize = os.path.getsize(filepath)
    size_mb = filesize / (1024 * 1024)
    print(f"  Uploading {filename} ({size_mb:.1f} MB)...", end=' ', flush=True)

    headers = get_headers(tokens)

    if filesize > 5 * 1024 * 1024:  # >5MB: use resumable upload
        # Initiate resumable upload
        metadata = json.dumps({'name': filename, 'parents': [parent_id]})
        resp = session.post(
            f'{API_BASE}/upload/drive/v3/files?uploadType=resumable',
            headers={
                **headers,
                'Content-Type': 'application/json; charset=UTF-8',
                'X-Upload-Content-Length': str(filesize)
            },
            data=metadata
        )
        if resp.status_code == 401:
            tokens = refresh_access_token(tokens)
            return upload_file(tokens, filepath, parent_id, retries)
        if resp.status_code != 200:
            if retries > 0:
                time.sleep(2)
                return upload_file(tokens, filepath, parent_id, retries - 1)
            print(f"FAILED (init: {resp.status_code})")
            return tokens, False

        upload_url = resp.headers['Location']

        # Upload content in one shot
        with open(filepath, 'rb') as f:
            resp = session.put(upload_url,
                               headers={'Content-Length': str(filesize)},
                               data=f)
        if resp.status_code in (200, 201):
            print("OK")
            return tokens, True
        else:
            if retries > 0:
                time.sleep(2)
                return upload_file(tokens, filepath, parent_id, retries - 1)
            print(f"FAILED ({resp.status_code})")
            return tokens, False
    else:
        # Small file: multipart upload
        boundary = '===boundary_upload==='
        metadata = json.dumps({'name': filename, 'parents': [parent_id]})
        with open(filepath, 'rb') as f:
            file_content = f.read()

        body = (
            f'--{boundary}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n'
            f'{metadata}\r\n'
            f'--{boundary}\r\nContent-Type: application/octet-stream\r\n\r\n'
        ).encode() + file_content + f'\r\n--{boundary}--'.encode()

        resp = session.post(
            f'{API_BASE}/upload/drive/v3/files?uploadType=multipart',
            headers={**headers, 'Content-Type': f'multipart/related; boundary={boundary}'},
            data=body
        )
        if resp.status_code == 401:
            tokens = refresh_access_token(tokens)
            return upload_file(tokens, filepath, parent_id, retries)
        if resp.status_code == 200:
            print("OK")
            return tokens, True
        else:
            if retries > 0:
                time.sleep(2)
                return upload_file(tokens, filepath, parent_id, retries - 1)
            print(f"FAILED ({resp.status_code})")
            return tokens, False


def upload_directory(tokens, local_dir, parent_id):
    """Recursively upload a directory to Google Drive."""
    ok_count = 0
    fail_count = 0

    for item in sorted(os.listdir(local_dir)):
        item_path = os.path.join(local_dir, item)
        if os.path.isdir(item_path):
            print(f"\n[Folder] {item}/")
            tokens, folder_id = find_or_create_folder(tokens, item, parent_id)
            sub_ok, sub_fail, tokens = upload_directory(tokens, item_path, folder_id)
            ok_count += sub_ok
            fail_count += sub_fail
        elif os.path.isfile(item_path):
            tokens, success = upload_file(tokens, item_path, parent_id)
            if success:
                ok_count += 1
            else:
                fail_count += 1

    return ok_count, fail_count, tokens


def main():
    target_dir = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), 'wo_data')
    if not os.path.exists(target_dir):
        print(f"Directory not found: {target_dir}")
        sys.exit(1)
    if not os.path.exists(TOKEN_FILE):
        print(f"Token file not found: {TOKEN_FILE}")
        sys.exit(1)

    tokens = load_tokens()

    # Count files first
    total_files = sum(len(files) for _, _, files in os.walk(target_dir))
    print(f"Uploading {total_files} files from {target_dir} to Google Drive...")

    tokens, wo_folder_id = find_or_create_folder(tokens, os.path.basename(target_dir), PARENT_FOLDER_ID)
    ok_count, fail_count, tokens = upload_directory(tokens, target_dir, wo_folder_id)

    print(f"\nDone! {ok_count} uploaded, {fail_count} failed.")


if __name__ == '__main__':
    main()

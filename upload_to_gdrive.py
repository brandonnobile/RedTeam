#!/usr/bin/env python3
"""Upload files from wo_data/ to Google Drive Redteam folder."""

import os
import sys
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

SCOPES = ['https://www.googleapis.com/auth/drive']
SERVICE_ACCOUNT_FILE = os.path.join(os.path.dirname(__file__), 'gdrive_service_account.json')
PARENT_FOLDER_ID = '1g2UjsH7E7Pu1K1-jtbFkOI2nLMIOT7G3'


def get_service():
    creds = service_account.Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE, scopes=SCOPES
    )
    return build('drive', 'v3', credentials=creds)


def find_or_create_folder(service, name, parent_id):
    """Find existing folder or create a new one."""
    query = f"name='{name}' and '{parent_id}' in parents and mimeType='application/vnd.google-apps.folder' and trashed=false"
    results = service.files().list(q=query, fields='files(id)').execute()
    files = results.get('files', [])
    if files:
        return files[0]['id']
    metadata = {
        'name': name,
        'mimeType': 'application/vnd.google-apps.folder',
        'parents': [parent_id]
    }
    folder = service.files().create(body=metadata, fields='id').execute()
    return folder['id']


def upload_file(service, filepath, parent_id):
    """Upload a single file to Google Drive."""
    filename = os.path.basename(filepath)
    size_mb = os.path.getsize(filepath) / (1024 * 1024)
    print(f"  Uploading {filename} ({size_mb:.1f} MB)...", end=' ', flush=True)
    media = MediaFileUpload(filepath, resumable=True)
    metadata = {'name': filename, 'parents': [parent_id]}
    request = service.files().create(body=metadata, media_body=media, fields='id')
    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            print(f"{int(status.progress() * 100)}%", end=' ', flush=True)
    print("Done.")
    return response.get('id')


def upload_directory(service, local_dir, parent_id):
    """Recursively upload a directory to Google Drive."""
    for item in sorted(os.listdir(local_dir)):
        item_path = os.path.join(local_dir, item)
        if os.path.isdir(item_path):
            print(f"\n[Folder] {item}/")
            folder_id = find_or_create_folder(service, item, parent_id)
            upload_directory(service, item_path, folder_id)
        elif os.path.isfile(item_path):
            upload_file(service, item_path, parent_id)


def main():
    target_dir = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), 'wo_data')
    if not os.path.exists(target_dir):
        print(f"Directory not found: {target_dir}")
        sys.exit(1)

    print(f"Uploading {target_dir} to Google Drive...")
    service = get_service()
    wo_folder_id = find_or_create_folder(service, os.path.basename(target_dir), PARENT_FOLDER_ID)
    upload_directory(service, target_dir, wo_folder_id)
    print("\nAll done!")


if __name__ == '__main__':
    main()

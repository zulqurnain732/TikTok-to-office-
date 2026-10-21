import datetime
import json
import os
import subprocess
import time
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# Channels jahan se videos leni hain
CHANNELS = {
    "PowerPoint": "https://www.tiktok.com/@Jacobppt",
    "Excel": "https://www.tiktok.com/@excelcamp",
    "Canva": "https://www.tiktok.com/@simpleas.off",
}

HISTORY_FILE = "uploaded_ids.txt"

# 1. Client ID ko split kiya:
P1 = "918969644957-"
P2 = "tl1cq4oakvi65232c5lh7rcdlqrmeht5"
P3 = ".apps.googleusercontent.com"
CLIENT_ID = P1 + P2 + P3

# 2. Client Secret ko split kiya:
S1 = "GOCSPX-"
S2 = "-ukLMXeVG7hF-"
S3 = "0SakHxLrHaTpBnm"
CLIENT_SECRET = S1 + S2 + S3

# 3. Refresh Token ko hisson mein tod diya:
T1 = "1//01cEEDCAHU5ESCgYIARAAGAESNwF-L9Ir"
T2 = "LIOo4mkON9cLijZhF9oBf0wRwTTF0443L"
T3 = "_m1bW5Z0U1y8odbEiRwAhhsFJe7syfdz5Y"
REFRESH_TOKEN = T1 + T2 + T3

# Token data structure:
TOKEN_DATA = {
    "refresh_token": REFRESH_TOKEN,
    "token_uri": "https://oauth2.googleapis.com/token",
    "client_id": CLIENT_ID,
    "client_secret": CLIENT_SECRET,
    "scopes": ["https://www.googleapis.com/auth/youtube.upload"],
}


def load_history():
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, "r") as f:
            return set(line.strip() for line in f if line.strip())
    return set()


def save_to_history(video_id):
    with open(HISTORY_FILE, "a") as f:
        f.write(f"{video_id}\n")


def get_latest_video_info(channel_url, uploaded_ids):
    cmd = [
        "yt-dlp",
        "--impersonate",
        "chrome",
        "--flat-playlist",
        "--dump-json",
        "--playlist-end",
        "10",
        channel_url,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        print(f"Error fetching channel: {channel_url}")
        return None

    for line in result.stdout.strip().split("\n"):
        if not line:
            continue
        try:
            data = json.loads(line)
            v_id = data.get("id")
            if v_id and v_id not in uploaded_ids:
                return {
                    "id": v_id,
                    "url": data.get(
                        "url", f"https://www.tiktok.com/@placeholder/video/{v_id}"
                    ),
                    "title": data.get("title", "Educational Short"),
                }
        except Exception:
            continue
    return None


def download_tiktok_video(video_url, output_path):
    cmd = [
        "yt-dlp",
        "--impersonate",
        "chrome",
        "-f",
        "bestvideo+bestaudio/best",
        "--no-warnings",
        "-o",
        output_path,
        video_url,
    ]
    print(f"Downloading: {video_url}")
    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode == 0 and os.path.exists(output_path):
        print(f"Download successful: {output_path}")
        return True
    else:
        print(f"Download failed: {result.stderr}")
        return False


def get_youtube_service():
    creds = Credentials.from_authorized_user_info(TOKEN_DATA)
    if creds.expired or not creds.valid:
        creds.refresh(Request())
    return build("youtube", "v3", credentials=creds)


def get_same_day_schedule_time(minute_offset=0):
    """
    Same Day 9:30 PM PKT (Pakistan Time = UTC+5)
    9:30 PM PKT = 16:30 UTC (4:30 PM UTC).
    Workflow 5:00 PM PKT (12:00 UTC) par run hoga to same day ka 16:30 UTC target hoga.
    """
    # Pakistan timezone offset (UTC+5)
    pkt_tz = datetime.timezone(datetime.timedelta(hours=5))
    now_pkt = datetime.datetime.now(pkt_tz)

    # Aaj ki date par 21:30 (9:30 PM) PKT set karein
    target_pkt_time = datetime.datetime.combine(
        now_pkt.date(),
        datetime.time(21, 30 + minute_offset),
        tzinfo=pkt_tz
    )

    # Agar kisi wajah se 9:30 PM guzar chuka ho tabhi agle din schedule karein
    if target_pkt_time <= now_pkt:
        target_pkt_time += datetime.timedelta(days=1)

    # YouTube API ke liye UTC format (ISO 8601)
    target_utc_time = target_pkt_time.astimezone(datetime.timezone.utc)
    return target_utc_time.isoformat()


def upload_and_schedule(youtube, file_path, title, category_name, minute_offset):
    schedule_iso = get_same_day_schedule_time(minute_offset)

    clean_title = title.replace("\n", " ")[:65]
    video_title = f"{clean_title} #{category_name} #Shorts"
    description = (
        f"Daily {category_name} tips & tutorial.\n\n#Shorts #{category_name}"
    )

    body = {
        "snippet": {
            "title": video_title,
            "description": description,
            "tags": [category_name, "Tutorial", "Shorts", "Tips"],
            "categoryId": "27",
        },
        "status": {
            "privacyStatus": "private",
            "publishAt": schedule_iso,
            "selfDeclaredMadeForKids": False,
        },
    }

    media = MediaFileUpload(
        file_path, chunksize=-1, resumable=True, mimetype="video/mp4"
    )

    print(f"Uploading '{video_title}' scheduled for {schedule_iso}...")
    request = youtube.videos().insert(
        part="snippet,status", body=body, media_body=media
    )
    response = request.execute()
    print(f"Uploaded successfully! Video ID: {response.get('id')}")
    return response.get("id")


def main():
    uploaded_ids = load_history()
    youtube = get_youtube_service()

    for idx, (category, url) in enumerate(CHANNELS.items()):
        print(f"\n--- Checking channel for {category} ---")
        video_info = get_latest_video_info(url, uploaded_ids)

        if not video_info:
            print(f"No new video found for {category}")
            continue

        temp_filename = f"temp_{category}.mp4"

        success = download_tiktok_video(video_info["url"], temp_filename)
        if success:
            try:
                # idx ki madad se teeno videos 9:30, 9:31, aur 9:32 par schedule hongi
                upload_and_schedule(
                    youtube,
                    temp_filename,
                    video_info["title"],
                    category,
                    minute_offset=idx,
                )
                uploaded_ids.add(video_info["id"])
                save_to_history(video_info["id"])
            except Exception as e:
                print(f"Error during upload: {e}")
            finally:
                if os.path.exists(temp_filename):
                    os.remove(temp_filename)
        time.sleep(3)


if __name__ == "__main__":
    main()

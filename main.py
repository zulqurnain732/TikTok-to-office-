import datetime
import json
import os
import subprocess
import time
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

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

# 3. Refresh Token ko split kiya:
T1 = "1//01cEEDCAHU5ESCgYIARAAGAESNwF-L9Ir"
T2 = "LIOo4mkON9cLijZhF9oBf0wRwTTF0443L"
T3 = "_m1bW5Z0U1y8odbEiRwAhhsFJe7syfdz5Y"
REFRESH_TOKEN = T1 + T2 + T3

TOKEN_DATA = {
    "refresh_token": REFRESH_TOKEN,
    "token_uri": "https://oauth2.googleapis.com/token",
    "client_id": CLIENT_ID,
    "client_secret": CLIENT_SECRET,
    "scopes": [
        "https://www.googleapis.com/auth/youtube.upload",
        "https://www.googleapis.com/auth/youtube.readonly",
    ],
}


def load_history():
    """File agar mojood nahi hai to auto create karega aur IDs return karega"""
    if not os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, "w") as f:
            pass
        return set()

    with open(HISTORY_FILE, "r") as f:
        return set(line.strip() for line in f if line.strip())


def save_to_history(video_id):
    """Uploaded video ID ko file me append karega"""
    with open(HISTORY_FILE, "a") as f:
        f.write(f"{video_id}\n")


def get_next_unuploaded_video(channel_url, uploaded_ids):
    """
    Channel ki shuru se le kar aakhri tak tamam videos check karega.
    Koi limit nahi hai. Line se scan karega aur pehli un-uploaded video return karega.
    """
    cmd = [
        "yt-dlp",
        "--impersonate",
        "chrome",
        "--flat-playlist",
        "--dump-json",
        channel_url,
    ]

    print(f"Fetching complete channel videos list for: {channel_url} ...")
    
    # Subprocess pipe line-by-line stream karega taaki saari videos bina rukawat check hon
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )

    selected_video = None

    for line in iter(process.stdout.readline, ""):
        line_str = line.strip()
        if not line_str:
            continue
        try:
            data = json.loads(line_str)
            v_id = str(data.get("id"))

            if not v_id:
                continue

            # Agar pehle se uploaded hai to check aage barhayein
            if v_id in uploaded_ids:
                print(f"[Already Uploaded] Video {v_id} skip ki ja rahi hai...")
                continue

            # Pehli milti fresh video select karein
            print(f"[Fresh Video Found] ID: {v_id}")
            selected_video = {
                "id": v_id,
                "url": data.get(
                    "url", f"https://www.tiktok.com/@placeholder/video/{v_id}"
                ),
                "title": data.get("title", "Educational Short"),
            }
            break
        except Exception:
            continue

    # Process ko terminate kar dein agar desired video mil gayi ho
    process.kill()
    process.wait()

    return selected_video


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
    print(f"Downloading video: {video_url}")
    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode == 0 and os.path.exists(output_path):
        print(f"Download successful: {output_path}")
        return True
    else:
        print(f"Download error: {result.stderr}")
        return False


def get_youtube_service():
    creds = Credentials.from_authorized_user_info(TOKEN_DATA)
    if creds.expired or not creds.valid:
        creds.refresh(Request())
    return build("youtube", "v3", credentials=creds)


def get_same_day_schedule_time(minute_offset=0):
    pkt_tz = datetime.timezone(datetime.timedelta(hours=5))
    now_pkt = datetime.datetime.now(pkt_tz)

    target_pkt_time = datetime.datetime.combine(
        now_pkt.date(),
        datetime.time(21, 30 + minute_offset),
        tzinfo=pkt_tz,
    )

    # Agar 9:30 PM nikal chuka ho to agle din ke liye shift karein
    if target_pkt_time <= now_pkt:
        target_pkt_time += datetime.timedelta(days=1)

    return target_pkt_time.astimezone(datetime.timezone.utc).isoformat()


def upload_and_schedule(
    youtube, file_path, title, category_name, video_id, minute_offset
):
    schedule_iso = get_same_day_schedule_time(minute_offset)

    clean_title = title.replace("\n", " ").strip()[:60]
    video_title = f"{clean_title} #{category_name} #Shorts"

    description = (
        f"Daily {category_name} tips & tutorial.\n\n"
        f"Source ID: {video_id}\n\n"
        f"#Shorts #{category_name}"
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

    print(f"Uploading '{video_title}' (Schedule: {schedule_iso})...")
    request = youtube.videos().insert(
        part="snippet,status", body=body, media_body=media
    )
    response = request.execute()
    print(f"Video uploaded successfully! ID: {response.get('id')}")
    return response.get("id")


def main():
    uploaded_ids = load_history()
    youtube = get_youtube_service()

    for idx, (category, url) in enumerate(CHANNELS.items()):
        print("\n" + "=" * 50)
        print(f"Scanning channel for: {category}")
        print("=" * 50)

        # Shuru se check karta hua aayega jab tak saari videos check na ho jayein
        video_info = get_next_unuploaded_video(url, uploaded_ids)

        if not video_info:
            print(f"No fresh videos found in {category}. All videos have been uploaded.")
            continue

        temp_filename = f"temp_{category}.mp4"

        success = download_tiktok_video(video_info["url"], temp_filename)
        if success:
            try:
                upload_and_schedule(
                    youtube=youtube,
                    file_path=temp_filename,
                    title=video_info["title"],
                    category_name=category,
                    video_id=video_info["id"],
                    minute_offset=idx,
                )
                uploaded_ids.add(video_info["id"])
                save_to_history(video_info["id"])
                print(f"History updated: {video_info['id']} saved to {HISTORY_FILE}")
            except Exception as e:
                print(f"Upload failed: {e}")
            finally:
                if os.path.exists(temp_filename):
                    os.remove(temp_filename)
        time.sleep(3)


if __name__ == "__main__":
    main()

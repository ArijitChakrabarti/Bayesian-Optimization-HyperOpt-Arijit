import argparse
import csv
from pathlib import Path

import yt_dlp
from yt_dlp.utils import DownloadError

HISTORY_DIR = Path("download_history")
CSV_LOG = HISTORY_DIR / "download_history.csv"  # Human-readable log
ARCHIVE_FILE = "download_archive.txt"  # yt-dlp internal archive


def progress_hook(d):
    status = d.get("status")
    if status == "downloading":
        percent = d.get("_percent_str", "0%")
        speed = d.get("_speed_str", "N/A")
        eta = d.get("_eta_str", "Unknown")
        print(f"\r[Progress] {percent} | Speed: {speed} | ETA: {eta}    ", end="", flush=True)
    elif status == "finished":
        print("\n[Status] Download complete! Processing metadata and album art...")
        info = d.get("info_dict", {})
        title = info.get("title", "Unknown Title")
        uploader = info.get("uploader", "Unknown Uploader")
        playlist = info.get("playlist_title") or "Single_Tracks"
        filepath = d.get("filename", "Unknown File")

        HISTORY_DIR.mkdir(exist_ok=True)
        file_exists = CSV_LOG.is_file()
        with open(CSV_LOG, "a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            if not file_exists:
                writer.writerow(["Playlist", "Title", "Uploader", "Filepath"])
            writer.writerow([playlist, title, uploader, filepath])


def read_urls_from_csv(csv_path: str, url_column: str = "url") -> list[str]:
    """Read all URL values from a CSV file.

    If a column named `url` exists, that column is preferred.
    Otherwise, a column is auto-detected by searching for values containing '.com'.
    """
    collected_urls = []

    with open(csv_path, "r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames:
            rows = list(reader)

            # Prefer explicitly named column if present and usable.
            if url_column in reader.fieldnames:
                for row in rows:
                    url = (row.get(url_column) or "").strip()
                    if ".com" in url:
                        collected_urls.append(url)
                if collected_urls:
                    return collected_urls

            # Auto-detect URL column by searching for values containing '.com'.
            for field in reader.fieldnames:
                field_urls = []
                for row in rows:
                    value = (row.get(field) or "").strip()
                    if ".com" in value:
                        field_urls.append(value)
                if field_urls:
                    return field_urls

    # Fallback for CSVs without headers or without a `url` column
    with open(csv_path, "r", newline="", encoding="utf-8") as f:
        plain_reader = csv.reader(f)
        for row in plain_reader:
            for cell in row:
                candidate = cell.strip()
                if candidate.startswith("http"):
                    collected_urls.append(candidate)
        if collected_urls:
            return collected_urls

    raise ValueError(f"No URLs found in CSV file: {csv_path}")


def find_csv_in_current_directory() -> Path:
    csv_files = sorted(Path.cwd().glob("*.csv"))
    if not csv_files:
        raise FileNotFoundError("No CSV file found in the current directory.")
    return csv_files[0]


def download_first_song(url, download_folder_name, browser=None, cookies_file=None):
    base_dir = Path(download_folder_name)
    base_dir.mkdir(exist_ok=True)

    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": str(base_dir / "%(title)s.%(ext)s"),
        "writethumbnail": True,
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "320",
            },
            {
                "key": "FFmpegMetadata",
                "add_metadata": True,
            },
            {
                "key": "EmbedThumbnail",
            },
        ],
        "restrictfilenames": True,
        "trim_filenames": 200,
        "download_archive": ARCHIVE_FILE,
        "ignoreerrors": False,
        "sleep_interval": 1,
        "max_sleep_interval": 3,
        "sleep_interval_requests": 1,
        "progress_hooks": [progress_hook],
        "quiet": True,
        "no_warnings": True,
        "retries": 10,
        "fragment_retries": 10,
        # Key change: if URL is a playlist, only fetch item 1.
        "playlist_items": "1",
    }

    if browser:
        ydl_opts["cookiesfrombrowser"] = (browser,)

    if cookies_file:
        ydl_opts["cookiefile"] = cookies_file

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            print(f"--- Fetching first song from: {url} ---")
            if "youtube.com" in url or "youtu.be" in url:
                if not browser and not cookies_file:
                    print("[Tip] If YouTube blocks this request, rerun with --browser or --cookies.")
            ydl.download([url])
            print(f"\n--- Success! First song saved in '{base_dir}' ---")
            print(f"--- Log updated in '{CSV_LOG}' ---")

    except DownloadError as e:
        msg = str(e)
        if "Sign in to confirm" in msg or "not a bot" in msg:
            print("\n[Error] YouTube blocked anonymous access for this request.")
            print("Try one of these:")
            print("  1) Use browser cookies:  python yt_music_downloader.py urls.csv --browser firefox")
            print("  2) Use exported cookies: python yt_music_downloader.py urls.csv --cookies /path/to/cookies.txt")
            print("  3) Cookie help FAQ:      https://github.com/yt-dlp/yt-dlp/wiki/FAQ#how-do-i-pass-cookies-to-yt-dlp")
            print("  4) Exporting cookies:    https://github.com/yt-dlp/yt-dlp/wiki/Extractors#exporting-youtube-cookies")
            print("  5) Update tooling:       pip install -U yt-dlp")
            print("  6) Ensure ffmpeg exists: ffmpeg -version")
        else:
            print(f"\n[Error] {e}")

    except Exception as e:
        print(f"\n[Error] {e}")


def main():
    parser = argparse.ArgumentParser(
        description="Read a YouTube URL from CSV, download only the first song, and save into a folder named after the CSV file"
    )
    parser.add_argument("csv_file", nargs="?", help="Optional path to CSV file containing YouTube URL(s)")
    parser.add_argument(
        "--url-column",
        default="url",
        help="CSV header name containing YouTube URLs (default: url)",
    )
    parser.add_argument("--browser", help="Read cookies from local browser (chrome/firefox/edge/brave)")
    parser.add_argument("--cookies", dest="cookies_file", help="Path to exported Netscape-format cookies file")
    args = parser.parse_args()

    try:
        csv_path = Path(args.csv_file) if args.csv_file else find_csv_in_current_directory()
        print(f"Using CSV file: {csv_path}")
        urls = read_urls_from_csv(str(csv_path), args.url_column)
        download_folder_name = csv_path.parent / (csv_path.stem or "Downloaded_Music")
        print(f"Found {len(urls)} URL(s). Starting sequential download...")
        for idx, url in enumerate(urls, start=1):
            print(f"\n[{idx}/{len(urls)}] Processing URL: {url}")
            download_first_song(
                url,
                download_folder_name=download_folder_name,
                browser=args.browser,
                cookies_file=args.cookies_file,
            )
    except Exception as e:
        print(f"[Error] {e}")


if __name__ == "__main__":
    main()

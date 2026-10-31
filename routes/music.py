import re
import random
import yt_dlp
from flask import Blueprint, request, jsonify

music_bp = Blueprint('music', __name__)

ARTIST_INDICATORS = ['songs', 'music', 'album', 'playlist', 'hits', 'audio', 'lyrics', 'official']

USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15',
]

def build_search_query(query):
    query_lower = query.lower()
    if any(word in query_lower for word in ARTIST_INDICATORS):
        return query
    word_count = len(query.strip().split())
    if word_count <= 3:
        return f"{query} songs"
    return query


# ─── Search ──────────────────────────────────────────────────────────
@music_bp.route('/search', methods=['GET'])
def search():
    query = request.args.get('q', '').strip()
    if not query:
        return jsonify({'success': False, 'error': 'No query'}), 400

    try:
        match    = re.search(
            r'(?:youtu\.be/|youtube\.com/(?:watch\?.*v=|shorts/|embed/|v/))([a-zA-Z0-9_-]{11})',
            query
        )
        video_id    = match.group(1) if match else None
        search_term = video_id if video_id else build_search_query(query)

        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': 'in_playlist',
            'skip_download': True,
            'http_headers': {'User-Agent': random.choice(USER_AGENTS)}
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            results = ydl.extract_info(f"ytsearch10:{search_term}", download=False)

        entries = [e for e in (results.get('entries') or []) if e and e.get('id')]

        if video_id:
            exact = next((e for e in entries if e.get('id') == video_id), None)
            entries = [exact] if exact else ([entries[0]] if entries else [])

        songs = []
        for e in entries:
            vid      = e.get('id', '')
            duration = int(e.get('duration', 0) or 0)
            songs.append({
                'videoId':    vid,
                'title':      e.get('title', ''),
                'thumbnail':  f'https://img.youtube.com/vi/{vid}/mqdefault.jpg',
                'duration':   f'{duration // 60}:{duration % 60:02d}',
                'durationMs': duration * 1000,
                'youtubeUrl': f'https://www.youtube.com/watch?v={vid}'
            })

        return jsonify({'success': True, 'results': songs})

    except Exception as e:
        print(f"SEARCH ERROR: {e}", flush=True)
        return jsonify({'success': False, 'error': str(e)}), 500


# ─── Extract ─────────────────────────────────────────────────────────
@music_bp.route('/extract', methods=['GET'])
def extract():
    video_id = request.args.get('video_id', '').strip()
    if not video_id:
        return jsonify({'success': False, 'error': 'video_id required'}), 400

    url = f'https://www.youtube.com/watch?v={video_id}'

    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'skip_download': True,
        'http_headers': {'User-Agent': random.choice(USER_AGENTS)},
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)

        formats     = info.get('formats', [])
        duration_ms = int((info.get('duration') or 0) * 1000)

        # PATH A — direct audio streams (prefer m4a ~128kbps)
        audio_formats = [
            f for f in formats
            if f.get('vcodec') == 'none'
            and f.get('acodec') != 'none'
            and f.get('url')
            and 'manifest' not in f.get('url', '').lower()
            and '.mpd' not in f.get('url', '').lower()
        ]

        chosen = None
        ext    = 'm4a'

        if audio_formats:
            m4a = [f for f in audio_formats if f.get('ext') == 'm4a']
            if m4a:
                chosen = min(m4a, key=lambda f: abs((f.get('abr') or 0) - 128))
            else:
                chosen = min(audio_formats, key=lambda f: (f.get('abr') or 999))
            ext = chosen.get('ext', 'm4a')

        # PATH B — DASH manifest
        if not chosen:
            dash = next((f for f in formats if f.get('url', '').endswith('.mpd')), None)
            if dash:
                return jsonify({
                    'success':     True,
                    'url':         dash['url'],
                    'headers':     dash.get('http_headers', {}),
                    'ext':         'mpd',
                    'duration_ms': duration_ms
                })

        # PATH C — HLS
        if not chosen:
            hls = next((f for f in formats if f.get('url', '').endswith('.m3u8')), None)
            if hls:
                return jsonify({
                    'success':     True,
                    'url':         hls['url'],
                    'headers':     hls.get('http_headers', {}),
                    'ext':         'm3u8',
                    'duration_ms': duration_ms
                })

        # PATH D — lowest quality video fallback
        if not chosen:
            video_formats = [f for f in formats if f.get('url')]
            chosen = min(video_formats, key=lambda f: (f.get('height') or 9999))
            ext    = chosen.get('ext', 'mp4')

        if not chosen:
            return jsonify({'success': False, 'error': 'No stream found'}), 500

        return jsonify({
            'success':     True,
            'url':         chosen['url'],
            'headers':     chosen.get('http_headers', {}),
            'ext':         ext,
            'duration_ms': duration_ms
        })

    except Exception as e:
        print(f"EXTRACT ERROR: {e}", flush=True)
        return jsonify({'success': False, 'error': str(e)}), 500

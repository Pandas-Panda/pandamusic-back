from flask import Blueprint, request, jsonify, g
from db.connection import get_db_conn
from utils.auth_middleware import require_jwt

stats_bp = Blueprint('stats', __name__)


# ─── Log Play ────────────────────────────────────────────────────────
@stats_bp.route('/stats/log', methods=['POST'])
@require_jwt
def log_play():
    conn = cur = None
    try:
        data               = request.get_json()
        video_id           = (data.get('video_id') or '').strip()
        title              = (data.get('title') or '').strip()
        duration_played_ms = data.get('duration_played_ms', 0)

        if not video_id:
            return jsonify({'success': False, 'error': 'video_id required'}), 400

        conn = get_db_conn()
        cur  = conn.cursor()
        cur.execute(
            "INSERT INTO play_history (user_id, video_id, title, duration_played_ms) VALUES (%s, %s, %s, %s)",
            (g.user_id, video_id, title, duration_played_ms)
        )
        conn.commit()
        return jsonify({'success': True})

    except Exception as e:
        if conn: conn.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        if cur: cur.close()
        if conn: conn.close()


# ─── Monthly Stats (Personal) ────────────────────────────────────────
@stats_bp.route('/stats/monthly', methods=['GET'])
@require_jwt
def monthly_stats():
    conn = cur = None
    try:
        conn = get_db_conn()
        cur  = conn.cursor()

        # Top 5 songs this month
        cur.execute(
            """
            SELECT video_id, title, COUNT(*) AS play_count
            FROM play_history
            WHERE user_id = %s
              AND DATE_TRUNC('month', played_at) = DATE_TRUNC('month', NOW())
            GROUP BY video_id, title
            ORDER BY play_count DESC
            LIMIT 5
            """,
            (g.user_id,)
        )
        top_songs = [
            {'videoId': r[0], 'title': r[1], 'play_count': r[2]}
            for r in cur.fetchall()
        ]

        # Total listening time this month
        cur.execute(
            """
            SELECT COALESCE(SUM(duration_played_ms), 0)
            FROM play_history
            WHERE user_id = %s
              AND DATE_TRUNC('month', played_at) = DATE_TRUNC('month', NOW())
            """,
            (g.user_id,)
        )
        total_ms = cur.fetchone()[0]

        # Songs added count (proxy: distinct video_ids played)
        cur.execute(
            """
            SELECT COUNT(DISTINCT video_id)
            FROM play_history
            WHERE user_id = %s
              AND DATE_TRUNC('month', played_at) = DATE_TRUNC('month', NOW())
            """,
            (g.user_id,)
        )
        songs_count = cur.fetchone()[0]

        # Most active day of week
        cur.execute(
            """
            SELECT TO_CHAR(played_at, 'Day') AS day_name, COUNT(*) AS cnt
            FROM play_history
            WHERE user_id = %s
              AND DATE_TRUNC('month', played_at) = DATE_TRUNC('month', NOW())
            GROUP BY day_name
            ORDER BY cnt DESC
            LIMIT 1
            """,
            (g.user_id,)
        )
        row              = cur.fetchone()
        most_active_day  = row[0].strip() if row else None

        # Most active hour
        cur.execute(
            """
            SELECT EXTRACT(HOUR FROM played_at) AS hr, COUNT(*) AS cnt
            FROM play_history
            WHERE user_id = %s
              AND DATE_TRUNC('month', played_at) = DATE_TRUNC('month', NOW())
            GROUP BY hr
            ORDER BY cnt DESC
            LIMIT 1
            """,
            (g.user_id,)
        )
        row              = cur.fetchone()
        most_active_hour = int(row[0]) if row else None

        # Listening streak (consecutive days with at least 1 play)
        cur.execute(
            """
            SELECT DISTINCT DATE(played_at) AS play_date
            FROM play_history
            WHERE user_id = %s
            ORDER BY play_date DESC
            """,
            (g.user_id,)
        )
        dates  = [r[0] for r in cur.fetchall()]
        streak = 0
        if dates:
            from datetime import date, timedelta
            today = date.today()
            for i, d in enumerate(dates):
                if d == today - timedelta(days=i):
                    streak += 1
                else:
                    break

        return jsonify({
            'success':             True,
            'top_songs':           top_songs,
            'total_listening_ms':  total_ms,
            'songs_added_count':   songs_count,
            'most_active_day':     most_active_day,
            'most_active_hour':    most_active_hour,
            'listening_streak_days': streak
        })

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        if cur: cur.close()
        if conn: conn.close()


# ─── Global Stats ────────────────────────────────────────────────────
@stats_bp.route('/stats/global', methods=['GET'])
def global_stats():
    conn = cur = None
    try:
        conn = get_db_conn()
        cur  = conn.cursor()

        # Most downloaded song this month
        cur.execute(
            """
            SELECT video_id, title, COUNT(*) AS cnt
            FROM play_history
            WHERE DATE_TRUNC('month', played_at) = DATE_TRUNC('month', NOW())
            GROUP BY video_id, title
            ORDER BY cnt DESC
            LIMIT 1
            """
        )
        row = cur.fetchone()
        most_downloaded = {'videoId': row[0], 'title': row[1], 'count': row[2]} if row else None

        # Total active users (played something this month)
        cur.execute(
            """
            SELECT COUNT(DISTINCT user_id)
            FROM play_history
            WHERE DATE_TRUNC('month', played_at) = DATE_TRUNC('month', NOW())
            """
        )
        total_active_users = cur.fetchone()[0]

        return jsonify({
            'success':             True,
            'most_downloaded_song': most_downloaded,
            'total_active_users':  total_active_users
        })

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        if cur: cur.close()
        if conn: conn.close()

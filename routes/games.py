from flask import Blueprint, request, jsonify, g
from db.connection import get_db_conn
from utils.auth_middleware import require_jwt
from datetime import datetime

games_bp = Blueprint('games', __name__)

VALID_GAMES = ('2048', 'blocks', 'arrow')


# ─── Submit Score ────────────────────────────────────────────────────
@games_bp.route('/games/score', methods=['POST'])
@require_jwt
def submit_score():
    conn = cur = None
    try:
        data  = request.get_json()
        game  = (data.get('game') or '').strip()
        score = data.get('score', 0)

        if game not in VALID_GAMES:
            return jsonify({'success': False, 'error': f'game must be one of {VALID_GAMES}'}), 400
        if not isinstance(score, int) or score <= 0:
            return jsonify({'success': False, 'error': 'Invalid score'}), 400

        conn = get_db_conn()
        cur  = conn.cursor()

        # Fetch user name for leaderboard display
        cur.execute("SELECT name, email FROM users WHERE id = %s", (g.user_id,))
        row  = cur.fetchone()
        name = (row[0] or row[1] or 'Panda') if row else 'Panda'

        cur.execute(
            "INSERT INTO game_scores (user_id, name, game, score) VALUES (%s, %s, %s, %s)",
            (g.user_id, name, game, score)
        )
        conn.commit()
        return jsonify({'success': True})

    except Exception as e:
        if conn: conn.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        if cur: cur.close()
        if conn: conn.close()


# ─── Leaderboard ─────────────────────────────────────────────────────
@games_bp.route('/games/leaderboard', methods=['GET'])
def leaderboard():
    conn = cur = None
    try:
        game = request.args.get('game', '').strip()
        if game not in VALID_GAMES:
            return jsonify({'success': False, 'error': f'game must be one of {VALID_GAMES}'}), 400

        conn = get_db_conn()
        cur  = conn.cursor()
        cur.execute(
            """
            SELECT name, MAX(score) AS best_score
            FROM game_scores
            WHERE game = %s
              AND DATE_TRUNC('month', submitted_at) = DATE_TRUNC('month', NOW())
            GROUP BY user_id, name
            ORDER BY best_score DESC
            LIMIT 20
            """,
            (game,)
        )
        rows   = cur.fetchall()
        result = [{'rank': i + 1, 'name': r[0], 'score': r[1]} for i, r in enumerate(rows)]
        return jsonify({'success': True, 'leaderboard': result})

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        if cur: cur.close()
        if conn: conn.close()


# ─── My Scores This Month ────────────────────────────────────────────
@games_bp.route('/games/my-scores', methods=['GET'])
@require_jwt
def my_scores():
    conn = cur = None
    try:
        conn = get_db_conn()
        cur  = conn.cursor()
        cur.execute(
            """
            SELECT game, MAX(score) AS best_score
            FROM game_scores
            WHERE user_id = %s
              AND DATE_TRUNC('month', submitted_at) = DATE_TRUNC('month', NOW())
            GROUP BY game
            """,
            (g.user_id,)
        )
        scores = {r[0]: r[1] for r in cur.fetchall()}
        # Fill missing games with 0
        result = {game: scores.get(game, 0) for game in VALID_GAMES}
        return jsonify({'success': True, 'scores': result})

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        if cur: cur.close()
        if conn: conn.close()

import json
import os
from flask import Flask, jsonify, send_file
import firebase_admin
from firebase_admin import credentials
from flask_cors import CORS  # ← add this

from config import FIREBASE_CREDENTIALS_JSON
from routes.auth         import auth_bp
from routes.music        import music_bp
from routes.user         import user_bp
from routes.subscription import subscription_bp
from routes.games        import games_bp
from routes.stats        import stats_bp

app = Flask(__name__)
CORS(app, origins=[
    "https://pandamusicforpandas.netlify.app",
    "https://pandauniverse.netlify.app"
])

# ─── Firebase Init ───────────────────────────────────────────────────
if FIREBASE_CREDENTIALS_JSON:
    try:
        cred_dict = json.loads(FIREBASE_CREDENTIALS_JSON)
        cred      = credentials.Certificate(cred_dict)
        firebase_admin.initialize_app(cred)
        print("Firebase initialized ✅", flush=True)
    except Exception as e:
        print(f"Firebase init failed: {e}", flush=True)

# ─── Register Blueprints ─────────────────────────────────────────────
app.register_blueprint(auth_bp)
app.register_blueprint(music_bp)
app.register_blueprint(user_bp)
app.register_blueprint(subscription_bp)
app.register_blueprint(games_bp)
app.register_blueprint(stats_bp)

# ─── Core Routes ─────────────────────────────────────────────────────
@app.route('/ping', methods=['GET'])
def ping():
    return jsonify({'status': 'alive'}), 200


APP_CONFIG = {
    "min_version":    1,
    "force_update":   False,
    "update_message": "🐼 Welcome to PandaMusic v2!"
}

@app.route('/config', methods=['GET'])
def config():
    return jsonify(APP_CONFIG), 200


@app.route('/download', methods=['GET'])
def download():
    apk_path = 'pandamusic.apk'
    if os.path.exists(apk_path):
        return send_file(apk_path, as_attachment=True)
    return jsonify({'error': 'APK not available yet'}), 404


# ─── Run ─────────────────────────────────────────────────────────────
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000, debug=True)

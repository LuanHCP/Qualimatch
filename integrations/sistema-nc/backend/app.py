import os
from flask import Flask, jsonify, send_from_directory, request

import config
import db

FRONTEND_DIR = os.environ.get(
    "FRONTEND_DIR",
    os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")),
)


def create_app():
    app = Flask(__name__, static_folder=None)
    app.config["MAX_CONTENT_LENGTH"] = config.MAX_UPLOAD_MB * 1024 * 1024 + (1024 * 1024)

    import routes_auth
    import routes_admin
    import routes_catalog
    import routes_ncs
    import routes_import_export

    app.register_blueprint(routes_auth.bp)
    app.register_blueprint(routes_admin.bp)
    app.register_blueprint(routes_catalog.bp)
    app.register_blueprint(routes_ncs.bp)
    app.register_blueprint(routes_import_export.bp)

    @app.after_request
    def set_security_headers(resp):
        # Cabeçalhos equivalentes ao que "helmet" faria em Express.
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers.pop("X-Frame-Options", None)
        resp.headers["Content-Security-Policy"] = (
            "frame-ancestors http://localhost:* http://127.0.0.1:*"
        )
        resp.headers["Referrer-Policy"] = "same-origin"
        resp.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
        if request.path.startswith("/api/"):
            resp.headers["Cache-Control"] = "no-store"
        return resp

    @app.errorhandler(413)
    def too_large(_e):
        return jsonify(error="Arquivo excede o tamanho máximo permitido."), 413

    @app.errorhandler(404)
    def not_found(e):
        if request.path.startswith("/api/"):
            return jsonify(error="rota não encontrada"), 404
        return send_from_directory(FRONTEND_DIR, "index.html")

    @app.errorhandler(500)
    def server_error(e):
        app.logger.exception(e)
        if request.path.startswith("/api/"):
            return jsonify(error="erro interno do servidor"), 500
        raise e

    @app.get("/api/health")
    def health():
        try:
            db.fetchone("SELECT 1 AS ok;")
            return jsonify(status="ok", app="sistema-nc")
        except Exception as e:
            return jsonify(status="degraded", detail=str(e)), 500

    # ---- serve o frontend estático (SPA) a partir da raiz do projeto ----
    @app.get("/")
    def index():
        return send_from_directory(FRONTEND_DIR, "index.html")

    @app.get("/assets/<path:subpath>")
    def assets(subpath):
        return send_from_directory(os.path.join(FRONTEND_DIR, "assets"), subpath)

    return app


app = create_app()

if __name__ == "__main__":
    debug = os.environ.get("FLASK_DEBUG", "false").lower() == "true"
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "8000")), debug=debug, threaded=True)

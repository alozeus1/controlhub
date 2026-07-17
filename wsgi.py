from app import create_app

app = create_app()

if __name__ == "__main__":
    # DEVELOPMENT ONLY. Production serves this module via gunicorn
    # (see Dockerfile.api / Procfile). The Flask dev server must never be used
    # to serve production traffic.
    import os
    if os.environ.get("ENVIRONMENT") == "production":
        raise SystemExit(
            "Refusing to start the Flask development server in production. "
            "Use gunicorn (see Dockerfile.api / Procfile)."
        )
    app.run(host="127.0.0.1", port=int(os.environ.get("PORT", 8000)), debug=False)

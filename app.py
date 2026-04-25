"""SecScenario — localhost vulnerability-to-CTF pipeline."""
import os
import re
import shutil
import uuid
from pathlib import Path

from flask import (
    Flask, render_template, request, redirect, url_for,
    flash, jsonify, abort, send_from_directory,
)
from werkzeug.utils import secure_filename

from config import Config
import database as db
from extractor import extract_text
from analyzer import analyze_report
from challenge_generator import generate_challenge
from url_fetcher import fetch_url, is_valid_url, detect_platform
import runner


def create_app() -> Flask:
    Config.ensure_dirs()
    db.init_db()

    app = Flask(__name__)
    app.config.from_object(Config)

    @app.route("/")
    def index():
        reports_all = db.list_reports()
        challenges_all = db.list_challenges()
        return render_template(
            "index.html",
            reports=reports_all[:5],
            challenges=challenges_all[:5],
            reports_total=len(reports_all),
            challenges_total=len(challenges_all),
        )

    @app.route("/reports")
    def list_reports():
        return render_template("list_reports.html", reports=db.list_reports())

    @app.route("/challenges")
    def list_challenges():
        return render_template("list_challenges.html", challenges=db.list_challenges())

    @app.route("/upload", methods=["GET", "POST"])
    def upload():
        if request.method == "GET":
            return render_template("upload.html")

        files = request.files.getlist("files")
        if not files or all(f.filename == "" for f in files):
            flash("No file selected.", "error")
            return redirect(url_for("upload"))

        saved_ids = []
        for f in files:
            if not f or not f.filename:
                continue
            original_name = f.filename
            ext = original_name.rsplit(".", 1)[-1].lower() if "." in original_name else ""
            if ext and ext not in Config.ALLOWED_EXTENSIONS:
                flash(f"Skipped '{original_name}' — unsupported type.", "warn")
                continue

            safe_base = secure_filename(Path(original_name).name) or "upload"
            unique = f"{uuid.uuid4().hex[:8]}_{safe_base}"
            dest = Config.UPLOAD_DIR / unique
            f.save(dest)

            try:
                text = extract_text(dest)
            except Exception as e:
                text = f"[extraction failed: {e}]"

            rid = db.insert_report(
                filename=unique,
                original_name=original_name,
                file_type=ext or "unknown",
                size_bytes=dest.stat().st_size,
                extracted_text=text,
            )
            saved_ids.append(rid)

        if not saved_ids:
            flash("Nothing was uploaded.", "error")
            return redirect(url_for("upload"))

        flash(f"Uploaded {len(saved_ids)} file(s).", "ok")
        if len(saved_ids) == 1:
            return redirect(url_for("view_report", report_id=saved_ids[0]))
        return redirect(url_for("index"))

    @app.route("/upload/url", methods=["POST"])
    def upload_url():
        url = (request.form.get("url") or "").strip()
        source_type = (request.form.get("source_type") or "blog").strip().lower()
        if source_type not in {"blog", "report"}:
            source_type = "blog"

        if not url or not is_valid_url(url):
            flash("Please paste a valid http(s) URL.", "error")
            return redirect(url_for("upload"))

        try:
            fetched = fetch_url(url)
        except Exception as e:
            flash(f"Couldn't fetch that URL: {e}", "error")
            return redirect(url_for("upload"))

        if not fetched.text or len(fetched.text) < 200:
            flash(
                "Fetched the page but couldn't extract readable content "
                "(likely login-gated or JS-rendered). Try pasting the report as a file instead.",
                "warn",
            )
            return redirect(url_for("upload"))

        # Save as a synthetic "file" so the rest of the pipeline treats it uniformly
        safe_title = re.sub(r"[^a-zA-Z0-9]+", "_", (fetched.title or "page"))[:60] or "page"
        unique = f"{uuid.uuid4().hex[:8]}_{safe_title}.txt"
        dest = Config.UPLOAD_DIR / unique

        header = (
            f"# Fetched from URL\n"
            f"Source type: {source_type}\n"
            f"Platform: {fetched.platform}\n"
            f"URL: {fetched.url}\n"
            f"Final URL: {fetched.final_url}\n"
            f"Title: {fetched.title}\n"
            f"{'-' * 60}\n\n"
        )
        full_text = header + fetched.text
        dest.write_text(full_text, encoding="utf-8")

        original_display = fetched.title or fetched.url
        rid = db.insert_report(
            filename=unique,
            original_name=f"[{source_type.upper()}] {original_display}",
            file_type=f"url-{fetched.platform}",
            size_bytes=dest.stat().st_size,
            extracted_text=full_text,
        )

        flash(f"Fetched {fetched.platform} {source_type}: \"{fetched.title or fetched.url}\"", "ok")
        return redirect(url_for("view_report", report_id=rid))

    @app.route("/report/<int:report_id>")
    def view_report(report_id):
        report = db.get_report(report_id)
        if not report:
            abort(404)
        analysis = db.get_analysis_by_report(report_id)
        return render_template("report.html", report=report, analysis=analysis)

    @app.route("/report/<int:report_id>/analyze", methods=["POST"])
    def analyze(report_id):
        report = db.get_report(report_id)
        if not report:
            abort(404)
        try:
            db.update_report_status(report_id, "analyzing")
            data, raw = analyze_report(report["extracted_text"] or "")
            import json as _json
            analysis_id = db.insert_analysis(report_id, data, _json.dumps(data, indent=2))
            db.update_report_status(report_id, "analyzed")
            return jsonify({"ok": True, "analysis_id": analysis_id, "data": data})
        except Exception as e:
            db.update_report_status(report_id, "error")
            return jsonify({"ok": False, "error": str(e)}), 500

    @app.route("/report/<int:report_id>/generate", methods=["POST"])
    def generate(report_id):
        report = db.get_report(report_id)
        if not report:
            abort(404)
        analysis = db.get_analysis_by_report(report_id)
        if not analysis:
            return jsonify({"ok": False, "error": "Run analysis first."}), 400
        try:
            used_ports = {c["port"] for c in db.list_challenges() if c.get("port")}
            spec, folder, flag, port = generate_challenge(
                dict(analysis), used_ports, report_text=report.get("extracted_text") or ""
            )
            cid = db.insert_challenge(
                analysis_id=analysis["id"],
                name=spec.get("name", "challenge"),
                description=spec.get("description", ""),
                difficulty=spec.get("difficulty", "Medium"),
                category=spec.get("category", "Web"),
                flag=flag,
                folder_path=str(folder),
                port=port,
            )
            return jsonify({
                "ok": True,
                "challenge_id": cid,
                "folder": str(folder),
                "port": port,
            })
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500

    @app.route("/challenge/<int:challenge_id>")
    def view_challenge(challenge_id):
        ch = db.get_challenge(challenge_id)
        if not ch:
            abort(404)
        folder = Path(ch["folder_path"])
        files = []
        spec = {}
        spec_path = folder / "spec.json"
        if spec_path.exists():
            try:
                import json as _json
                spec = _json.loads(spec_path.read_text(encoding="utf-8"))
            except Exception:
                spec = {}
        # Only expose the solution walkthrough — all other source stays hidden.
        solution_path = folder / "SOLUTION.md"
        if solution_path.is_file():
            try:
                files.append({
                    "name": "SOLUTION.md",
                    "content": solution_path.read_text(encoding="utf-8", errors="ignore"),
                })
            except Exception:
                pass
        return render_template("challenge.html", ch=ch, files=files, spec=spec)

    @app.route("/challenge/<int:challenge_id>/submit", methods=["POST"])
    def submit_answer(challenge_id):
        ch = db.get_challenge(challenge_id)
        if not ch:
            return jsonify({"ok": False, "error": "Not found"}), 404
        task_n = request.json.get("task_n") if request.is_json else request.form.get("task_n")
        submitted = (request.json.get("answer") if request.is_json else request.form.get("answer") or "").strip()
        folder = Path(ch["folder_path"])
        spec_path = folder / "spec.json"
        if not spec_path.exists():
            return jsonify({"ok": False, "error": "Challenge spec missing"}), 500
        import json as _json
        try:
            spec = _json.loads(spec_path.read_text(encoding="utf-8"))
        except Exception:
            return jsonify({"ok": False, "error": "Corrupt spec"}), 500
        tasks = spec.get("tasks") or []
        expected = None
        for t in tasks:
            if str(t.get("n")) == str(task_n):
                expected = (t.get("answer") or "").strip()
                break
        if expected is None:
            return jsonify({"ok": False, "error": "Unknown task"}), 400
        correct = submitted.lower() == expected.lower() or submitted == expected
        return jsonify({"ok": True, "correct": correct})

    @app.route("/challenge/<int:challenge_id>/launch", methods=["POST"])
    def launch_challenge(challenge_id):
        ch = db.get_challenge(challenge_id)
        if not ch:
            return jsonify({"ok": False, "error": "Challenge not found"}), 404
        try:
            snap = runner.launch(challenge_id, ch["folder_path"], ch["port"])
            return jsonify({
                "ok": True,
                "state": snap["state"],
                "port": snap["port"],
                "url": f"http://127.0.0.1:{snap['port']}",
                "log": runner.tail_log(challenge_id, 30),
            })
        except Exception as e:
            return jsonify({"ok": False, "error": str(e), "log": runner.tail_log(challenge_id, 30)}), 500

    @app.route("/challenge/<int:challenge_id>/stop", methods=["POST"])
    def stop_challenge(challenge_id):
        ch = db.get_challenge(challenge_id)
        if not ch:
            return jsonify({"ok": False, "error": "Challenge not found"}), 404
        err = None
        try:
            runner.stop(challenge_id, port=ch.get("port"))
        except Exception as e:
            err = f"{type(e).__name__}: {e}"
            app.logger.exception("runner.stop failed for challenge %s", challenge_id)
        return jsonify({"ok": True, "state": "stopped", "error": err})

    @app.route("/challenge/<int:challenge_id>/status")
    def challenge_status(challenge_id):
        ch = db.get_challenge(challenge_id)
        if not ch:
            return jsonify({"ok": False, "error": "Challenge not found"}), 404
        try:
            snap = runner.status(challenge_id, ch["port"])
        except Exception as e:
            app.logger.exception("runner.status failed for challenge %s", challenge_id)
            snap = {"state": "unknown", "port": ch["port"]}
        return jsonify({
            "ok": True,
            "state": snap.get("state", "unknown"),
            "port": snap.get("port", ch["port"]),
            "url": f"http://127.0.0.1:{snap.get('port', ch['port'])}",
            "log": runner.tail_log(challenge_id, 30),
        })

    @app.route("/challenge/<int:challenge_id>/delete", methods=["POST"])
    def delete_challenge_route(challenge_id):
        ch = db.get_challenge(challenge_id)
        if not ch:
            return jsonify({"ok": False, "error": "Not found"}), 404
        # Stop if running (port-aware so orphans also die)
        try:
            runner.stop(challenge_id, port=ch.get("port"))
        except Exception:
            pass
        # Remove folder
        folder = Path(ch["folder_path"]) if ch.get("folder_path") else None
        if folder and folder.exists() and folder.is_dir():
            try:
                shutil.rmtree(folder, ignore_errors=True)
            except Exception:
                pass
        db.delete_challenge(challenge_id)
        return jsonify({"ok": True, "redirect": url_for("index")})

    @app.route("/report/<int:report_id>/delete", methods=["POST"])
    def delete_report_route(report_id):
        report = db.get_report(report_id)
        if not report:
            return jsonify({"ok": False, "error": "Not found"}), 404
        # Stop + remove every child challenge folder
        children = db.get_challenges_by_report(report_id)
        for ch in children:
            try:
                runner.stop(ch["id"], port=ch.get("port"))
            except Exception:
                pass
            folder = Path(ch["folder_path"]) if ch.get("folder_path") else None
            if folder and folder.exists() and folder.is_dir():
                try:
                    shutil.rmtree(folder, ignore_errors=True)
                except Exception:
                    pass
        # Remove the uploaded source file (and any _extracted folder from zip)
        upload_path = Config.UPLOAD_DIR / report["filename"] if report.get("filename") else None
        if upload_path and upload_path.exists():
            try:
                upload_path.unlink()
            except Exception:
                pass
        extracted_dir = Config.UPLOAD_DIR / f"{Path(report['filename']).stem}_extracted"
        if extracted_dir.exists() and extracted_dir.is_dir():
            try:
                shutil.rmtree(extracted_dir, ignore_errors=True)
            except Exception:
                pass
        db.delete_report_cascade(report_id)
        return jsonify({"ok": True, "redirect": url_for("index")})

    @app.route("/uploads/<path:name>")
    def serve_upload(name):
        return send_from_directory(Config.UPLOAD_DIR, name, as_attachment=True)

    @app.errorhandler(413)
    def too_large(_e):
        return render_template("error.html", message="File too large (limit 100 MB)."), 413

    return app


if __name__ == "__main__":
    app = create_app()
    app.run(host=Config.HOST, port=Config.PORT, debug=Config.DEBUG)

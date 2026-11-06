import io
import math
import os
import re
from pathlib import Path
from uuid import uuid4

from bson import ObjectId
from flask import Flask, jsonify, render_template, request, send_from_directory
from flask import current_app
from PIL import Image, UnidentifiedImageError
from pymongo import MongoClient
from pymongo.errors import PyMongoError
from werkzeug.exceptions import RequestEntityTooLarge


BASE_DIR = Path(__file__).resolve().parent
GENEROS = ("Rock", "Pop", "Rap", "Electrónica")
MAXIMO_IMAGEN = 5 * 1024 * 1024
MAXIMO_LOG = 5000
FORMATOS_IMAGEN = {
    "PNG": ".png",
    "JPEG": ".jpg",
    "GIF": ".gif",
    "BMP": ".bmp",
    "WEBP": ".webp",
}


def create_app():
    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = MAXIMO_IMAGEN + 64 * 1024
    app.config["IMAGE_FOLDER"] = BASE_DIR / "imagenes_canciones"
    app.config["MONGODB_URI"] = os.environ.get("MONGODB_URI", "mongodb://localhost:27017/")

    client = MongoClient(app.config["MONGODB_URI"], serverSelectionTimeoutMS=2000)
    app.extensions["mongodb_client"] = client
    app.extensions["songs_collection"] = client["lettermusicbox"]["canciones"]

    @app.get("/")
    def index():
        return render_template("index.html", generos=GENEROS)

    @app.get("/logo.png")
    def logo():
        return send_from_directory(BASE_DIR, "logo.png")

    @app.get("/uploads/<path:filename>")
    def uploaded_image(filename):
        if not re.fullmatch(r"[A-Za-z0-9._-]{1,255}", filename):
            return jsonify(error="Imagen no encontrada."), 404
        return send_from_directory(current_app.config["IMAGE_FOLDER"], filename)

    @app.get("/api/songs")
    def list_songs():
        query = request.args.get("q", "").strip()[:100]
        genre = request.args.get("genre", "").strip()
        criteria = {}
        if query:
            escaped_query = re.escape(query)
            criteria["$or"] = [
                {"nombre": {"$regex": escaped_query, "$options": "i"}},
                {"artista": {"$regex": escaped_query, "$options": "i"}},
            ]
        if genre and genre in GENEROS:
            criteria["genero"] = genre
        try:
            songs = [
                _serialize_song(song)
                for song in app.extensions["songs_collection"].find(criteria).sort("nombre", 1)
            ]
            return jsonify(songs=songs)
        except PyMongoError:
            app.logger.exception("No se pudo consultar la biblioteca.")
            return jsonify(error="No se pudo conectar con MongoDB."), 503

    @app.post("/api/songs")
    def create_song():
        data, error = _read_song_data()
        if error:
            return jsonify(error=error), 400
        try:
            image_name = _save_uploaded_image(request.files.get("image"))
        except ValueError as image_error:
            return jsonify(error=str(image_error)), 400
        except OSError:
            app.logger.exception("No se pudo guardar la portada.")
            return jsonify(error="No se pudo guardar la portada en el servidor."), 500
        data["imagen"] = image_name
        try:
            result = app.extensions["songs_collection"].insert_one(data)
            data["_id"] = result.inserted_id
            return jsonify(song=_serialize_song(data)), 201
        except PyMongoError:
            _remove_uploaded_image(image_name)
            app.logger.exception("No se pudo guardar la canción.")
            return jsonify(error="No se pudo guardar la canción en MongoDB."), 503

    @app.put("/api/songs/<song_id>")
    def update_song(song_id):
        if not ObjectId.is_valid(song_id):
            return jsonify(error="Canción no encontrada."), 404
        data, error = _read_song_data()
        if error:
            return jsonify(error=error), 400
        try:
            image_name = _save_uploaded_image(request.files.get("image"))
        except ValueError as image_error:
            return jsonify(error=str(image_error)), 400
        except OSError:
            app.logger.exception("No se pudo guardar la portada.")
            return jsonify(error="No se pudo guardar la portada en el servidor."), 500

        if image_name:
            data["imagen"] = image_name
        elif request.form.get("remove_image") == "true":
            data["imagen"] = None

        try:
            collection = app.extensions["songs_collection"]
            result = collection.update_one({"_id": ObjectId(song_id)}, {"$set": data})
            if result.matched_count == 0:
                _remove_uploaded_image(image_name)
                return jsonify(error="Canción no encontrada."), 404
            song = collection.find_one({"_id": ObjectId(song_id)})
            return jsonify(song=_serialize_song(song))
        except PyMongoError:
            _remove_uploaded_image(image_name)
            app.logger.exception("No se pudo actualizar la canción.")
            return jsonify(error="No se pudo actualizar la canción en MongoDB."), 503

    @app.delete("/api/songs/<song_id>")
    def delete_song(song_id):
        if not ObjectId.is_valid(song_id):
            return jsonify(error="Canción no encontrada."), 404
        try:
            result = app.extensions["songs_collection"].delete_one({"_id": ObjectId(song_id)})
            if result.deleted_count == 0:
                return jsonify(error="Canción no encontrada."), 404
            return jsonify(ok=True)
        except PyMongoError:
            app.logger.exception("No se pudo eliminar la canción.")
            return jsonify(error="No se pudo eliminar la canción de MongoDB."), 503

    @app.errorhandler(RequestEntityTooLarge)
    def request_too_large(_error):
        return jsonify(error="La imagen supera el límite de 5 MB."), 413

    return app


def _read_song_data():
    name = request.form.get("nombre", "").strip()
    artist = request.form.get("artista", "").strip()
    genre = request.form.get("genero", "").strip()
    log = request.form.get("log", "").strip()
    rating_text = request.form.get("calificacion", "0").strip()

    if not name or not artist:
        return None, "Completa el nombre de la canción y el artista."
    if len(name) > 200 or len(artist) > 200:
        return None, "El nombre y el artista deben tener como máximo 200 caracteres."
    if genre not in GENEROS:
        return None, "Selecciona un género válido."
    if len(log) > MAXIMO_LOG:
        return None, f"El log puede tener como máximo {MAXIMO_LOG} caracteres."
    try:
        rating = float(rating_text)
    except ValueError:
        return None, "La calificación debe ser un número entre 0 y 5."
    if not math.isfinite(rating) or not 0 <= rating <= 5 or rating * 2 % 1:
        return None, "La calificación debe estar entre 0 y 5, en incrementos de 0,5."

    return {
        "nombre": name,
        "artista": artist,
        "genero": genre,
        "log": log,
        "calificacion": rating,
    }, None


def _save_uploaded_image(upload):
    if upload is None or not upload.filename:
        return None
    contents = upload.stream.read(MAXIMO_IMAGEN + 1)
    if len(contents) > MAXIMO_IMAGEN:
        raise ValueError("La imagen supera el límite de 5 MB.")
    try:
        with Image.open(io.BytesIO(contents)) as image:
            image_format = image.format
            dimensiones_grandes = image.width * image.height > 40_000_000
            if not dimensiones_grandes:
                image.verify()
    except (UnidentifiedImageError, Image.DecompressionBombError, OSError, ValueError) as error:
        raise ValueError("El archivo seleccionado no es una imagen válida.") from error
    if dimensiones_grandes:
        raise ValueError("La imagen tiene dimensiones demasiado grandes.")
    extension = FORMATOS_IMAGEN.get(image_format)
    if extension is None:
        raise ValueError("Formato no compatible. Usa PNG, JPG, GIF, BMP o WEBP.")

    folder = current_app.config["IMAGE_FOLDER"]
    folder.mkdir(parents=True, exist_ok=True)
    filename = f"{uuid4().hex}{extension}"
    (folder / filename).write_bytes(contents)
    return filename


def _remove_uploaded_image(filename):
    if filename:
        (current_app.config["IMAGE_FOLDER"] / filename).unlink(missing_ok=True)


def _serialize_song(song):
    return {
        "id": str(song["_id"]),
        "nombre": song.get("nombre", ""),
        "artista": song.get("artista", ""),
        "genero": song.get("genero", ""),
        "log": song.get("log", ""),
        "calificacion": song.get("calificacion", 0),
        "imagen": song.get("imagen"),
    }


app = create_app()


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)

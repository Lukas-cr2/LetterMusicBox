import ipaddress
import io
import re
import shutil
import socket
import tempfile
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk
from urllib.error import HTTPError
from urllib.parse import urljoin, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
from uuid import uuid4

from pymongo import MongoClient
from pymongo.errors import PyMongoError, ServerSelectionTimeoutError
from bson import ObjectId
from PIL import Image, ImageTk


MONGODB_URI = "mongodb://localhost:27017/"
DATABASE_NAME = "lettermusicbox"
COLLECTION_NAME = "canciones"
GENEROS = ("Rock", "Pop", "Rap", "Electrónica")
TAMANO_MAXIMO_IMAGEN = 5 * 1024 * 1024
MAXIMO_CARACTERES_LOG = 5000


class _SinRedirecciones(HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, new_url):
        return None


class BibliotecaMusical:
    def __init__(self, root):
        self.root = root
        self.root.title("LetterMusicBox | Mejor que ayer")
        self.root.geometry("1400x900")
        self.root.minsize(760, 560)
        self.root.configure(bg="#f3f5f9")
        self.cancion_seleccionada = None
        self.imagen_guardada = None
        self.imagen_pendiente = None
        self.imagen_temporal_url = None
        self.quitar_imagen = False
        self.portada_img = None

        # MongoDB se ejecuta localmente y esto lo hizo la ia asi que no lo toquen
        self.cliente = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=2000)
        self.cliente.admin.command("ping")
        self.canciones = self.cliente[DATABASE_NAME][COLLECTION_NAME]

        self._configurar_estilos()
        self._crear_interfaz()
        self.mostrar_canciones()

    def _configurar_estilos(self):
        estilo = ttk.Style()
        estilo.theme_use("clam")
        estilo.configure("TFrame", background="#f3f5f9")
        estilo.configure("TLabel", background="#f3f5f9", foreground="#202938", font=("TkDefaultFont", 10))
        estilo.configure("Titulo.TLabel", font=("TkDefaultFont", 20, "bold"), foreground="#172554")
        estilo.configure("Subtitulo.TLabel", font=("TkDefaultFont", 10), foreground="#64748b")
        estilo.configure("TButton", padding=(10, 7))
        estilo.configure("Treeview", rowheight=30, font=("TkDefaultFont", 10))
        estilo.configure("Treeview.Heading", font=("TkDefaultFont", 10, "bold"))

    def _crear_interfaz(self):
        contenedor = ttk.Frame(self.root, padding=22)
        contenedor.pack(fill="both", expand=True)

        encabezado = ttk.Frame(contenedor)
        encabezado.pack(fill="x", pady=(0, 18))
        texto_encabezado = ttk.Frame(encabezado)
        texto_encabezado.pack(side="left", anchor="w")
        ttk.Label(texto_encabezado, text="LetterMusicBox", style="Titulo.TLabel").pack(anchor="w")
        ttk.Label(
            texto_encabezado,
            text="Como letterbox, pero para musica",
            style="Subtitulo.TLabel",
        ).pack(anchor="w", pady=(2, 0))

        ruta_logo = Path(__file__).with_name("logo.png")
        self.logo_img = None
        if ruta_logo.is_file():
            imagen_logo = tk.PhotoImage(file=str(ruta_logo))
            factor = max(1, (imagen_logo.width() + 139) // 140, (imagen_logo.height() + 139) // 140)
            self.logo_img = imagen_logo.subsample(factor, factor)
            ttk.Label(encabezado, image=self.logo_img).pack(side="right", anchor="e")

        formulario = ttk.LabelFrame(contenedor, text="Datos de la canción", padding=14)
        formulario.pack(fill="x", pady=(0, 14))
        formulario.columnconfigure(1, weight=1)
        formulario.columnconfigure(3, weight=1)

        ttk.Label(formulario, text="Nombre:").grid(row=0, column=0, sticky="w", padx=(0, 8), pady=5)
        self.entrada_nombre = ttk.Entry(formulario)
        self.entrada_nombre.grid(row=0, column=1, sticky="ew", padx=(0, 18), pady=5)

        ttk.Label(formulario, text="Artista:").grid(row=0, column=2, sticky="w", padx=(0, 8), pady=5)
        self.entrada_artista = ttk.Entry(formulario)
        self.entrada_artista.grid(row=0, column=3, sticky="ew", pady=5)

        ttk.Label(formulario, text="Género:").grid(row=1, column=0, sticky="w", padx=(0, 8), pady=5)
        self.genero = ttk.Combobox(formulario, values=GENEROS, state="readonly")
        self.genero.set(GENEROS[0])
        self.genero.grid(row=1, column=1, sticky="ew", padx=(0, 18), pady=5)

        ttk.Label(formulario, text="Log:").grid(row=1, column=2, sticky="nw", padx=(0, 8), pady=5)
        self.entrada_log = tk.Text(formulario, height=3, wrap="word", font=("TkDefaultFont", 10))
        self.entrada_log.grid(row=1, column=3, sticky="ew", pady=5)

        imagen_frame = ttk.LabelFrame(formulario, text="Portada", padding=5)
        imagen_frame.grid(row=0, column=4, rowspan=2, padx=(8, 0), pady=5)
        self.imagen_preview = tk.Button(
            imagen_frame,
            text="+",
            width=8,
            height=2,
            font=("TkDefaultFont", 22, "bold"),
            bg="#f8fafc",
            fg="#64748b",
            relief="solid",
            command=self._elegir_imagen,
        )
        self.imagen_preview.pack(side="left")
        acciones_portada = ttk.Frame(imagen_frame)
        acciones_portada.pack(side="left", padx=(4, 0))
        ttk.Button(acciones_portada, text="URL", width=4, command=self._pedir_url_imagen).pack(pady=(0, 4))
        ttk.Button(acciones_portada, text="×", width=2, command=self._quitar_imagen_actual).pack()

        calificacion_frame = ttk.Frame(formulario)
        calificacion_frame.grid(row=2, column=0, columnspan=5, pady=(8, 0))
        ttk.Label(calificacion_frame, text="Calificación:").pack(side="left", padx=(0, 6))
        self.calificacion = tk.DoubleVar(value=0.0)
        tk.Button(
            calificacion_frame,
            text="0",
            width=1,
            padx=1,
            pady=1,
            command=lambda: self._set_calificacion(0.0),
        ).pack(side="left", padx=(0, 3))
        self.botones_estrellas = []

        for indice in range(5):
            boton = tk.Button(
                calificacion_frame,
                text="☆",
                width=2,
                relief="flat",
                borderwidth=1,
                font=("TkDefaultFont", 12, "bold"),
            )
            boton.bind(
                "<Button-1>",
                lambda evento, indice=indice: self._calificar_estrella(evento, indice),
            )
            boton.pack(side="left", padx=1)
            self.botones_estrellas.append(boton)

        self.calificacion_label = ttk.Label(calificacion_frame, text="0.0 / 5")
        self.calificacion_label.pack(side="left", padx=(10, 0))
        self._actualizar_estrellas()

        acciones = ttk.Frame(formulario)
        acciones.grid(row=3, column=0, columnspan=5, sticky="w", pady=(8, 0))
        ttk.Button(acciones, text="Agregar canción", command=self.agregar_cancion).pack(side="left", padx=(0, 8))
        ttk.Button(acciones, text="Guardar cambios", command=self.editar_cancion).pack(side="left", padx=(0, 8))
        ttk.Button(acciones, text="Eliminar seleccionada", command=self.eliminar_cancion).pack(side="left", padx=(0, 8))
        ttk.Button(acciones, text="Limpiar", command=self.limpiar_formulario).pack(side="left")

        filtros = ttk.Frame(contenedor)
        filtros.pack(fill="x", pady=(0, 10))
        ttk.Label(filtros, text="Buscar:").pack(side="left", padx=(0, 7))
        self.busqueda = tk.StringVar()
        self.busqueda.trace_add("write", lambda *_: self.mostrar_canciones())
        ttk.Entry(filtros, textvariable=self.busqueda).pack(side="left", fill="x", expand=True, padx=(0, 14))
        ttk.Label(filtros, text="Género:").pack(side="left", padx=(0, 7))
        self.filtro_genero = ttk.Combobox(
            filtros,
            values=("Todos", *GENEROS),
            state="readonly",
            width=16,
        )
        self.filtro_genero.set("Todos")
        self.filtro_genero.pack(side="left")
        self.filtro_genero.bind("<<ComboboxSelected>>", lambda _event: self.mostrar_canciones())

        tabla_frame = ttk.Frame(contenedor)
        tabla_frame.pack(fill="both", expand=True)
        columnas = ("nombre", "artista", "genero", "calificacion")
        self.tabla = ttk.Treeview(tabla_frame, columns=columnas, show="headings", selectmode="browse")
        self.tabla.heading("nombre", text="Canción")
        self.tabla.heading("artista", text="Artista")
        self.tabla.heading("genero", text="Género")
        self.tabla.heading("calificacion", text="Calificación")
        self.tabla.column("nombre", width=190, minwidth=120)
        self.tabla.column("artista", width=160, minwidth=110)
        self.tabla.column("genero", width=120, minwidth=90)
        self.tabla.column("calificacion", width=140, minwidth=110, anchor="center")
        scrollbar = ttk.Scrollbar(tabla_frame, orient="vertical", command=self.tabla.yview)
        self.tabla.configure(yscrollcommand=scrollbar.set)
        self.tabla.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        self.tabla.bind("<<TreeviewSelect>>", self._seleccionar_cancion)

        self.estado = tk.StringVar(value="Conectado a MongoDB local.")
        ttk.Label(contenedor, textvariable=self.estado, style="Subtitulo.TLabel").pack(anchor="w", pady=(10, 0))

    def _datos_formulario(self):
        nombre = self.entrada_nombre.get().strip()
        artista = self.entrada_artista.get().strip()
        log = self.entrada_log.get("1.0", "end").strip()
        if not nombre or not artista:
            messagebox.showwarning("Oye, y perry?", "Completa el nombre de la canción y el artista.", parent=self.root)
            return None
        if len(log) > MAXIMO_CARACTERES_LOG:
            messagebox.showwarning(
                "Log demasiado largo",
                f"El log puede tener como máximo {MAXIMO_CARACTERES_LOG} caracteres.",
                parent=self.root,
            )
            return None
        return {
            "nombre": nombre,
            "artista": artista,
            "genero": self.genero.get(),
            "log": log,
            "calificacion": float(self.calificacion.get()),
        }

    def _set_calificacion(self, valor):
        self.calificacion.set(valor)
        self._actualizar_estrellas()

    def _elegir_imagen(self):
        ruta = filedialog.askopenfilename(
            parent=self.root,
            title="Seleccionar imagen de la canción",
            filetypes=(("Imágenes", "*.png *.jpg *.jpeg *.gif *.bmp *.webp"), ("Todos los archivos", "*.*")),
        )
        if not ruta:
            return
        self._limpiar_imagen_temporal_url()
        self.imagen_pendiente = Path(ruta)
        self.quitar_imagen = False
        self._actualizar_vista_imagen()

    def _pedir_url_imagen(self):
        url = simpledialog.askstring(
            "Agregar url",
            "Pegala aca:",
            parent=self.root,
        )
        if not url or not url.strip():
            return
        self.estado.set("Descargando bip bop…")
        self.root.update_idletasks()
        try:
            ruta = self._descargar_imagen_desde_url(url.strip())
        except (OSError, ValueError, HTTPError) as error:
            self.estado.set("ERROR ERROR ERROR ERROR.")
            messagebox.showerror("No se pudo cargar la imagen", str(error), parent=self.root)
            return
        self._limpiar_imagen_temporal_url()
        self.imagen_pendiente = ruta
        self.imagen_temporal_url = ruta
        self.quitar_imagen = False
        self._actualizar_vista_imagen()
        self.estado.set("Portada cargada.")

    def _descargar_imagen_desde_url(self, url):
        opener = build_opener(_SinRedirecciones())
        direccion = url
        datos = None
        for intento in range(6):
            self._validar_url_publica(direccion)
            solicitud = Request(direccion, headers={"User-Agent": "LetterMusicBox/1.0", "Accept": "image/*"})
            try:
                with opener.open(solicitud, timeout=8) as respuesta:
                    if not respuesta.headers.get_content_type().startswith("image/"):
                        raise ValueError("El enlace no apunta a un archivo de imagen.")
                    longitud = respuesta.headers.get("Content-Length")
                    if longitud and int(longitud) > TAMANO_MAXIMO_IMAGEN:
                        raise ValueError("La imagen supera el límite de 5 MB.")
                    datos = respuesta.read(TAMANO_MAXIMO_IMAGEN + 1)
                    if len(datos) > TAMANO_MAXIMO_IMAGEN:
                        raise ValueError("La imagen supera el límite de 5 MB.")
                break
            except HTTPError as error:
                if error.code not in (301, 302, 303, 307, 308) or intento == 5:
                    raise ValueError(f"El servidor respondió con HTTP {error.code}.") from error
                destino = error.headers.get("Location")
                if not destino:
                    raise ValueError("El enlace redirigió sin indicar un destino.") from error
                direccion = urljoin(direccion, destino)
        if datos is None:
            raise ValueError("No se pudo descargar la imagen.")

        try:
            imagen = Image.open(io.BytesIO(datos))
            formato = imagen.format
            imagen.verify()
        except (OSError, ValueError) as error:
            raise ValueError("El contenido descargado no es una imagen válida.") from error
        extensiones = {"PNG": ".png", "JPEG": ".jpg", "GIF": ".gif", "BMP": ".bmp", "WEBP": ".webp"}
        extension = extensiones.get(formato)
        if extension is None:
            raise ValueError("Formato no compatible. Usa PNG, JPG, GIF, BMP o WEBP.")
        with tempfile.NamedTemporaryFile(prefix="lettermusicbox_", suffix=extension, delete=False) as archivo:
            archivo.write(datos)
            return Path(archivo.name)

    @staticmethod
    def _validar_url_publica(url):
        partes = urlsplit(url)
        if partes.scheme not in ("http", "https") or not partes.hostname or partes.username or partes.password:
            raise ValueError("Usa una URL pública que empiece con http:// o https://.")
        try:
            puerto = partes.port or (443 if partes.scheme == "https" else 80)
            if puerto not in (80, 443):
                raise ValueError("Solo se permiten URLs en los puertos web estándar.")
            try:
                direcciones = {str(ipaddress.ip_address(partes.hostname))}
            except ValueError:
                resultados = socket.getaddrinfo(partes.hostname, puerto, type=socket.SOCK_STREAM)
                direcciones = {resultado[4][0].split("%")[0] for resultado in resultados}
            if not direcciones or any(not ipaddress.ip_address(direccion).is_global for direccion in direcciones):
                raise ValueError("Por seguridad, solo se permiten servidores públicos de internet.")
        except OSError as error:
            raise ValueError("No se pudo encontrar el servidor de esa URL.") from error

    def _quitar_imagen_actual(self):
        self._limpiar_imagen_temporal_url()
        self.imagen_pendiente = None
        self.imagen_guardada = None
        self.quitar_imagen = True
        self._actualizar_vista_imagen()

    def _limpiar_imagen_temporal_url(self):
        if self.imagen_temporal_url is not None:
            self.imagen_temporal_url.unlink(missing_ok=True)
            self.imagen_temporal_url = None

    def _actualizar_vista_imagen(self):
        ruta = self.imagen_pendiente
        if ruta is None and self.imagen_guardada and not self.quitar_imagen:
            ruta = Path(__file__).with_name("imagenes_canciones") / Path(self.imagen_guardada).name
        if ruta is None or not ruta.is_file():
            self.portada_img = None
            self.imagen_preview.configure(image="", text="+", width=8, height=2)
            return
        try:
            with Image.open(ruta) as imagen:
                imagen.thumbnail((90, 58))
                self.portada_img = ImageTk.PhotoImage(imagen.copy())
            self.imagen_preview.configure(image=self.portada_img, text="", width=90, height=58)
        except (OSError, ValueError):
            self.portada_img = None
            self.imagen_preview.configure(image="", text="!", width=8, height=2)

    def _guardar_imagen(self):
        if self.imagen_pendiente is not None:
            carpeta = Path(__file__).with_name("imagenes_canciones")
            carpeta.mkdir(exist_ok=True)
            nombre = f"{uuid4().hex}{self.imagen_pendiente.suffix.lower()}"
            shutil.copy2(self.imagen_pendiente, carpeta / nombre)
            self.imagen_guardada = nombre
            self.imagen_pendiente = None
            self._limpiar_imagen_temporal_url()
            self.quitar_imagen = False
        return None if self.quitar_imagen else self.imagen_guardada

    def _calificar_estrella(self, evento, indice):
        mitad = evento.x < evento.widget.winfo_width() / 2
        self._set_calificacion(indice + (0.5 if mitad else 1.0))
        return "break"

    def _actualizar_estrellas(self):
        valor_actual = float(self.calificacion.get())
        self.calificacion_label.configure(text=f"{valor_actual:.1f} / 5")

        for indice, boton in enumerate(self.botones_estrellas):
            inicio_estrella = float(indice)
            if valor_actual >= inicio_estrella + 1:
                boton.configure(text="★", bg="#fff7ed", fg="#fbbf24", relief="solid")
            elif valor_actual >= inicio_estrella + 0.5:
                boton.configure(text="⯨", bg="#fff7ed", fg="#fbbf24", relief="solid")
            else:
                boton.configure(text="☆", bg="#f8fafc", fg="#cbd5e1", relief="flat")

    def _formato_estrellas(self, valor):
        valor = max(0.0, min(float(valor or 0), 5.0))
        estrellas = []
        for indice in range(5):
            if valor >= indice + 1:
                estrellas.append("★")
            elif valor >= indice + 0.5:
                estrellas.append("⯨")
            else:
                estrellas.append("☆")
        return "".join(estrellas)

    def agregar_cancion(self):
        datos = self._datos_formulario()
        if datos is None:
            return
        try:
            datos["imagen"] = self._guardar_imagen()
            self.canciones.insert_one(datos)
            self.limpiar_formulario()
            self.mostrar_canciones()
            self.estado.set("Se agrego la cancion")
        except OSError as error:
            messagebox.showerror("Error de imagen", f"No se pudo guardar la imagen.\n\n{error}", parent=self.root)
        except PyMongoError as error:
            self._mostrar_error_db(error)

    def editar_cancion(self):
        if self.cancion_seleccionada is None:
            messagebox.showinfo("No tenemos feria", "Elige una canción de la lista antes de guardar cambios.", parent=self.root)
            return
        datos = self._datos_formulario()
        if datos is None:
            return
        try:
            datos["imagen"] = self._guardar_imagen()
            self.canciones.update_one({"_id": ObjectId(self.cancion_seleccionada)}, {"$set": datos})
            self.limpiar_formulario()
            self.mostrar_canciones()
            self.estado.set("Si si se guardo")
        except OSError as error:
            messagebox.showerror("Error de imagen", f"No se pudo guardar la imagen.\n\n{error}", parent=self.root)
        except PyMongoError as error:
            self._mostrar_error_db(error)

    def eliminar_cancion(self):
        if self.cancion_seleccionada is None:
            messagebox.showinfo("Perfectamente equilibrado", "Elige una canción de la lista para eliminarla.", parent=self.root)
            return
        if not messagebox.askyesno("Chasqueas los dedos?", "¿Eliminar esta canción de la biblioteca?", parent=self.root):
            return
        try:
            self.canciones.delete_one({"_id": ObjectId(self.cancion_seleccionada)})
            self.limpiar_formulario()
            self.mostrar_canciones()
            self.estado.set("Supongo que se acabo...")
        except PyMongoError as error:
            self._mostrar_error_db(error)

    def mostrar_canciones(self):
        if not hasattr(self, "tabla"):
            return
        for elemento in self.tabla.get_children():
            self.tabla.delete(elemento)

        texto = self.busqueda.get().strip() if hasattr(self, "busqueda") else ""
        genero = self.filtro_genero.get() if hasattr(self, "filtro_genero") else "Todos"
        consulta = {}
        if texto:
            patron = re.escape(texto)
            consulta["$or"] = [
                {"nombre": {"$regex": patron, "$options": "i"}},
                {"artista": {"$regex": patron, "$options": "i"}},
            ]
        if genero and genero != "Todos":
            consulta["genero"] = genero

        try:
            for cancion in self.canciones.find(consulta).sort("nombre", 1):
                self.tabla.insert(
                    "",
                    "end",
                    iid=str(cancion["_id"]),
                    values=(
                        cancion.get("nombre", ""),
                        cancion.get("artista", ""),
                        cancion.get("genero", ""),
                        self._formato_estrellas(cancion.get("calificacion", 0)),
                    ),
                )
            total = len(self.tabla.get_children())
            self.estado.set(f"{total} canción(es) · MongoDB local")
        except PyMongoError as error:
            self._mostrar_error_db(error)

    def _seleccionar_cancion(self, _event=None):
        seleccion = self.tabla.selection()
        if not seleccion:
            return
        self._limpiar_imagen_temporal_url()
        self.cancion_seleccionada = seleccion[0]
        cancion = self.canciones.find_one({"_id": ObjectId(self.cancion_seleccionada)})
        if cancion is None:
            return
        self.entrada_nombre.delete(0, "end")
        self.entrada_nombre.insert(0, cancion.get("nombre", ""))
        self.entrada_artista.delete(0, "end")
        self.entrada_artista.insert(0, cancion.get("artista", ""))
        self.genero.set(cancion.get("genero", GENEROS[0]))
        self.entrada_log.delete("1.0", "end")
        self.entrada_log.insert("1.0", cancion.get("log", ""))
        self.imagen_guardada = Path(cancion["imagen"]).name if cancion.get("imagen") else None
        self.imagen_pendiente = None
        self.quitar_imagen = False
        self._actualizar_vista_imagen()
        self.calificacion.set(float(cancion.get("calificacion", 0.0)))
        self._actualizar_estrellas()
        self.estado.set("Canción seleccionada: edita sus datos y tocaq en guardar.")

    def limpiar_formulario(self):
        self._limpiar_imagen_temporal_url()
        self.cancion_seleccionada = None
        self.tabla.selection_remove(self.tabla.selection())
        self.entrada_nombre.delete(0, "end")
        self.entrada_artista.delete(0, "end")
        self.genero.set(GENEROS[0])
        self.entrada_log.delete("1.0", "end")
        self.imagen_guardada = None
        self.imagen_pendiente = None
        self.quitar_imagen = False
        self._actualizar_vista_imagen()
        self.calificacion.set(0.0)
        self._actualizar_estrellas()
        self.entrada_nombre.focus_set()

    def _mostrar_error_db(self, error):
        self.estado.set("Error de conexión o de operación con MongoDB.")
        messagebox.showerror(
            "Error de MongoDB",
            f"No se pudo completar la operación. Comprueba que MongoDB esté iniciado en {MONGODB_URI}.\n\n{error}",
            parent=self.root,
        )


def main():
    root = tk.Tk()
    try:
        BibliotecaMusical(root)
    except (ServerSelectionTimeoutError, PyMongoError) as error:
        messagebox.showerror(
            "No se pudo conectar a MongoDB",
            "Inicia MongoDB local y vuelve a abrir la aplicación.\n\n"
            f"Conexión configurada: {MONGODB_URI}\n\n{error}",
            parent=root,
        )
        root.destroy()
        return
    root.mainloop()


if __name__ == "__main__":
    main()
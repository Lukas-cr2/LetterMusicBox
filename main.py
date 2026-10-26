import re
import shutil
import uuid
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from PIL import Image, ImageTk
from pymongo import MongoClient
from pymongo.errors import PyMongoError, ServerSelectionTimeoutError
from bson import ObjectId


MONGODB_URI = "mongodb://localhost:27017/"
DATABASE_NAME = "lettermusicbox"
COLLECTION_NAME = "canciones"
GENEROS = ("Rock", "Pop", "Rap", "Electrónica")


class BibliotecaMusical:
    def __init__(self, root):
        self.root = root
        self.root.title("LetterMusicBox | Mejor que ayer")
        self.root.geometry("1400x900")
        self.root.minsize(760, 560)
        self.root.configure(bg="#f3f5f9")
        self.cancion_seleccionada = None
        self.imagen_seleccionada = None
        self.portada_photo = None

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

        acciones = ttk.Frame(formulario)
        acciones.grid(row=2, column=0, columnspan=4, sticky="w", pady=(10, 0))
        ttk.Button(acciones, text="Agregar canción", command=self.agregar_cancion).pack(side="left", padx=(0, 8))
        ttk.Button(acciones, text="Guardar cambios", command=self.editar_cancion).pack(side="left", padx=(0, 8))
        ttk.Button(acciones, text="Eliminar seleccionada", command=self.eliminar_cancion).pack(side="left", padx=(0, 8))
        ttk.Button(acciones, text="Limpiar", command=self.limpiar_formulario).pack(side="left")

        calificacion_frame = ttk.Frame(formulario)
        calificacion_frame.grid(row=2, column=4, sticky="w", pady=(10, 0), padx=(12, 0))
        self.portada_canvas = tk.Canvas(
            calificacion_frame,
            width=140,
            height=140,
            bg="#ffffff",
            highlightthickness=1,
            highlightbackground="#cbd5e1",
        )
        self.portada_canvas.pack(anchor="w")
        self._mostrar_portada(None)
        ttk.Button(
            calificacion_frame,
            text="Elegir portada",
            command=self.seleccionar_portada,
        ).pack(anchor="w", pady=(5, 0))

        controles_calificacion = ttk.Frame(calificacion_frame)
        controles_calificacion.pack(anchor="w", pady=(8, 0))
        ttk.Label(controles_calificacion, text="Calificación:").pack(side="left", padx=(0, 6))
        self.calificacion = tk.DoubleVar(value=0.0)
        tk.Button(
            controles_calificacion,
            text="0",
            width=1,
            padx=1,
            pady=1,
            command=lambda: self._set_calificacion(0.0),
        ).pack(side="left", padx=(0, 3))
        self.botones_estrellas = []

        for indice in range(5):
            boton = tk.Button(
            controles_calificacion,
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

        self.calificacion_label = ttk.Label(controles_calificacion, text="0.0 / 5")
        self.calificacion_label.pack(side="left", padx=(10, 0))
        self._actualizar_estrellas()

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
        if not nombre or not artista:
            messagebox.showwarning("Oye, y perry?", "Completa el nombre de la canción y el artista.", parent=self.root)
            return None
        return {
            "nombre": nombre,
            "artista": artista,
            "genero": self.genero.get(),
            "log": self.entrada_log.get("1.0", "end").strip(),
            "calificacion": float(self.calificacion.get()),
            "imagen": self.imagen_seleccionada.as_posix() if self.imagen_seleccionada else "",
        }

    def seleccionar_portada(self):
        ruta_origen = filedialog.askopenfilename(
            parent=self.root,
            title="Elegir portada de la canción",
            filetypes=(
                ("Imágenes", "*.png *.jpg *.jpeg *.gif *.bmp *.webp"),
                ("Todos los archivos", "*.*"),
            ),
        )
        if not ruta_origen:
            return

        origen = Path(ruta_origen)
        carpeta_portadas = Path(__file__).resolve().parent / "covers"
        try:
            with Image.open(origen) as imagen:
                imagen.verify()
            carpeta_portadas.mkdir(exist_ok=True)
            destino = carpeta_portadas / f"{uuid.uuid4().hex}{origen.suffix.lower()}"
            shutil.copy2(origen, destino)
        except (OSError, shutil.Error) as error:
            messagebox.showerror(
                "No se pudo cargar la imagen",
                f"Elige un archivo de imagen válido.\n\n{error}",
                parent=self.root,
            )
            return

        self.imagen_seleccionada = Path("covers") / destino.name
        self._mostrar_portada(self.imagen_seleccionada)

    def _mostrar_portada(self, ruta):
        self.portada_canvas.delete("all")
        if not ruta:
            self.portada_photo = None
            self.portada_canvas.create_text(70, 70, text="Sin portada", fill="#64748b")
            return

        ruta_imagen = Path(ruta)
        if not ruta_imagen.is_absolute():
            ruta_imagen = Path(__file__).resolve().parent / ruta_imagen
        try:
            with Image.open(ruta_imagen) as imagen:
                imagen.thumbnail((140, 140))
                self.portada_photo = ImageTk.PhotoImage(imagen.copy(), master=self.root)
        except (OSError, ValueError):
            self.portada_photo = None
            self.portada_canvas.create_text(
                70,
                70,
                text="Imagen no\ndisponible",
                fill="#64748b",
                justify="center",
            )
            return

        self.portada_canvas.create_image(70, 70, image=self.portada_photo)

    def _set_calificacion(self, valor):
        self.calificacion.set(valor)
        self._actualizar_estrellas()

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
            self.canciones.insert_one(datos)
            self.limpiar_formulario()
            self.mostrar_canciones()
            self.estado.set("Se agrego la cancion")
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
            self.canciones.update_one({"_id": ObjectId(self.cancion_seleccionada)}, {"$set": datos})
            self.limpiar_formulario()
            self.mostrar_canciones()
            self.estado.set("Si si se guardo")
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
        self.imagen_seleccionada = Path(cancion["imagen"]) if cancion.get("imagen") else None
        self._mostrar_portada(self.imagen_seleccionada)
        self.calificacion.set(float(cancion.get("calificacion", 0.0)))
        self._actualizar_estrellas()
        self.estado.set("Canción seleccionada: edita sus datos y tocaq en guardar.")

    def limpiar_formulario(self):
        self.cancion_seleccionada = None
        self.tabla.selection_remove(self.tabla.selection())
        self.entrada_nombre.delete(0, "end")
        self.entrada_artista.delete(0, "end")
        self.genero.set(GENEROS[0])
        self.entrada_log.delete("1.0", "end")
        self.imagen_seleccionada = None
        self._mostrar_portada(None)
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

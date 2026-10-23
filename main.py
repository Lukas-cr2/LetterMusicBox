import re
import tkinter as tk
from tkinter import messagebox, ttk

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
        self.root.geometry("1000x750")
        self.root.minsize(760, 560)
        self.root.configure(bg="#f3f5f9")
        self.cancion_seleccionada = None

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

        ttk.Label(contenedor, text="LetterMusicBox", style="Titulo.TLabel").pack(anchor="w")
        ttk.Label(
            contenedor,
            text="Como letterbox, pero para musica",
            style="Subtitulo.TLabel",
        ).pack(anchor="w", pady=(2, 18))

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
        columnas = ("nombre", "artista", "genero", "log")
        self.tabla = ttk.Treeview(tabla_frame, columns=columnas, show="headings", selectmode="browse")
        self.tabla.heading("nombre", text="Canción")
        self.tabla.heading("artista", text="Artista")
        self.tabla.heading("genero", text="Género")
        self.tabla.heading("log", text="Log / notas")
        self.tabla.column("nombre", width=190, minwidth=120)
        self.tabla.column("artista", width=160, minwidth=110)
        self.tabla.column("genero", width=120, minwidth=90)
        self.tabla.column("log", width=330, minwidth=150)
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
        }

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
                        cancion.get("log", "") or "—",
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
        self.estado.set("Canción seleccionada: edita sus datos y tocaq en guardar.")

    def limpiar_formulario(self):
        self.cancion_seleccionada = None
        self.tabla.selection_remove(self.tabla.selection())
        self.entrada_nombre.delete(0, "end")
        self.entrada_artista.delete(0, "end")
        self.genero.set(GENEROS[0])
        self.entrada_log.delete("1.0", "end")
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

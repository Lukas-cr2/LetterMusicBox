import os
import tkinter as tk


def crear_ventana():
    if not os.environ.get("DISPLAY"):
        raise RuntimeError(
            "No hay una sesión gráfica disponible. "
            "Ejecuta esta app en un entorno con escritorio o con X11 habilitado."
        )

    ventana = tk.Tk()
    ventana.title("LetterMusicBox")
    ventana.geometry("700x600")

    tk.Label(ventana, text= "holaaaa como anda profe").pack(pady=20)
    tk.Button(ventana, text="boton de prueba osiosi").pack(pady=20)
    ventana.mainloop()


if __name__ == "__main__":
    crear_ventana()
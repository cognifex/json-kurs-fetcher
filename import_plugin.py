"""Simple UI plugin to choose between importing from a link or an uploaded file."""

from __future__ import annotations

import tkinter as tk
from tkinter import filedialog, messagebox
from pathlib import Path


class ImportPluginUI:
    def __init__(self, master: tk.Tk) -> None:
        self.master = master
        self.master.title("Kurs-Import")
        self.master.geometry("480x320")

        self.source_var = tk.StringVar(value="url")
        self.file_path: Path | None = None

        heading = tk.Label(
            master,
            text="Quelle für den Import wählen",
            font=("Helvetica", 14, "bold"),
            pady=10,
        )
        heading.pack()

        self._build_link_section(master)
        self._build_file_section(master)
        self._build_selection_section(master)

        self.status_var = tk.StringVar()
        self.status_label = tk.Label(
            master,
            textvariable=self.status_var,
            fg="#555",
            wraplength=440,
            justify=tk.LEFT,
            pady=10,
        )
        self.status_label.pack()

        import_button = tk.Button(
            master,
            text="Import starten",
            command=self.perform_import,
            width=20,
            pady=5,
        )
        import_button.pack(pady=5)

        self.update_status()

    def _build_link_section(self, master: tk.Misc) -> None:
        frame = tk.Frame(master, padx=20, pady=5)
        frame.pack(fill=tk.X)

        tk.Radiobutton(
            frame,
            text="Link verwenden",
            variable=self.source_var,
            value="url",
            command=self.update_status,
        ).grid(row=0, column=0, sticky="w")

        self.url_entry = tk.Entry(frame, width=45)
        self.url_entry.grid(row=1, column=0, columnspan=2, sticky="we", pady=(4, 0))
        frame.columnconfigure(0, weight=1)

        hint = tk.Label(
            frame,
            text="Bitte einen vollständigen HTTPS-Link eingeben.",
            fg="#666",
        )
        hint.grid(row=2, column=0, columnspan=2, sticky="w", pady=(2, 0))

    def _build_file_section(self, master: tk.Misc) -> None:
        frame = tk.Frame(master, padx=20, pady=5)
        frame.pack(fill=tk.X)

        tk.Radiobutton(
            frame,
            text="Datei verwenden",
            variable=self.source_var,
            value="file",
            command=self.update_status,
        ).grid(row=0, column=0, sticky="w")

        choose_button = tk.Button(frame, text="Datei auswählen", command=self.choose_file)
        choose_button.grid(row=1, column=0, sticky="w", pady=(4, 0))

        self.file_label = tk.Label(frame, text="Keine Datei ausgewählt", fg="#666")
        self.file_label.grid(row=1, column=1, sticky="w", padx=(10, 0))

    def _build_selection_section(self, master: tk.Misc) -> None:
        info = tk.Label(
            master,
            text="Hinweis: Wählen Sie explizit aus, ob der Link oder die hochgeladene Datei"
            " importiert werden soll. Die aktuelle Auswahl wird unten angezeigt.",
            wraplength=440,
            justify=tk.LEFT,
            padx=20,
        )
        info.pack(fill=tk.X, pady=(10, 0))

    def choose_file(self) -> None:
        path = filedialog.askopenfilename(
            title="Datei für Import auswählen",
            filetypes=[("JSON-Dateien", "*.json"), ("Alle Dateien", "*.*")],
        )
        if path:
            self.file_path = Path(path)
            display = self.file_path.name
            if len(display) > 40:
                display = display[:37] + "..."
            self.file_label.config(text=display, fg="#000")
        else:
            self.file_path = None
            self.file_label.config(text="Keine Datei ausgewählt", fg="#666")
        self.update_status()

    def update_status(self) -> None:
        selected = self.source_var.get()
        if selected == "url":
            url = self.url_entry.get().strip()
            if url:
                self.status_var.set(f"Aktuelle Quelle: Link ({url})")
            else:
                self.status_var.set("Aktuelle Quelle: Link (noch kein Link eingegeben)")
        else:
            if self.file_path:
                self.status_var.set(f"Aktuelle Quelle: Datei ({self.file_path.name})")
            else:
                self.status_var.set("Aktuelle Quelle: Datei (noch keine Datei ausgewählt)")

    def perform_import(self) -> None:
        selected = self.source_var.get()
        if selected == "url":
            url = self.url_entry.get().strip()
            if not url:
                messagebox.showwarning(
                    "Link fehlt",
                    "Bitte geben Sie einen Link ein oder wählen Sie stattdessen eine Datei aus.",
                )
                return
            messagebox.showinfo("Import", f"Der Import wird mit dem Link gestartet:\n{url}")
        else:
            if not self.file_path:
                messagebox.showwarning(
                    "Datei fehlt",
                    "Bitte wählen Sie eine Datei aus oder wechseln Sie zum Link-Import.",
                )
                return
            messagebox.showinfo(
                "Import",
                f"Der Import wird mit der Datei gestartet:\n{self.file_path}",
            )


def main() -> None:
    root = tk.Tk()
    app = ImportPluginUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()

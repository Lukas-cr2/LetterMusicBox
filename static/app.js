const form = document.querySelector("#song-form");
const songList = document.querySelector("#song-list");
const statusMessage = document.querySelector("#status");
const songCount = document.querySelector("#song-count");
const searchInput = document.querySelector("#search");
const genreFilter = document.querySelector("#genre-filter");
const ratingInput = document.querySelector("#rating");
const ratingValue = document.querySelector("#rating-value");
const imageInput = document.querySelector("#image");
const imagePreview = document.querySelector("#image-preview");
const removeImageWrap = document.querySelector("#remove-image-wrap");
const removeImage = document.querySelector("#remove-image");
const saveButton = document.querySelector("#save-button");
const cancelEdit = document.querySelector("#cancel-edit");
const formTitle = document.querySelector("#form-title");
let editingId = null;
let editingImage = null;
let previewUrl = null;
let searchTimer = null;

function showStatus(message, isError = false) {
  statusMessage.textContent = message;
  statusMessage.classList.toggle("error", isError);
}

async function api(url, options = {}) {
  const response = await fetch(url, options);
  const result = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(result.error || `Error del servidor (${response.status}).`);
  }
  return result;
}

function formatStars(value) {
  const rating = Math.max(0, Math.min(Number(value) || 0, 5));
  const whole = Math.floor(rating);
  const half = rating - whole >= 0.5 ? "⯨" : "";
  return "★".repeat(whole) + half + "☆".repeat(5 - whole - (half ? 1 : 0));
}

function makeElement(tag, className, text) {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (text !== undefined) element.textContent = text;
  return element;
}

function renderSongs(songs) {
  songList.replaceChildren();
  songCount.textContent = `${songs.length} canción${songs.length === 1 ? "" : "es"}`;
  if (!songs.length) {
    songList.append(makeElement("p", "empty-state", "Todavía no hay canciones con esos filtros."));
    return;
  }

  for (const song of songs) {
    const card = makeElement("article", "song-card");
    if (song.imagen) {
      const cover = makeElement("img", "cover");
      cover.src = `/uploads/${encodeURIComponent(song.imagen)}`;
      cover.alt = `Portada de ${song.nombre}`;
      cover.loading = "lazy";
      cover.addEventListener("error", () => {
        const placeholder = makeElement("div", "cover-placeholder", song.nombre.slice(0, 1).toUpperCase());
        cover.replaceWith(placeholder);
      }, { once: true });
      card.append(cover);
    } else {
      card.append(makeElement("div", "cover-placeholder", song.nombre.slice(0, 1).toUpperCase()));
    }

    const info = makeElement("div", "song-info");
    info.append(makeElement("h3", "", song.nombre));
    info.append(makeElement("p", "song-artist", song.artista));
    info.append(makeElement("p", "song-genre", song.genero));
    info.append(makeElement("p", "song-stars", formatStars(song.calificacion)));
    card.append(info);
    if (song.log) card.append(makeElement("p", "song-log", song.log));

    const actions = makeElement("div", "card-actions");
    const editButton = makeElement("button", "", "Editar");
    editButton.type = "button";
    editButton.addEventListener("click", () => startEdit(song));
    const deleteButton = makeElement("button", "delete-button", "Eliminar");
    deleteButton.type = "button";
    deleteButton.addEventListener("click", () => deleteSong(song));
    actions.append(editButton, deleteButton);
    card.append(actions);
    songList.append(card);
  }
}

async function loadSongs() {
  showStatus("");
  songCount.textContent = "Cargando…";
  const params = new URLSearchParams();
  if (searchInput.value.trim()) params.set("q", searchInput.value.trim());
  if (genreFilter.value) params.set("genre", genreFilter.value);
  try {
    const result = await api(`/api/songs?${params}`);
    renderSongs(result.songs);
  } catch (error) {
    songCount.textContent = "";
    songList.replaceChildren();
    showStatus(error.message, true);
  }
}

function resetForm() {
  editingId = null;
  editingImage = null;
  form.reset();
  ratingValue.value = "0.0 / 5";
  imagePreview.classList.add("hidden");
  imagePreview.removeAttribute("src");
  removeImage.checked = false;
  removeImageWrap.classList.add("hidden");
  cancelEdit.classList.add("hidden");
  saveButton.textContent = "Agregar canción";
  formTitle.textContent = "Agregar canción";
  if (previewUrl) {
    URL.revokeObjectURL(previewUrl);
    previewUrl = null;
  }
  showStatus("");
}

function startEdit(song) {
  editingId = song.id;
  editingImage = song.imagen;
  form.elements.nombre.value = song.nombre;
  form.elements.artista.value = song.artista;
  form.elements.genero.value = song.genero;
  form.elements.log.value = song.log;
  ratingInput.value = String(song.calificacion || 0);
  ratingValue.value = `${Number(song.calificacion || 0).toFixed(1)} / 5`;
  imageInput.value = "";
  removeImage.checked = false;
  removeImageWrap.classList.toggle("hidden", !song.imagen);
  if (song.imagen) {
    imagePreview.src = `/uploads/${encodeURIComponent(song.imagen)}`;
    imagePreview.classList.remove("hidden");
  } else {
    imagePreview.classList.add("hidden");
  }
  cancelEdit.classList.remove("hidden");
  saveButton.textContent = "Guardar cambios";
  formTitle.textContent = "Editar canción";
  form.scrollIntoView({ behavior: "smooth", block: "start" });
}

async function deleteSong(song) {
  if (!window.confirm(`¿Eliminar "${song.nombre}" de la biblioteca?`)) return;
  try {
    await api(`/api/songs/${encodeURIComponent(song.id)}`, { method: "DELETE" });
    if (editingId === song.id) resetForm();
    showStatus("Se eliminó la canción.");
    await loadSongs();
  } catch (error) {
    showStatus(error.message, true);
  }
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const data = new FormData(form);
  data.set("calificacion", ratingInput.value);
  data.set("remove_image", String(removeImage.checked));
  saveButton.disabled = true;
  showStatus(editingId ? "Guardando cambios…" : "Agregando canción…");
  try {
    await api(editingId ? `/api/songs/${encodeURIComponent(editingId)}` : "/api/songs", {
      method: editingId ? "PUT" : "POST",
      body: data,
    });
    resetForm();
    showStatus("Canción guardada.");
    await loadSongs();
  } catch (error) {
    showStatus(error.message, true);
  } finally {
    saveButton.disabled = false;
  }
});

ratingInput.addEventListener("input", () => {
  ratingValue.value = `${Number(ratingInput.value).toFixed(1)} / 5`;
});

imageInput.addEventListener("change", () => {
  if (previewUrl) URL.revokeObjectURL(previewUrl);
  const file = imageInput.files[0];
  if (!file) return;
  previewUrl = URL.createObjectURL(file);
  imagePreview.src = previewUrl;
  imagePreview.classList.remove("hidden");
  removeImage.checked = false;
});

removeImage.addEventListener("change", () => {
  if (removeImage.checked) {
    imageInput.value = "";
    imagePreview.classList.add("hidden");
  } else if (editingImage) {
    imagePreview.src = `/uploads/${encodeURIComponent(editingImage)}`;
    imagePreview.classList.remove("hidden");
  }
});

document.querySelector("#clear-button").addEventListener("click", resetForm);
cancelEdit.addEventListener("click", resetForm);
searchInput.addEventListener("input", () => {
  window.clearTimeout(searchTimer);
  searchTimer = window.setTimeout(loadSongs, 180);
});
genreFilter.addEventListener("change", loadSongs);

loadSongs();

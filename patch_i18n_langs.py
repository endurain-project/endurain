import json
import os

base_dir = r"C:\Users\Julien\Documents\GitHub\endurain-course\endurain\frontend\app\src\i18n"
langs = ['ca', 'cn', 'de', 'es', 'gl', 'it', 'nl', 'pt', 'sl', 'sv', 'tw']

navbar_additions = {
    'ca': {'routes': 'Rutes', 'routesList': 'Mostrar rutes', 'routeCreate': 'Crear una ruta'},
    'cn': {'routes': '路线', 'routesList': '显示路线', 'routeCreate': '创建路线'},
    'de': {'routes': 'Routen', 'routesList': 'Routen anzeigen', 'routeCreate': 'Route erstellen'},
    'es': {'routes': 'Rutas', 'routesList': 'Mostrar rutas', 'routeCreate': 'Crear ruta'},
    'gl': {'routes': 'Rutas', 'routesList': 'Amosar rutas', 'routeCreate': 'Crear ruta'},
    'it': {'routes': 'Percorsi', 'routesList': 'Mostra percorsi', 'routeCreate': 'Crea un percorso'},
    'nl': {'routes': 'Routes', 'routesList': 'Toon routes', 'routeCreate': 'Maak een route'},
    'pt': {'routes': 'Rotas', 'routesList': 'Mostrar rotas', 'routeCreate': 'Criar uma rota'},
    'sl': {'routes': 'Poti', 'routesList': 'Pokaži poti', 'routeCreate': 'Ustvari pot'},
    'sv': {'routes': 'Rutter', 'routesList': 'Visa rutter', 'routeCreate': 'Skapa en rutt'},
    'tw': {'routes': '路線', 'routesList': '顯示路線', 'routeCreate': '建立路線'}
}

# English fallback
with open(os.path.join(base_dir, "us", "routesView.json"), "r", encoding="utf-8") as f:
    us_routes = json.load(f)

translations = {
    'ca': {
        "type_running": "Cursa", "btn_save": "Desar", "search_placeholder": "Cerca una ciutat...", "title_edit": "Editar Ruta",
        "btn_undo": "Desfer", "btn_redo": "Refer", "title_create": "Crear Ruta", "success_create": "Ruta desada!",
        "success_update": "Ruta actualitzada!", "form_name": "Nom de la ruta", "form_desc": "Descripció"
    },
    'es': {
        "type_running": "Correr", "btn_save": "Guardar", "search_placeholder": "Buscar una ciudad, dirección...",
        "title_edit": "Editar Ruta", "title_create": "Crear Ruta", "form_name": "Nombre de la ruta",
        "form_desc": "Descripción", "success_create": "Ruta guardada exitosamente!", "success_update": "Ruta actualizada!",
        "btn_export_gpx": "Exportar GPX", "btn_undo": "Deshacer", "btn_redo": "Rehacer"
    },
    'de': {
        "type_running": "Laufen", "btn_save": "Speichern", "search_placeholder": "Stadt oder Adresse suchen...",
        "title_edit": "Route bearbeiten", "title_create": "Route erstellen", "form_name": "Routenname",
        "form_desc": "Beschreibung", "success_create": "Route erfolgreich gespeichert!", "success_update": "Route aktualisiert!",
        "btn_export_gpx": "GPX Exportieren", "btn_undo": "Rückgängig", "btn_redo": "Wiederholen"
    },
    'it': {
        "type_running": "Corsa", "btn_save": "Salva", "search_placeholder": "Cerca una città, un indirizzo...",
        "title_edit": "Modifica Percorso", "title_create": "Crea Percorso", "form_name": "Nome percorso",
        "form_desc": "Descrizione", "success_create": "Percorso salvato con successo!", "success_update": "Percorso aggiornato!",
        "btn_export_gpx": "Esporta GPX", "btn_undo": "Annulla", "btn_redo": "Ripeti"
    },
    'pt': {
        "type_running": "Corrida", "btn_save": "Salvar", "search_placeholder": "Buscar uma cidade, endereço...",
        "title_edit": "Editar Rota", "title_create": "Criar Rota", "form_name": "Nome da rota",
        "form_desc": "Descrição", "success_create": "Rota salva com sucesso!", "success_update": "Rota atualizada!",
        "btn_export_gpx": "Exportar GPX", "btn_undo": "Desfazer", "btn_redo": "Refazer"
    }
}

for lang in langs:
    # 1. Update navbarComponent.json
    nav_file = os.path.join(base_dir, lang, "components", "navbar", "navbarComponent.json")
    if os.path.exists(nav_file):
        with open(nav_file, "r", encoding="utf-8") as f:
            nav_data = json.load(f)
        nav_data.update(navbar_additions[lang])
        with open(nav_file, "w", encoding="utf-8") as f:
            json.dump(nav_data, f, ensure_ascii=False, indent=2)
            
    # 2. Create routesView.json with English as base, override with any available translations
    combined_routes = dict(us_routes)
    if lang in translations:
        combined_routes.update(translations[lang])
        
    routes_file = os.path.join(base_dir, lang, "routesView.json")
    with open(routes_file, "w", encoding="utf-8") as f:
        json.dump(combined_routes, f, ensure_ascii=False, indent=4)

print("Translations generated successfully.")

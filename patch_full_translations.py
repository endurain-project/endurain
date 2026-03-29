import json
import os

base_dir = r"C:\Users\Julien\Documents\GitHub\endurain-course\endurain\frontend\app\src\i18n"
langs = ['ca', 'cn', 'de', 'es', 'gl', 'it', 'nl', 'pt', 'sl', 'sv', 'tw']

translations = {
    'ca': {
        "type_running": "Cursa", "btn_save": "Desar", "search_placeholder": "Cerca una ciutat, una adreça...", 
        "subtype_trail_running": "Cursa de muntanya", "search_button_aria": "Inicia la cerca d'adreça", 
        "subtype_road_running": "Cursa d'asfalt", "title_edit": "Editar Ruta", "form_cancel": "Cancel·lar", 
        "subtype_nordic_walking": "Marxa nòrdica", "form_subtype": "Subtipus", "subtype_gravel": "Gravel", 
        "error_load": "No s'ha pogut carregar la ruta per editar", "btn_undo": "Desfer", 
        "mode_hybrid": "Mode híbrid (carreteretes i senders)", "subtype_mountain_bike": "Bicicleta de muntanya", 
        "subtype_bikepacking": "Bikepacking", "form_submit_create": "Desar", "search_input_aria": "Cerca una ciutat o adreça", 
        "form_type": "Tipus", "subtype_trekking": "Trekking", "title_create": "Crear Ruta", "mode_road": "Només carreteres", 
        "subtype_day_hike": "Excursió d'un dia", "subtype_fast_hiking": "Fast hiking", 
        "error_elevation_429": "Servei d'elevació saturat (429). Reintentant en uns segons.", "type_hiking": "Senderisme", 
        "btn_save_edit": "Desar modificacions", "subtype_long_run": "Tirada llarga", "btn_redo": "Refer", 
        "success_update": "Ruta actualitzada correctament!", "subtype_interval": "Sèries", 
        "success_create": "Ruta desada correctament!", "error_save": "Error al desar la ruta", "form_submit_edit": "Actualitzar", 
        "form_desc": "Descripció", "error_update": "Error en actualitzar la ruta", "btn_loop": "Tornar a l'inici", 
        "type_cycling": "Ciclisme", "error_not_found": "Ubicació no trobada", "subtype_trail": "Camí", "type_other": "Altres", 
        "form_name": "Nom de la ruta", "mode_path": "Només camins", "search_loading": "Cercant...", 
        "mode_auto": "Encaminament automàtic (OSM)", "marker_delete": "Eliminar", "subtype_road": "Carretera", 
        "btn_export_gpx": "Exportar GPX", "ele_gain": "Desnivell Positiu", "ele_loss": "Desnivell Negatiu", 
        "no_desc": "Sense descripció", "waypoints": "Punts", "city": "Ciutat", "cols_coords": "Coordenades", 
        "cols_distance": "Distància", "cols_ele": "Elevació", "start": "Inici", "finish": "Final", "step": "Pas", 
        "no_routes": "No s'han trobat rutes", "start_creating": "Comença creant la teva primera ruta!", 
        "success_delete": "Ruta eliminada!", "search_result": "Resultat"
    },
    'es': {
        "type_running": "Carrera", "btn_save": "Guardar", "search_placeholder": "Busca una ciudad, dirección...",
        "subtype_trail_running": "Trail running", "search_button_aria": "Iniciar búsqueda",
        "subtype_road_running": "Carrera en asfalto", "title_edit": "Editar Ruta", "form_cancel": "Cancelar",
        "subtype_nordic_walking": "Marcha nórdica", "form_subtype": "Subtipo", "subtype_gravel": "Gravel",
        "error_load": "Error al cargar la ruta", "btn_undo": "Deshacer", "mode_hybrid": "Modo híbrido",
        "subtype_mountain_bike": "Bicicleta de montaña", "subtype_bikepacking": "Bikepacking", "form_submit_create": "Guardar",
        "search_input_aria": "Buscar una ciudad", "form_type": "Tipo", "subtype_trekking": "Trekking",
        "title_create": "Crear Ruta", "mode_road": "Solo carreteras", "subtype_day_hike": "Excursión",
        "subtype_fast_hiking": "Fast hiking", "error_elevation_429": "Servicio de elevación saturado. Reintentando...",
        "type_hiking": "Senderismo", "btn_save_edit": "Guardar cambios", "subtype_long_run": "Tirada larga",
        "btn_redo": "Rehacer", "success_update": "¡Ruta actualizada!", "subtype_interval": "Series",
        "success_create": "¡Ruta guardada!", "error_save": "Error al guardar", "form_submit_edit": "Actualizar",
        "form_desc": "Descripción", "error_update": "Error al actualizar", "btn_loop": "Volver al inicio",
        "type_cycling": "Ciclismo", "error_not_found": "Ubicación no encontrada", "subtype_trail": "Sendero",
        "type_other": "Otros", "form_name": "Nombre", "mode_path": "Solo caminos", "search_loading": "Buscando...",
        "mode_auto": "Enrutamiento automático", "marker_delete": "Eliminar punto", "subtype_road": "Carretera",
        "btn_export_gpx": "Exportar GPX", "ele_gain": "Desnivel Positivo", "ele_loss": "Desnivel Negativo",
        "no_desc": "Sin descripción", "waypoints": "Puntos", "city": "Ciudad", "cols_coords": "Coordenadas",
        "cols_distance": "Distancia", "cols_ele": "Elevación", "start": "Inicio", "finish": "Fin", "step": "Paso",
        "no_routes": "No hay rutas", "start_creating": "¡Crea tu primera ruta!", "success_delete": "Ruta eliminada",
        "search_result": "Resultado"
    },
    'de': {
        "type_running": "Laufen", "btn_save": "Speichern", "search_placeholder": "Suche nach einer Stadt...",
        "subtype_trail_running": "Trailrunning", "search_button_aria": "Suche starten", "subtype_road_running": "Straßenlauf",
        "title_edit": "Route bearbeiten", "form_cancel": "Abbrechen", "subtype_nordic_walking": "Nordic Walking",
        "form_subtype": "Untertyp", "subtype_gravel": "Gravel", "error_load": "Fehler beim Laden",
        "btn_undo": "Rückgängig", "mode_hybrid": "Hybridmodus", "subtype_mountain_bike": "Mountainbike",
        "subtype_bikepacking": "Bikepacking", "form_submit_create": "Speichern", "search_input_aria": "Stadt suchen",
        "form_type": "Typ", "subtype_trekking": "Trekking", "title_create": "Route erstellen", "mode_road": "Nur Straßen",
        "subtype_day_hike": "Tageswanderung", "subtype_fast_hiking": "Fast Hiking", "error_elevation_429": "Höhendienst überlastet. Neuversuch...",
        "type_hiking": "Wandern", "btn_save_edit": "Änderungen speichern", "subtype_long_run": "Langer Lauf",
        "btn_redo": "Wiederholen", "success_update": "Route aktualisiert!", "subtype_interval": "Intervall",
        "success_create": "Route gespeichert!", "error_save": "Fehler beim Speichern", "form_submit_edit": "Aktualisieren",
        "form_desc": "Beschreibung", "error_update": "Fehler beim Aktualisieren", "btn_loop": "Zurück zum Start",
        "type_cycling": "Radfahren", "error_not_found": "Nicht gefunden", "subtype_trail": "Trail",
        "type_other": "Sonstiges", "form_name": "Routenname", "mode_path": "Nur Wege", "search_loading": "Suchen...",
        "mode_auto": "Auto. Routing", "marker_delete": "Löschen", "subtype_road": "Straße",
        "btn_export_gpx": "GPX exportieren", "ele_gain": "Höhenmeter", "ele_loss": "Tiefenmeter",
        "no_desc": "Keine Beschreibung", "waypoints": "Wegpunkte", "city": "Stadt", "cols_coords": "Koordinaten",
        "cols_distance": "Distanz", "cols_ele": "Höhe", "start": "Start", "finish": "Ziel", "step": "Schritt",
        "no_routes": "Keine Routen", "start_creating": "Erstelle eine Route!", "success_delete": "Gelöscht",
        "search_result": "Ergebnis"
    },
    'it': {
        "type_running": "Corsa", "btn_save": "Salva", "search_placeholder": "Cerca una città...",
        "subtype_trail_running": "Trail running", "search_button_aria": "Avvia ricerca", "subtype_road_running": "Corsa su strada",
        "title_edit": "Modifica Percorso", "form_cancel": "Annulla", "subtype_nordic_walking": "Nordic walking",
        "form_subtype": "Sottotipo", "subtype_gravel": "Gravel", "error_load": "Errore di caricamento",
        "btn_undo": "Annulla", "mode_hybrid": "Modalità ibrida", "subtype_mountain_bike": "Mountain bike",
        "subtype_bikepacking": "Bikepacking", "form_submit_create": "Salva", "search_input_aria": "Cerca città",
        "form_type": "Tipo", "subtype_trekking": "Trekking", "title_create": "Crea Percorso", "mode_road": "Solo strade",
        "subtype_day_hike": "Escursione", "subtype_fast_hiking": "Fast hiking", "error_elevation_429": "Servizio elevazione saturo.",
        "type_hiking": "Escursionismo", "btn_save_edit": "Salva modifiche", "subtype_long_run": "Corsa lunga",
        "btn_redo": "Ripeti", "success_update": "Percorso aggiornato!", "subtype_interval": "Ripetute",
        "success_create": "Percorso salvato!", "error_save": "Errore", "form_submit_edit": "Aggiorna",
        "form_desc": "Descrizione", "error_update": "Errore", "btn_loop": "Torna alla partenza",
        "type_cycling": "Ciclismo", "error_not_found": "Non trovato", "subtype_trail": "Sentiero",
        "type_other": "Altro", "form_name": "Nome", "mode_path": "Solo sentieri", "search_loading": "Ricerca...",
        "mode_auto": "Percorso automatico", "marker_delete": "Elimina", "subtype_road": "Strada",
        "btn_export_gpx": "Esporta GPX", "ele_gain": "Dislivello Positivo", "ele_loss": "Dislivello Negativo",
        "no_desc": "Nessuna descrizione", "waypoints": "Punti", "city": "Città", "cols_coords": "Coordinate",
        "cols_distance": "Distanza", "cols_ele": "Elevazione", "start": "Inizio", "finish": "Fine", "step": "Passo",
        "no_routes": "Nessun percorso", "start_creating": "Crea il tuo percorso!", "success_delete": "Eliminato!",
        "search_result": "Risultato"
    },
    'pt': {
        "type_running": "Corrida", "btn_save": "Salvar", "search_placeholder": "Buscar uma cidade...",
        "subtype_trail_running": "Corrida em trilha", "search_button_aria": "Iniciar busca", "subtype_road_running": "Corrida de rua",
        "title_edit": "Editar Rota", "form_cancel": "Cancelar", "subtype_nordic_walking": "Caminhada nórdica",
        "form_subtype": "Subtipo", "subtype_gravel": "Gravel", "error_load": "Erro ao carregar",
        "btn_undo": "Desfazer", "mode_hybrid": "Modo híbrido", "subtype_mountain_bike": "Mountain bike",
        "subtype_bikepacking": "Bikepacking", "form_submit_create": "Salvar", "search_input_aria": "Buscar cidade",
        "form_type": "Tipo", "subtype_trekking": "Trekking", "title_create": "Criar Rota", "mode_road": "Apenas ruas",
        "subtype_day_hike": "Trilha diária", "subtype_fast_hiking": "Fast hiking", "error_elevation_429": "Serviço de elevação indisponível. Tentando...",
        "type_hiking": "Caminhada", "btn_save_edit": "Salvar", "subtype_long_run": "Treino longo",
        "btn_redo": "Refazer", "success_update": "Rota atualizada!", "subtype_interval": "Intervalado",
        "success_create": "Rota salva!", "error_save": "Erro ao salvar", "form_submit_edit": "Atualizar",
        "form_desc": "Descrição", "error_update": "Erro", "btn_loop": "Voltar ao início",
        "type_cycling": "Ciclismo", "error_not_found": "Não encontrado", "subtype_trail": "Trilha",
        "type_other": "Outros", "form_name": "Nome", "mode_path": "Apenas trilhas", "search_loading": "Buscando...",
        "mode_auto": "Rotas automáticas", "marker_delete": "Deletar", "subtype_road": "Estrada",
        "btn_export_gpx": "Exportar GPX", "ele_gain": "Elevação Positiva", "ele_loss": "Elevação Negativa",
        "no_desc": "Sem descrição", "waypoints": "Pontos", "city": "Cidade", "cols_coords": "Coordenadas",
        "cols_distance": "Distância", "cols_ele": "Elevação", "start": "Início", "finish": "Fim", "step": "Passo",
        "no_routes": "Nenhuma rota", "start_creating": "Crie sua primeira rota!", "success_delete": "Deletado!",
        "search_result": "Resultado"
    },
    'nl': {
        "type_running": "Hardlopen", "btn_save": "Opslaan", "search_placeholder": "Zoek een stad...",
        "subtype_trail_running": "Trailrunning", "search_button_aria": "Zoeken starten", "subtype_road_running": "Weg hardlopen",
        "title_edit": "Route bewerken", "form_cancel": "Annuleren", "subtype_nordic_walking": "Nordic walking",
        "form_subtype": "Subtype", "subtype_gravel": "Gravel", "error_load": "Fout bij laden",
        "btn_undo": "Ongedaan maken", "mode_hybrid": "Hybride modus", "subtype_mountain_bike": "Mountainbike",
        "subtype_bikepacking": "Bikepacking", "form_submit_create": "Opslaan", "search_input_aria": "Zoek adres",
        "form_type": "Type", "subtype_trekking": "Trekking", "title_create": "Route maken", "mode_road": "Verharde wegen",
        "subtype_day_hike": "Dagwandeling", "subtype_fast_hiking": "Fast hiking", "error_elevation_429": "Hoogteservice overbelast.",
        "type_hiking": "Wandelen", "btn_save_edit": "Opslaan", "subtype_long_run": "Duurloop",
        "btn_redo": "Opnieuw", "success_update": "Route bijgewerkt!", "subtype_interval": "Interval",
        "success_create": "Route opgeslagen!", "error_save": "Fout", "form_submit_edit": "Bijwerken",
        "form_desc": "Beschrijving", "error_update": "Fout", "btn_loop": "Terug naar start",
        "type_cycling": "Fietsen", "error_not_found": "Niet gevonden", "subtype_trail": "Pad",
        "type_other": "Anders", "form_name": "Naam", "mode_path": "Alleen onverhard", "search_loading": "Zoeken...",
        "mode_auto": "Auto route", "marker_delete": "Verwijder", "subtype_road": "Weg",
        "btn_export_gpx": "GPX Exporteren", "ele_gain": "Hoogtemeters", "ele_loss": "Dalingsmeters",
        "no_desc": "Geen beschrijving", "waypoints": "Waypoints", "city": "Stad", "cols_coords": "Coördinaten",
        "cols_distance": "Afstand", "cols_ele": "Hoogte", "start": "Start", "finish": "Einde", "step": "Stap",
        "no_routes": "Geen routes gevonden", "start_creating": "Begin met je eerste route!", "success_delete": "Route verwijderd!",
        "search_result": "Resultaat"
    },
    'cn': {
        "type_running": "跑步", "btn_save": "保存", "search_placeholder": "搜索城市、地址...", "subtype_trail_running": "越野跑", "search_button_aria": "启动地址搜索", "subtype_road_running": "公路跑", "title_edit": "编辑路线", "form_cancel": "取消", "subtype_nordic_walking": "越野行走", "form_subtype": "子类型", "subtype_gravel": "砾石", "error_load": "加载路线失败", "btn_undo": "撤销", "mode_hybrid": "混合模式", "subtype_mountain_bike": "山地自行车", "subtype_bikepacking": "自行车旅行", "form_submit_create": "保存", "search_input_aria": "搜索城市", "form_type": "类型", "subtype_trekking": "徒步", "title_create": "创建路线", "mode_road": "仅铺装路面", "subtype_day_hike": "单日徒步", "subtype_fast_hiking": "快速徒步", "error_elevation_429": "海拔服务已饱和，重试中...", "type_hiking": "徒步", "btn_save_edit": "保存修改", "subtype_long_run": "长跑", "btn_redo": "重做", "success_update": "路线已更新！", "subtype_interval": "间歇跑", "success_create": "路线已保存！", "error_save": "保存出错", "form_submit_edit": "更新", "form_desc": "描述", "error_update": "更新出错", "btn_loop": "返回起点", "type_cycling": "骑行", "error_not_found": "未找到位置", "subtype_trail": "步道", "type_other": "其他", "form_name": "名称", "mode_path": "仅小路", "search_loading": "搜索中...", "mode_auto": "自动规划", "marker_delete": "删除", "subtype_road": "公路", "btn_export_gpx": "导出 GPX", "ele_gain": "累计爬升", "ele_loss": "累计下降", "no_desc": "无描述。", "waypoints": "途径点", "city": "城市", "cols_coords": "坐标", "cols_distance": "距离", "cols_ele": "海拔", "start": "起点", "finish": "终点", "step": "步骤", "no_routes": "未找到路线", "start_creating": "创建第一条路线！", "success_delete": "已删除！", "search_result": "结果"
    },
    'tw': {
        "type_running": "跑步", "btn_save": "儲存", "search_placeholder": "搜尋城市、地址...", "subtype_trail_running": "越野跑", "search_button_aria": "啟動地址搜尋", "subtype_road_running": "公路跑", "title_edit": "編輯路線", "form_cancel": "取消", "subtype_nordic_walking": "越野行走", "form_subtype": "子類型", "subtype_gravel": "礫石", "error_load": "載入路線失敗", "btn_undo": "復原", "mode_hybrid": "混合模式", "subtype_mountain_bike": "登山車", "subtype_bikepacking": "單車旅行", "form_submit_create": "儲存", "search_input_aria": "搜尋城市", "form_type": "類型", "subtype_trekking": "徒步", "title_create": "建立路線", "mode_road": "僅鋪裝路面", "subtype_day_hike": "單日徒步", "subtype_fast_hiking": "快速徒步", "error_elevation_429": "海拔服務已飽和，重試中...", "type_hiking": "徒步", "btn_save_edit": "儲存修改", "subtype_long_run": "長跑", "btn_redo": "重做", "success_update": "路線已更新！", "subtype_interval": "間歇跑", "success_create": "路線已儲存！", "error_save": "儲存出錯", "form_submit_edit": "更新", "form_desc": "描述", "error_update": "更新出錯", "btn_loop": "返回起點", "type_cycling": "騎行", "error_not_found": "未找到位置", "subtype_trail": "步道", "type_other": "其他", "form_name": "名稱", "mode_path": "僅小路", "search_loading": "搜尋中...", "mode_auto": "自動規劃", "marker_delete": "刪除", "subtype_road": "公路", "btn_export_gpx": "匯出 GPX", "ele_gain": "累計爬升", "ele_loss": "累計下降", "no_desc": "無描述。", "waypoints": "途經點", "city": "城市", "cols_coords": "座標", "cols_distance": "距離", "cols_ele": "海拔", "start": "起點", "finish": "終點", "step": "步驟", "no_routes": "未找到路線", "start_creating": "建立第一條路線！", "success_delete": "已刪除！", "search_result": "結果"
    },
    'sv': {
        "type_running": "Löpning", "btn_save": "Spara", "search_placeholder": "Sök stad eller adress...", "subtype_trail_running": "Traillöpning", "search_button_aria": "Sök", "subtype_road_running": "Väglöpning", "title_edit": "Redigera Rutt", "form_cancel": "Avbryt", "subtype_nordic_walking": "Gång", "form_subtype": "Undertyp", "subtype_gravel": "Gravel", "error_load": "Kunde inte ladda rutt", "btn_undo": "Ångra", "mode_hybrid": "Hybridläge", "subtype_mountain_bike": "Mountainbike", "subtype_bikepacking": "Bikepacking", "form_submit_create": "Spara", "search_input_aria": "Sök", "form_type": "Typ", "subtype_trekking": "Trekking", "title_create": "Skapa Rutt", "mode_road": "Bara väg", "subtype_day_hike": "Dagsvandring", "subtype_fast_hiking": "Snabbvandring", "error_elevation_429": "Höjdtjänst nere, försöker igen...", "type_hiking": "Vandring", "btn_save_edit": "Spara ändringar", "subtype_long_run": "Långpass", "btn_redo": "Gör om", "success_update": "Rutt uppdaterad!", "subtype_interval": "Intervall", "success_create": "Rutt sparad!", "error_save": "Fel", "form_submit_edit": "Uppdatera", "form_desc": "Beskrivning", "error_update": "Fel", "btn_loop": "Tillbaka till start", "type_cycling": "Cykling", "error_not_found": "Hittades inte", "subtype_trail": "Stig", "type_other": "Annat", "form_name": "Namn", "mode_path": "Bara stigar", "search_loading": "Söker...", "mode_auto": "Automatisk rutt", "marker_delete": "Ta bort", "subtype_road": "Väg", "btn_export_gpx": "Exportera GPX", "ele_gain": "Stigning", "ele_loss": "Minskning", "no_desc": "Ingen beskrivning.", "waypoints": "Vägpunkter", "city": "Stad", "cols_coords": "Koordinater", "cols_distance": "Avstånd", "cols_ele": "Höjd", "start": "Start", "finish": "Mål", "step": "Steg", "no_routes": "Inga rutter", "start_creating": "Skapa din första rutt!", "success_delete": "Borttagen", "search_result": "Resultat"
    },
    'sl': {
        "type_running": "Tek", "btn_save": "Shrani", "search_placeholder": "Išči mesto, naslov...", "subtype_trail_running": "Gorski tek", "search_button_aria": "Išči", "subtype_road_running": "Cestni tek", "title_edit": "Uredi pot", "form_cancel": "Prekliči", "subtype_nordic_walking": "Nordijska hoja", "form_subtype": "Podvrsta", "subtype_gravel": "Gravel", "error_load": "Napaka", "btn_undo": "Razveljavi", "mode_hybrid": "Hibrid", "subtype_mountain_bike": "Gorsko kolesarjenje", "subtype_bikepacking": "Bikepacking", "form_submit_create": "Shrani", "search_input_aria": "Išči", "form_type": "Tip", "subtype_trekking": "Trekking", "title_create": "Ustvari Pot", "mode_road": "Cesta", "subtype_day_hike": "Dnevni pohod", "subtype_fast_hiking": "Hitri pohod", "error_elevation_429": "Napaka pri nadmorski višini...", "type_hiking": "Pohodništvo", "btn_save_edit": "Shrani spremembe", "subtype_long_run": "Dolgi tek", "btn_redo": "Uveljavi", "success_update": "Pot posodobljena!", "subtype_interval": "Intervali", "success_create": "Pot shranjena!", "error_save": "Napaka", "form_submit_edit": "Posodobi", "form_desc": "Opis", "error_update": "Napaka", "btn_loop": "Nazaj na start", "type_cycling": "Kolesarjenje", "error_not_found": "Ni najdeno", "subtype_trail": "Pot", "type_other": "Drugo", "form_name": "Ime", "mode_path": "Poti", "search_loading": "Iskanje...", "mode_auto": "Avto usmerjanje", "marker_delete": "Izbriši", "subtype_road": "Cesta", "btn_export_gpx": "Izvozi GPX", "ele_gain": "Vzpon", "ele_loss": "Spust", "no_desc": "Brez opisa.", "waypoints": "Točke", "city": "Mesto", "cols_coords": "Koordinate", "cols_distance": "Razdalja", "cols_ele": "Višina", "start": "Začetek", "finish": "Konec", "step": "Korak", "no_routes": "Ni poti", "start_creating": "Ustvari pot!", "success_delete": "Izbrisano!", "search_result": "Rezultat"
    },
    'gl': {
        "type_running": "Carreira", "btn_save": "Gardar", "search_placeholder": "Busca unha cidade, dirección...", "subtype_trail_running": "Carreira de montaña", "search_button_aria": "Buscar", "subtype_road_running": "Carreira en asfalto", "title_edit": "Editar Ruta", "form_cancel": "Cancelar", "subtype_nordic_walking": "Marcha nórdica", "form_subtype": "Subtipo", "subtype_gravel": "Gravel", "error_load": "Erro ao cargar a ruta", "btn_undo": "Desfacer", "mode_hybrid": "Modo híbrido", "subtype_mountain_bike": "Bicicleta de montaña", "subtype_bikepacking": "Bikepacking", "form_submit_create": "Gardar", "search_input_aria": "Buscar", "form_type": "Tipo", "subtype_trekking": "Trekking", "title_create": "Crear Ruta", "mode_road": "Só estradas", "subtype_day_hike": "Sendeirismo", "subtype_fast_hiking": "Fast hiking", "error_elevation_429": "Servizo da elevación cheo, reintentando...", "type_hiking": "Sendeirismo", "btn_save_edit": "Gardar cambios", "subtype_long_run": "Carreira longa", "btn_redo": "Refacer", "success_update": "Ruta actualizada!", "subtype_interval": "Series", "success_create": "Ruta gardada!", "error_save": "Erro ao gardar", "form_submit_edit": "Actualizar", "form_desc": "Descrición", "error_update": "Erro", "btn_loop": "Volver ao inicio", "type_cycling": "Ciclismo", "error_not_found": "Situación non atopada", "subtype_trail": "Camiño", "type_other": "Outros", "form_name": "Nome", "mode_path": "Só camiños", "search_loading": "Buscando...", "mode_auto": "Aparcamento automático", "marker_delete": "Eliminar punto", "subtype_road": "Estrada", "btn_export_gpx": "Exportar GPX", "ele_gain": "Desnivel Positivo", "ele_loss": "Desnivel Negativo", "no_desc": "Sen descrición.", "waypoints": "Puntos de paso", "city": "Cidade", "cols_coords": "Coordenadas", "cols_distance": "Distancia", "cols_ele": "Elevación", "start": "Inicio", "finish": "Fin", "step": "Paso", "no_routes": "Non se atoparon rutas", "start_creating": "Comeza a crear a túa ruta!", "success_delete": "Eliminada", "search_result": "Resultado"
    }
}

for lang in langs:
    routes_file = os.path.join(base_dir, lang, "routesView.json")
    # write specific translations 
    # Only if it strictly exists in our dict
    if lang in translations:
        with open(routes_file, "w", encoding="utf-8") as f:
            json.dump(translations[lang], f, ensure_ascii=False, indent=4)

print("Actual full translations generated logic ran!")

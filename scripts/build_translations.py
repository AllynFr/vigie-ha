# ruff: noqa: E501
"""Build strings.json and translations/*.json from one table (keeps keys in sync)."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "custom_components" / "vigie"
LANGS = ["en", "fr", "de", "es", "it", "zh-Hans"]

# key -> texts in LANGS order
T: dict[str, list[str]] = {
    # config flow
    "config.step.user.title": ["Connect to ioDek", "Connexion à ioDek", "Mit ioDek verbinden", "Conectar con ioDek", "Connessione a ioDek", "连接 ioDek"],
    "config.step.user.description": [
        "Create an API key in ioDek under Account → API keys. The read permission is required; add charge, comfort, access or signal to control the car.",
        "Créez une clé API dans ioDek, Compte → Clés API. Le droit lecture est obligatoire ; ajoutez charge, confort, accès ou signal pour piloter la voiture.",
        "Erstellen Sie in ioDek unter Konto → API-Schlüssel einen Schlüssel. Das Leserecht ist Pflicht; Laden, Komfort, Zugang oder Signal erlauben die Steuerung.",
        "Cree una clave API en ioDek, Cuenta → Claves API. El permiso de lectura es obligatorio; añada carga, confort, acceso o señal para controlar el coche.",
        "Crea una chiave API in ioDek, Account → Chiavi API. Il permesso di lettura è obbligatorio; aggiungi ricarica, comfort, accesso o segnale per comandare l'auto.",
        "在 ioDek 的“账户 → API 密钥”中创建密钥。必须包含读取权限；如需控制车辆，请添加充电、舒适、门禁或信号权限。",
    ],
    "config.step.user.data.url": ["ioDek address", "Adresse d'ioDek", "ioDek-Adresse", "Dirección de ioDek", "Indirizzo di ioDek", "ioDek 地址"],
    "config.step.user.data.api_key": ["API key", "Clé API", "API-Schlüssel", "Clave API", "Chiave API", "API 密钥"],
    "config.step.user.data_description.url": [
        "Leave the default unless you use another ioDek instance.",
        "Laissez la valeur par défaut, sauf pour une autre instance d'ioDek.",
        "Standardwert beibehalten, außer bei einer anderen ioDek-Instanz.",
        "Deje el valor por defecto salvo que use otra instancia de ioDek.",
        "Lascia il valore predefinito, salvo per un'altra istanza di ioDek.",
        "除非使用其他 ioDek 实例，否则保留默认值。",
    ],
    "config.step.user.data_description.api_key": ["Starts with vigie_ (shown once at creation).", "Commence par vigie_ (affichée une seule fois à la création).", "Beginnt mit vigie_ (nur einmal beim Erstellen angezeigt).", "Empieza por vigie_ (se muestra una sola vez al crearla).", "Inizia con vigie_ (mostrata una sola volta alla creazione).", "以 vigie_ 开头（仅在创建时显示一次）。"],
    "config.step.vehicles.title": ["Cars", "Voitures", "Fahrzeuge", "Coches", "Auto", "车辆"],
    "config.step.vehicles.description": ["Choose the cars to add to Home Assistant.", "Choisissez les voitures à ajouter dans Home Assistant.", "Fahrzeuge für Home Assistant auswählen.", "Elija los coches que añadir a Home Assistant.", "Scegli le auto da aggiungere a Home Assistant.", "选择要添加到 Home Assistant 的车辆。"],
    "config.step.vehicles.data.vehicles": ["Cars", "Voitures", "Fahrzeuge", "Coches", "Auto", "车辆"],
    "config.step.reauth_confirm.title": ["New API key", "Nouvelle clé API", "Neuer API-Schlüssel", "Nueva clave API", "Nuova chiave API", "新 API 密钥"],
    "config.step.reauth_confirm.description": [
        "ioDek at {url} refused the key (revoked or expired). Enter a new one.",
        "ioDek ({url}) refuse la clé (révoquée ou expirée). Saisissez-en une nouvelle.",
        "ioDek ({url}) lehnt den Schlüssel ab (widerrufen oder abgelaufen). Neuen eingeben.",
        "ioDek ({url}) rechaza la clave (revocada o caducada). Introduzca una nueva.",
        "ioDek ({url}) rifiuta la chiave (revocata o scaduta). Inseriscine una nuova.",
        "ioDek（{url}）拒绝了该密钥（已撤销或过期）。请输入新密钥。",
    ],
    "config.step.reauth_confirm.data.api_key": ["API key", "Clé API", "API-Schlüssel", "Clave API", "Chiave API", "API 密钥"],
    "config.error.invalid_auth": ["Invalid, expired or revoked key.", "Clé invalide, expirée ou révoquée.", "Schlüssel ungültig, abgelaufen oder widerrufen.", "Clave no válida, caducada o revocada.", "Chiave non valida, scaduta o revocata.", "密钥无效、已过期或已撤销。"],
    "config.error.missing_read": ["This key lacks the read permission.", "Cette clé n'a pas le droit lecture.", "Diesem Schlüssel fehlt das Leserecht.", "A esta clave le falta el permiso de lectura.", "A questa chiave manca il permesso di lettura.", "此密钥没有读取权限。"],
    "config.error.cannot_connect": ["Cannot reach ioDek at this address.", "ioDek injoignable à cette adresse.", "ioDek ist unter dieser Adresse nicht erreichbar.", "No se puede contactar con ioDek en esta dirección.", "ioDek non raggiungibile a questo indirizzo.", "无法通过此地址连接 ioDek。"],
    "config.error.rate_limited": ["Too many requests. Try again in a minute.", "Trop de requêtes. Réessayez dans une minute.", "Zu viele Anfragen. In einer Minute erneut versuchen.", "Demasiadas solicitudes. Reintente en un minuto.", "Troppe richieste. Riprova tra un minuto.", "请求过多，请一分钟后再试。"],
    "config.error.no_vehicles": ["No car on this ioDek account.", "Aucune voiture sur ce compte ioDek.", "Kein Fahrzeug in diesem ioDek-Konto.", "No hay ningún coche en esta cuenta de ioDek.", "Nessuna auto su questo account ioDek.", "此 ioDek 账户下没有车辆。"],
    "config.error.no_selection": ["Choose at least one car.", "Choisissez au moins une voiture.", "Mindestens ein Fahrzeug auswählen.", "Elija al menos un coche.", "Scegli almeno un'auto.", "请至少选择一辆车。"],
    "config.error.invalid_url": ["The address must start with https://", "L'adresse doit commencer par https://", "Die Adresse muss mit https:// beginnen.", "La dirección debe empezar por https://", "L'indirizzo deve iniziare con https://", "地址必须以 https:// 开头。"],
    "config.error.unknown": ["Unexpected error.", "Erreur inattendue.", "Unerwarteter Fehler.", "Error inesperado.", "Errore imprevisto.", "意外错误。"],
    "config.abort.already_configured": ["This ioDek account is already configured.", "Ce compte ioDek est déjà configuré.", "Dieses ioDek-Konto ist bereits eingerichtet.", "Esta cuenta de ioDek ya está configurada.", "Questo account ioDek è già configurato.", "此 ioDek 账户已配置。"],
    "config.abort.reauth_successful": ["Key updated.", "Clé mise à jour.", "Schlüssel aktualisiert.", "Clave actualizada.", "Chiave aggiornata.", "密钥已更新。"],
    "config.abort.wrong_account": ["This key belongs to another account: none of the configured cars is visible.", "Cette clé appartient à un autre compte : aucune des voitures configurées n'est visible.", "Dieser Schlüssel gehört zu einem anderen Konto: keines der Fahrzeuge ist sichtbar.", "Esta clave es de otra cuenta: no se ve ninguno de los coches configurados.", "Questa chiave appartiene a un altro account: nessuna delle auto configurate è visibile.", "此密钥属于其他账户：看不到任何已配置的车辆。"],
    # options
    "options.step.init.title": ["ioDek options", "Options d'ioDek", "ioDek-Optionen", "Opciones de ioDek", "Opzioni di ioDek", "ioDek 选项"],
    "options.step.init.data.scan_interval": ["Update interval", "Intervalle d'actualisation", "Aktualisierungsintervall", "Intervalo de actualización", "Intervallo di aggiornamento", "更新间隔"],
    "options.step.init.data.signal_buttons": ["Horn and flash buttons", "Boutons klaxon et appel de phares", "Tasten Hupe und Lichthupe", "Botones de claxon y ráfaga", "Pulsanti clacson e lampeggio", "鸣笛和闪灯按钮"],
    "options.step.init.data_description.scan_interval": [
        "30 to 300 seconds. Reads are free; the limit is 60 per minute per key.",
        "De 30 à 300 secondes. Les lectures sont gratuites ; limite de 60 par minute et par clé.",
        "30 bis 300 Sekunden. Lesezugriffe sind kostenlos; Grenze 60 pro Minute und Schlüssel.",
        "De 30 a 300 segundos. Las lecturas son gratuitas; límite de 60 por minuto y clave.",
        "Da 30 a 300 secondi. Le letture sono gratuite; limite di 60 al minuto per chiave.",
        "30 至 300 秒。读取免费；每个密钥每分钟最多 60 次。",
    ],
    "options.step.init.data_description.signal_buttons": [
        "Turn on only if the key has the signal permission. ioDek cannot report it without sounding the horn.",
        "À activer seulement si la clé a le droit signal. ioDek ne peut pas le vérifier sans klaxonner.",
        "Nur aktivieren, wenn der Schlüssel das Signalrecht hat. ioDek kann es nicht prüfen, ohne zu hupen.",
        "Actívelo solo si la clave tiene el permiso de señal. ioDek no puede comprobarlo sin tocar el claxon.",
        "Attiva solo se la chiave ha il permesso segnale. ioDek non può verificarlo senza suonare il clacson.",
        "仅当密钥具有信号权限时开启。ioDek 无法在不鸣笛的情况下检测该权限。",
    ],
    "options.step.init.data.location_entity": [
        "Position sent to ioDek (away mode for climate)",
        "Position à envoyer à ioDek (mode éloignement de la climatisation)",
        "An ioDek gesendete Position (Abwesenheitsmodus der Klimatisierung)",
        "Posición enviada a ioDek (modo alejamiento de la climatización)",
        "Posizione inviata a ioDek (modalità lontananza della climatizzazione)",
        "发送给 ioDek 的位置（空调远离模式）",
    ],
    "options.step.init.data_description.location_entity": [
        "A person or device tracker. Leave empty to send nothing. ioDek keeps only the last position, for 24 h at most. The key needs the position permission.",
        "Une personne ou un suivi d'appareil. Laissez vide pour ne rien envoyer. ioDek ne garde que la dernière position, 24 h au plus. La clé doit avoir le droit position.",
        "Eine Person oder ein Geräte-Tracker. Leer lassen, um nichts zu senden. ioDek speichert nur die letzte Position, höchstens 24 h. Der Schlüssel braucht das Positionsrecht.",
        "Una persona o un rastreador de dispositivo. Déjelo vacío para no enviar nada. ioDek solo guarda la última posición, 24 h como máximo. La clave necesita el permiso de posición.",
        "Una persona o un tracker di dispositivo. Lascia vuoto per non inviare nulla. ioDek conserva solo l'ultima posizione, per 24 h al massimo. La chiave deve avere il permesso posizione.",
        "选择一个人员或设备追踪器。留空则不发送。ioDek 只保存最后一个位置，最长 24 小时。密钥需要位置权限。",
    ],
    # repairs
    "issues.location_ability_missing.title": [
        "ioDek refuses the position",
        "ioDek refuse la position",
        "ioDek lehnt die Position ab",
        "ioDek rechaza la posición",
        "ioDek rifiuta la posizione",
        "ioDek 拒绝接收位置",
    ],
    "issues.location_ability_missing.description": [
        "The API key lacks the position permission, so the position of {entity} is no longer sent. Add the permission to the key in ioDek (Account → API keys), then reload the integration or change its options.",
        "La clé API n'a pas le droit position : la position de {entity} n'est plus envoyée. Ajoutez ce droit à la clé dans ioDek (Compte → Clés API), puis rechargez l'intégration ou modifiez ses options.",
        "Dem API-Schlüssel fehlt das Positionsrecht, die Position von {entity} wird nicht mehr gesendet. Recht in ioDek hinzufügen (Konto → API-Schlüssel), dann die Integration neu laden oder ihre Optionen ändern.",
        "La clave API no tiene el permiso de posición: la posición de {entity} ya no se envía. Añada el permiso a la clave en ioDek (Cuenta → Claves API) y recargue la integración o cambie sus opciones.",
        "La chiave API non ha il permesso posizione: la posizione di {entity} non viene più inviata. Aggiungi il permesso alla chiave in ioDek (Account → Chiavi API), poi ricarica l'integrazione o modificane le opzioni.",
        "API 密钥没有位置权限，{entity} 的位置已停止发送。请在 ioDek（账户 → API 密钥）中为密钥添加该权限，然后重新加载集成或修改其选项。",
    ],
    "issues.location_disabled.title": [
        "Position turned off in ioDek",
        "Position désactivée dans ioDek",
        "Position in ioDek deaktiviert",
        "Posición desactivada en ioDek",
        "Posizione disattivata in ioDek",
        "ioDek 中已关闭位置",
    ],
    "issues.location_disabled.description": [
        "The use of your position is turned off in the ioDek app, so the position of {entity} is no longer sent. Turn it back on in ioDek, then reload the integration, or clear the entity in the options.",
        "L'usage de votre position est désactivé dans l'application ioDek : la position de {entity} n'est plus envoyée. Réactivez-le dans ioDek puis rechargez l'intégration, ou retirez l'entité dans les options.",
        "Die Nutzung Ihrer Position ist in der ioDek-App deaktiviert, die Position von {entity} wird nicht mehr gesendet. In ioDek wieder aktivieren und die Integration neu laden, oder die Entität in den Optionen entfernen.",
        "El uso de su posición está desactivado en la app ioDek: la posición de {entity} ya no se envía. Actívelo de nuevo en ioDek y recargue la integración, o quite la entidad en las opciones.",
        "L'uso della tua posizione è disattivato nell'app ioDek: la posizione di {entity} non viene più inviata. Riattivalo in ioDek e ricarica l'integrazione, oppure rimuovi l'entità nelle opzioni.",
        "ioDek 应用中已关闭位置使用，{entity} 的位置已停止发送。请在 ioDek 中重新开启并重新加载集成，或在选项中清除该实体。",
    ],
    # entities
    "entity.sensor.energy_remaining.name": ["Energy remaining", "Énergie disponible", "Verfügbare Energie", "Energía disponible", "Energia disponibile", "剩余电量"],
    "entity.sensor.range.name": ["Range", "Autonomie", "Reichweite", "Autonomía", "Autonomia", "续航里程"],
    "entity.sensor.estimated_range.name": ["Estimated range", "Autonomie estimée", "Geschätzte Reichweite", "Autonomía estimada", "Autonomia stimata", "预估续航"],
    "entity.sensor.battery_health.name": ["Battery health", "Santé de la batterie", "Batteriezustand", "Salud de la batería", "Salute della batteria", "电池健康度"],
    "entity.sensor.battery_capacity.name": ["Battery capacity", "Capacité de la batterie", "Batteriekapazität", "Capacidad de la batería", "Capacità della batteria", "电池容量"],
    "entity.sensor.battery_cycles.name": ["Battery cycles", "Cycles de la batterie", "Batteriezyklen", "Ciclos de la batería", "Cicli della batteria", "电池循环次数"],
    "entity.sensor.cell_gap.name": ["Cell voltage gap", "Écart entre cellules", "Zellspannungsdifferenz", "Diferencia entre celdas", "Scarto tra celle", "电芯压差"],
    "entity.sensor.battery_temp_min.name": ["Battery temperature min", "Température batterie min", "Batterietemperatur min", "Temperatura batería mín", "Temperatura batteria min", "电池最低温度"],
    "entity.sensor.battery_temp_max.name": ["Battery temperature max", "Température batterie max", "Batterietemperatur max", "Temperatura batería máx", "Temperatura batteria max", "电池最高温度"],
    "entity.sensor.pack_voltage.name": ["Pack voltage", "Tension du pack", "Packspannung", "Tensión del pack", "Tensione del pacco", "电池包电压"],
    "entity.sensor.pack_current.name": ["Pack current", "Courant du pack", "Packstrom", "Corriente del pack", "Corrente del pacco", "电池包电流"],
    "entity.sensor.pack_power.name": ["Pack power", "Puissance du pack", "Packleistung", "Potencia del pack", "Potenza del pacco", "电池包功率"],
    "entity.sensor.charging_power.name": ["Charging power", "Puissance de charge", "Ladeleistung", "Potencia de carga", "Potenza di ricarica", "充电功率"],
    "entity.sensor.charge_energy_added.name": ["Charge energy added", "Énergie ajoutée", "Geladene Energie", "Energía añadida", "Energia aggiunta", "本次充入电量"],
    "entity.sensor.last_charge_energy.name": ["Last charge energy", "Énergie de la dernière charge", "Energie letzte Ladung", "Energía de la última carga", "Energia ultima ricarica", "上次充电电量"],
    "entity.sensor.energy_charged_total.name": ["Total energy charged", "Énergie chargée totale", "Gesamte geladene Energie", "Energía cargada total", "Energia caricata totale", "累计充电量"],
    "entity.sensor.energy_used_total.name": ["Total energy used", "Énergie consommée totale", "Gesamter Energieverbrauch", "Energía consumida total", "Energia consumata totale", "累计耗电量"],
    "entity.sensor.charge_state.name": ["Charge state", "État de charge", "Ladezustand", "Estado de carga", "Stato di ricarica", "充电状态"],
    "entity.sensor.charge_state.state.disconnected": ["Unplugged", "Débranchée", "Nicht eingesteckt", "Desenchufado", "Scollegata", "未插枪"],
    "entity.sensor.charge_state.state.no_power": ["No power", "Pas de courant", "Kein Strom", "Sin corriente", "Nessuna corrente", "无电力"],
    "entity.sensor.charge_state.state.starting": ["Starting", "Démarrage", "Startet", "Iniciando", "Avvio", "正在启动"],
    "entity.sensor.charge_state.state.charging": ["Charging", "En charge", "Lädt", "Cargando", "In carica", "充电中"],
    "entity.sensor.charge_state.state.complete": ["Complete", "Terminée", "Abgeschlossen", "Completada", "Completata", "已充满"],
    "entity.sensor.charge_state.state.stopped": ["Stopped", "Arrêtée", "Gestoppt", "Detenida", "Interrotta", "已停止"],
    "entity.sensor.charge_state.state.unknown": ["Unknown", "Inconnu", "Unbekannt", "Desconocido", "Sconosciuto", "未知"],
    "entity.sensor.charge_limit.name": ["Charge limit", "Limite de charge", "Ladelimit", "Límite de carga", "Limite di ricarica", "充电上限"],
    "entity.sensor.charge_current.name": ["Charge current", "Intensité de charge", "Ladestrom", "Intensidad de carga", "Corrente di ricarica", "充电电流"],
    "entity.sensor.odometer.name": ["Odometer", "Kilométrage", "Kilometerstand", "Cuentakilómetros", "Contachilometri", "总里程"],
    "entity.sensor.inside_temperature.name": ["Inside temperature", "Température intérieure", "Innentemperatur", "Temperatura interior", "Temperatura interna", "车内温度"],
    "entity.sensor.outside_temperature.name": ["Outside temperature", "Température extérieure", "Außentemperatur", "Temperatura exterior", "Temperatura esterna", "车外温度"],
    "entity.sensor.tyre_pressure_front_left.name": ["Tyre pressure front left", "Pression pneu avant gauche", "Reifendruck vorne links", "Presión neumático delantero izquierdo", "Pressione pneumatico anteriore sinistro", "左前胎压"],
    "entity.sensor.tyre_pressure_front_right.name": ["Tyre pressure front right", "Pression pneu avant droit", "Reifendruck vorne rechts", "Presión neumático delantero derecho", "Pressione pneumatico anteriore destro", "右前胎压"],
    "entity.sensor.tyre_pressure_rear_left.name": ["Tyre pressure rear left", "Pression pneu arrière gauche", "Reifendruck hinten links", "Presión neumático trasero izquierdo", "Pressione pneumatico posteriore sinistro", "左后胎压"],
    "entity.sensor.tyre_pressure_rear_right.name": ["Tyre pressure rear right", "Pression pneu arrière droit", "Reifendruck hinten rechts", "Presión neumático trasero derecho", "Pressione pneumatico posteriore destro", "右后胎压"],
    "entity.sensor.charge_time_remaining.name": ["Charged in", "Chargé dans", "Geladen in", "Cargado en", "Carica tra", "充满还需"],
    "entity.sensor.charge_end.name": ["Charge end", "Fin de charge", "Ladeende", "Fin de carga", "Fine ricarica", "充电结束时间"],
    "entity.sensor.nav_distance_remaining.name": ["Distance remaining", "Distance restante", "Verbleibende Strecke", "Distancia restante", "Distanza rimanente", "剩余距离"],
    "entity.sensor.nav_arrival.name": ["Expected arrival", "Arrivée prévue", "Voraussichtliche Ankunft", "Llegada prevista", "Arrivo previsto", "预计到达时间"],
    "entity.sensor.nav_battery_at_arrival.name": ["Battery at arrival", "Batterie à l'arrivée", "Akkustand bei Ankunft", "Batería a la llegada", "Batteria all'arrivo", "到达时电量"],
    "entity.sensor.last_seen.name": ["Last data received", "Dernière réception", "Letzter Datenempfang", "Última recepción", "Ultima ricezione", "最后接收时间"],
    "entity.binary_sensor.online.name": ["Online", "En ligne", "Online", "En línea", "Online", "在线"],
    "entity.binary_sensor.charging.name": ["Charging", "En charge", "Lädt", "Cargando", "In carica", "充电中"],
    "entity.binary_sensor.plugged_in.name": ["Plugged in", "Branchée", "Eingesteckt", "Enchufado", "Collegata", "已插枪"],
    "entity.binary_sensor.charge_port_door.name": ["Charge port door", "Trappe de charge", "Ladeklappe", "Tapa de carga", "Sportello di ricarica", "充电口盖"],
    "entity.binary_sensor.fast_charger.name": ["Fast charger", "Borne rapide", "Schnelllader", "Cargador rápido", "Colonnina rapida", "快充桩"],
    "entity.binary_sensor.battery_heater.name": ["Battery heater", "Chauffage batterie", "Batterieheizung", "Calefacción de batería", "Riscaldamento batteria", "电池加热"],
    "entity.binary_sensor.locked.name": ["Doors lock", "Verrouillage", "Verriegelung", "Cierre", "Chiusura", "车门锁"],
    "entity.binary_sensor.doors.name": ["Doors", "Portes", "Türen", "Puertas", "Portiere", "车门"],
    "entity.binary_sensor.frunk.name": ["Frunk", "Coffre avant", "Frunk", "Maletero delantero", "Bagagliaio anteriore", "前备箱"],
    "entity.binary_sensor.trunk.name": ["Trunk", "Coffre arrière", "Kofferraum", "Maletero", "Bagagliaio", "后备箱"],
    "entity.binary_sensor.windows.name": ["Windows", "Vitres", "Fenster", "Ventanillas", "Finestrini", "车窗"],
    "entity.binary_sensor.sentry.name": ["Sentry Mode", "Mode Sentinelle", "Wächter-Modus", "Modo Centinela", "Modalità Sentinella", "哨兵模式"],
    "entity.binary_sensor.climate.name": ["Climate", "Climatisation", "Klimaanlage", "Climatización", "Climatizzazione", "空调"],
    "entity.binary_sensor.tyre_warning.name": ["Tyre pressure warning", "Alerte pression pneus", "Reifendruckwarnung", "Aviso de presión", "Avviso pressione pneumatici", "胎压警告"],
    "entity.device_tracker.location.name": ["Location", "Position", "Standort", "Ubicación", "Posizione", "位置"],
    "entity.switch.charge.name": ["Charge", "Charge", "Laden", "Carga", "Ricarica", "充电"],
    "entity.switch.sentry_mode.name": ["Sentry Mode", "Mode Sentinelle", "Wächter-Modus", "Modo Centinela", "Modalità Sentinella", "哨兵模式"],
    "entity.switch.steering_wheel_heater.name": ["Heated steering wheel", "Volant chauffant", "Lenkradheizung", "Volante calefactado", "Volante riscaldato", "方向盘加热"],
    "entity.number.charge_limit.name": ["Charge limit", "Limite de charge", "Ladelimit", "Límite de carga", "Limite di ricarica", "充电上限"],
    "entity.number.charge_current.name": ["Charge current", "Intensité de charge", "Ladestrom", "Intensidad de carga", "Corrente di ricarica", "充电电流"],
    "entity.climate.climate.name": ["Climate", "Climatisation", "Klimaanlage", "Climatización", "Climatizzazione", "空调"],
    "entity.lock.lock.name": ["Doors", "Portes", "Türen", "Puertas", "Portiere", "车门"],
    "entity.button.open_frunk.name": ["Open frunk", "Ouvrir le coffre avant", "Frunk öffnen", "Abrir maletero delantero", "Apri bagagliaio anteriore", "打开前备箱"],
    "entity.button.actuate_trunk.name": ["Open or close trunk", "Ouvrir ou fermer le coffre", "Kofferraum öffnen oder schließen", "Abrir o cerrar maletero", "Apri o chiudi bagagliaio", "开关后备箱"],
    "entity.button.honk.name": ["Honk", "Klaxon", "Hupen", "Claxon", "Clacson", "鸣笛"],
    "entity.button.flash_lights.name": ["Flash lights", "Appel de phares", "Lichthupe", "Ráfaga de luces", "Lampeggio fari", "闪灯"],
    "entity.button.wake.name": ["Wake up", "Réveiller", "Aufwecken", "Despertar", "Risveglia", "唤醒"],
    "entity.select.seat_heater_left.name": ["Seat heater driver", "Siège chauffant conducteur", "Sitzheizung Fahrer", "Asiento calefactado conductor", "Sedile riscaldato guida", "主驾座椅加热"],
    "entity.select.seat_heater_right.name": ["Seat heater passenger", "Siège chauffant passager", "Sitzheizung Beifahrer", "Asiento calefactado acompañante", "Sedile riscaldato passeggero", "副驾座椅加热"],
    "entity.select.seat_heater_rear_left.name": ["Seat heater rear left", "Siège chauffant arrière gauche", "Sitzheizung hinten links", "Asiento calefactado trasero izquierdo", "Sedile riscaldato posteriore sinistro", "左后座椅加热"],
    "entity.select.seat_heater_rear_center.name": ["Seat heater rear centre", "Siège chauffant arrière centre", "Sitzheizung hinten Mitte", "Asiento calefactado trasero central", "Sedile riscaldato posteriore centrale", "后排中间座椅加热"],
    "entity.select.seat_heater_rear_right.name": ["Seat heater rear right", "Siège chauffant arrière droit", "Sitzheizung hinten rechts", "Asiento calefactado trasero derecho", "Sedile riscaldato posteriore destro", "右后座椅加热"],
    # services
    "services.refresh.name": ["Refresh", "Actualiser", "Aktualisieren", "Actualizar", "Aggiorna", "刷新"],
    "services.refresh.description": ["Reads the latest data from ioDek now. Free, does not wake the car.", "Relit tout de suite les dernières données d'ioDek. Gratuit, ne réveille pas la voiture.", "Liest sofort die neuesten Daten von ioDek. Kostenlos, weckt das Fahrzeug nicht.", "Lee ahora los últimos datos d'ioDek. Gratis, no despierta el coche.", "Rilegge subito gli ultimi dati da ioDek. Gratuito, non risveglia l'auto.", "立即从 ioDek 读取最新数据。免费，不会唤醒车辆。"],
    "services.refresh.fields.device_id.name": ["Cars", "Voitures", "Fahrzeuge", "Coches", "Auto", "车辆"],
    "services.refresh.fields.device_id.description": ["Cars to refresh. All when empty.", "Voitures à actualiser. Toutes si vide.", "Zu aktualisierende Fahrzeuge. Alle, wenn leer.", "Coches que actualizar. Todos si está vacío.", "Auto da aggiornare. Tutte se vuoto.", "要刷新的车辆。留空则刷新全部。"],
    # exceptions
    "exceptions.invalid_auth.message": ["ioDek refused the API key.", "ioDek refuse la clé API.", "ioDek lehnt den API-Schlüssel ab.", "ioDek rechaza la clave API.", "ioDek rifiuta la chiave API.", "ioDek 拒绝了 API 密钥。"],
    "exceptions.rate_limited.message": ["ioDek limit reached, try again shortly.", "Limite d'ioDek atteinte, réessayez dans un instant.", "ioDek-Limit erreicht, gleich erneut versuchen.", "Límite de ioDek alcanzado, reintente en un momento.", "Limite di ioDek raggiunto, riprova tra poco.", "已达到 ioDek 限制，请稍后再试。"],
    "exceptions.vehicle_not_found.message": ["This car is no longer visible with this key.", "Cette voiture n'est plus visible avec cette clé.", "Dieses Fahrzeug ist mit diesem Schlüssel nicht mehr sichtbar.", "Este coche ya no es visible con esta clave.", "Quest'auto non è più visibile con questa chiave.", "使用此密钥已看不到该车辆。"],
    "exceptions.read_forbidden.message": ["The key no longer has the read permission.", "La clé n'a plus le droit lecture.", "Der Schlüssel hat kein Leserecht mehr.", "La clave ya no tiene permiso de lectura.", "La chiave non ha più il permesso di lettura.", "该密钥已没有读取权限。"],
    "exceptions.update_failed.message": ["ioDek is unreachable ({error}).", "ioDek est injoignable ({error}).", "ioDek ist nicht erreichbar ({error}).", "ioDek no responde ({error}).", "ioDek non è raggiungibile ({error}).", "无法连接 ioDek（{error}）。"],
    "exceptions.vehicle_asleep.message": ["The car is asleep. Press Wake up first (3 per hour).", "La voiture dort. Appuyez d'abord sur Réveiller (3 par heure).", "Das Fahrzeug schläft. Zuerst Aufwecken drücken (3 pro Stunde).", "El coche está dormido. Pulse primero Despertar (3 por hora).", "L'auto dorme. Premi prima Risveglia (3 all'ora).", "车辆处于休眠状态。请先按“唤醒”（每小时 3 次）。"],
    "exceptions.ability_missing.message": ["The API key lacks the permission for this command: {message}", "La clé API n'a pas le droit pour cette commande : {message}", "Dem API-Schlüssel fehlt das Recht für diesen Befehl: {message}", "La clave API no tiene permiso para este comando: {message}", "La chiave API non ha il permesso per questo comando: {message}", "API 密钥没有执行此命令的权限：{message}"],
    "exceptions.option_disabled.message": ["This option is off for the car in ioDek: {message}", "Cette option est désactivée pour la voiture dans ioDek : {message}", "Diese Option ist für das Fahrzeug in ioDek deaktiviert: {message}", "Esta opción está desactivada para el coche en ioDek: {message}", "Questa opzione è disattivata per l'auto in ioDek: {message}", "ioDek 中该车辆的此选项已关闭：{message}"],
    "exceptions.command_failed.message": ["Command refused: {message}", "Commande refusée : {message}", "Befehl abgelehnt: {message}", "Comando rechazado: {message}", "Comando rifiutato: {message}", "命令被拒绝：{message}"],
}

SELECT_STATES = {
    "off": ["Off", "Arrêt", "Aus", "Apagado", "Spento", "关闭"],
    "low": ["Low", "Faible", "Niedrig", "Bajo", "Basso", "低"],
    "medium": ["Medium", "Moyen", "Mittel", "Medio", "Medio", "中"],
    "high": ["High", "Fort", "Hoch", "Alto", "Alto", "高"],
}
for seat in ("left", "right", "rear_left", "rear_center", "rear_right"):
    for state, texts in SELECT_STATES.items():
        T[f"entity.select.seat_heater_{seat}.state.{state}"] = texts


def build(index: int) -> dict:
    out: dict = {}
    for dotted, texts in T.items():
        node = out
        parts = dotted.split(".")
        for p in parts[:-1]:
            node = node.setdefault(p, {})
        node[parts[-1]] = texts[index]
    return out


def main() -> None:
    for lang in LANGS:
        assert all(len(v) == len(LANGS) for v in T.values())
        data = build(LANGS.index(lang))
        text = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
        (ROOT / "translations" / f"{lang}.json").write_text(text, encoding="utf-8")
        if lang == "en":
            (ROOT / "strings.json").write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()

<p align="center"><img src="custom_components/vigie/brand/icon.png" width="128" height="128" alt="ioDek"></p>

# ioDek pour Home Assistant

[English below](#english)

Intégration Home Assistant pour [ioDek](https://iodek.fr) (anciennement Vigie), l'application de suivi et de pilotage des Tesla. Elle lit l'API publique d'ioDek (`https://api.iodek.fr/v1`) avec une clé API personnelle.

ioDek est une application indépendante, sans lien avec Tesla, Inc.

Le domaine technique de l'intégration reste `vigie` : les installations existantes continuent de fonctionner sans rien changer, avec leur adresse d'origine (`https://vigie.allyn.fr` reste acceptée).

## Ce que vous obtenez

Un appareil par voiture, avec :

- **Batterie** : niveau de charge, énergie disponible, autonomie, santé (SOH), capacité, cycles, écart entre cellules, températures min et max, tension, courant et puissance du pack.
- **Charge** : état, puissance, énergie ajoutée, **chargé dans** (minutes jusqu'à la limite) et **fin de charge** (heure), énergie de la dernière charge, énergie chargée totale (utilisable dans le tableau Énergie), branchée, en charge, trappe. « Chargé dans » reprend l'estimation de Tesla quand la voiture l'envoie, sinon celle d'ioDek (attribut `source` : `tesla` ou `estimation`).
- **Navigation** (option Localisation) : distance restante, arrivée prévue, batterie à l'arrivée, quand une destination est saisie dans le GPS de la voiture. Un traqueur « Destination » (0.5.1) place la destination sur la carte, avec son nom en attribut : un déclencheur de zone sur ce traqueur part dès que le trajet vers cette zone commence.
- **Voiture** : kilométrage, températures intérieure et extérieure, pression des quatre pneus, verrouillage, portes, coffres, vitres, Sentinelle, climatisation, dernière réception, en ligne ou endormie.
- **Position** (`device_tracker`) si l'option Localisation est active sur la voiture dans ioDek.
- **Plan de charge** du planificateur d'ioDek : statut, début et fin prévus, pourcentage visé, raison (minimum du jour, agenda, trajet prévu).
- **Commandes**, selon les droits de la clé et les options de la voiture : charge marche/arrêt, limite de charge, intensité, climatisation et consigne, verrouillage, coffres, Sentinelle, sièges et volant chauffants, réveil, klaxon et appel de phares.

Et un appareil **ioDek Électricité** pour le compte : prix du kWh en cours, période (base, heures pleines, heures creuses, gratuit), prochain changement et prix suivant, couleur Tempo du jour et du lendemain.

Tesla n'envoie une valeur que lorsqu'elle change. Une entité apparaît donc dès que la voiture a transmis la donnée correspondante, parfois quelques jours après l'installation.

Quand la voiture dort, les dernières valeurs restent affichées. Les mesures instantanées (puissance, courant, tension) passent en « indisponible ». « Chargé dans » et « Fin de charge » sont indisponibles hors charge, les capteurs de navigation sans destination.

## Installation

### HACS (dépôt personnalisé)

1. HACS → menu ⋮ → **Dépôts personnalisés**.
2. URL du dépôt, catégorie **Intégration**.
3. Installez **ioDek**, puis redémarrez Home Assistant.

### Manuelle

Copiez `custom_components/vigie` dans le dossier `config/custom_components/` de Home Assistant, puis redémarrez.

## Configuration

1. Dans ioDek : **Compte → Clés API**, créez une clé. Le droit **lecture** suffit pour les capteurs. Ajoutez **charge**, **confort**, **accès** ou **signal** pour obtenir les commandes correspondantes.
2. Dans Home Assistant : **Paramètres → Appareils et services → Ajouter une intégration → ioDek**.
3. Adresse (par défaut `https://api.iodek.fr`) et clé, puis choix des voitures.

Options : intervalle d'actualisation (30 à 300 s, 60 par défaut), boutons klaxon / appel de phares, position envoyée à ioDek, entités pour les boutons du tableau de bord ioDek (voir plus bas).

Une commande n'existe que si la clé a le droit **et** si l'option correspondante est active sur la voiture (ioDek → Réglages de la voiture). Si vous changez ces options dans ioDek, l'intégration se recharge d'elle-même.

Le droit **signal** ne peut pas être détecté sans klaxonner : cochez l'option « Boutons klaxon et appel de phares » si votre clé l'a.

## Position pour le mode éloignement

La programmation de la climatisation dans ioDek peut ne pas se déclencher quand vous êtes loin de la voiture. Pour cela, ioDek a besoin de votre position, et Home Assistant la connaît souvent mieux que le téléphone.

Dans les options de l'intégration, choisissez une entité `person` ou `device_tracker`. Laissé vide (par défaut), rien n'est envoyé.

- Envoi à la première position connue, puis dès que vous vous êtes déplacé de plus de 200 m, au plus une fois par minute.
- Nouvel envoi toutes les 3 h sans déplacement, pour que la position reste à jour côté ioDek.
- Les états sans coordonnées (inconnu, indisponible) sont ignorés.
- La clé API doit avoir le droit **position** (ioDek → Compte → Clés API). Sans ce droit, ou si l'usage de la position est désactivé dans l'application, l'intégration arrête d'envoyer et le signale dans **Réparations**, jusqu'au prochain changement d'options ou redémarrage.
- ioDek ne garde que la dernière position, sans historique. Elle est jugée à jour 6 h et effacée au bout de 24 h. Les coordonnées n'apparaissent ni dans les journaux ni dans les diagnostics.

## Boutons du tableau de bord ioDek

Le tableau de bord d'ioDek peut afficher des boutons qui actionnent des entités de Home Assistant : ouvrir le portail, lancer un script, allumer une lumière…

1. Dans ioDek : **Compte → Clés API**, ajoutez le droit **domotique** à la clé utilisée par Home Assistant.
2. Dans Home Assistant : options de l'intégration ioDek, champ « Entités pour les boutons du tableau de bord ioDek ». Choisissez les entités à exposer. Laissé vide (par défaut), rien n'est exposé.

Rien n'est à ouvrir sur Internet : c'est Home Assistant qui se connecte à ioDek (WebSocket sortant) et reçoit les ordres. ioDek ne détient aucun jeton Home Assistant.

Domaines et services permis (liste fermée, vérifiée par ioDek et par l'intégration) :

| Domaine | Services |
|---|---|
| `script`, `scene` | `turn_on` |
| `button`, `input_button` | `press` |
| `automation` | `trigger` |
| `switch`, `input_boolean`, `light`, `fan` | `toggle`, `turn_on`, `turn_off` |
| `cover` | `toggle`, `open_cover`, `close_cover`, `stop_cover` |
| `lock` | `lock`, `unlock` |

- ioDek demande une confirmation avant d'actionner une serrure, un volet ou un portail.
- L'intégration n'exécute que les entités exposées et les services de la liste, même si on lui demande autre chose. Un ordre périmé ou déjà reçu est ignoré, et chaque ordre fait l'objet d'un compte rendu à ioDek (réussi, refusé, délai dépassé, erreur).
- Le nom, l'icône et l'état des entités exposées sont envoyés à ioDek au démarrage, toutes les 6 h et à chaque changement d'état (regroupés par seconde).
- Chaque ordre exécuté est noté dans le journal (« ioDek : toggle sur light.salon »).
- Sans le droit **domotique**, ou si votre formule ioDek ne comprend pas l'API, l'intégration arrête le pont et le signale dans **Réparations**, jusqu'au prochain changement d'options ou redémarrage.
- Vider la liste retire les boutons côté ioDek.

## Électricité et plan de charge

L'appareil **ioDek Électricité** reprend le tarif saisi dans ioDek (Compte → Électricité, lieux de recharge) : celui du domicile du conducteur s'il en a un, sinon du lieu par défaut. Lu toutes les 5 minutes.

| Entité | Unité ou valeurs |
|---|---|
| `sensor.iodek_electricite_prix_en_cours` | EUR/kWh ; attributs `tariff`, `period`, `tempo_color`, `place`, `place_source` |
| `sensor.iodek_electricite_periode` | `base`, `peak` (heures pleines), `offpeak` (heures creuses), `free` |
| `sensor.iodek_electricite_prochain_changement` | horodatage ; attributs `period`, `tempo_color` |
| `sensor.iodek_electricite_prix_suivant` | EUR/kWh |
| `sensor.iodek_electricite_tempo_aujourd_hui`, `…_tempo_demain` | `blue`, `white`, `red`, `unknown` (couleur du lendemain publiée vers 10 h 40) |

Sur chaque voiture, le **plan de charge** en cours ou à venir : `…_plan_de_charge` (statut : `planned`, `unplugged`, `running`, `done`, `none`, `nodata`, `unmanaged`, `away`, `failed`, ou `no_plan`), `…_debut_de_charge_prevu` et `…_fin_de_charge_prevue` (horodatages), `…_pourcentage_vise` (%), `…_raison_du_plan` (`minimum`, `calendar`, `trip`). Lu avec le reste quand le planificateur est actif, toutes les 15 minutes sinon. Les identifiants d'entités dépendent de la langue de Home Assistant à l'installation.

## Événements pour les automatisations

ioDek prévient Home Assistant dès qu'un événement arrive sur la voiture, par le même canal que les boutons (WebSocket sortant, rien à ouvrir). La clé doit avoir le droit **domotique** en plus de **lecture** ; aucune entité n'a besoin d'être exposée.

Chaque événement déclenche un événement Home Assistant `vigie_event`, et existe aussi comme **déclencheur d'appareil** sur la voiture (éditeur d'automatisations → Appareil → la voiture) :

| `type` | Quand | Données utiles |
|---|---|---|
| `charge_started` | charge commencée | `soc` |
| `charge_complete` | charge terminée | `soc` |
| `charge_stopped` | charge interrompue (pas à la limite) | `soc`, `reason` (`stopped`, `no_power`) |
| `battery_low` | batterie sous votre seuil d'alerte (ioDek → Compte → Alertes) | `soc`, `threshold` |
| `sentry_alert` | alarme Sentinelle | `level` (`aware` : présence, `panic` : alarme) |
| `parked` | voiture garée | `soc`, `place`, `at_home` (option Localisation) |
| `charge_limit_set` | limite de charge du lieu appliquée | `limit`, `place` |

Toujours présents : `vehicle_id`, `vehicle_name`, `at` (UTC), `device_id` (l'appareil de la voiture). `location` (`lat`, `lon`) pour `parked` et `sentry_alert` seulement si l'option Localisation est active et si la clé a le droit **position**. Le VIN n'est jamais envoyé. Un événement vieux de plus de 15 minutes n'est pas transmis.

Alarme Sentinelle → allumer une lumière :

```yaml
automation:
  - alias: "Tesla : alarme Sentinelle"
    triggers:
      - trigger: event
        event_type: vigie_event
        event_data:
          type: sentry_alert
          level: panic
    actions:
      - action: light.turn_on
        target:
          entity_id: light.allee
        data:
          flash: long
```

Heures creuses → lancer le chauffe-eau :

```yaml
automation:
  - alias: "Chauffe-eau en heures creuses"
    triggers:
      - trigger: state
        entity_id: sensor.iodek_electricite_periode
        to: offpeak
    actions:
      - action: switch.turn_on
        target:
          entity_id: switch.chauffe_eau
  - alias: "Chauffe-eau coupé en heures pleines"
    triggers:
      - trigger: state
        entity_id: sensor.iodek_electricite_periode
        to: peak
    conditions:
      # Pas de chauffe un jour rouge Tempo.
      - condition: not
        conditions:
          - condition: state
            entity_id: sensor.iodek_electricite_tempo_aujourd_hui
            state: red
    actions:
      - action: switch.turn_off
        target:
          entity_id: switch.chauffe_eau
```

Pour cibler une voiture précise avec `vigie_event`, ajoutez `device_id` (ou `vehicle_id`) dans `event_data`, ou utilisez le déclencheur d'appareil.

## Coûts et limites

- Les lectures viennent de la base d'ioDek et ne coûtent rien. Elles ne réveillent pas la voiture.
- Commandes et réveils consomment des crédits ioDek.
- Une commande ne réveille jamais la voiture : si elle dort, Home Assistant affiche l'erreur et il faut appuyer sur **Réveiller** (3 réveils par heure et par voiture).
- Limites de l'API : 60 lectures et 10 commandes par minute et par clé. L'électricité ajoute une lecture toutes les 5 minutes, le plan de charge une par voiture et par actualisation quand le planificateur est actif. Les événements arrivent par le WebSocket, sans lecture.

## Service

`vigie.refresh` relit tout de suite les données (toutes les voitures, ou celles passées en `device_id`).

## Clé révoquée

Si la clé est révoquée ou expire, Home Assistant propose d'en saisir une nouvelle (réauthentification).

---

## English

Home Assistant integration for [ioDek](https://iodek.fr) (formerly Vigie), a Tesla monitoring and control app. It reads ioDek's public API (`https://api.iodek.fr/v1`) with a personal API key. ioDek is not affiliated with Tesla, Inc.

The integration's technical domain stays `vigie`: existing installs keep working unchanged, with their original address (`https://vigie.allyn.fr` is still accepted).

**Entities** (one device per car): battery level, energy remaining, range, state of health, capacity, cycles, cell voltage gap, battery temperatures, pack voltage/current/power, charge state and power, energy added, **charged in** (minutes to the charge limit) and **charge end** (time), total energy charged (Energy dashboard ready), odometer, inside/outside temperature, tyre pressures, lock, doors, trunks, windows, Sentry Mode, climate, last data received, online/asleep, GPS position when the car's Location option is on. With Location on and a destination in the car's navigation: distance remaining, expected arrival, battery at arrival, and a **Destination** tracker (0.5.1, attribute `destination_name`) so a zone trigger fires when a drive to that zone starts. "Charged in" uses Tesla's own estimate when the car sends it, otherwise ioDek's (attribute `source`: `tesla` or `estimation`); it is unavailable when not charging.

**Controls**, created only when the key has the ability and the car option is on: charging on/off, charge limit, charge current, climate and target temperature, lock, trunks, Sentry Mode, seat and steering wheel heaters, wake-up, horn and lights (enable the option: the signal ability cannot be detected without honking).

Tesla sends a field only when it changes, so some entities appear once the car has reported them. While the car sleeps, last known values stay; live measurements (power, current, voltage) become unavailable.

**Install**: HACS custom repository (category Integration), or copy `custom_components/vigie` to `config/custom_components/` and restart.

**Setup**: create a key in ioDek (Account → API keys; `lecture` is required), then add the **ioDek** integration in Home Assistant with the address `https://api.iodek.fr`. Options: update interval 30-300 s (default 60), horn and lights buttons, position, dashboard buttons.

**Position for away mode**: in the options, pick a `person` or `device_tracker` entity (empty by default, nothing sent). Its position goes to ioDek so scheduled climate can skip when you are far from the car: on the first known position, after a move of more than 200 m (at most once a minute), and every 3 h otherwise. The key needs the **position** permission. ioDek keeps only the last position, fresh for 6 h and deleted after 24 h.

**Dashboard buttons**: ioDek's dashboard can show buttons that operate Home Assistant entities (open the gate, run a script, turn on a light). Add the **domotique** (home automation) permission to the key in ioDek, then pick the entities in the integration options (empty by default: nothing exposed). Nothing has to be opened to the Internet: Home Assistant connects out to ioDek over a WebSocket and receives the orders; ioDek holds no Home Assistant token. Allowed domains and services (closed list, checked on both sides): `script`/`scene` `turn_on`; `button`/`input_button` `press`; `automation` `trigger`; `switch`/`input_boolean`/`light`/`fan` `toggle`, `turn_on`, `turn_off`; `cover` `toggle`, `open_cover`, `close_cover`, `stop_cover`; `lock` `lock`, `unlock`. ioDek asks for a confirmation before operating a lock, a cover or a gate. The integration runs only exposed entities and listed services, whatever it is asked, ignores expired or duplicate orders and reports each outcome to ioDek. Without the permission (or the plan), the bridge stops and a Repairs issue explains why.

**Electricity and charge plan** (0.5.0): an **ioDek Electricity** device per account with the current price (EUR/kWh, attributes tariff, period, place), period (`base`, `peak`, `offpeak`, `free`), next change (timestamp) and next price, Tempo colour of today and tomorrow (`blue`, `white`, `red`, `unknown`); read every 5 minutes. Each car gets its charge plan: status, planned start and end (timestamps), target (%), reason (`minimum`, `calendar`, `trip`).

**Events for automations** (0.5.0): with the **domotique** and **lecture** permissions, ioDek pushes the car's events over the same outgoing WebSocket. Each one fires a `vigie_event` event (`type`, `vehicle_id`, `vehicle_name`, `at`, `device_id`, plus `soc`, `reason`, `threshold`, `level`, `place`, `at_home`, `limit` as relevant; `location` only with the Location option and the **position** permission; never the VIN) and is available as a device trigger on the car: `charge_started`, `charge_complete`, `charge_stopped`, `battery_low` (your alert threshold in ioDek), `sentry_alert` (`aware` or `panic`), `parked`, `charge_limit_set`. See the French section above for YAML examples (Sentry alarm → light, off-peak hours → water heater).

**Costs**: reads are free and never wake the car. Commands and wake-ups use ioDek credits. Commands never wake the car; press **Wake up** first (3 per hour). API limits: 60 reads and 10 commands per minute per key.

**Service**: `vigie.refresh` reads fresh data now.

## Development

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements_test.txt
.venv/bin/pytest -q
.venv/bin/python scripts/build_translations.py   # regenerates strings.json and translations/
```

License: MIT.

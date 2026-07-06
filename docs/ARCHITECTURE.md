# Architecture

## Comment ça marche

1. Les scrapers (`tayara.py`, `mubawab.py`) récupèrent les annonces (vente et location)
2. `insert.py` les met dans PostgreSQL (sans doublon sur `source` + `ad_id`)
3. `main.py` expose l'API FastAPI
4. `queries.py` gère la recherche

Plus tard : React au-dessus de l'API, Gemini et ML à côté.

## Services Docker

| Service | Rôle | Port |
|---|---|---|
| `db` | PostgreSQL 16 | 5434 (hôte) |
| `backend` | FastAPI | 8000 |
| `frontend` | React | 3000 |

Le port 5434 évite le conflit avec un Postgres Windows sur 5432.

## Base de données

Une seule table **`properties`** :

| Colonnes communes (toujours renseignées) | |
|---|---|
| `source`, `ad_id`, `property_type`, `listing_type` | identité et classification |
| `title`, `description`, `price`, `area`, `city`, `address`, `url` | contenu de l'annonce |

| Colonnes maison (`property_type = house`) | NULL pour les terrains |
|---|---|
| `bedrooms`, `bathrooms`, `garage`, `furnished`, `terrace`, `pool` | |

| Colonnes terrain (`property_type = land`) | NULL pour les maisons |
|---|---|
| `buildable`, `road_access` | |

## Endpoints

- `/scrape` — lance le scraping, retourne inserted/skipped/errors
- `/properties/search` — filtres + pagination (ville, type, transaction, prix, surface, chambres)
- `/properties/{id}` — un bien

Swagger : http://localhost:8000/docs

## Config (.env)

- Dans Docker : `DB_HOST=db`, `DB_PORT=5432`
- En local : `DB_HOST=localhost`, `DB_PORT=5434`

Voir `.env.example`.

## Fichiers importants

```
scraper/main.py       → API
scraper/insert.py     → insertion DB
scraper/scrapers/     → Tayara, Mubawab
db/init.sql           → création de la table
db/migrate_ad_id.sql  → migrations pour bases existantes
docker-compose.yml    → lance tout
```

## Roadmap

- **S2** : scraping automatique, nettoyage des données
- **S3** : frontend React
- **S4** : ML estimation de prix
- **S5** : Gemini
- **S6** : simulation financière

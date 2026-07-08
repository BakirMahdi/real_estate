## Lancer le projet

```bash
cp .env.example .env
docker compose up -d --build
```

- Frontend : http://localhost:3000
- API : http://localhost:8000/docs
- pgAdmin : http://localhost:5433 (login : `admin@admin.com` / `admin`)
- PostgreSQL (direct) : port **5434**

## Scraper des annonces

Swagger → `GET /scrape` → Execute

Ou :

```bash
curl http://localhost:8000/scrape
```

## Dev local (sans rebuild Docker)

```bash
pip install -r requirements.txt
```

Dans `.env` :

```
DB_HOST=localhost
DB_PORT=5434
```

Puis :

```bash
uvicorn scraper.main:app --reload
```

## API

- `GET /health` — API ok
- `GET /health/db` — DB ok
- `GET /scrape` — scrape + insert
- `GET /properties/all` — toutes les annonces
- `GET /properties/search` — recherche (ville, type, transaction, prix, surface, chambres)
- `GET /properties/{id}` — détail d'un bien

## Frontend

Interface web React sur http://localhost:3000 :

- **Annonces** — catalogue avec filtres et pagination
- **Détail** — fiche complète d'une annonce
- **Dashboard** — statut API/DB, lancement du scrape

## Structure

- `frontend/` — interface React (Vite + Tailwind)
- `scraper/` — API + scrapers
- `db/init.sql` — tables
- `docs/` — architecture

## Problèmes fréquents

- **pgAdmin vide** → connecte le serveur `realestate`, password = celui dans `.env` (`0000` par défaut)
- **pgAdmin ne s'ouvre pas** → `docker compose up -d pgadmin` puis http://localhost:5433
- **0 inserted au scrape** → `docker compose logs backend`
- **Scrape lent** → normal (~10–15 min) : chaque annonce Mubawab ouvre sa page détail pour récupérer toutes les photos et la description complète
- **Tables manquantes / colonnes obsolètes** → `docker exec realestate-postgres psql -U postgres -d realestate -f /migrations/migrate_ad_id.sql`

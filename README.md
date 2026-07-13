## Lancer le projet

```bash
cp .env.example .env
docker compose up -d --build
```

- Frontend : http://localhost:3000
- API : http://localhost:8000/docs
- pgAdmin : http://localhost:5433
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
- `GET /properties/{id}/estimate` — estimation ML du prix + score d'investissement

## Estimation IA (ML)

Le modèle estime le prix théorique d'un bien et en déduit un **score
d'investissement** (0–100, affiché sur la fiche du bien) :

- `50` = prix conforme à l'estimation ; `100` = affiché ≥ 30 % sous
  l'estimation (bonne affaire) ; `0` = ≥ 30 % au-dessus.
- Pas de score pour les locations ni les annonces sans prix affiché
  (l'estimation reste calculée).

### Entraîner / réentraîner le modèle

À faire une première fois après l'installation (sinon `/estimate` répond
503), puis après chaque gros scrape :

```bash
docker exec realestate-backend python -m scraper.ml.train_price_model
docker compose restart backend   # recharge le nouveau modèle
```

Le script nettoie les données (prix placeholder, valeurs aberrantes),
entraîne un gradient boosting sur log(prix) et affiche les métriques
d'évaluation (R², erreur médiane par type de transaction). Le modèle est
sauvegardé dans `./models/` (volume Docker, survit aux rebuilds, non
versionné).

### Tester

```bash
curl http://localhost:8000/properties/<id>/estimate
```

Code source : `scraper/ml/` (`prepare_training_data.py` nettoyage,
`train_price_model.py` entraînement, `estimator.py` prédiction + score).

## Frontend

Interface web React sur http://localhost:3000 :

- **Annonces** — catalogue avec filtres et pagination
- **Détail** — fiche complète d'une annonce, estimation IA + score d'investissement, simulateur de crédit
- **Dashboard** — statut API/DB, lancement du scrape

## Structure

- `frontend/` — interface React (Vite + Tailwind)
- `scraper/` — API + scrapers
- `db/init.sql` — tables
- `docs/` — architecture

## Problèmes fréquents

- **pgAdmin vide** → connecte le serveur `realestate`, password = celui dans `.env`
- **pgAdmin ne s'ouvre pas** → `docker compose up -d pgadmin` puis http://localhost:5433
- **0 inserted au scrape** → `docker compose logs backend`
- **Scrape lent** → normal (~10–15 min) : chaque annonce Mubawab ouvre sa page détail pour récupérer toutes les photos et la description complète
- **Tables manquantes / colonnes obsolètes** → `docker exec realestate-postgres psql -U postgres -d realestate -f /migrations/migrate_ad_id.sql`
- **`/estimate` répond 503 / pas d'estimation sur la fiche** → le modèle n'est pas encore entraîné, voir « Estimation IA (ML) »

# LogiTicket Pro — version production UX

Plateforme de ticketing logistique eCommerce avec séparation stricte **admin/client**, authentification sécurisée, filtres métiers, notifications et dashboard KPI.

## Ce que vous avez maintenant
- Interface modernisée (design dashboard, filtres, recherche, feedback visuel).
- Authentification sécurisée (mots de passe hashés PBKDF2, sessions persistées en base).
- Mode admin : vision globale + changement de statut.
- Mode client : création et suivi de ses tickets uniquement.

## Comment l'utiliser maintenant (pas à pas)
### 1) Lancer l'application
```bash
python3 app.py
```
Ouvrez ensuite : `http://localhost:8000`.

### 2) Se connecter
Comptes de démonstration :
- `admin` / `Admin2026!`
- `client_mode_paris` / `Paris#123`
- `client_beaute_lyon` / `Lyon#123`
- `client_tech_lille` / `Lille#123`

### 3) Utilisation côté client
- Cliquer sur **Nouveau ticket**.
- Renseigner type d’incident, priorité, commande, description.
- Suivre le statut dans la liste des tickets.

### 4) Utilisation côté admin
- Voir tous les tickets de tous les clients.
- Filtrer par statut, rechercher par commande/client/ticket.
- Mettre à jour les statuts (Nouveau / En-cours / Résolu).

## Variables d'environnement
- `DB_PATH` : chemin de la base SQLite (défaut: `./data.db`).
- `PORT` : port HTTP (défaut: `8000`).
- `SESSION_TTL_HOURS` : durée de vie de session (défaut: `12`).
- `COOKIE_SECURE` : `true` en HTTPS (recommandé prod), `false` en local.
- `PBKDF2_ITERATIONS` : coût du hash mot de passe (défaut: `260000`).

## Lancement production recommandé
```bash
export DB_PATH="/var/lib/logiticket/data.db"
export PORT="8000"
export COOKIE_SECURE="true"
python3 app.py
```

## Docker
```bash
docker build -t logiticket .
docker run -p 8000:8000 \
  -v $(pwd)/data:/data \
  -e DB_PATH=/data/data.db \
  -e COOKIE_SECURE=true \
  logiticket
```

## Bonnes pratiques prod
- Mettre l'app derrière un reverse-proxy HTTPS (Nginx/Caddy/Traefik).
- Activer monitoring + sauvegarde quotidienne de la base SQLite.
- Restreindre les IP d’administration si possible.

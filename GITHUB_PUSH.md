# Publier le projet sur GitHub

Le code est commité localement, mais **aucun remote GitHub n'est configuré**.

## 1) Créer un repo GitHub
Créez un dépôt vide (ex: `logiticket-pro`) sur votre compte GitHub.

## 2) Ajouter le remote
```bash
git remote add origin https://github.com/<votre-compte>/<votre-repo>.git
```

## 3) Pousser la branche courante
```bash
git push -u origin work
```

## 4) Vérifier
```bash
git remote -v
git branch -vv
```

## Pourquoi ce n'est pas automatique ?
- Le dépôt local n'a pas d'URL `origin`.
- L'agent n'a pas vos identifiants GitHub/token pour pousser à votre place.

Une fois le remote configuré, les prochains push se font avec `git push`.

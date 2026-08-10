import {
  createContext,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";

export type Lang = "fr" | "en";

const STORAGE_KEY = "lang";

function readStoredLang(): Lang {
  try {
    return localStorage.getItem(STORAGE_KEY) === "en" ? "en" : "fr";
  } catch {
    return "fr";
  }
}

// Module-level current language so plain helpers (lib/format.ts) can localize
// too. It is kept in sync with the provider state: every translated component
// subscribes to the context, so a language switch re-renders them after this
// variable has been updated.
let currentLang: Lang = readStoredLang();

const fr: Record<string, string> = {
  // Generic fallbacks
  "common.loading": "Chargement...",

  // Header / nav
  "nav.home": "Accueil",
  "nav.listings": "Annonces",
  "nav.favorites": "Favoris",
  "nav.dashboard": "Dashboard",
  "nav.login": "Connexion",
  "nav.logout": "Déconnexion",
  "nav.menu": "Menu principal",
  "nav.openMenu": "Ouvrir le menu",
  "nav.closeMenu": "Fermer le menu",
  "nav.darkMode": "Mode sombre",
  "nav.lightMode": "Mode clair",
  "footer.tagline": "Rews — Agrégateur immobilier Tunisie",

  // Welcome page
  "welcome.badge": "Plateforme immobilière intelligente · Tunisie",
  "welcome.titlePrefix": "Trouvez le bien idéal avec",
  "welcome.subtitle":
    "Rews est une plateforme de veille immobilière qui agrège des milliers d'annonces en Tunisie, estime le juste prix par intelligence artificielle et vous accompagne dans votre décision d'achat ou de location.",
  "welcome.explore": "Explorer les annonces",
  "welcome.login": "Se connecter",
  "welcome.f1.title": "Veille multi-sources",
  "welcome.f1.text":
    "Les annonces de Tayara et Mubawab réunies et dédupliquées au même endroit.",
  "welcome.f2.title": "Estimation par IA",
  "welcome.f2.text":
    "Un prix théorique et un score d'investissement calculés pour chaque bien.",
  "welcome.f3.title": "Assistant intelligent",
  "welcome.f3.text":
    "Posez vos questions en langage naturel et laissez l'agent chercher pour vous.",
  "welcome.f4.title": "Simulateur de crédit",
  "welcome.f4.text":
    "Capacité d'achat, mensualités et alternatives adaptées à votre budget.",

  // Login page
  "login.title": "Connexion",
  "login.titleRegister": "Créer un compte",
  "login.subtitle": "Connectez-vous pour discuter avec l'assistant",
  "login.subtitleRegister": "Créez un compte pour commencer",
  "login.username": "Nom d'utilisateur",
  "login.usernamePlaceholder": "votre_nom",
  "login.password": "Mot de passe",
  "login.submit": "Se connecter",
  "login.submitRegister": "Créer un compte",
  "login.loading": "Chargement...",
  "login.or": "ou",
  "login.toggleToRegister": "Pas encore de compte ? Créer un compte",
  "login.toggleToLogin": "Déjà un compte ? Se connecter",
  "login.backHome": "← Retour à l'accueil",
  "login.email": "E-mail",
  "login.emailPlaceholder": "vous@exemple.com",

  "verify.title": "Vérifiez votre e-mail",
  "verify.subtitle": "Saisissez le code à 6 chiffres envoyé à",
  "verify.codeLabel": "Code de vérification",
  "verify.submit": "Vérifier et continuer",
  "verify.resend": "Renvoyer le code",
  "verify.back": "← Retour",
  "verify.sent": "Un code de vérification a été envoyé à votre adresse e-mail.",
  "verify.resent": "Un nouveau code a été envoyé.",

  // Auth / network errors
  "error.badCredentials": "E-mail ou mot de passe incorrect.",
  "error.emailExists": "Cet e-mail est déjà utilisé. Connectez-vous.",
  "error.emailInvalid": "Veuillez saisir une adresse e-mail valide.",
  "error.emailNotVerified":
    "E-mail non vérifié. Un nouveau code vous a été envoyé.",
  "error.codeInvalid":
    "Code incorrect ou expiré. Réessayez ou renvoyez un code.",
  "error.emailSendFailed":
    "Impossible d'envoyer l'e-mail de vérification. Réessayez.",
  "error.rateLimited":
    "Trop de tentatives. Patientez une minute puis réessayez.",
  "error.usernameTaken":
    "Ce nom d'utilisateur est déjà utilisé. Choisissez-en un autre ou connectez-vous.",
  "error.usernameShort":
    "Le nom d'utilisateur doit contenir au moins 3 caractères.",
  "error.passwordShort": "Le mot de passe doit contenir au moins 8 caractères.",
  "error.timeout":
    "Le serveur met trop de temps à répondre. Veuillez réessayer.",
  "error.network":
    "Impossible de contacter le serveur. Vérifiez votre connexion.",
  "error.generic": "Une erreur est survenue. Veuillez réessayer.",
  "error.google": "Échec de la connexion Google.",

  // Listings page
  "home.catalog": "Catalogue",
  "home.title": "Trouvez votre bien",
  "home.subtitle":
    "Annonces immobilières agrégées depuis Tayara et Mubawab — maisons, appartements et terrains à travers la Tunisie.",
  "home.found.one": "annonce trouvée",
  "home.found.many": "annonces trouvées",
  "home.loading": "Chargement des annonces...",
  "home.loadError": "Erreur de chargement",
  "home.retry": "Réessayer",
  "home.noResults": "Aucune annonce ne correspond à vos filtres.",
  "home.showing": "Affichage de",
  "home.to": "à",
  "home.of": "sur",
  "home.listings": "annonces",
  "home.prevPage": "Page précédente",
  "home.nextPage": "Page suivante",

  // Filter bar
  "filter.search":
    "Rechercher par mot-clé (ex: piscine, vue mer, villa, Lac 2...)",
  "filter.filters": "Filtres",
  "filter.reset": "Réinitialiser",
  "filter.governorate": "Gouvernorat",
  "filter.category": "Catégorie",
  "filter.all": "Tous",
  "filter.allF": "Toutes",
  "filter.transaction": "Transaction",
  "filter.minPrice": "Prix Min (DT)",
  "filter.maxPrice": "Prix Max (DT)",
  "filter.minArea": "Surface Min (m²)",
  "filter.maxArea": "Surface Max (m²)",
  "filter.bedroomsMin": "Chambres (min)",

  // Property categories / listing types
  "cat.apartment": "Appartement",
  "cat.house": "Maison / Villa",
  "cat.office": "Bureau / Commerce",
  "cat.studio": "Studio / Chambre",
  "cat.land": "Terrain",
  "cat.houseOrApartment": "Maison / Appartement",
  "listing.sale": "À vendre",
  "listing.rent": "À louer",
  "common.yes": "Oui",
  "common.no": "Non",
  "format.priceOnRequest": "Prix sur demande",

  // Property card
  "card.viewDetails": "Voir détails",
  "card.bedroomsAbbr": "ch.",

  // Property page
  "prop.back": "Retour",
  "prop.loading": "Chargement de l'annonce...",
  "prop.notFound": "Annonce introuvable",
  "prop.noImage": "Aucune image disponible",
  "prop.prevImage": "Image précédente",
  "prop.nextImage": "Image suivante",
  "prop.location": "Localisation",
  "prop.area": "Surface",
  "prop.source": "Source",
  "prop.type": "Type",
  "prop.transaction": "Transaction",
  "prop.bedrooms": "Chambres",
  "prop.garage": "Garage",
  "prop.furnished": "Meublé",
  "prop.terrace": "Terrasse / Balcon",
  "prop.pool": "Piscine",
  "prop.description": "Description",
  "prop.viewOn": "Voir sur",
  "prop.simulate": "Simuler un crédit",
  "prop.addFavorite": "Ajouter aux favoris",
  "prop.removeFavorite": "Retirer des favoris",

  // Favorites page
  "favorites.eyebrow": "Vos annonces enregistrées",
  "favorites.title": "Mes favoris",
  "favorites.subtitle":
    "Retrouvez ici toutes les annonces que vous avez enregistrées.",
  "favorites.loading": "Chargement de vos favoris...",
  "favorites.loadError": "Impossible de charger vos favoris.",
  "favorites.empty":
    "Vous n'avez pas encore de favoris. Ouvrez une annonce et cliquez sur le cœur pour l'enregistrer ici.",
  "favorites.browse": "Parcourir les annonces",
  "favorites.count.one": "favori",
  "favorites.count.many": "favoris",

  // AI estimate card
  "est.title": "Estimation IA",
  "est.salePrice": "Prix théorique estimé",
  "est.rentPrice": "Loyer théorique estimé",
  "est.perMonth": "/ mois",
  "est.asking": "Prix affiché",
  "est.vsEstimate": "par rapport à l'estimation",
  "est.score": "Score d'investissement",
  "est.good": "Bonne opportunité",
  "est.fair": "Prix conforme au marché",
  "est.high": "Au-dessus du prix du marché",
  "est.disclaimer":
    "Estimation calculée par un modèle entraîné sur les annonces collectées (localisation, surface, type de bien, équipements). Indicative, ne remplace pas une expertise.",

  // Credit simulator
  "sim.title": "Simulateur de crédit",
  "sim.close": "Fermer",
  "sim.price": "Prix du bien (TND)",
  "sim.down": "Apport personnel (TND)",
  "sim.years": "Durée du prêt (années)",
  "sim.income": "Revenu mensuel net (TND)",
  "sim.requiredPh": "Requis pour la simulation",
  "sim.fillIn":
    "Veuillez renseigner l'apport personnel, la durée du prêt et votre revenu mensuel net pour lancer la simulation.",
  "sim.monthly": "Mensualité estimée",
  "sim.perMonth": "/ mois",
  "sim.loanAmount": "Montant emprunté",
  "sim.totalInterest": "Coût total du crédit",
  "sim.totalPaid": "Total remboursé",
  "sim.dti": "Taux d'endettement",
  "sim.dtiHigh": " — largement au-dessus du seuil recommandé (35%)",
  "sim.dtiAbove": " — au-dessus du seuil recommandé (35%)",
  "sim.dtiOk": " — dans la limite recommandée",
  "sim.capacity": "Capacité d'achat estimée",
  "sim.capacityNote1": "Basée sur une mensualité maximale recommandée de",
  "sim.capacityNote2": "(35% de votre revenu), apport personnel inclus.",
  "sim.exceeds": "Ce bien dépasse votre capacité d'achat de",
  "sim.searching": "Recherche de biens plus adaptés à votre budget…",
  "sim.alternatives": "Alternatives dans votre budget",
  "sim.noAlternatives":
    "Aucun bien similaire trouvé dans votre budget pour le moment.",
  "sim.disclaimer":
    "Estimation indicative, hors assurance et frais de dossier. Ne constitue pas une offre de prêt.",

  // Agent chat widget
  "chat.title": "Assistant Rews",
  "chat.aboutListing": "À propos de cette annonce",
  "chat.close": "Fermer",
  "chat.loginPrompt": "Connectez-vous pour discuter avec l'assistant Rews.",
  "chat.login": "Se connecter",
  "chat.emptyHint":
    "Posez une question sur l'immobilier en Tunisie, ou sur cette annonce.",
  "chat.sessionExpired": "Session expirée.",
  "chat.reconnect": "Reconnectez-vous",
  "chat.toContinue": "pour continuer.",
  "chat.placeholder": "Écrire un message...",
  "chat.historyError": "Impossible de charger l'historique.",
  "chat.replyError": "L'assistant n'a pas pu répondre.",
  "chat.send": "Envoyer",
  "chat.open": "Assistant Rews",

  // Dashboard (admin)
  "dashboard.authRequired": "Authentification requise",
  "dashboard.authSubtitle":
    "Veuillez vous connecter pour accéder au dashboard.",
  "dashboard.passwordPlaceholder": "Mot de passe",
  "dashboard.verifying": "Vérification…",
  "dashboard.signIn": "Se connecter",
  "dashboard.wrongPassword": "Mot de passe incorrect. Veuillez réessayer.",
  "dashboard.administration": "Administration",
  "dashboard.title": "Dashboard",
  "dashboard.online": "En ligne",
  "dashboard.offline": "Hors ligne",
  "dashboard.database": "Base de données",
  "dashboard.connected": "Connectée",
  "dashboard.unavailable": "Indisponible",
  "dashboard.totalAds": "Annonces en base",
  "dashboard.archivedAds": "Annonces archivées",
  "dashboard.users": "Utilisateurs inscrits",
  "dashboard.activeSources": "Sources actives",
  "dashboard.propsByType": "Propriétés par type",
  "dashboard.adsBySource": "Annonces par source",
  "dashboard.typeHouse": "Maison",
  "dashboard.typeLand": "Terrain",
  "dashboard.typeApartment": "Appartement",
  "dashboard.typeStudio": "Studio",
  "dashboard.typeOffice": "Bureau",
  "dashboard.noData": "Aucune donnée disponible",
  "dashboard.totalLabel": "Total",
  "dashboard.otherLabel": "Autres",
  "dashboard.dailyTraffic": "Trafic quotidien",
  "dashboard.views": "vues",
  "dashboard.visitors": "visiteurs sur la période",
  "dashboard.trafficEmpty":
    "Aucune visite enregistrée pour l'instant. Le graphique se remplit dès que le site reçoit du trafic.",
  "dashboard.overview": "Vue d'ensemble",
  "dashboard.adsManagement": "Gestion des annonces",
  "dashboard.searchPlaceholder": "Rechercher (nom, localisation, source...)",
  "dashboard.all": "Toutes",
  "dashboard.archivedOnly": "Archivées uniquement",
  "dashboard.governorate": "Gouvernorat",
  "dashboard.category": "Catégorie",
  "dashboard.transaction": "Transaction",
  "dashboard.priceMin": "Prix Min (DT)",
  "dashboard.priceMax": "Prix Max (DT)",
  "dashboard.areaMin": "Surface Min (m²)",
  "dashboard.areaMax": "Surface Max (m²)",
  "dashboard.bedroomsMin": "Chambres (min)",
  "dashboard.filterAllM": "Tous",
  "dashboard.filterAllF": "Toutes",
  "dashboard.catApartment": "Appartement",
  "dashboard.catHouse": "Maison / Villa",
  "dashboard.catOffice": "Bureau / Commerce",
  "dashboard.catStudio": "Studio / Chambre",
  "dashboard.catLand": "Terrain",
  "dashboard.forSale": "À vendre",
  "dashboard.forRent": "À louer",
  "dashboard.resetFilters": "Réinitialiser les filtres",
  "dashboard.colName": "Nom",
  "dashboard.colLocation": "Localisation",
  "dashboard.colCategory": "Catégorie",
  "dashboard.colTransaction": "Transaction",
  "dashboard.colPrice": "Prix",
  "dashboard.colArea": "Surface",
  "dashboard.colBedrooms": "Chambres",
  "dashboard.colSource": "Source",
  "dashboard.colArchived": "Archivé",
  "dashboard.archiveAd": "Archiver l'annonce",
  "dashboard.restoreAd": "Restaurer l'annonce",
  "dashboard.dtProcessing": "Chargement…",
  "dashboard.dtLengthMenu": "Afficher _MENU_ lignes",
  "dashboard.dtInfo": "_START_ à _END_ sur _TOTAL_ lignes",
  "dashboard.dtInfoEmpty": "Aucune ligne à afficher",
  "dashboard.dtInfoFiltered": "(filtré depuis _MAX_ lignes)",
  "dashboard.dtZeroRecords": "Aucune annonce trouvée",
  "dashboard.dtFirst": "Premier",
  "dashboard.dtLast": "Dernier",
  "dashboard.dtNext": "Suivant",
  "dashboard.dtPrevious": "Précédent",
  "dashboard.runScrapeTitle": "Lancer un scrape",
  "dashboard.autoScrape": "Scrape automatique",
  "dashboard.everyMonday": "Chaque lundi à 00h00",
  "dashboard.nextAutoScrape": "Prochain scrape automatique dans",
  "dashboard.calculating": "Calcul en cours…",
  "dashboard.starting": "Démarrage…",
  "dashboard.scrapingInProgress": "Scrape en cours…",
  "dashboard.retraining": "Ré-entraînement du modèle…",
  "dashboard.startScrape": "Démarrer le scrape",
  "dashboard.stopping": "Arrêt en cours…",
  "dashboard.stopScrape": "Arrêter le scrape",
  "dashboard.startFailed": "Échec du démarrage du scrape",
  "dashboard.cancelFailed": "Échec de l'annulation du scrape",
  "dashboard.scrapeCancelledMsg":
    "Scrape arrêté — les annonces déjà insérées avant l'arrêt ont été conservées en base.",
  "dashboard.scrapeProgress": "Progression du scrape",
  "dashboard.sourcesCompleted": "Sources complétées",
  "dashboard.phase": "Phase",
  "dashboard.done": "Terminé",
  "dashboard.error": "Erreur",
  "dashboard.cancelled": "Annulé",
  "dashboard.pending": "En attente",
  "dashboard.running": "en cours…",
  "dashboard.phaseRent": "Location",
  "dashboard.phaseSale": "Vente",
  "dashboard.phaseLand": "Terrains",
  "dashboard.stepListing": "Collecte des pages",
  "dashboard.stepEnriching": "Détails des annonces",
  "dashboard.stepInserting": "Insertion en base",
  "dashboard.completedIn": "Terminé en {n} secondes.",
  "dashboard.found": "Trouvées",
  "dashboard.inserted": "Insérées",
  "dashboard.alreadyInDb": "Déjà en base",
  "dashboard.errors": "Erreurs",
  "dashboard.archived": "Archivées",
  "dashboard.total": "Total",
  "dashboard.pagesSuffix": "pages",
  "dashboard.alreadyInDbNote":
    "« Déjà en base » = annonce déjà enregistrée (même source + id). Les doublons entre vente et location sont filtrés avant l'insertion.",
};

const en: Record<string, string> = {
  // Generic fallbacks
  "common.loading": "Loading...",

  // Header / nav
  "nav.home": "Home",
  "nav.listings": "Listings",
  "nav.favorites": "Favorites",
  "nav.dashboard": "Dashboard",
  "nav.login": "Log in",
  "nav.logout": "Log out",
  "nav.menu": "Main menu",
  "nav.openMenu": "Open menu",
  "nav.closeMenu": "Close menu",
  "nav.darkMode": "Dark mode",
  "nav.lightMode": "Light mode",
  "footer.tagline": "Rews — Tunisia real estate aggregator",

  // Welcome page
  "welcome.badge": "Smart real estate platform · Tunisia",
  "welcome.titlePrefix": "Find the perfect property with",
  "welcome.subtitle":
    "Rews is a real estate monitoring platform that aggregates thousands of listings across Tunisia, estimates fair prices with AI and helps you make the right buying or renting decision.",
  "welcome.explore": "Browse listings",
  "welcome.login": "Log in",
  "welcome.f1.title": "Multi-source aggregation",
  "welcome.f1.text":
    "Listings from Tayara and Mubawab gathered and deduplicated in one place.",
  "welcome.f2.title": "AI price estimates",
  "welcome.f2.text":
    "A theoretical price and an investment score computed for every property.",
  "welcome.f3.title": "Smart assistant",
  "welcome.f3.text":
    "Ask questions in natural language and let the agent search for you.",
  "welcome.f4.title": "Credit simulator",
  "welcome.f4.text":
    "Purchasing capacity, monthly payments and alternatives that fit your budget.",

  // Login page
  "login.title": "Log in",
  "login.titleRegister": "Create an account",
  "login.subtitle": "Log in to chat with the assistant",
  "login.subtitleRegister": "Create an account to get started",
  "login.username": "Username",
  "login.usernamePlaceholder": "your_name",
  "login.password": "Password",
  "login.submit": "Log in",
  "login.submitRegister": "Create an account",
  "login.loading": "Loading...",
  "login.or": "or",
  "login.toggleToRegister": "No account yet? Create one",
  "login.toggleToLogin": "Already have an account? Log in",
  "login.backHome": "← Back to home",
  "login.email": "Email",
  "login.emailPlaceholder": "you@example.com",

  "verify.title": "Verify your email",
  "verify.subtitle": "Enter the 6-digit code sent to",
  "verify.codeLabel": "Verification code",
  "verify.submit": "Verify and continue",
  "verify.resend": "Resend code",
  "verify.back": "← Back",
  "verify.sent": "A verification code has been sent to your email address.",
  "verify.resent": "A new code has been sent.",

  // Auth / network errors
  "error.badCredentials": "Incorrect email or password.",
  "error.emailExists": "This email is already registered. Please log in.",
  "error.emailInvalid": "Please enter a valid email address.",
  "error.emailNotVerified":
    "Email not verified. A new code has been sent to you.",
  "error.codeInvalid": "Incorrect or expired code. Try again or resend a code.",
  "error.emailSendFailed":
    "Could not send the verification email. Please try again.",
  "error.rateLimited": "Too many attempts. Please wait a minute and try again.",
  "error.usernameTaken":
    "This username is already taken. Pick another one or log in.",
  "error.usernameShort": "The username must be at least 3 characters long.",
  "error.passwordShort": "The password must be at least 8 characters long.",
  "error.timeout":
    "The server is taking too long to respond. Please try again.",
  "error.network": "Could not reach the server. Check your connection.",
  "error.generic": "Something went wrong. Please try again.",
  "error.google": "Google sign-in failed.",

  // Listings page
  "home.catalog": "Catalog",
  "home.title": "Find your property",
  "home.subtitle":
    "Real estate listings aggregated from Tayara and Mubawab — houses, apartments and land across Tunisia.",
  "home.found.one": "listing found",
  "home.found.many": "listings found",
  "home.loading": "Loading listings...",
  "home.loadError": "Failed to load",
  "home.retry": "Retry",
  "home.noResults": "No listings match your filters.",
  "home.showing": "Showing",
  "home.to": "to",
  "home.of": "of",
  "home.listings": "listings",
  "home.prevPage": "Previous page",
  "home.nextPage": "Next page",

  // Filter bar
  "filter.search": "Search by keyword (e.g. pool, sea view, villa, Lac 2...)",
  "filter.filters": "Filters",
  "filter.reset": "Reset",
  "filter.governorate": "Governorate",
  "filter.category": "Category",
  "filter.all": "All",
  "filter.allF": "All",
  "filter.transaction": "Transaction",
  "filter.minPrice": "Min price (TND)",
  "filter.maxPrice": "Max price (TND)",
  "filter.minArea": "Min area (m²)",
  "filter.maxArea": "Max area (m²)",
  "filter.bedroomsMin": "Bedrooms (min)",

  // Property categories / listing types
  "cat.apartment": "Apartment",
  "cat.house": "House / Villa",
  "cat.office": "Office / Commercial",
  "cat.studio": "Studio / Room",
  "cat.land": "Land",
  "cat.houseOrApartment": "House / Apartment",
  "listing.sale": "For sale",
  "listing.rent": "For rent",
  "common.yes": "Yes",
  "common.no": "No",
  "format.priceOnRequest": "Price on request",

  // Property card
  "card.viewDetails": "View details",
  "card.bedroomsAbbr": "bd",

  // Property page
  "prop.back": "Back",
  "prop.loading": "Loading listing...",
  "prop.notFound": "Listing not found",
  "prop.noImage": "No image available",
  "prop.prevImage": "Previous image",
  "prop.nextImage": "Next image",
  "prop.location": "Location",
  "prop.area": "Area",
  "prop.source": "Source",
  "prop.type": "Type",
  "prop.transaction": "Transaction",
  "prop.bedrooms": "Bedrooms",
  "prop.garage": "Garage",
  "prop.furnished": "Furnished",
  "prop.terrace": "Terrace / Balcony",
  "prop.pool": "Pool",
  "prop.description": "Description",
  "prop.viewOn": "View on",
  "prop.simulate": "Simulate a loan",
  "prop.addFavorite": "Add to favorites",
  "prop.removeFavorite": "Remove from favorites",

  // Favorites page
  "favorites.eyebrow": "Your saved listings",
  "favorites.title": "My favorites",
  "favorites.subtitle": "All the listings you've saved, in one place.",
  "favorites.loading": "Loading your favorites...",
  "favorites.loadError": "Couldn't load your favorites.",
  "favorites.empty":
    "You haven't saved any favorites yet. Open a listing and tap the heart to save it here.",
  "favorites.browse": "Browse listings",
  "favorites.count.one": "favorite",
  "favorites.count.many": "favorites",

  // AI estimate card
  "est.title": "AI estimate",
  "est.salePrice": "Estimated market price",
  "est.rentPrice": "Estimated market rent",
  "est.perMonth": "/ month",
  "est.asking": "Asking price",
  "est.vsEstimate": "vs. the estimate",
  "est.score": "Investment score",
  "est.good": "Good opportunity",
  "est.fair": "In line with the market",
  "est.high": "Above market price",
  "est.disclaimer":
    "Estimate computed by a model trained on the collected listings (location, area, property type, amenities). Indicative only — not a substitute for a professional appraisal.",

  // Credit simulator
  "sim.title": "Credit simulator",
  "sim.close": "Close",
  "sim.price": "Property price (TND)",
  "sim.down": "Down payment (TND)",
  "sim.years": "Loan term (years)",
  "sim.income": "Net monthly income (TND)",
  "sim.requiredPh": "Required for the simulation",
  "sim.fillIn":
    "Please fill in the down payment, the loan term and your net monthly income to run the simulation.",
  "sim.monthly": "Estimated monthly payment",
  "sim.perMonth": "/ month",
  "sim.loanAmount": "Amount borrowed",
  "sim.totalInterest": "Total cost of credit",
  "sim.totalPaid": "Total repaid",
  "sim.dti": "Debt-to-income ratio",
  "sim.dtiHigh": " — well above the recommended threshold (35%)",
  "sim.dtiAbove": " — above the recommended threshold (35%)",
  "sim.dtiOk": " — within the recommended limit",
  "sim.capacity": "Estimated purchasing capacity",
  "sim.capacityNote1": "Based on a maximum recommended monthly payment of",
  "sim.capacityNote2": "(35% of your income), down payment included.",
  "sim.exceeds": "This property exceeds your purchasing capacity by",
  "sim.searching": "Searching for properties better suited to your budget…",
  "sim.alternatives": "Alternatives within your budget",
  "sim.noAlternatives":
    "No similar property found within your budget at the moment.",
  "sim.disclaimer":
    "Indicative estimate, excluding insurance and processing fees. This is not a loan offer.",

  // Agent chat widget
  "chat.title": "Rews Assistant",
  "chat.aboutListing": "About this listing",
  "chat.close": "Close",
  "chat.loginPrompt": "Log in to chat with the Rews assistant.",
  "chat.login": "Log in",
  "chat.emptyHint":
    "Ask a question about real estate in Tunisia, or about this listing.",
  "chat.sessionExpired": "Session expired.",
  "chat.reconnect": "Log back in",
  "chat.toContinue": "to continue.",
  "chat.placeholder": "Type a message...",
  "chat.historyError": "Couldn't load the conversation history.",
  "chat.replyError": "The assistant couldn't reply.",
  "chat.send": "Send",
  "chat.open": "Rews Assistant",

  // Dashboard (admin)
  "dashboard.authRequired": "Authentication required",
  "dashboard.authSubtitle": "Please log in to access the dashboard.",
  "dashboard.passwordPlaceholder": "Password",
  "dashboard.verifying": "Verifying…",
  "dashboard.signIn": "Log in",
  "dashboard.wrongPassword": "Incorrect password. Please try again.",
  "dashboard.administration": "Administration",
  "dashboard.title": "Dashboard",
  "dashboard.online": "Online",
  "dashboard.offline": "Offline",
  "dashboard.database": "Database",
  "dashboard.connected": "Connected",
  "dashboard.unavailable": "Unavailable",
  "dashboard.totalAds": "Ads in database",
  "dashboard.archivedAds": "Archived ads",
  "dashboard.users": "Registered users",
  "dashboard.activeSources": "Active sources",
  "dashboard.propsByType": "Properties by type",
  "dashboard.adsBySource": "Ads by source",
  "dashboard.typeHouse": "House",
  "dashboard.typeLand": "Land",
  "dashboard.typeApartment": "Apartment",
  "dashboard.typeStudio": "Studio",
  "dashboard.typeOffice": "Office",
  "dashboard.noData": "No data available",
  "dashboard.totalLabel": "Total",
  "dashboard.otherLabel": "Other",
  "dashboard.dailyTraffic": "Daily traffic",
  "dashboard.views": "views",
  "dashboard.visitors": "visitors over the period",
  "dashboard.trafficEmpty":
    "No visits recorded yet. The chart fills in as soon as the site receives traffic.",
  "dashboard.overview": "Overview",
  "dashboard.adsManagement": "Ad management",
  "dashboard.searchPlaceholder": "Search (name, location, source...)",
  "dashboard.all": "All",
  "dashboard.archivedOnly": "Archived only",
  "dashboard.governorate": "Governorate",
  "dashboard.category": "Category",
  "dashboard.transaction": "Transaction",
  "dashboard.priceMin": "Min price (DT)",
  "dashboard.priceMax": "Max price (DT)",
  "dashboard.areaMin": "Min area (m²)",
  "dashboard.areaMax": "Max area (m²)",
  "dashboard.bedroomsMin": "Bedrooms (min)",
  "dashboard.filterAllM": "All",
  "dashboard.filterAllF": "All",
  "dashboard.catApartment": "Apartment",
  "dashboard.catHouse": "House / Villa",
  "dashboard.catOffice": "Office / Retail",
  "dashboard.catStudio": "Studio / Room",
  "dashboard.catLand": "Land",
  "dashboard.forSale": "For sale",
  "dashboard.forRent": "For rent",
  "dashboard.resetFilters": "Reset filters",
  "dashboard.colName": "Name",
  "dashboard.colLocation": "Location",
  "dashboard.colCategory": "Category",
  "dashboard.colTransaction": "Transaction",
  "dashboard.colPrice": "Price",
  "dashboard.colArea": "Area",
  "dashboard.colBedrooms": "Bedrooms",
  "dashboard.colSource": "Source",
  "dashboard.colArchived": "Archived",
  "dashboard.archiveAd": "Archive the ad",
  "dashboard.restoreAd": "Restore the ad",
  "dashboard.dtProcessing": "Loading…",
  "dashboard.dtLengthMenu": "Show _MENU_ rows",
  "dashboard.dtInfo": "_START_ to _END_ of _TOTAL_ rows",
  "dashboard.dtInfoEmpty": "No rows to display",
  "dashboard.dtInfoFiltered": "(filtered from _MAX_ rows)",
  "dashboard.dtZeroRecords": "No ads found",
  "dashboard.dtFirst": "First",
  "dashboard.dtLast": "Last",
  "dashboard.dtNext": "Next",
  "dashboard.dtPrevious": "Previous",
  "dashboard.runScrapeTitle": "Run a scrape",
  "dashboard.autoScrape": "Automatic scrape",
  "dashboard.everyMonday": "Every Monday at 00:00",
  "dashboard.nextAutoScrape": "Next automatic scrape in",
  "dashboard.calculating": "Calculating…",
  "dashboard.starting": "Starting…",
  "dashboard.scrapingInProgress": "Scraping…",
  "dashboard.retraining": "Retraining the model…",
  "dashboard.startScrape": "Start the scrape",
  "dashboard.stopping": "Stopping…",
  "dashboard.stopScrape": "Stop the scrape",
  "dashboard.startFailed": "Failed to start the scrape",
  "dashboard.cancelFailed": "Failed to cancel the scrape",
  "dashboard.scrapeCancelledMsg":
    "Scrape stopped — ads already inserted before the stop were kept in the database.",
  "dashboard.scrapeProgress": "Scrape progress",
  "dashboard.sourcesCompleted": "Sources completed",
  "dashboard.phase": "Phase",
  "dashboard.done": "Done",
  "dashboard.error": "Error",
  "dashboard.cancelled": "Cancelled",
  "dashboard.pending": "Pending",
  "dashboard.running": "running…",
  "dashboard.phaseRent": "Rent",
  "dashboard.phaseSale": "Sale",
  "dashboard.phaseLand": "Land",
  "dashboard.stepListing": "Collecting pages",
  "dashboard.stepEnriching": "Ad details",
  "dashboard.stepInserting": "Inserting into database",
  "dashboard.completedIn": "Completed in {n} seconds.",
  "dashboard.found": "Found",
  "dashboard.inserted": "Inserted",
  "dashboard.alreadyInDb": "Already in DB",
  "dashboard.errors": "Errors",
  "dashboard.archived": "Archived",
  "dashboard.total": "Total",
  "dashboard.pagesSuffix": "pages",
  "dashboard.alreadyInDbNote":
    "“Already in DB” = ad already stored (same source + id). Duplicates between sale and rent are filtered out before insertion.",
};

const dicts: Record<Lang, Record<string, string>> = { fr, en };

/** Translate a key in the current language, falling back to French, then to
 * the key itself so a missing entry stays visible instead of blanking out. */
export function t(key: string): string {
  return dicts[currentLang][key] ?? fr[key] ?? key;
}

export function getLang(): Lang {
  return currentLang;
}

const LangContext = createContext<{
  lang: Lang;
  setLang: (lang: Lang) => void;
}>({
  lang: currentLang,
  setLang: () => {},
});

export function LanguageProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Lang>(currentLang);

  const setLang = (next: Lang) => {
    currentLang = next;
    try {
      localStorage.setItem(STORAGE_KEY, next);
    } catch {
      /* private mode: the choice just won't persist */
    }
    document.documentElement.lang = next;
    setLangState(next);
  };

  useEffect(() => {
    document.documentElement.lang = lang;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <LangContext.Provider value={{ lang, setLang }}>
      {children}
    </LangContext.Provider>
  );
}

/** Subscribe a component to the current language. Components must use this
 * hook (not the bare `t` import) so they re-render on language change. */
export function useLang() {
  const { lang, setLang } = useContext(LangContext);
  return { lang, setLang, t };
}

"""Etiquetas por ID de liga (API-Football) — compartido por bot y análisis central."""

# Nombres cortos para calibración / API (sin emoji)
LEAGUE_NAMES = {
    # Américas (foco por defecto)
    265: "Primera División Chile",
    71: "Brasileirão Serie A",
    262: "Liga MX",
    253: "MLS",
    128: "Liga Profesional Argentina",
    239: "Primera A Colombia",
    281: "Liga 1 Perú",
    242: "Liga Pro Ecuador",
    # Europa y otras
    39: "Premier League",
    140: "La Liga",
    135: "Serie A",
    78: "Bundesliga",
    61: "Ligue 1",
    2: "Champions League",
    3: "Europa League",
    94: "Primeira Liga",
    88: "Eredivisie",
    203: "Super Lig",
    307: "Saudi Pro League",
}

LEAGUES_DISPLAY = {
    265: "🇨🇱 Primera Chile",
    71:  "🇧🇷 Brasileirão",
    262: "🇲🇽 Liga MX",
    253: "🇺🇸 MLS",
    128: "🇦🇷 Liga Argentina",
    239: "🇨🇴 Primera Colombia",
    281: "🇵🇪 Liga 1",
    242: "🇪🇨 Liga Pro",
    39:  "🏴 Premier League",
    140: "🇪🇸 La Liga",
    135: "🇮🇹 Serie A",
    78:  "🇩🇪 Bundesliga",
    61:  "🇫🇷 Ligue 1",
    2:   "🏆 Champions League",
    3:   "🏆 Europa League",
    94:  "🇵🇹 Primeira Liga",
    88:  "🇳🇱 Eredivisie",
    203: "🇹🇷 Süper Lig",
    307: "🇸🇦 Saudi Pro League",
}


def league_display_name(league_id: int) -> str:
    """Nombre legible; si el ID no está mapeado, muestra el número."""
    plain = LEAGUE_NAMES.get(league_id)
    if plain:
        return plain
    return f"Liga {league_id}"

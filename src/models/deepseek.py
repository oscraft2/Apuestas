"""
CAPA 5: DeepSeek IA — Razonamiento cualitativo
Compatible con formato OpenAI. Costo ~$0.01/partido.
"""
import json
import logging
import httpx
from config import config

logger = logging.getLogger(__name__)


class DeepSeekReasoner:
    API_URL = "https://api.deepseek.com/chat/completions"

    def __init__(self, api_key: str = None):
        self.api_key = api_key or config.deepseek_api_key
        self.enabled = bool(self.api_key)

    async def analyze(
        self,
        home: str,
        away: str,
        league: str,
        stats: dict,
        features: dict = None,
    ) -> dict | None:
        if not self.enabled:
            return None

        feat_str = ""
        if features:
            feat_str = (
                f"Forma local: {features.get('home_form', '?'):.2f}, "
                f"Forma visita: {features.get('away_form', '?'):.2f}, "
                f"Racha local: {features.get('home_streak', {}).get('type', '?')} "
                f"x{features.get('home_streak', {}).get('len', 0)}"
            )

        prompt = f"""Analiza este partido de fútbol. Responde SOLO JSON válido, sin markdown.

PARTIDO: {home} vs {away} ({league})

DATOS:
- Prob. mercado 1X2: L={stats.get('mkt_h', 0):.1%}, E={stats.get('mkt_d', 0):.1%}, V={stats.get('mkt_a', 0):.1%}
- Prob. Poisson 1X2: L={stats.get('poi_h', 0):.1%}, E={stats.get('poi_d', 0):.1%}, V={stats.get('poi_a', 0):.1%}
- xG: Local={stats.get('xg_h', 0):.2f}, Visita={stats.get('xg_a', 0):.2f}
- Over 2.5 prob: {stats.get('over25', 0):.1%}
- {feat_str}

Responde con este JSON exacto:
{{"reasoning":"análisis breve máx 100 palabras","confidence":0.7,"lean":"home","key_factors":["factor1","factor2"],"risk":"medium","adj_1x2":{{"home":0.0,"draw":0.0,"away":0.0}},"adj_ou":{{"over":0.0,"under":0.0}}}}

Los adj son ajustes de -0.05 a +0.05 a las probabilidades del consenso."""

        try:
            async with httpx.AsyncClient(timeout=25) as http:
                resp = await http.post(
                    self.API_URL,
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {self.api_key}",
                    },
                    json={
                        "model": config.deepseek_model,
                        "messages": [
                            {
                                "role": "system",
                                "content": (
                                    "Eres un analista deportivo experto. "
                                    "Respondes SOLO en JSON válido. "
                                    "Analiza factores cualitativos: lesiones, "
                                    "motivación, contexto de temporada."
                                ),
                            },
                            {"role": "user", "content": prompt},
                        ],
                        "max_tokens": 500,
                        "temperature": 0.3,
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                text = data["choices"][0]["message"]["content"].strip()
                if text.startswith("```"):
                    text = text.split("```")[1]
                    if text.startswith("json"):
                        text = text[4:]
                    text = text.strip()
                return json.loads(text)
        except json.JSONDecodeError as e:
            logger.warning(f"DeepSeek JSON parse error: {e}")
            return None
        except Exception as e:
            logger.warning(f"DeepSeek error: {e}")
            return None

"""
CAPA 5: DeepSeek IA — Razonamiento cualitativo
Compatible con formato OpenAI. Costo ~$0.01/partido.
"""
import json
import re
import logging
from typing import Optional
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
    ) -> Optional[dict]:   # Bug #26: usar Optional[dict] en vez de dict | None (compatible Python 3.9+)
        if not self.enabled:
            return None

        # Bug #22: usar valores numéricos con default 0 para evitar TypeError en format spec
        feat_str = ""
        if features:
            home_form = features.get("home_form", 0)
            away_form = features.get("away_form", 0)
            streak = features.get("home_streak", {})
            feat_str = (
                f"Forma local: {home_form:.2f}, "
                f"Forma visita: {away_form:.2f}, "
                f"Racha local: {streak.get('type', 'N/A')} x{streak.get('len', 0)}"
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
                                    "Respondes SOLO en JSON válido, sin texto adicional. "
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

                # Bug #37: parsing robusto con regex en lugar de split frágil
                json_text = self._extract_json(text)
                if json_text is None:
                    logger.warning("DeepSeek: no se encontró JSON válido en la respuesta")
                    return None
                return json.loads(json_text)

        except json.JSONDecodeError as e:
            logger.warning(f"DeepSeek JSON parse error: {e}")
            return None
        except Exception as e:
            logger.warning(f"DeepSeek error: {e}")
            return None

    @staticmethod
    def _extract_json(text: str) -> Optional[str]:
        """Extrae el primer objeto JSON válido del texto de forma robusta."""
        # 1. Intentar directo
        text = text.strip()
        if text.startswith("{"):
            return text

        # 2. Buscar bloque ```json ... ```
        m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
        if m:
            return m.group(1)

        # 3. Buscar cualquier { ... } en el texto
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            return m.group(0)

        return None

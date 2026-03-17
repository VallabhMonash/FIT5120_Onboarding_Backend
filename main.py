import os
from typing import Any

import psycopg2
import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from psycopg2 import Error as PsycopgError
from psycopg2.extras import RealDictCursor

load_dotenv()

app = FastAPI(title="FIT5120 UV Backend", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "https://vallabhmonash.github.io",
        "https://vallabhmonash.github.io/FIT5120_Onboarding_Frontend/",
        "https://www.sunsafecamp.live/"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_conn():
    return psycopg2.connect(
        host=os.getenv("PGHOST"),
        dbname=os.getenv("PGDATABASE"),
        user=os.getenv("PGUSER"),
        password=os.getenv("PGPASSWORD"),
        sslmode=os.getenv("PGSSLMODE", "require"),
        channel_binding=os.getenv("PGCHANNELBINDING", "require"),
    )


def run_query(sql: str, params: tuple[Any, ...] = ()) -> list[dict]:
    try:
        with get_conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(sql, params)
                rows = cur.fetchall()
                return [dict(r) for r in rows]
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/api/v1/viz/skin-cancer-trend")
def get_skin_cancer_trend():
    sql = """
        select year, cases, deaths
        from viz_skin_cancer_trend
        order by year;
    """
    return run_query(sql)


@app.get("/api/v1/viz/heat-trend-series")
def get_heat_trend_series():
    sql = """
        select year, region, avg_uv
        from viz_heat_trend_series
        order by region, year;
    """
    return run_query(sql)


@app.get("/api/v1/content/myth-cards")
def get_myth_cards():
    sql = """
        select
            myth_id as id,
            title,
            myth_text,
            explanation as explanation
        from myth_card
        order by myth_id;
    """
    return run_query(sql)


@app.get("/api/v1/content/skin-tones")
def get_skin_tones():
    sql = """
        select
            skin_tone_id as id,
            skin_tone,
            risk_level,
            explanation as description,
            protection_advice as recommendation
        from skin_tone
        order by skin_tone_id;
    """
    return run_query(sql)


# Optional: real UV by coordinates (OpenWeather One Call 3.0)
@app.get("/api/v1/uv/by-coordinates")
async def get_uv_by_coordinates(
    lat: float = Query(...),
    lon: float = Query(...),
):
    api_key = os.getenv("OPENWEATHER_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="OPENWEATHER_API_KEY is not configured.")

    url = "https://api.openweathermap.org/data/3.0/onecall"
    params = {
        "lat": lat,
        "lon": lon,
        "exclude": "minutely,hourly,daily,alerts",
        "appid": api_key,
    }

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(url, params=params)
        if resp.status_code != 200:
            raise HTTPException(status_code=resp.status_code, detail=f"OpenWeather error: {resp.text}")

        payload = resp.json()
        current = payload.get("current", {})
        uv_index = current.get("uvi")

        if uv_index is None:
            raise HTTPException(status_code=502, detail="UV index not found in upstream response.")

        return {"uv_index": uv_index, "lat": lat, "lon": lon}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


# Global handlers
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": True,
            "type": "http_error",
            "message": exc.detail,
            "path": str(request.url.path),
        },
    )


@app.exception_handler(PsycopgError)
async def db_exception_handler(request: Request, exc: PsycopgError):
    return JSONResponse(
        status_code=500,
        content={
            "error": True,
            "type": "database_error",
            "message": "Database operation failed.",
            "path": str(request.url.path),
        },
    )


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={
            "error": True,
            "type": "internal_error",
            "message": "Unexpected server error.",
            "path": str(request.url.path),
        },
    )


@app.get("/api/v1/errors/test")
def test_error():
    raise RuntimeError("Intentional test error")

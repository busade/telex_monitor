from fastapi import FastAPI, BackgroundTasks, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Dict
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.sql import text
import asyncio, json, httpx, os, asyncpg, time, logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class Setting(BaseModel):
    label: str
    type: str
    required: bool
    default: str

class MonitorPayLoad(BaseModel):
    channel_id: str
    return_url: str
    settings: List[Setting]

    def get_setting(self, label: str, default=None):
        """Helper function to extract a setting by label."""
        for setting in self.settings:
            if setting.label == label:
                return setting.default
        return default

app = FastAPI()

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],  
    allow_headers=["*"],
)

def get_db_engine(database_url: str):
    """Reusable function to get async database engine."""
    if database_url.startswith("postgresql://"):
       database_url = database_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    
    return create_async_engine(database_url, echo=True)

@app.get('/integration')
def get_integration_json(request: Request):
    base_url = str(request.base_url).rstrip("/")
    integration_json = {
        "data": {
            "date": {
                "created_at": "2025-02-18",
                "updated_at": "2025-02-18"
            },
            "descriptions": {
                "app_name": "Postgresql Database Performance",
                "app_description": "Postgres Database Monitoring system",
                "app_logo": "https://postgres-monitor.onrender.com",
                "app_url": "https://postgres-monitor.onrender.com",
                "background_color": "#fff"
            },
            "is_active": True,
            "integration_type": "interval",
            "key_features": ["Database Monitoring"],
            "author": "Adesola",
            "integration_category": "Performance Monitoring",
            "settings": [
                {"label": "site", "type": "text", "required": True, "default": "https://postgres-monitor.onrender.com/"},
                {"label": "database_url", "type": "text", "required": True, "default": "postgresql://user:password@db-host:5432/yourdatabase"},
                {"label": "Interval", "type": "dropdown", "required": True, "default": "*/4 * * * *"}
            ],
            "tick_url": f"{base_url}/tick"
        }
    }
    return JSONResponse(integration_json)

async def check_database_connection(payload: MonitorPayLoad):
    """Check if the database is reachable."""
    DATABASE_URL = payload.get_setting("database_url")
    engine = get_db_engine(DATABASE_URL)
    try:
        conn = await asyncpg.connect(DATABASE_URL)
        await conn.close()
        return "Database is reachable"
    except Exception as e:
        logger.error(f"Database connection failed: {str(e)}")
        return f"Database connection failed: {str(e)}"

async def get_database_size(payload: MonitorPayLoad):
    DATABASE_URL = payload.get_setting("database_url")
    engine = get_db_engine(DATABASE_URL)
    try:
        async with engine.connect() as conn:
            result = await conn.execute(text("SELECT pg_size_pretty(pg_database_size(current_database()));"))
            return f"Database size: {await result.scalar()}"
    except Exception as e:
        logger.error(f"Error retrieving database size: {str(e)}")
        return f"Error retrieving database size: {str(e)}"

async def get_active_connections(payload: MonitorPayLoad):
    DATABASE_URL = payload.get_setting("database_url")
    engine = get_db_engine(DATABASE_URL)
    try:
        async with engine.connect() as conn:
            result = await conn.execute(text("SELECT COUNT(*) FROM pg_stat_activity"))
            return f"Active connections: {await result.scalar()}"
    except Exception as e:
        logger.error(f"Error retrieving active connections: {str(e)}")
        return f"Error retrieving active connections: {str(e)}"

async def get_long_running_queries(payload: MonitorPayLoad):
    DATABASE_URL = payload.get_setting("database_url")
    engine = get_db_engine(DATABASE_URL)
    threshold = int(payload.get_setting("max_query_duration", 10))
    try:
        async with engine.connect() as conn:
            result = await conn.execute(text(f"""
                SELECT pid, state, query, EXTRACT(EPOCH FROM (NOW()-query_start)) AS duration
                FROM pg_stat_activity
                WHERE state <> 'idle' AND (NOW() - query_start) > INTERVAL '{threshold} seconds' 
                ORDER BY duration DESC;
            """))
            long_queries = await result.fetchall()
            queries = [f"PID: {q[0]}, State: {q[1]}, Query: {q[2]}, Duration: {q[3]}s" for q in long_queries]
            return "\n".join(queries) if queries else "No long-running queries"
    except Exception as e:
        logger.error(f"Error retrieving long-running queries: {str(e)}")
        return f"Error retrieving long-running queries: {str(e)}"
    
async def check_site_status(site: str) -> Dict[str, str]:
    start_time = time.time()
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(site, timeout=10)
            end_time = time.time()
            return {
                "site": site,
                "status_code": response.status_code,
                "response": response.text,
                "response_time": round(end_time - start_time, 4)
            }
    except Exception as e:
        end_time = time.time()
        return {"site": site, "error": str(e), "response_time": round(end_time - start_time, 4)}

async def monitor_task(payload: MonitorPayLoad):
    """Background task to monitor database and send results."""
    try:
        sites = [s.default for s in payload.settings if s.label.startswith("site")]

        # Run all monitoring tasks concurrently
        monitoring_tasks = [
            *(check_site_status(site) for site in sites),
            check_database_connection(payload),
            get_database_size(payload),
            get_active_connections(payload),
            get_long_running_queries(payload)
        ]

        results = await asyncio.gather(*monitoring_tasks, return_exceptions=True)

        # Convert results to string and handle exceptions
        results_text = "\n".join(
            str(result) if not isinstance(result, Exception) else f"Error: {result}"
            for result in results
        )

        # Determine status
        status = "error" if "Error" in results_text else "success"

        # Construct the response payload
        telex_format = {
            "message": results_text,
            "username": "DB Monitor",
            "event_name": "Database Check",
            "status": status
        }

        # Send results asynchronously
        async with httpx.AsyncClient() as client:
            await client.post(
                payload.return_url, 
                json=telex_format, 
                headers={"Content-Type": "application/json"}
            )

    except Exception as e:
        # Log or handle unexpected exceptions
        print(f"Unexpected error in monitor_task: {e}")
@app.post("/tick", status_code=202)
def monitor(payload: MonitorPayLoad, background_tasks: BackgroundTasks):
    background_tasks.add_task(monitor_task, payload)
    return {"status": "success"}

@app.get("/")
def home():
    return "Welcome to PostgreSQL Monitor"

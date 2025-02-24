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
                "app_url": "https://telex-monitor-ttdn.onrender.com",
                "background_color": "#fff"
            },
            "is_active": True,
            "integration_type": "interval",
            "key_features": ["Database Monitoring"],
            "author": "Adesola",
            "integration_category": "Performance Monitoring",
            "settings": [
                {"label": "database_url", "type": "text", "required": True, "default": "postgresql://user:password@db-host:5432/yourdatabase"},
                {"label": "Interval", "type": "text", "required": True, "default": "*/4 * * * *"}
            ],
            "target_url":"https://ping.telex.im/v1/webhooks/01952975-1a16-7ecb-9126-fbf9c1056d0b",
            "tick_url": f"{base_url}/tick"
        }
    }
    return JSONResponse(integration_json)

async def check_database_connection(database_url:str):
    """Check if the database is reachable."""
    DATABASE_URL = database_url
    if not DATABASE_URL:
        return {"status": "error", "message": "No database URL provided."}
    try:
        async with asyncpg.create_pool(DATABASE_URL) as pool:
            async with pool.acquire() as conn:
                return {"status": "success", "message": "Database is reachable"}
    except Exception as e:
        logger.error(f"Database connection failed: {str(e)}")
        return {"status": "error", "message": str(e)}
        
async def get_database_size(database_url:str):
    DATABASE_URL = database_url
    if not DATABASE_URL:                    
        return {"status": "error", "message": "No database URL provided."}

    engine = get_db_engine(DATABASE_URL)
    try:
        async with engine.begin() as conn:
            result = await conn.execute(text("SELECT pg_size_pretty(pg_database_size(current_database()));"))
            return f"Database size: {result.scalar()}"
    except Exception as e:
        logger.error(f"Error retrieving database size: {str(e)}")
        return f"Error retrieving database size: {str(e)}"

async def get_active_connections(database_url:str):
    DATABASE_URL = database_url
    if not DATABASE_URL:
        return {"status": "error", "message": "No database URL provided."}

    engine = get_db_engine(DATABASE_URL)

    try:
        async with engine.begin() as conn:
            result = await conn.execute(text("SELECT COUNT(*) FROM pg_stat_activity;"))
            active_connections = result.scalar_one_or_none()
            return {"status": "success", "active_connections": active_connections}
    except Exception as e:
        logger.error(f"Error retrieving active connections: {str(e)}")
        return {"status": "error", "message": str(e)}
    finally:
        await engine.dispose()
    
async def get_long_running_queries(database_url:str):
    DATABASE_URL = database_url
    if not DATABASE_URL:
        return {"status": "error", "message": "No database URL provided."}

    engine = get_db_engine(DATABASE_URL)
    threshold = 10
    try:
        async with engine.connect() as conn:
            result = await conn.execute(text(f"""
                SELECT pid, state, query, EXTRACT(EPOCH FROM (NOW()-query_start)) AS duration
                FROM pg_stat_activity
                WHERE state <> 'idle' AND (NOW() - query_start) > INTERVAL '{threshold} seconds' 
                ORDER BY duration DESC;
            """))
            long_queries =  result.fetchall()
            queries = [f"PID: {q[0]}, State: {q[1]}, Query: {q[2]}, Duration: {q[3]}s" for q in long_queries]
            return "\n".join(queries) if queries else "No long-running queries"
    except Exception as e:
        logger.error(f"Error retrieving long-running queries: {str(e)}")
        return f"Error retrieving long-running queries: {str(e)}"
    
print(MonitorPayLoad)
async def monitor_task(payload: MonitorPayLoad):
    """Background task to monitor database and send results."""
    try:    
        # database_url = [s.default for s in payload.settings if s.label.startswith("database_url")]
        database_url = payload.get_setting("database_url")
        if not database_url:
            return {"error": "No valid database_url provided in payload."}

        # Prepare monitoring tasks
        monitoring_tasks = [
            check_database_connection(database_url),
            get_database_size(database_url),
            get_active_connections(database_url),
            get_long_running_queries(database_url)
        ]

        # Execute tasks concurrently
        results = await asyncio.gather(*monitoring_tasks, return_exceptions=True)

        formatted_results = []
        for res in results:
            if isinstance(res, Exception):
                formatted_results.append(f"Error: {str(res)}")
            else:
                formatted_results.append(str(res))

        # Format results
        results_text = "\n".join(str(res) if res is not None else "Error: Missing result" for res in results)
        status = "error" if "Error" in results_text else "success"

        # Prepare payload for notification
        notification_payload = {
            "message": results_text,
            "username": "DB Monitor",
            "event_name": "Database Check",
            "status": status
        }

        # Send results via HTTP request
        async with httpx.AsyncClient() as client:
            await client.post(
                payload.return_url, 
                json=notification_payload, 
                headers={"Content-Type": "application/json"}
            )

    except Exception as e:
        logger.error(f"Unexpected error in monitor_task: {e}")




@app.post("/tick", status_code=202)
def monitor(payload: MonitorPayLoad, background_tasks: BackgroundTasks):
    background_tasks.add_task(monitor_task, payload)
    return {"status": "success"}

@app.get("/")
def home():
    return "Welcome to PostgreSQL Monitor"




if __name__=="__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
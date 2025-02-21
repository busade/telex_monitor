from fastapi import FastAPI, BackgroundTasks,Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List,Dict
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.sql import text
import asyncio,json,httpx, os, asyncpg,time

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


@app.get('/integration')
def get_integration_json(request:Request):
    base_url = str(request.base_url).rstrip("/")
    integration_json = {
    "data": {
        "date": {
        "created_at": "2025-02-18",
        "updated_at": "2025-02-18"
        },
        "descriptions": {
        "app_name": "Postgresql Database Performance ",
        "app_description": "Postgres Database Monitoring system",
        "app_logo": "https://postgres-monitor.onrender.com",
        "app_url": "https://postgres-monitor.onrender.com",
        "background_color": "#fff"
        },
        "is_active": True,
        "integration_type": "interval",
        "key_features": [
        "Database Monitoring"
        ],
        "author": "Adesola",
        "integration_category": "Performance Monitoring",
        "settings": [
        {
            "label":"site",
            "type":"text",
            "required":True,
            "default":"https://postgres-monitor.onrender.com/"
        },
        {
                "label": "database_url",
                "type": "text",
                "required": True,
                "default": "postgresql://user:password@db-host:5432/yourdatabase"
        },        
        {
            "label": "Interval",
            "type": "dropdown",
            "required": True,
            "default": "*/4 * * * *",
            
        }
        ],
        "tick_url": f"{base_url}/tick"
        }
        }
    return JSONResponse(integration_json)

# DATABASE_URL = payload.get_setting("database_url")

class MonitorPayload(BaseModel):
    return_url: str

async def check_database_connection(payload:MonitorPayLoad):
    """Check if the database is reachable."""
    DATABASE_URL=payload.get_setting("database_url")
    engine = create_async_engine(DATABASE_URL, echo=True)

    try:
        conn = await asyncpg.connect(DATABASE_URL)
        await conn.close()
        return "Database is reachable"
    except Exception as e:
        return f"Database connection failed: {str(e)}"

async def get_database_size(payload: MonitorPayLoad):
    DATABASE_URL=payload.get_setting("database_url")
    engine = create_async_engine(DATABASE_URL, echo=True)
    try:
        async with engine.connect() as conn:
            result = await conn.execute(text("SELECT pg_size_pretty(pg_database_size(current_database()));"))
            return f"Database size: {result.scalar()}"
    except Exception as e:
        return f"Error retrieving database size: {str(e)}"

async def get_active_connections(payload: MonitorPayLoad):
    DATABASE_URL=payload.get_setting("database_url")
    engine = create_async_engine(DATABASE_URL, echo=True)
    try:
        async with engine.connect() as conn:
            result = await conn.execute(text("SELECT COUNT(*) FROM pg_stat_activity"))
            return f"Active connections: {result.scalar()}"
    except Exception as e:
        return f"Error retrieving active connections: {str(e)}"

async def get_long_running_queries(payload:MonitorPayLoad):
    DATABASE_URL=payload.get_setting("database_url")
    engine = create_async_engine(DATABASE_URL, echo=True)
    threshold = int(payload.get_setting("max_query_duration", 10))

    try:
        async with engine.connect() as conn:
            result = await conn.execute(text(f"""
                    SELECT
                        pid,
                        state,
                        query,
                        EXTRACT(EPOCH FROM (NOW()-query_start)) AS duration
                    FROM pg_stat_activity
                    WHERE state <> 'idle' and (NOW() - query_start) > INTERVAL '{threshold} seconds' 
                    ORDER BY duration DESC;
            """))
            long_queries = result.fetchall()
            queries = [f"PID: {q[0]}, State: {q[1]}, Query: {q[2]}, Duration: {q[3]}s" for q in long_queries]
            return "\n".join(queries) if queries else "No long-running queries"
    except Exception as e:
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

async def monitor_task(payload: MonitorPayload):
    """Background task to monitor database and send results."""
    sites = [s.default for s in payload.settings if s.label.startswith("site")]
    results = await asyncio.gather(
        *(check_site_status(site) for site in sites),
        check_database_connection(),
        get_database_size(),
        get_active_connections(),
        get_long_running_queries()
    )
    results_text = "\n".join(results)
    
    telex_format = {
        "message": results_text,
        "username": "DB Monitor",
        "event_name": "Database Check",
        "status": "error" if "Error" in results_text else "success"
    }
    
    async with httpx.AsyncClient() as client:
        await client.post(payload.return_url, json=telex_format, headers={"Content-Type": "application/json"})


@app.post("/tick", status_code=202)
def monitor(payload: MonitorPayload, background_tasks: BackgroundTasks):
    background_tasks.add_task(monitor_task, payload)
    return {"status": "success"}



@app.get("/")
def home():
    return "welcome to postgres monitor"

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app)
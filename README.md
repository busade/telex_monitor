# Postgres Database monitoring

## Overview

This project is a RESTful API built with FastAPI Integrated on TELEX for monitoring a Postgres Database performance. It perfoms a check on the response time of each request made into the db, size of the DB,number of active connections to the DB and gets long queries that last longer than 10seconds.

## Features

- checks the size of the DB
- Number of active connections on the DB
- API documentation (auto-generated by FastAPI)
- CORS middleware enabled

## Project Structure

```
telex_monitor/

├───app
|       ├─  __init_.py
|       |
|       └──  main.py
|
├─── tests
|       ├─ 
│       ├── __init__.py
│       └── test_monitor.py      
│   
├── requirements.txt        # Project dependencies
└── README.md
```

## Technologies Used

- Python 3.12
- FastAPI
- Pydantic
- pytest
- Postgresql
- uvicorn

## Installation

1. Clone the repository:

```bash
git clone https://github.com/busade/telex_monitor.git
cd Posgres monitor
```

2. Create a virtual environment:

```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:

```bash
pip install -r requirements.txt
```

## Running the Application

1. Start the server:

```bash
uvicorn app.main:app
```

2. Access the API documentation:

- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## API Endpoints

### Books

- `GET /` - Home route
- `POST /tick` - Provide the postgres database url and the interval at which  you want to monitor in the request body.








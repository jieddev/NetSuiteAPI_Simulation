from fastapi import FastAPI, Depends, HTTPException, Request, Header
from fastapi.middleware.cors import CORSMiddleware
import asyncpg
import asyncio
import time
import random
import os
from typing import Optional
import jwt
from pydantic import BaseModel
from datetime import datetime, timedelta

# Initialize FastAPI
app = FastAPI(title="NetSuite API Simulation")

# Database connection pool
pool = None

# Simulated cache
cache = {}

# Auth token secret
SECRET_KEY = "netsuite_simulation_secret"

# Customer tiers - simulating multi-tenancy
CUSTOMER_TIERS = {
    "standard": {"rate_limit": 30, "priority": 1},
    "premium": {"rate_limit": 100, "priority": 2},
    "enterprise": {"rate_limit": 300, "priority": 3}
}

@app.get("/health")
async def health_check():
    return {"status": "ok"}

# Startup event - initialize connection pool
@app.on_event("startup")
async def startup():
    global pool
    # Connect to your PostgreSQL database
    pool = await asyncpg.create_pool(
        "postgresql://postgres:JED567DELpostgresql@localhost/SNetsuite_db",
        min_size=5,
        max_size=20,  # Limited connection pool
    )
    
    # Create tables if they don't exist
    async with pool.acquire() as conn:
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS inventory (
                id SERIAL PRIMARY KEY,
                item_id VARCHAR(50) UNIQUE,
                name VARCHAR(100),
                quantity INTEGER,
                last_updated TIMESTAMP
            )
        ''')
        
        # Insert sample data if needed
        count = await conn.fetchval("SELECT COUNT(*) FROM inventory")
        if count == 0:
            # Insert sample inventory items
            for i in range(1000):
                await conn.execute(
                    "INSERT INTO inventory (item_id, name, quantity, last_updated) VALUES ($1, $2, $3, $4)",
                    f"ITEM-{i}",
                    f"Product {i}",
                    random.randint(0, 1000),
                    datetime.now()
                )

# Authentication
def create_token(customer_id: str, tier: str):
    expiration = datetime.utcnow() + timedelta(hours=24)
    payload = {
        "sub": customer_id,
        "tier": tier,
        "exp": expiration
    }
    return jwt.encode(payload, SECRET_KEY, algorithm="HS256")

def decode_token(token: str):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        return payload
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid authentication token")

# Middleware for authentication and rate limiting
@app.middleware("http")
async def auth_and_rate_limit(request: Request, call_next):
    # Skip auth for login endpoint
    if request.url.path == "/api/login":
        return await call_next(request)
    
    # Check for token
    token = request.headers.get("Authorization")
    if not token or not token.startswith("Bearer "):
        return HTTPException(status_code=401, detail="Authentication required")
    
    try:
        # Decode token
        token_data = decode_token(token.replace("Bearer ", ""))
        customer_id = token_data["sub"]
        tier = token_data["tier"]
        
        # Apply rate limiting based on tier
        rate_limit = CUSTOMER_TIERS[tier]["rate_limit"]
        
        # Simple rate limiting implementation
        # In a real system, you'd use Redis or another external store
        cache_key = f"rate_limit:{customer_id}"
        current_hour = datetime.now().strftime("%Y-%m-%d-%H")
        
        if cache_key not in cache:
            cache[cache_key] = {"count": 0, "hour": current_hour}
        
        # Reset counter if hour changed
        if cache[cache_key]["hour"] != current_hour:
            cache[cache_key] = {"count": 0, "hour": current_hour}
        
        # Check limit
        if cache[cache_key]["count"] >= rate_limit:
            return HTTPException(status_code=429, detail="Rate limit exceeded")
        
        # Increment counter
        cache[cache_key]["count"] += 1
        
        # Add customer data to request state for later use
        request.state.customer_id = customer_id
        request.state.tier = tier
        
        # Proceed with request
        start_time = time.time()
        response = await call_next(request)
        duration = time.time() - start_time
        
        # Add processing time header
        response.headers["X-Processing-Time"] = str(duration)
        return response
        
    except Exception as e:
        return HTTPException(status_code=401, detail=f"Authentication error: {str(e)}")

# Login endpoint
class LoginRequest(BaseModel):
    customer_id: str
    api_key: str

@app.post("/api/login")
async def login(request: LoginRequest):
    # In a real system, you'd validate against a database
    # For simulation, we'll just check a few hardcoded values
    valid_customers = {
        "CUST001": {"key": "apikey001", "tier": "standard"},
        "CUST002": {"key": "apikey002", "tier": "premium"},
        "CUST003": {"key": "apikey003", "tier": "enterprise"}
    }
    
    if request.customer_id not in valid_customers:
        raise HTTPException(status_code=401, detail="Invalid customer ID")
    
    if valid_customers[request.customer_id]["key"] != request.api_key:
        raise HTTPException(status_code=401, detail="Invalid API key")
    
    # Create token
    token = create_token(
        request.customer_id, 
        valid_customers[request.customer_id]["tier"]
    )
    
    return {"access_token": token, "token_type": "bearer"}

# Sample API endpoints that simulate NetSuite behavior
@app.get("/api/inventory")
async def get_inventory(
    request: Request,
    item_id: Optional[str] = None,
    page: int = 1,
    limit: int = 100
):
    # Get customer tier from request state
    tier = request.state.tier
    
    # Simulate different performance based on tier
    if tier == "standard":
        # Standard tier gets slower response
        await asyncio.sleep(0.5)
    elif tier == "premium":
        # Premium is faster
        await asyncio.sleep(0.2)
    else:
        # Enterprise is fastest
        await asyncio.sleep(0.1)
    
    # Simulate occasional slowdowns during "peak hours"
    current_hour = datetime.now().hour
    if 9 <= current_hour <= 17:  # 9 AM to 5 PM
        # 20% chance of slowdown during business hours
        if random.random() < 0.2:
            await asyncio.sleep(2)
    
    try:
        # Acquire connection from pool - this is where bottlenecks happen
        async with pool.acquire() as conn:
            # Simulate connection acquisition delay during high load
            await asyncio.sleep(0.1)
            
            if item_id:
                # Get specific item - direct query, usually fast
                query = "SELECT * FROM inventory WHERE item_id = $1"
                result = await conn.fetch(query, item_id)
            else:
                # List with pagination - can be slower
                offset = (page - 1) * limit
                query = "SELECT * FROM inventory ORDER BY id LIMIT $1 OFFSET $2"
                result = await conn.fetch(query, limit, offset)
                
                # Enterprise tier gets count as well
                if tier == "enterprise":
                    count = await conn.fetchval("SELECT COUNT(*) FROM inventory")
                else:
                    count = None
            
            # Simulate DB processing time
            await asyncio.sleep(0.1)
            
            # Convert to dict for response
            items = [dict(item) for item in result]
            
            # Enterprise gets more data
            if tier == "enterprise" and not item_id:
                return {
                    "items": items,
                    "total": count,
                    "page": page,
                    "limit": limit,
                    "pages": (count + limit - 1) // limit if count else None
                }
            else:
                return {"items": items}
                
    except asyncpg.exceptions.TooManyConnectionsError:
        # Simulate connection pool exhaustion
        raise HTTPException(
            status_code=503, 
            detail="Service temporarily unavailable. Connection pool exhausted."
        )
    except Exception as e:
        # General error
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

# Add more endpoints to simulate other NetSuite functions

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
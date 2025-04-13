from fastapi import FastAPI, HTTPException, Request
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
    return {
        "status": "ok", 
        "timestamp": datetime.now().isoformat(),
        "version": "1.0.0"
    }

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

# Login endpoint
class LoginRequest(BaseModel):
    customer_id: str
    api_key: str

@app.post("/api/login")
async def login(request: LoginRequest):
    valid_customers = {
        "CUST001": {"key": "apikey001", "tier": "standard"},
        "CUST002": {"key": "apikey002", "tier": "premium"},
        "CUST003": {"key": "apikey003", "tier": "enterprise"}
    }
    
    if request.customer_id not in valid_customers:
        raise HTTPException(status_code=401, detail="Invalid customer ID")
    
    if valid_customers[request.customer_id]["key"] != request.api_key:
        raise HTTPException(status_code=401, detail="Invalid API key")
    
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
    # Simulate data retrieval
    items = []
    for i in range(1000):
        items.append({
            "id": i,
            "item_id": f"ITEM-{i}",
            "name": f"Product {i}",
            "quantity": random.randint(0, 1000),
            "last_updated": datetime.now()
        })
    
    # Filter by item_id if provided
    if item_id:
        items = [item for item in items if item['item_id'] == item_id]
    
    # Pagination
    start = (page - 1) * limit
    end = start + limit
    paginated_items = items[start:end]
    
    return {
        "items": paginated_items,
        "total": len(items),
        "page": page,
        "limit": limit,
        "pages": (len(items) + limit - 1) // limit
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
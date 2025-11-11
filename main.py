import os
from typing import List, Optional, Dict, Any
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr, HttpUrl, Field
from bson import ObjectId

from database import db, create_document, get_documents

app = FastAPI(title="Startup Fundraising Platform API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Helpers

def oid(id_str: str) -> ObjectId:
    try:
        return ObjectId(id_str)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid id format")


def to_public(doc: Dict[str, Any]) -> Dict[str, Any]:
    if not doc:
        return doc
    d = dict(doc)
    if "_id" in d:
        d["id"] = str(d.pop("_id"))
    return d


# Request models
class StartupRegisterRequest(BaseModel):
    email: EmailStr
    company_name: str
    product_description: str
    image_urls: List[HttpUrl] = []
    previous_funding: Optional[str] = None
    full_name: Optional[str] = None

class InvestorRegisterRequest(BaseModel):
    email: EmailStr
    full_name: str
    company: Optional[str] = None

class InterestCreateRequest(BaseModel):
    investor_user_id: str
    message: Optional[str] = None
    committed_amount: float = Field(0.0, ge=0)

class ReportCreateRequest(BaseModel):
    reporter_user_id: Optional[str] = None
    target_type: str
    target_id: Optional[str] = None
    reason: str

class AdminBootstrapRequest(BaseModel):
    email: EmailStr
    full_name: str


@app.get("/")
def read_root():
    return {"message": "Startup Fundraising Platform API running"}


@app.get("/test")
def test_database():
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": None,
        "database_name": None,
        "connection_status": "Not Connected",
        "collections": []
    }
    try:
        if db is not None:
            response["database"] = "✅ Available"
            response["database_url"] = "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set"
            response["database_name"] = db.name
            response["connection_status"] = "Connected"
            try:
                collections = db.list_collection_names()
                response["collections"] = collections
                response["database"] = "✅ Connected & Working"
            except Exception as e:
                response["database"] = f"⚠️ Connected but Error: {str(e)[:80]}"
        else:
            response["database"] = "⚠️ Available but not initialized"
    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:80]}"
    return response


# Registration Endpoints
@app.post("/api/register/startup")
def register_startup(payload: StartupRegisterRequest):
    # Create user
    existing = db["user"].find_one({"email": payload.email})
    if existing:
        # Allow if same user re-submits; ensure role is startup
        db["user"].update_one({"_id": existing["_id"]}, {"$set": {"role": "startup", "full_name": payload.full_name}})
        user_id = str(existing["_id"])    
    else:
        user_id = create_document("user", {
            "email": payload.email,
            "full_name": payload.full_name,
            "role": "startup",
            "is_active": True,
        })
    # Create startup pitch
    pitch_doc = {
        "owner_user_id": user_id,
        "company_name": payload.company_name,
        "product_description": payload.product_description,
        "image_urls": payload.image_urls,
        "previous_funding": payload.previous_funding,
        "status": "pending",
        "total_raised": 0.0,
    }
    existing_pitch = db["startuppitch"].find_one({"owner_user_id": user_id})
    if existing_pitch:
        db["startuppitch"].update_one({"_id": existing_pitch["_id"]}, {"$set": pitch_doc})
        startup_id = str(existing_pitch["_id"])    
    else:
        startup_id = create_document("startuppitch", pitch_doc)
    return {"user_id": user_id, "startup_id": startup_id, "role": "startup"}


@app.post("/api/register/investor")
def register_investor(payload: InvestorRegisterRequest):
    existing = db["user"].find_one({"email": payload.email})
    if existing:
        db["user"].update_one({"_id": existing["_id"]}, {"$set": {"role": "investor", "full_name": payload.full_name, "company": payload.company}})
        user_id = str(existing["_id"])    
    else:
        user_id = create_document("user", {
            "email": payload.email,
            "full_name": payload.full_name,
            "company": payload.company,
            "role": "investor",
            "is_active": True,
        })
    prof = db["investorprofile"].find_one({"user_id": user_id})
    if prof:
        db["investorprofile"].update_one({"_id": prof["_id"]}, {"$set": {"full_name": payload.full_name, "company": payload.company}})
    else:
        create_document("investorprofile", {"user_id": user_id, "full_name": payload.full_name, "company": payload.company})
    return {"user_id": user_id, "role": "investor"}


# Public Startups listing
@app.get("/api/startups")
def list_startups(status: Optional[str] = "approved"):
    q = {}
    if status:
        q["status"] = status
    items = [to_public(s) for s in db["startuppitch"].find(q).sort("_id", -1)]
    return {"items": items}


# Investor expresses interest
@app.post("/api/startups/{startup_id}/interest")
def express_interest(startup_id: str, payload: InterestCreateRequest):
    s = db["startuppitch"].find_one({"_id": oid(startup_id)})
    if not s:
        raise HTTPException(status_code=404, detail="Startup not found")
    inv_user = db["user"].find_one({"_id": oid(payload.investor_user_id)})
    if not inv_user or inv_user.get("role") != "investor":
        raise HTTPException(status_code=400, detail="Invalid investor user")
    interest_id = create_document("interest", {
        "startup_id": startup_id,
        "investor_user_id": payload.investor_user_id,
        "message": payload.message,
        "committed_amount": payload.committed_amount,
    })
    # Update aggregate
    total = 0.0
    for it in db["interest"].find({"startup_id": startup_id}):
        total += float(it.get("committed_amount", 0) or 0)
    db["startuppitch"].update_one({"_id": oid(startup_id)}, {"$set": {"total_raised": total}})
    return {"interest_id": interest_id, "total_raised": total}


# Startup Dashboard data
@app.get("/api/startups/{startup_id}/dashboard")
def startup_dashboard(startup_id: str):
    s = db["startuppitch"].find_one({"_id": oid(startup_id)})
    if not s:
        raise HTTPException(status_code=404, detail="Startup not found")
    # Interested investors detail
    interests = list(db["interest"].find({"startup_id": startup_id}).sort("_id", -1))
    investor_ids = [oid(i["investor_user_id"]) for i in interests] if interests else []
    users_map: Dict[str, Dict[str, Any]] = {}
    if investor_ids:
        for u in db["user"].find({"_id": {"$in": investor_ids}}):
            users_map[str(u["_id"])] = u
    enriched = []
    for i in interests:
        u = users_map.get(i["investor_user_id"]) or users_map.get(str(i.get("investor_user_id")))
        enriched.append({
            "id": str(i["_id"]),
            "message": i.get("message"),
            "committed_amount": i.get("committed_amount", 0),
            "investor": {
                "id": str(u["_id"]) if u else i.get("investor_user_id"),
                "full_name": (u or {}).get("full_name"),
                "company": (u or {}).get("company"),
                "email": (u or {}).get("email"),
            }
        })
    total = float(s.get("total_raised", 0) or 0)
    return {
        "startup": to_public(s),
        "interested_investors": enriched,
        "total_raised": total
    }


# Reports
@app.post("/api/reports")
def create_report(payload: ReportCreateRequest):
    rid = create_document("report", payload.dict())
    return {"report_id": rid}

@app.get("/api/admin/reports")
def list_reports():
    return {"items": [to_public(r) for r in db["report"].find().sort("_id", -1)]}


# Admin bootstrap and moderation
@app.post("/api/admin/bootstrap")
def admin_bootstrap(payload: AdminBootstrapRequest):
    # If an admin exists, return that user; otherwise create one.
    existing = db["user"].find_one({"email": payload.email})
    if existing:
        db["user"].update_one({"_id": existing["_id"]}, {"$set": {"role": "admin", "full_name": payload.full_name}})
        return {"user_id": str(existing["_id"]), "role": "admin"}
    uid = create_document("user", {"email": payload.email, "full_name": payload.full_name, "role": "admin", "is_active": True})
    return {"user_id": uid, "role": "admin"}

@app.post("/api/admin/startups/{startup_id}/approve")
def approve_startup(startup_id: str):
    res = db["startuppitch"].update_one({"_id": oid(startup_id)}, {"$set": {"status": "approved"}})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Startup not found")
    return {"status": "approved"}

@app.post("/api/admin/startups/{startup_id}/reject")
def reject_startup(startup_id: str):
    res = db["startuppitch"].update_one({"_id": oid(startup_id)}, {"$set": {"status": "rejected"}})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Startup not found")
    return {"status": "rejected"}

@app.get("/api/admin/analytics")
def analytics():
    users_total = db["user"].count_documents({})
    startups_total = db["startuppitch"].count_documents({})
    investors_total = db["user"].count_documents({"role": "investor"})
    interest_count = db["interest"].count_documents({})
    total_funds = 0.0
    for s in db["startuppitch"].find({}):
        total_funds += float(s.get("total_raised", 0) or 0)
    return {
        "users": users_total,
        "startups": startups_total,
        "investors": investors_total,
        "interests": interest_count,
        "total_funds": total_funds
    }


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)

import os
from datetime import datetime
from typing import List, Optional, Any, Dict

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from bson import ObjectId

from database import db, create_document, get_documents

app = FastAPI(title="Funky Todo API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Helpers
class PyObjectId(ObjectId):
    @classmethod
    def __get_validators__(cls):
        yield cls.validate

    @classmethod
    def validate(cls, v):
        if isinstance(v, ObjectId):
            return v
        try:
            return ObjectId(str(v))
        except Exception:
            raise ValueError("Invalid ObjectId")


def serialize_task(doc: Dict[str, Any]) -> Dict[str, Any]:
    if not doc:
        return doc
    return {
        "id": str(doc.get("_id")),
        "title": doc.get("title"),
        "notes": doc.get("notes"),
        "priority": doc.get("priority", "normal"),
        "due_date": doc.get("due_date").isoformat() if doc.get("due_date") else None,
        "completed": bool(doc.get("completed", False)),
        "created_at": doc.get("created_at").isoformat() if doc.get("created_at") else None,
        "updated_at": doc.get("updated_at").isoformat() if doc.get("updated_at") else None,
    }


# Pydantic models for requests
class TaskCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    notes: Optional[str] = Field(None, max_length=2000)
    priority: str = Field("normal")
    due_date: Optional[datetime] = None


class TaskUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=200)
    notes: Optional[str] = Field(None, max_length=2000)
    priority: Optional[str] = None
    due_date: Optional[datetime] = None
    completed: Optional[bool] = None


@app.get("/")
def read_root():
    return {"message": "Funky Todo API is live!"}


@app.get("/api/tasks")
def list_tasks() -> List[Dict[str, Any]]:
    if db is None:
        raise HTTPException(status_code=500, detail="Database not configured")
    docs = db["task"].find({}).sort("created_at", -1)
    return [serialize_task(d) for d in docs]


@app.post("/api/tasks", status_code=201)
def create_task(payload: TaskCreate) -> Dict[str, Any]:
    if db is None:
        raise HTTPException(status_code=500, detail="Database not configured")
    # Use helper to auto add timestamps
    _id = create_document("task", {
        "title": payload.title,
        "notes": payload.notes,
        "priority": payload.priority,
        "due_date": payload.due_date,
        "completed": False,
    })
    doc = db["task"].find_one({"_id": ObjectId(_id)})
    return serialize_task(doc)


@app.patch("/api/tasks/{task_id}")
def update_task(task_id: str, payload: TaskUpdate) -> Dict[str, Any]:
    if db is None:
        raise HTTPException(status_code=500, detail="Database not configured")
    try:
        oid = ObjectId(task_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid task id")

    updates = {k: v for k, v in payload.model_dump(exclude_unset=True).items()}
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")

    updates["updated_at"] = datetime.utcnow()
    res = db["task"].update_one({"_id": oid}, {"$set": updates})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Task not found")
    doc = db["task"].find_one({"_id": oid})
    return serialize_task(doc)


@app.post("/api/tasks/{task_id}/toggle")
def toggle_task(task_id: str) -> Dict[str, Any]:
    if db is None:
        raise HTTPException(status_code=500, detail="Database not configured")
    try:
        oid = ObjectId(task_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid task id")

    doc = db["task"].find_one({"_id": oid})
    if not doc:
        raise HTTPException(status_code=404, detail="Task not found")
    new_val = not bool(doc.get("completed", False))
    db["task"].update_one({"_id": oid}, {"$set": {"completed": new_val, "updated_at": datetime.utcnow()}})
    doc = db["task"].find_one({"_id": oid})
    return serialize_task(doc)


@app.delete("/api/tasks/{task_id}", status_code=204)
def delete_task(task_id: str):
    if db is None:
        raise HTTPException(status_code=500, detail="Database not configured")
    try:
        oid = ObjectId(task_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid task id")

    res = db["task"].delete_one({"_id": oid})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Task not found")
    return


@app.get("/test")
def test_database():
    """Test endpoint to check if database is available and accessible"""
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
            response["database_url"] = "✅ Configured"
            response["database_name"] = db.name if hasattr(db, 'name') else "✅ Connected"
            response["connection_status"] = "Connected"

            # Try to list collections to verify connectivity
            try:
                collections = db.list_collection_names()
                response["collections"] = collections[:10]
                response["database"] = "✅ Connected & Working"
            except Exception as e:
                response["database"] = f"⚠️  Connected but Error: {str(e)[:50]}"
        else:
            response["database"] = "⚠️  Available but not initialized"

    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:50]}"

    # Check environment variables
    response["database_url"] = "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set"
    response["database_name"] = "✅ Set" if os.getenv("DATABASE_NAME") else "❌ Not Set"

    return response


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)

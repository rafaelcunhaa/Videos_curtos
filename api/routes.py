from fastapi import APIRouter

router = APIRouter()

@router.get("/")
def home():
    return {
        "projeto": "BoomVibes",
        "status": "online"
    }
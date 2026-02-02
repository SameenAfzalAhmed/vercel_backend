from fastapi import FastAPI, APIRouter, HTTPException
from mangum import Mangum
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional
from datetime import datetime, timezone
import uuid
import os
import logging
from dotenv import load_dotenv
from bson import ObjectId 

# -------------------------
# LOAD ENV VARIABLES
# -------------------------
load_dotenv()
MONGO_URL = os.environ.get("MONGO_URL")
DB_NAME = os.environ.get("DB_NAME")
CORS_ORIGINS = os.environ.get("CORS_ORIGINS", "*").split(",")

if not MONGO_URL or not DB_NAME:
    raise RuntimeError("Missing MONGO_URL or DB_NAME environment variables")

# -------------------------
# DATABASE CONNECTION
# -------------------------
client = AsyncIOMotorClient(MONGO_URL)
db = client[DB_NAME]

# -------------------------
# FASTAPI APP
# -------------------------
app = FastAPI(title="E1 Music API")
api_router = APIRouter(prefix="")

# MIDDLEWARE
# -------------------------
# This FIXES the error:
# "No 'Access-Control-Allow-Origin' header is present"
# REQUIRED for localhost, Netlify, Firebase, Emergent, etc.
origins = [
    "http://localhost:3000",
    "https://musicplayerfullstack.netlify.app/"
]



app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,  # ✅ TEMP: allow all (safe for now)
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -------------------------
# LOGGING
# -------------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("firebase-fastapi")
logger.info(f"Connected to MongoDB: {DB_NAME}")

# -------------------------
# UTILITY: MongoDB -> JSON-safe dict
# -------------------------
def mongo_to_dict(doc):
    """
    Convert MongoDB _id to string 'id' and ensure all fields exist to avoid validation errors.
    """
    if not doc:
        return None
    doc = dict(doc)
    if "_id" in doc:
        doc["id"] = str(doc["_id"])
        del doc["_id"]

    # --- FIX: Ensure all fields exist to prevent ResponseValidationError ---
    doc.setdefault("title", None)
    doc.setdefault("artist", None)
    doc.setdefault("album", None)
    doc.setdefault("duration", None)
    doc.setdefault("cover_url", None)
    doc.setdefault("audio_url", None)
    doc.setdefault("created_at", None)
    doc.setdefault("name", None)
    doc.setdefault("description", "")
    doc.setdefault("song_ids", [])
    return doc

# -------------------------
# MODELS
# -------------------------
class Song(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: Optional[str] = Field(default_factory=lambda: str(uuid.uuid4()))
    title: Optional[str] = None         # <-- FIX: made optional
    artist: Optional[str] = None        # <-- FIX: made optional
    album: Optional[str] = None
    duration: Optional[int] = None      # <-- FIX: made optional
    cover_url: Optional[str] = None     # <-- FIX: made optional
    audio_url: Optional[str] = None     # <-- FIX: made optional
    created_at: Optional[datetime] = Field(default_factory=lambda: datetime.now(timezone.utc))

class SongCreate(BaseModel):
    title: str
    artist: str
    album: str
    duration: int
    cover_url: str
    audio_url: str

class Playlist(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: Optional[str] = Field(default_factory=lambda: str(uuid.uuid4()))
    name: Optional[str] = None
    description: Optional[str] = ""
    cover_url: Optional[str] = None
    song_ids: List[str] = Field(default_factory=list)
    created_at: Optional[datetime] = Field(default_factory=lambda: datetime.now(timezone.utc))

class PlaylistCreate(BaseModel):
    name: str
    description: Optional[str] = ""
    cover_url: str

class PlaylistAddSong(BaseModel):
    song_id: str

class Favorite(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: Optional[str] = Field(default_factory=lambda: str(uuid.uuid4()))
    song_id: Optional[str]
    created_at: Optional[datetime] = Field(default_factory=lambda: datetime.now(timezone.utc))

class FavoriteCreate(BaseModel):
    song_id: str

# -------------------------
# ROUTES
# -------------------------
@api_router.get("/")
async def root():
    return {"message": "E1 Music API"}


    # ---- SONGS TEST ----
@api_router.get("/songs-test")
async def songs_test():
    try:
        songs = await db.songs.find({}).to_list(10)
        # Use mongo_to_dict to safely convert _id to string
        return [mongo_to_dict(song) for song in songs]
    except Exception as e:
        return {"error": str(e)}


# -------------------------
# SONGS ROUTES initialization to Read Data 
# -------------------------
@api_router.get("/init-data")
async def init_data():
    return {"message": "ok"}





@api_router.get("/songs", response_model=List[Song])
async def get_songs(search: Optional[str] = None):
    try:
        query = {}
        if search:
            query = {
                "$or": [
                    {"title": {"$regex": search, "$options": "i"}},
                    {"artist": {"$regex": search, "$options": "i"}},
                    {"album": {"$regex": search, "$options": "i"}},
                ]
            }
        songs = await db.songs.find(query).to_list(1000)
        # --- FIX: Convert MongoDB docs to dicts safely ---
        return [mongo_to_dict(song) for song in songs]
    except Exception as e:
        logger.error(f"Error fetching songs: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")


        #Response Get

@api_router.get("/songs/{song_id}", response_model=Song)
async def get_song(song_id: str):
    try:
        song = await db.songs.find_one({"id": song_id})
        song = mongo_to_dict(song)
        if not song:
            raise HTTPException(status_code=404, detail="Song not found")
        return song
    except Exception as e:
        logger.error(f"Error fetching song {song_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")

        #Create Songs

@api_router.post("/songs", response_model=Song)
async def create_song(input: SongCreate):
    try:
        song = Song(**input.model_dump())
        song_dict = song.model_dump(mode="json")
        await db.songs.insert_one(song_dict)
        # --- FIX: Return dict with all fields to prevent validation error ---
        return mongo_to_dict(song_dict)
    except Exception as e:
        logger.error(f"Error creating song: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")

#
# -------------------------
# -------------------------
# PLAYLISTS ROUTES
# -------------------------
@api_router.get("/playlists", response_model=List[Playlist])
async def get_playlists():
    try:
        playlists = await db.playlists.find({}).to_list(1000)
        return [mongo_to_dict(p) for p in playlists]
    except Exception as e:
        logger.error(f"Error fetching playlists: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")

@api_router.get("/playlists/{playlist_id}", response_model=Playlist)
async def get_playlist(playlist_id: str):
    try:
        playlist = await db.playlists.find_one({"id": playlist_id})
        playlist = mongo_to_dict(playlist)
        if not playlist:
            raise HTTPException(status_code=404, detail="Playlist not found")
        return playlist
    except Exception as e:
        logger.error(f"Error fetching playlist {playlist_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")

@api_router.post("/playlists", response_model=Playlist)
async def create_playlist(input: PlaylistCreate):
    try:
        playlist = Playlist(**input.model_dump())
        playlist_dict = playlist.model_dump(mode="json")
        await db.playlists.insert_one(playlist_dict)
        return mongo_to_dict(playlist_dict)
    except Exception as e:
        logger.error(f"Error creating playlist: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")


# Get songs in a playlist
@api_router.get("/playlists/{playlist_id}/songs", response_model=List[Song])
async def get_playlist_songs(playlist_id: str):

    playlist = await db.playlists.find_one({"_id": ObjectId(playlist_id)})
    if not playlist:
        raise HTTPException(status_code=404, detail="Playlist not found")
    song_ids = playlist.get("song_ids", [])
    if not song_ids:
        return []
    
    songs = await db.songs.find({"_id": {"$in": [ObjectId(sid) for sid in song_ids]}}).to_list(1000)
    return [mongo_to_dict(song) for song in songs]

# Add song to playlist
@api_router.post("/playlists/{playlist_id}/songs")
async def add_song_to_playlist(playlist_id: str, input: PlaylistAddSong):
    playlist = await db.playlists.find_one({"_id": ObjectId(playlist_id)})
    if not playlist:
        raise HTTPException(status_code=404, detail="Playlist not found")
    song = await db.songs.find_one({"_id": ObjectId(input.song_id)})
    if not song:
        raise HTTPException(status_code=404, detail="Song not found")
    song_ids = playlist.get("song_ids", [])
    if input.song_id in song_ids:
        raise HTTPException(status_code=400, detail="Song already in playlist")
    await db.playlists.update_one({"_id": ObjectId(playlist_id)}, {"$push": {"song_ids": str(song["_id"])}})
    return {"message": "Song added to playlist"}



@api_router.delete("/playlists/{playlist_id}")
async def delete_playlist(playlist_id: str):
    try:
        result = await db.playlists.delete_one({"_id": ObjectId(playlist_id)})
        if result.deleted_count == 0:
            raise HTTPException(status_code=404, detail="Playlist not found")
        return {"message": "Playlist deleted"}
    except Exception as e:
        logger.error(f"Error deleting playlist {playlist_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")
# FAVORITES ROUTES
# -------------------------
@api_router.get("/favorites", response_model=List[Favorite])
async def get_favorites():
    try:
        favorites = await db.favorites.find({}).to_list(1000)
        return [mongo_to_dict(fav) for fav in favorites]
    except Exception as e:
        logger.error(f"Error fetching favorites: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")

@api_router.post("/favorites", response_model=Favorite)
async def add_favorite(input: FavoriteCreate):
    try:
        existing = await db.favorites.find_one({"song_id": input.song_id})
        if existing:
            raise HTTPException(status_code=400, detail="Song already favorited")
        favorite = Favorite(**input.model_dump())
        favorite_dict = favorite.model_dump(mode="json")
        await db.favorites.insert_one(favorite_dict)
        return mongo_to_dict(favorite_dict)
    except Exception as e:
        logger.error(f"Error adding favorite: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")

@api_router.delete("/favorites/{song_id}")
async def remove_favorite(song_id: str):
    try:
        result = await db.favorites.delete_one({"song_id": song_id})
        if result.deleted_count == 0:
            raise HTTPException(status_code=404, detail="Favorite not found")
        return {"message": "Removed from favorites"}
    except Exception as e:
        logger.error(f"Error removing favorite {song_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")

# -------------------------


app.include_router(api_router)

# -------------------------
# FIREBASE HANDLER
# -------------------------
handler = Mangum(app)

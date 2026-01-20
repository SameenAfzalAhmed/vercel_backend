from fastapi import FastAPI, APIRouter, HTTPException
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
from pathlib import Path
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional
import uuid
from datetime import datetime, timezone


ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# MongoDB connection
mongo_url = os.getenv['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

# Create the main app without a prefix
app = FastAPI()

# Create a router with the /api prefix
api_router = APIRouter(prefix="/api")


# Define Models
class Song(BaseModel):
    model_config = ConfigDict(extra="ignore")
    
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    title: str
    artist: str
    album: str
    duration: int  # in seconds
    cover_url: str
    audio_url: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class SongCreate(BaseModel):
    title: str
    artist: str
    album: str
    duration: int
    cover_url: str
    audio_url: str

class Playlist(BaseModel):
    model_config = ConfigDict(extra="ignore")
    
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    description: Optional[str] = ""
    cover_url: str
    song_ids: List[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class PlaylistCreate(BaseModel):
    name: str
    description: Optional[str] = ""
    cover_url: str

class PlaylistAddSong(BaseModel):
    song_id: str

class Favorite(BaseModel):
    model_config = ConfigDict(extra="ignore")
    
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    song_id: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class FavoriteCreate(BaseModel):
    song_id: str


# Routes
@api_router.get("/")
async def root():
    return {"message": "E1 Music API"}

# Songs endpoints
@api_router.get("/songs", response_model=List[Song])
async def get_songs(search: Optional[str] = None):
    query = {}
    if search:
        query = {
            "$or": [
                {"title": {"$regex": search, "$options": "i"}},
                {"artist": {"$regex": search, "$options": "i"}},
                {"album": {"$regex": search, "$options": "i"}}
            ]
        }
    
    songs = await db.songs.find(query, {"_id": 0}).to_list(1000)
    
    for song in songs:
        if isinstance(song['created_at'], str):
            song['created_at'] = datetime.fromisoformat(song['created_at'])
    
    return songs

@api_router.get("/songs/{song_id}", response_model=Song)
async def get_song(song_id: str):
    song = await db.songs.find_one({"id": song_id}, {"_id": 0})
    if not song:
        raise HTTPException(status_code=404, detail="Song not found")
    
    if isinstance(song['created_at'], str):
        song['created_at'] = datetime.fromisoformat(song['created_at'])
    
    return song

@api_router.post("/songs", response_model=Song)
async def create_song(input: SongCreate):
    song_dict = input.model_dump()
    song_obj = Song(**song_dict)
    
    doc = song_obj.model_dump()
    doc['created_at'] = doc['created_at'].isoformat()
    
    await db.songs.insert_one(doc)
    return song_obj

# Playlists endpoints
@api_router.get("/playlists", response_model=List[Playlist])
async def get_playlists():
    playlists = await db.playlists.find({}, {"_id": 0}).to_list(1000)
    
    for playlist in playlists:
        if isinstance(playlist['created_at'], str):
            playlist['created_at'] = datetime.fromisoformat(playlist['created_at'])
    
    return playlists

@api_router.get("/playlists/{playlist_id}", response_model=Playlist)
async def get_playlist(playlist_id: str):
    playlist = await db.playlists.find_one({"id": playlist_id}, {"_id": 0})
    if not playlist:
        raise HTTPException(status_code=404, detail="Playlist not found")
    
    if isinstance(playlist['created_at'], str):
        playlist['created_at'] = datetime.fromisoformat(playlist['created_at'])
    
    return playlist

@api_router.post("/playlists", response_model=Playlist)
async def create_playlist(input: PlaylistCreate):
    playlist_dict = input.model_dump()
    playlist_obj = Playlist(**playlist_dict)
    
    doc = playlist_obj.model_dump()
    doc['created_at'] = doc['created_at'].isoformat()
    
    await db.playlists.insert_one(doc)
    return playlist_obj

@api_router.post("/playlists/{playlist_id}/songs")
async def add_song_to_playlist(playlist_id: str, input: PlaylistAddSong):
    playlist = await db.playlists.find_one({"id": playlist_id}, {"_id": 0})
    if not playlist:
        raise HTTPException(status_code=404, detail="Playlist not found")
    
    song = await db.songs.find_one({"id": input.song_id}, {"_id": 0})
    if not song:
        raise HTTPException(status_code=404, detail="Song not found")
    
    if input.song_id in playlist.get('song_ids', []):
        raise HTTPException(status_code=400, detail="Song already in playlist")
    
    await db.playlists.update_one(
        {"id": playlist_id},
        {"$push": {"song_ids": input.song_id}}
    )
    
    return {"message": "Song added to playlist"}

@api_router.delete("/playlists/{playlist_id}/songs/{song_id}")
async def remove_song_from_playlist(playlist_id: str, song_id: str):
    result = await db.playlists.update_one(
        {"id": playlist_id},
        {"$pull": {"song_ids": song_id}}
    )
    
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Playlist or song not found")
    
    return {"message": "Song removed from playlist"}

@api_router.delete("/playlists/{playlist_id}")
async def delete_playlist(playlist_id: str):
    result = await db.playlists.delete_one({"id": playlist_id})
    
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Playlist not found")
    
    return {"message": "Playlist deleted"}

# Favorites endpoints
@api_router.get("/favorites", response_model=List[Favorite])
async def get_favorites():
    favorites = await db.favorites.find({}, {"_id": 0}).to_list(1000)
    
    for favorite in favorites:
        if isinstance(favorite['created_at'], str):
            favorite['created_at'] = datetime.fromisoformat(favorite['created_at'])
    
    return favorites

@api_router.post("/favorites", response_model=Favorite)
async def add_favorite(input: FavoriteCreate):
    # Check if song exists
    song = await db.songs.find_one({"id": input.song_id}, {"_id": 0})
    if not song:
        raise HTTPException(status_code=404, detail="Song not found")
    
    # Check if already favorited
    existing = await db.favorites.find_one({"song_id": input.song_id}, {"_id": 0})
    if existing:
        raise HTTPException(status_code=400, detail="Song already in favorites")
    
    favorite_dict = input.model_dump()
    favorite_obj = Favorite(**favorite_dict)
    
    doc = favorite_obj.model_dump()
    doc['created_at'] = doc['created_at'].isoformat()
    
    await db.favorites.insert_one(doc)
    return favorite_obj

@api_router.delete("/favorites/{song_id}")
async def remove_favorite(song_id: str):
    result = await db.favorites.delete_one({"song_id": song_id})
    
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Favorite not found")
    
    return {"message": "Removed from favorites"}

# Initialize database with sample data
@api_router.post("/init-data")
async def init_sample_data():
    # Check if data already exists
    existing_songs = await db.songs.count_documents({})
    if existing_songs > 0:
        return {"message": "Data already initialized"}
    
    # Sample songs
    sample_songs = [
        {
            "id": str(uuid.uuid4()),
            "title": "Neon Dreams",
            "artist": "Synthwave Collective",
            "album": "Electric Nights",
            "duration": 245,
            "cover_url": "https://images.unsplash.com/photo-1764936510087-e113d6da4af9?crop=entropy&cs=srgb&fm=jpg&q=85",
            "audio_url": "https://www.soundhelix.com/examples/mp3/SoundHelix-Song-1.mp3",
            "created_at": datetime.now(timezone.utc).isoformat()
        },
        {
            "id": str(uuid.uuid4()),
            "title": "Midnight City",
            "artist": "Urban Echo",
            "album": "City Lights",
            "duration": 198,
            "cover_url": "https://images.unsplash.com/photo-1760574765516-3e12ccb32073?crop=entropy&cs=srgb&fm=jpg&q=85",
            "audio_url": "https://www.soundhelix.com/examples/mp3/SoundHelix-Song-2.mp3",
            "created_at": datetime.now(timezone.utc).isoformat()
        },
        {
            "id": str(uuid.uuid4()),
            "title": "Retro Wave",
            "artist": "Neon Pulse",
            "album": "80s Revival",
            "duration": 223,
            "cover_url": "https://images.unsplash.com/photo-1767481626894-bab78ae919be?crop=entropy&cs=srgb&fm=jpg&q=85",
            "audio_url": "https://www.soundhelix.com/examples/mp3/SoundHelix-Song-3.mp3",
            "created_at": datetime.now(timezone.utc).isoformat()
        },
        {
            "id": str(uuid.uuid4()),
            "title": "Digital Love",
            "artist": "Cyber Hearts",
            "album": "Virtual Romance",
            "duration": 267,
            "cover_url": "https://images.unsplash.com/photo-1749222200222-93399b2b65dd?crop=entropy&cs=srgb&fm=jpg&q=85",
            "audio_url": "https://www.soundhelix.com/examples/mp3/SoundHelix-Song-4.mp3",
            "created_at": datetime.now(timezone.utc).isoformat()
        },
        {
            "id": str(uuid.uuid4()),
            "title": "Cosmic Journey",
            "artist": "Space Travelers",
            "album": "Beyond Stars",
            "duration": 301,
            "cover_url": "https://images.unsplash.com/photo-1748854091034-abd9d3ea6be8?crop=entropy&cs=srgb&fm=jpg&q=85",
            "audio_url": "https://www.soundhelix.com/examples/mp3/SoundHelix-Song-5.mp3",
            "created_at": datetime.now(timezone.utc).isoformat()
        },
        {
            "id": str(uuid.uuid4()),
            "title": "Pulse",
            "artist": "Beat Makers",
            "album": "Rhythm Nation",
            "duration": 189,
            "cover_url": "https://images.unsplash.com/photo-1764936510087-e113d6da4af9?crop=entropy&cs=srgb&fm=jpg&q=85",
            "audio_url": "https://www.soundhelix.com/examples/mp3/SoundHelix-Song-6.mp3",
            "created_at": datetime.now(timezone.utc).isoformat()
        },
        {
            "id": str(uuid.uuid4()),
            "title": "Echoes",
            "artist": "Sound Waves",
            "album": "Reflections",
            "duration": 234,
            "cover_url": "https://images.unsplash.com/photo-1760574765516-3e12ccb32073?crop=entropy&cs=srgb&fm=jpg&q=85",
            "audio_url": "https://www.soundhelix.com/examples/mp3/SoundHelix-Song-7.mp3",
            "created_at": datetime.now(timezone.utc).isoformat()
        },
        {
            "id": str(uuid.uuid4()),
            "title": "Velocity",
            "artist": "Fast Lane",
            "album": "Speed of Sound",
            "duration": 212,
            "cover_url": "https://images.unsplash.com/photo-1767481626894-bab78ae919be?crop=entropy&cs=srgb&fm=jpg&q=85",
            "audio_url": "https://www.soundhelix.com/examples/mp3/SoundHelix-Song-8.mp3",
            "created_at": datetime.now(timezone.utc).isoformat()
        }
    ]
    
    await db.songs.insert_many(sample_songs)
    
    # Sample playlists
    sample_playlists = [
        {
            "id": str(uuid.uuid4()),
            "name": "Synthwave Essentials",
            "description": "The best synthwave tracks",
            "cover_url": "https://images.unsplash.com/photo-1764936510087-e113d6da4af9?crop=entropy&cs=srgb&fm=jpg&q=85",
            "song_ids": [sample_songs[0]["id"], sample_songs[2]["id"]],
            "created_at": datetime.now(timezone.utc).isoformat()
        },
        {
            "id": str(uuid.uuid4()),
            "name": "Night Drive",
            "description": "Perfect playlist for late night drives",
            "cover_url": "https://images.unsplash.com/photo-1760574765516-3e12ccb32073?crop=entropy&cs=srgb&fm=jpg&q=85",
            "song_ids": [sample_songs[1]["id"], sample_songs[3]["id"]],
            "created_at": datetime.now(timezone.utc).isoformat()
        }
    ]
    
    await db.playlists.insert_many(sample_playlists)
    
    return {"message": "Sample data initialized", "songs": len(sample_songs), "playlists": len(sample_playlists)}

# Include the router in the main app
app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
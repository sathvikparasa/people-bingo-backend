"""
People Bingo - FastAPI Backend

This is the original Python/FastAPI backend with WebSocket support.
To use this backend instead of the Next.js API routes:

1. Install dependencies:
   pip install fastapi uvicorn websockets

2. Run the server:
   python scripts/backend.py

3. Update your environment variables to point to this backend:
   NEXT_PUBLIC_API_URL=http://localhost:8000/api
   NEXT_PUBLIC_WS_URL=ws://localhost:8000

The backend will run on http://localhost:8000
"""

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Dict, List, Optional
import random
import string
import time
from datetime import datetime
import asyncio
import json

app = FastAPI()

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Game storage
games: Dict[str, dict] = {}

# WebSocket connections
class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, List[WebSocket]] = {}
    
    async def connect(self, websocket: WebSocket, game_code: str):
        await websocket.accept()
        if game_code not in self.active_connections:
            self.active_connections[game_code] = []
        self.active_connections[game_code].append(websocket)
    
    def disconnect(self, websocket: WebSocket, game_code: str):
        if game_code in self.active_connections:
            self.active_connections[game_code].remove(websocket)
    
    async def broadcast(self, game_code: str, message: dict):
        if game_code in self.active_connections:
            dead_connections = []
            for connection in self.active_connections[game_code]:
                try:
                    await connection.send_json(message)
                except:
                    dead_connections.append(connection)
            
            # Clean up dead connections
            for conn in dead_connections:
                self.active_connections[game_code].remove(conn)

manager = ConnectionManager()

# Models
class CreateGameRequest(BaseModel):
    duration: int = 15

class JoinGameRequest(BaseModel):
    game_code: str
    player_name: str

class UpdateCellRequest(BaseModel):
    game_code: str
    index: int
    value: str

class UpdatePlayerCellRequest(BaseModel):
    game_code: str
    player_name: str
    cell_index: int
    name_value: str

class StartGameRequest(BaseModel):
    game_code: str

class FinishGameRequest(BaseModel):
    game_code: str
    player_name: str

# Helper functions
def generate_game_code():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))

def get_default_cells():
    return [
        "Has run a marathon", "Can name 3 AI models", "Speaks 3+ languages",
        "Has been skydiving", "Plays a musical instrument", "Has visited 10+ countries",
        "Can solve a Rubik's cube", "Has a pet", "Loves spicy food",
        "Morning person", "Has broken a bone", "Can cook 5+ dishes",
        "FREE SPACE", "Loves horror movies", "Has met a celebrity",
        "Night owl", "Can do a handstand", "Has lived abroad",
        "Knows how to code", "Loves karaoke", "Has run a business",
        "Vegetarian/Vegan", "Can name all continents", "Has a hidden talent",
        "Loves ice cream"
    ]

# Routes
@app.post("/api/games/create")
async def create_game(request: CreateGameRequest):
    code = generate_game_code()
    while code in games:
        code = generate_game_code()
    
    games[code] = {
        "code": code,
        "cells": get_default_cells(),
        "players": {},
        "started": False,
        "duration": request.duration,
        "start_time": None,
        "finished": [],
        "created_at": time.time()
    }
    
    return {"game_code": code, "game": games[code]}

@app.get("/api/games/{game_code}")
async def get_game(game_code: str):
    if game_code not in games:
        raise HTTPException(status_code=404, detail="Game not found")
    return games[game_code]

@app.post("/api/games/join")
async def join_game(request: JoinGameRequest):
    game_code = request.game_code.upper()
    
    if game_code not in games:
        raise HTTPException(status_code=404, detail="Game not found")
    
    game = games[game_code]
    
    if request.player_name in game["players"]:
        return {"message": "Player already in game", "game": game}
    
    game["players"][request.player_name] = {
        "name": request.player_name,
        "grid": [""] * 25,
        "completed": False,
        "finish_time": None,
        "joined_at": time.time()
    }
    
    # Broadcast update
    await manager.broadcast(game_code, {
        "type": "player_joined",
        "player_name": request.player_name,
        "player_count": len(game["players"])
    })
    
    return {"message": "Joined successfully", "game": game}

@app.post("/api/games/update-cell")
async def update_cell(request: UpdateCellRequest):
    game_code = request.game_code.upper()
    
    if game_code not in games:
        raise HTTPException(status_code=404, detail="Game not found")
    
    game = games[game_code]
    
    if game["started"]:
        raise HTTPException(status_code=400, detail="Cannot edit cells after game started")
    
    if request.index < 0 or request.index >= 25:
        raise HTTPException(status_code=400, detail="Invalid cell index")
    
    if request.index == 12:
        raise HTTPException(status_code=400, detail="Cannot edit FREE SPACE")
    
    game["cells"][request.index] = request.value
    
    # Broadcast update
    await manager.broadcast(game_code, {
        "type": "cell_updated",
        "index": request.index,
        "value": request.value
    })
    
    return {"message": "Cell updated", "game": game}

@app.post("/api/games/start")
async def start_game(request: StartGameRequest):
    game_code = request.game_code.upper()
    
    if game_code not in games:
        raise HTTPException(status_code=404, detail="Game not found")
    
    game = games[game_code]
    
    if game["started"]:
        raise HTTPException(status_code=400, detail="Game already started")
    
    if len(game["players"]) == 0:
        raise HTTPException(status_code=400, detail="No players in game")
    
    game["started"] = True
    game["start_time"] = time.time()
    
    # Broadcast game start
    await manager.broadcast(game_code, {
        "type": "game_started",
        "start_time": game["start_time"]
    })
    
    return {"message": "Game started", "game": game}

@app.post("/api/games/update-player-cell")
async def update_player_cell(request: UpdatePlayerCellRequest):
    game_code = request.game_code.upper()
    
    if game_code not in games:
        raise HTTPException(status_code=404, detail="Game not found")
    
    game = games[game_code]
    
    if not game["started"]:
        raise HTTPException(status_code=400, detail="Game not started yet")
    
    if request.player_name not in game["players"]:
        raise HTTPException(status_code=404, detail="Player not found")
    
    player = game["players"][request.player_name]
    
    if player["completed"]:
        raise HTTPException(status_code=400, detail="Player already finished")
    
    if request.cell_index < 0 or request.cell_index >= 25:
        raise HTTPException(status_code=400, detail="Invalid cell index")
    
    player["grid"][request.cell_index] = request.name_value
    
    return {"message": "Cell updated", "player": player}

@app.post("/api/games/finish")
async def finish_game(request: FinishGameRequest):
    game_code = request.game_code.upper()
    
    if game_code not in games:
        raise HTTPException(status_code=404, detail="Game not found")
    
    game = games[game_code]
    
    if request.player_name not in game["players"]:
        raise HTTPException(status_code=404, detail="Player not found")
    
    player = game["players"][request.player_name]
    
    if player["completed"]:
        raise HTTPException(status_code=400, detail="Player already finished")
    
    # Verify all cells are filled (except index 12 which is FREE)
    for i, cell in enumerate(player["grid"]):
        if i != 12 and not cell.strip():
            raise HTTPException(status_code=400, detail="Not all cells are filled")
    
    finish_time = time.time()
    player["completed"] = True
    player["finish_time"] = finish_time
    
    game["finished"].append({
        "name": request.player_name,
        "time": finish_time,
        "elapsed": finish_time - game["start_time"]
    })
    
    # Sort finished list by time
    game["finished"].sort(key=lambda x: x["elapsed"])
    
    # Broadcast finish
    await manager.broadcast(game_code, {
        "type": "player_finished",
        "player_name": request.player_name,
        "finish_time": finish_time,
        "position": len(game["finished"])
    })
    
    return {"message": "Game finished", "position": len(game["finished"]), "player": player}

@app.get("/api/games/{game_code}/insights")
async def get_insights(game_code: str):
    if game_code not in games:
        raise HTTPException(status_code=404, detail="Game not found")
    
    game = games[game_code]
    insights = []
    
    for idx, cell in enumerate(game["cells"]):
        if idx == 12:  # Skip FREE SPACE
            continue
        
        entries = []
        for player in game["players"].values():
            name = player["grid"][idx]
            if name.strip():
                entries.append(name)
        
        # Count occurrences
        counts = {}
        for name in entries:
            counts[name] = counts.get(name, 0) + 1
        
        insights.append({
            "index": idx,
            "cell": cell,
            "total_entries": len(entries),
            "unique_entries": len(counts),
            "name_counts": counts
        })
    
    return {"insights": insights}

@app.websocket("/ws/{game_code}")
async def websocket_endpoint(websocket: WebSocket, game_code: str):
    await manager.connect(websocket, game_code.upper())
    try:
        while True:
            # Keep connection alive
            data = await websocket.receive_text()
            # Echo back to confirm connection
            await websocket.send_json({"type": "ping", "message": "connected"})
    except WebSocketDisconnect:
        manager.disconnect(websocket, game_code.upper())

@app.get("/")
async def root():
    return {"message": "People Bingo API", "active_games": len(games)}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

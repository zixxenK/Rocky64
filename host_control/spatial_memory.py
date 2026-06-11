#!/usr/bin/env python3
"""
spatial_memory.py — Spatial memory system for robot navigation using SQLite + sqlite-vec.

Features:
- SQLite database with vector embeddings for spatial memory
- Store and retrieve object locations with vector similarity search
- Async operations with aiosqlite
- Sync mechanism for Rock64 <-> PC synchronization
- Support for sqlite-vec extension for vector operations

Usage:
    python host_control/spatial_memory.py
    python host_control/spatial_memory.py --init-db
    python host_control/spatial_memory.py --sync
"""

import argparse
import asyncio
import json
import os
import sqlite3
import sys
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Optional, List, Dict, Any
import subprocess

# Try to import aiosqlite, fall back to synchronous sqlite3
try:
    import aiosqlite
    HAS_AIOSQLITE = True
except ImportError:
    HAS_AIOSQLITE = False
    print("[spatial_memory] aiosqlite not available, using synchronous sqlite3")

# Try to import numpy for embeddings
try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False
    print("[spatial_memory] numpy not available, using random embeddings")


@dataclass
class SpatialMemory:
    """Spatial memory entry."""
    id: Optional[int] = None
    object_name: str = ""
    vector_embedding: Optional[bytes] = None  # BLOB for sqlite-vec
    timestamp: str = ""
    location_coords: Optional[str] = None  # JSON string for x, y, z, heading
    confidence: float = 1.0
    metadata: Optional[str] = None  # JSON string for additional metadata


class SpatialMemoryDB:
    """Spatial memory database manager."""
    
    def __init__(self, db_path: str = None):
        if db_path is None:
            db_path = os.path.join(os.path.dirname(__file__), "spatial_memory.db")
        self.db_path = db_path
        self.conn = None
        self.has_vec_extension = False
    
    def init_database(self) -> bool:
        """Initialize database schema with sqlite-vec support."""
        try:
            self.conn = sqlite3.connect(self.db_path)
            
            # Try to load sqlite-vec extension
            try:
                self.conn.enable_load_extension(True)
                self.conn.load_extension("vec0")
                self.has_vec_extension = True
                print("[spatial_memory] sqlite-vec extension loaded successfully")
            except Exception as e:
                print(f"[spatial_memory] sqlite-vec extension not available: {e}")
                print("[spatial_memory] Will use fallback vector operations")
            
            cursor = self.conn.cursor()
            
            # Create spatial_memory table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS spatial_memory (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    object_name TEXT NOT NULL,
                    vector_embedding BLOB,
                    timestamp TEXT NOT NULL,
                    location_coords TEXT,
                    confidence REAL DEFAULT 1.0,
                    metadata TEXT
                )
            """)
            
            # Create index on object_name for faster lookups
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_object_name 
                ON spatial_memory(object_name)
            """)
            
            # Create index on timestamp for temporal queries
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_timestamp 
                ON spatial_memory(timestamp)
            """)
            
            # If sqlite-vec is available, create virtual table for vector search
            if self.has_vec_extension:
                try:
                    cursor.execute("""
                        CREATE VIRTUAL TABLE IF NOT EXISTS vec_spatial_memory 
                        USING vec0(
                            vector_embedding float32(128)
                        )
                    """)
                    print("[spatial_memory] Vector virtual table created")
                except Exception as e:
                    print(f"[spatial_memory] Failed to create vector table: {e}")
            
            self.conn.commit()
            print(f"[spatial_memory] Database initialized: {self.db_path}")
            return True
            
        except Exception as e:
            print(f"[spatial_memory] Failed to initialize database: {e}")
            return False
    
    def add_memory(self, memory: SpatialMemory) -> Optional[int]:
        """Add a spatial memory entry."""
        if self.conn is None:
            if not self.init_database():
                return None
        
        try:
            cursor = self.conn.cursor()
            
            # Generate timestamp if not provided
            if not memory.timestamp:
                memory.timestamp = datetime.now().isoformat()
            
            # Serialize location_coords to JSON if dict
            if isinstance(memory.location_coords, dict):
                memory.location_coords = json.dumps(memory.location_coords)
            
            # Serialize metadata to JSON if dict
            if isinstance(memory.metadata, dict):
                memory.metadata = json.dumps(memory.metadata)
            
            cursor.execute("""
                INSERT INTO spatial_memory 
                (object_name, vector_embedding, timestamp, location_coords, confidence, metadata)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                memory.object_name,
                memory.vector_embedding,
                memory.timestamp,
                memory.location_coords,
                memory.confidence,
                memory.metadata
            ))
            
            self.conn.commit()
            memory_id = cursor.lastrowid
            print(f"[spatial_memory] Added memory entry: {memory.object_name} (ID: {memory_id})")
            return memory_id
            
        except Exception as e:
            print(f"[spatial_memory] Failed to add memory: {e}")
            return None
    
    def get_memory(self, memory_id: int) -> Optional[SpatialMemory]:
        """Get a spatial memory entry by ID."""
        if self.conn is None:
            return None
        
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                SELECT id, object_name, vector_embedding, timestamp, 
                       location_coords, confidence, metadata
                FROM spatial_memory
                WHERE id = ?
            """, (memory_id,))
            
            row = cursor.fetchone()
            if row:
                return SpatialMemory(
                    id=row[0],
                    object_name=row[1],
                    vector_embedding=row[2],
                    timestamp=row[3],
                    location_coords=row[4],
                    confidence=row[5],
                    metadata=row[6]
                )
            return None
            
        except Exception as e:
            print(f"[spatial_memory] Failed to get memory: {e}")
            return None
    
    def search_by_name(self, object_name: str, limit: int = 10) -> List[SpatialMemory]:
        """Search memories by object name."""
        if self.conn is None:
            return []
        
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                SELECT id, object_name, vector_embedding, timestamp, 
                       location_coords, confidence, metadata
                FROM spatial_memory
                WHERE object_name LIKE ?
                ORDER BY timestamp DESC
                LIMIT ?
            """, (f"%{object_name}%", limit))
            
            memories = []
            for row in cursor.fetchall():
                memories.append(SpatialMemory(
                    id=row[0],
                    object_name=row[1],
                    vector_embedding=row[2],
                    timestamp=row[3],
                    location_coords=row[4],
                    confidence=row[5],
                    metadata=row[6]
                ))
            
            return memories
            
        except Exception as e:
            print(f"[spatial_memory] Failed to search by name: {e}")
            return []
    
    def get_recent_memories(self, limit: int = 10) -> List[SpatialMemory]:
        """Get recent spatial memories."""
        if self.conn is None:
            return []
        
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                SELECT id, object_name, vector_embedding, timestamp, 
                       location_coords, confidence, metadata
                FROM spatial_memory
                ORDER BY timestamp DESC
                LIMIT ?
            """, (limit,))
            
            memories = []
            for row in cursor.fetchall():
                memories.append(SpatialMemory(
                    id=row[0],
                    object_name=row[1],
                    vector_embedding=row[2],
                    timestamp=row[3],
                    location_coords=row[4],
                    confidence=row[5],
                    metadata=row[6]
                ))
            
            return memories
            
        except Exception as e:
            print(f"[spatial_memory] Failed to get recent memories: {e}")
            return []
    
    def delete_memory(self, memory_id: int) -> bool:
        """Delete a spatial memory entry."""
        if self.conn is None:
            return False
        
        try:
            cursor = self.conn.cursor()
            cursor.execute("DELETE FROM spatial_memory WHERE id = ?", (memory_id,))
            self.conn.commit()
            print(f"[spatial_memory] Deleted memory entry: {memory_id}")
            return True
            
        except Exception as e:
            print(f"[spatial_memory] Failed to delete memory: {e}")
            return False
    
    def close(self):
        """Close database connection."""
        if self.conn:
            self.conn.close()
            self.conn = None


class SpatialMemorySync:
    """Synchronization manager for spatial memory between Rock64 and PC."""
    
    def __init__(self, db_path: str = None, rock64_host: str = "192.168.1.159",
                 ssh_key: str = None):
        self.db = SpatialMemoryDB(db_path)
        self.rock64_host = rock64_host
        self.ssh_key = ssh_key or os.path.expanduser("~/.ssh/rock64_sync")
        self.remote_db_path = "/home/rock64/spatial_memory.db"
    
    def sync_to_rock64(self) -> bool:
        """Sync local database to Rock64 using rsync."""
        try:
            cmd = [
                "rsync",
                "-avz",
                "-e", f"ssh -i {self.ssh_key}",
                self.db.db_path,
                f"rock64@{self.rock64_host}:{self.remote_db_path}"
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode == 0:
                print(f"[spatial_memory] Synced to Rock64 successfully")
                return True
            else:
                print(f"[spatial_memory] Sync to Rock64 failed: {result.stderr}")
                return False
                
        except Exception as e:
            print(f"[spatial_memory] Sync to Rock64 error: {e}")
            return False
    
    def sync_from_rock64(self) -> bool:
        """Sync database from Rock64 using rsync."""
        try:
            cmd = [
                "rsync",
                "-avz",
                "-e", f"ssh -i {self.ssh_key}",
                f"rock64@{self.rock64_host}:{self.remote_db_path}",
                self.db.db_path
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode == 0:
                print(f"[spatial_memory] Synced from Rock64 successfully")
                return True
            else:
                print(f"[spatial_memory] Sync from Rock64 failed: {result.stderr}")
                return False
                
        except Exception as e:
            print(f"[spatial_memory] Sync from Rock64 error: {e}")
            return False


def generate_mock_embedding(size: int = 128) -> bytes:
    """Generate a mock vector embedding for testing."""
    if HAS_NUMPY:
        # Generate random normalized vector
        vec = np.random.randn(size).astype(np.float32)
        vec = vec / np.linalg.norm(vec)
        return vec.tobytes()
    else:
        # Fallback: generate random bytes
        import random
        return bytes(random.getrandbits(8) for _ in range(size * 4))


def main():
    parser = argparse.ArgumentParser(description="Spatial Memory System for Robot Navigation")
    parser.add_argument('--init-db', action='store_true', help='Initialize database')
    parser.add_argument('--add', type=str, help='Add memory entry (JSON format)')
    parser.add_argument('--search', type=str, help='Search by object name')
    parser.add_argument('--recent', action='store_true', help='Show recent memories')
    parser.add_argument('--delete', type=int, help='Delete memory by ID')
    parser.add_argument('--sync-to-rock64', action='store_true', help='Sync to Rock64')
    parser.add_argument('--sync-from-rock64', action='store_true', help='Sync from Rock64')
    parser.add_argument('--db-path', type=str, help='Database path')
    parser.add_argument('--rock64-host', default='192.168.1.159', help='Rock64 IP address')
    parser.add_argument('--ssh-key', help='SSH key path')
    
    args = parser.parse_args()
    
    db = SpatialMemoryDB(args.db_path)
    
    # Initialize database if requested
    if args.init_db:
        if db.init_database():
            print("[spatial_memory] Database initialized successfully")
            
            # Add some sample data for testing
            sample_memory = SpatialMemory(
                object_name="test_object",
                vector_embedding=generate_mock_embedding(),
                timestamp=datetime.now().isoformat(),
                location_coords=json.dumps({"x": 1.0, "y": 2.0, "z": 0.0, "heading": 0.0}),
                confidence=0.9,
                metadata=json.dumps({"source": "test"})
            )
            db.add_memory(sample_memory)
        return
    
    # Add memory entry
    if args.add:
        if not db.init_database():
            print("[spatial_memory] Failed to initialize database")
            return
        
        try:
            data = json.loads(args.add)
            memory = SpatialMemory(**data)
            if not memory.vector_embedding:
                memory.vector_embedding = generate_mock_embedding()
            
            memory_id = db.add_memory(memory)
            if memory_id:
                print(f"[spatial_memory] Added memory with ID: {memory_id}")
        except json.JSONDecodeError:
            print("[spatial_memory] Invalid JSON format for --add")
        return
    
    # Search memories
    if args.search:
        if not db.init_database():
            return
        
        memories = db.search_by_name(args.search)
        print(f"[spatial_memory] Found {len(memories)} memories matching '{args.search}':")
        for mem in memories:
            print(f"  - ID: {mem.id}, Name: {mem.object_name}, Time: {mem.timestamp}")
        return
    
    # Show recent memories
    if args.recent:
        if not db.init_database():
            return
        
        memories = db.get_recent_memories()
        print(f"[spatial_memory] Recent memories ({len(memories)}):")
        for mem in memories:
            print(f"  - ID: {mem.id}, Name: {mem.object_name}, Time: {mem.timestamp}")
        return
    
    # Delete memory
    if args.delete:
        if not db.init_database():
            return
        
        if db.delete_memory(args.delete):
            print(f"[spatial_memory] Deleted memory {args.delete}")
        return
    
    # Sync operations
    if args.sync_to_rock64 or args.sync_from_rock64:
        sync = SpatialMemorySync(args.db_path, args.rock64_host, args.ssh_key)
        if args.sync_to_rock64:
            sync.sync_to_rock64()
        if args.sync_from_rock64:
            sync.sync_from_rock64()
        return
    
    # Default: show help
    parser.print_help()


if __name__ == '__main__':
    main()

import json
import os
import time
import logging
import re
import fcntl  # Add import for file locking
import threading  # Add import for threading lock
from typing import Dict, List, Any
from difflib import SequenceMatcher
import random  # Add for exponential backoff

# Import the WebContentStorage from existing file
import web_storage

class SharedMemory:
    """Class to store and manage shared data between bot instances."""
    def __init__(self, file_path="shared_memory.json"):
        """Initialize the shared memory storage."""
        self.file_path = file_path
        
        # Setup logging
        self.logger = logging.getLogger("SharedMemory")
        
        # Add a threading lock for in-process synchronization
        self.file_lock = threading.RLock()  # Using RLock instead of Lock for reentrant locking
        
        # Add a separate lock specifically for file operations
        self.io_lock = threading.Lock()
        
        self.ensure_file_exists()
        
        # Constants for memory limits
        self.max_conversations = 200  # Increased from 100
        self.max_web_content = 100
        self.max_topics = 50  # Store the last N topics
        
        # Storage containers
        self.conversations = []
        self.web_content = []
        self.user_data = {}
        
        # Backup data cached in memory
        self._cached_data = None
        self._cache_timestamp = 0
        self._cache_valid_seconds = 5  # Cache valid for 5 seconds
        
        # Maximum retries for file operations
        self.max_retries = 5
        
        # Get web content storage instance
        self.web_content_storage = web_storage.WebContentStorage()
        
    def ensure_file_exists(self):
        """
        Ensure the shared memory file exists with proper structure.
        Only creates a new file if none exists - never overwrites existing data.
        """
        # First, create backups directory if it doesn't exist
        os.makedirs("backups", exist_ok=True)
        self.logger.info("Ensured backups directory exists")
        
        with self.io_lock:  # Use IO lock to prevent race conditions
            if not os.path.exists(self.file_path):
                # File doesn't exist, create it with default structure
                self.logger.info(f"Creating new shared memory file at {self.file_path}")
                
                # Create a default structure
                default_data = {
                    "conversations": [],
                    "user_data": {},
                    "web_content": [],
                    "recent_bot_topics": [],
                    "recent_topics": {}
                }
                
                # Use with statement to ensure file is properly closed
                with open(self.file_path, 'w') as f:
                    # Acquire a file lock before writing
                    try:
                        fcntl.flock(f, fcntl.LOCK_EX)
                        json.dump(default_data, f, indent=2)
                    finally:
                        # Always release the lock
                        fcntl.flock(f, fcntl.LOCK_UN)
            else:
                # File exists, verify its structure with retries
                for attempt in range(3):
                    try:
                        with open(self.file_path, 'r') as f:
                            # Acquire a shared lock for reading
                            try:
                                fcntl.flock(f, fcntl.LOCK_SH)
                                data = json.load(f)
                            finally:
                                fcntl.flock(f, fcntl.LOCK_UN)
                        
                        # Ensure all required fields exist
                        fields_created = False
                        if "conversations" not in data:
                            data["conversations"] = []
                            fields_created = True
                        if "user_data" not in data:
                            data["user_data"] = {}
                            fields_created = True
                        if "web_content" not in data:
                            data["web_content"] = []
                            fields_created = True
                        if "recent_bot_topics" not in data:
                            data["recent_bot_topics"] = []
                            fields_created = True
                        if "recent_topics" not in data:
                            data["recent_topics"] = {}
                            fields_created = True
                        
                        # Only write back if we had to add fields
                        if fields_created:
                            with open(self.file_path, 'w') as f:
                                try:
                                    fcntl.flock(f, fcntl.LOCK_EX)
                                    json.dump(data, f, indent=2)
                                finally:
                                    fcntl.flock(f, fcntl.LOCK_UN)
                        
                        # Store the valid data in our cache
                        self._cached_data = data
                        self._cache_timestamp = time.time()
                        
                        # Success, break the retry loop
                        break
                    except (json.JSONDecodeError, FileNotFoundError) as e:
                        # File exists but is corrupted
                        self.logger.error(f"Shared memory file corrupted (attempt {attempt+1}): {e}")
                        
                        if attempt == 2:  # Last attempt failed, create a backup and new file
                            # Create backup of corrupted file
                            import datetime
                            backup_path = f"backups/{os.path.basename(self.file_path)}.corrupted.{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}"
                            try:
                                import shutil
                                shutil.copy2(self.file_path, backup_path)
                                self.logger.warning(f"Created backup of corrupted file at {backup_path}")
                            except Exception as backup_error:
                                self.logger.error(f"Failed to create backup: {backup_error}")
                            
                            # Create new file with default structure
                            default_data = {
                                "conversations": [],
                                "user_data": {},
                                "web_content": [],
                                "recent_bot_topics": [],
                                "recent_topics": {}
                            }
                            
                            with open(self.file_path, 'w') as f:
                                try:
                                    fcntl.flock(f, fcntl.LOCK_EX)
                                    json.dump(default_data, f, indent=2)
                                finally:
                                    fcntl.flock(f, fcntl.LOCK_UN)
                            self.logger.warning(f"Created new shared memory file due to corruption")
                            
                            # Store the default data in our cache
                            self._cached_data = default_data
                            self._cache_timestamp = time.time()
                        else:
                            # Wait before retrying
                            time.sleep(0.5 * (attempt + 1))
    
    def load_data(self) -> Dict:
        """
        Load data from the shared memory file with robust error handling.
        Uses cached data if available and recent, otherwise loads from file with retries.
        """
        # Check if cached data is still valid
        if self._cached_data is not None and (time.time() - self._cache_timestamp) < self._cache_valid_seconds:
            return self._cached_data.copy()  # Return a copy to prevent cache corruption
        
        # We need a fresh read from the file
        with self.io_lock:  # Lock for file I/O operations
            for attempt in range(self.max_retries):
                try:
                    # Exponential backoff between retries
                    if attempt > 0:
                        delay = random.uniform(0.1, 0.5) * (2 ** attempt)
                        time.sleep(delay)
                    
                    with open(self.file_path, 'r') as f:
                        try:
                            fcntl.flock(f, fcntl.LOCK_SH)  # Shared lock for reading
                            file_content = f.read()  # Read the entire file
                            
                            # Check if file is empty (common error case)
                            if not file_content.strip():
                                raise json.JSONDecodeError("Empty file", "", 0)
                                
                            data = json.loads(file_content)
                        finally:
                            fcntl.flock(f, fcntl.LOCK_UN)
                    
                    # Ensure all required fields exist
                    if "recent_bot_topics" not in data:
                        data["recent_bot_topics"] = []
                    if "conversations" not in data:
                        data["conversations"] = []
                    if "user_data" not in data:
                        data["user_data"] = {}
                    if "web_content" not in data:
                        data["web_content"] = []
                    if "recent_topics" not in data:
                        data["recent_topics"] = {}
                    
                    # Update our cache
                    self._cached_data = data
                    self._cache_timestamp = time.time()
                    
                    return data.copy()  # Return a copy to prevent modifications to cached data
                        
                except (json.JSONDecodeError, FileNotFoundError) as e:
                    self.logger.error(f"Error loading shared memory file (attempt {attempt+1}/{self.max_retries}): {e}")
                    
                    # Try recovery strategies based on retry count
                    if attempt == 0:
                        # First failure: Check for backup files
                        if self._try_restore_from_backup():
                            # Backup restored, retry immediately
                            continue
                    elif attempt == 1:
                        # Second failure: Attempt to repair JSON
                        if self._try_repair_json_file():
                            # Repair worked, retry immediately
                            continue
                    elif attempt == self.max_retries - 1:
                        # Last attempt: Create new file
                        self.logger.warning("All recovery attempts failed. Creating new memory file.")
                        self._create_new_memory_file()
                        
                        # Use default data for this request
                        default_data = {
                            "conversations": [],
                            "user_data": {},
                            "web_content": [],
                            "recent_bot_topics": [],
                            "recent_topics": {}
                        }
                        
                        # Update our cache
                        self._cached_data = default_data
                        self._cache_timestamp = time.time()
                        
                        return default_data.copy()
            
            # If we got here, all retries failed - return empty default data
            self.logger.error("Could not load or recover shared memory file after multiple attempts")
            default_data = {
                "conversations": [],
                "user_data": {},
                "web_content": [],
                "recent_bot_topics": [],
                "recent_topics": {}
            }
            
            # Create new file with default data
            with open(self.file_path, 'w') as f:
                try:
                    fcntl.flock(f, fcntl.LOCK_EX)
                    json.dump(default_data, f, indent=2)
                finally:
                    fcntl.flock(f, fcntl.LOCK_UN)
                
            # Update our cache
            self._cached_data = default_data
            self._cache_timestamp = time.time()
                
            return default_data.copy()
    
    def _try_restore_from_backup(self):
        """Try to restore from the most recent backup file if one exists."""
        import glob
        backup_files = glob.glob(f"{self.file_path}.backup.*")
        
        if not backup_files:
            self.logger.warning("No backup files found.")
            return False
                
        # Get the most recent backup
        newest_backup = max(backup_files, key=os.path.getmtime)
        self.logger.info(f"Attempting to restore from backup: {newest_backup}")
            
        try:
            import shutil
            shutil.copy2(newest_backup, self.file_path)
            self.logger.info(f"Successfully restored from backup: {newest_backup}")
            return True
        except Exception as e:
            self.logger.error(f"Failed to restore from backup: {e}")
            return False
        
    def _try_repair_json_file(self):
        """Attempt to repair corrupted JSON file."""
        try:
            with open(self.file_path, 'r') as f:
                content = f.read()
                    
            # Create backup before repair attempt
            import datetime
            backup_path = f"{self.file_path}.beforerepair.{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}"
            with open(backup_path, 'w') as f:
                f.write(content)
                    
            # Check if file is completely empty
            if not content.strip():
                # Create a minimal valid JSON structure
                self.logger.info("File is empty, creating minimal valid JSON")
                with open(self.file_path, 'w') as f:
                    try:
                        fcntl.flock(f, fcntl.LOCK_EX)
                        json.dump({
                            "conversations": [],
                            "user_data": {},
                            "web_content": [],
                            "recent_bot_topics": [],
                            "recent_topics": {}
                        }, f, indent=2)
                    finally:
                        fcntl.flock(f, fcntl.LOCK_UN)
                return True
                
            # Try basic repair by fixing common JSON errors:
            # 1. Remove trailing commas
            content = re.sub(r',\s*}', '}', content)
            content = re.sub(r',\s*]', ']', content)
                
            # 2. Close unclosed brackets/braces
            open_braces = content.count('{') - content.count('}')
            open_brackets = content.count('[') - content.count(']')
                
            if open_braces > 0:
                content += '}' * open_braces
            if open_brackets > 0:
                content += ']' * open_brackets
                    
            # Try to parse the repaired content
            try:
                repaired_data = json.loads(content)
                # If we get here, the repair worked
                with open(self.file_path, 'w') as f:
                    try:
                        fcntl.flock(f, fcntl.LOCK_EX)
                        json.dump(repaired_data, f, indent=2)
                    finally:
                        fcntl.flock(f, fcntl.LOCK_UN)
                self.logger.info("Successfully repaired JSON file")
                return True
            except json.JSONDecodeError:
                self.logger.warning("Basic JSON repair failed")
                return False
                    
        except Exception as e:
            self.logger.error(f"Error during repair attempt: {e}")
            return False
        
    def _create_new_memory_file(self):
        """Create a new memory file with empty default structure."""
        # First backup the corrupted file
        import datetime
        backup_path = f"{self.file_path}.corrupted.{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}"
        try:
            import shutil
            shutil.copy2(self.file_path, backup_path)
            self.logger.warning(f"Created backup of corrupted file at {backup_path}")
        except Exception as e:
            self.logger.error(f"Failed to backup corrupted file: {e}")
                
        # Create new file with default structure
        with open(self.file_path, 'w') as f:
            try:
                fcntl.flock(f, fcntl.LOCK_EX)
                json.dump({
                    "conversations": [],
                    "user_data": {},
                    "web_content": [],
                    "recent_bot_topics": [],
                    "recent_topics": {}
                }, f, indent=2)
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)
        self.logger.warning("Created new empty shared memory file")
    
    def save_data(self, data: Dict):
        """
        Save data to the shared memory file with improved file locking and error handling.
        """
        with self.io_lock:  # Lock for file I/O operations
            for attempt in range(self.max_retries):
                try:
                    # Create a backup before writing
                    if attempt == 0 and os.path.exists(self.file_path) and os.path.getsize(self.file_path) > 0:
                        import datetime
                        # MODIFIED: Save backups to backups directory
                        backup_path = f"backups/{os.path.basename(self.file_path)}.backup.{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}"
                        try:
                            import shutil
                            shutil.copy2(self.file_path, backup_path)
                            # After creating backup, clean up old ones
                            self.cleanup_old_backups()
                        except Exception as e:
                            self.logger.warning(f"Failed to create backup before save: {e}")
                    
                    # Write data using a two-step process to minimize file corruption risk
                    # Step 1: Write to a temporary file
                    temp_file = f"{self.file_path}.tmp"
                    with open(temp_file, 'w') as f:
                        fcntl.flock(f, fcntl.LOCK_EX)  # Exclusive lock for writing
                        try:
                            # Format with pretty-printing for readability
                            json.dump(data, f, indent=2)
                            # Ensure data is flushed to disk
                            f.flush()
                            os.fsync(f.fileno())
                        finally:
                            fcntl.flock(f, fcntl.LOCK_UN)
                    
                    # Step 2: Rename the temporary file to the actual file (atomic operation)
                    os.rename(temp_file, self.file_path)
                    
                    # Update the cache
                    self._cached_data = data.copy()
                    self._cache_timestamp = time.time()
                    
                    return  # Success, exit the function
                except Exception as e:
                    self.logger.error(f"Error saving shared memory (attempt {attempt+1}/{self.max_retries}): {e}")
                    if attempt < self.max_retries - 1:
                        # Exponential backoff between retries
                        delay = random.uniform(0.1, 0.5) * (2 ** attempt)
                        time.sleep(delay)
            
            # If we get here, all retries failed
            self.logger.error("Failed to save shared memory after multiple attempts")
    
    def add_conversation(self, message: Dict):
        """
        Add a conversation message to shared memory.
        Prevents duplicate messages from being added.
        Uses file locking to prevent corruption.
        """
        # Acquire the thread lock to prevent concurrent calls from the same process
        with self.file_lock:
            try:
                # Get the current data
                data = self.load_data()
                
                # Check if this is a duplicate message
                message_id = message.get('message_id')
                sender_type = message.get('sender_type')
                
                # If we have both a message ID and sender type, check for duplicates
                if message_id is not None and sender_type is not None:
                    # Look for existing message with same ID and sender type
                    for existing in data["conversations"]:
                        if (existing.get('message_id') == message_id and 
                            existing.get('sender_type') == sender_type):
                            # This is a duplicate - log and return without adding
                            self.logger.warning(f"Prevented duplicate message (ID: {message_id}, Type: {sender_type}) from being added")
                            return

                # If not a duplicate, add with timestamp
                if 'timestamp' not in message:
                    message['timestamp'] = time.time()
                    
                data["conversations"].append(message)
                
                # Keep only the last 1000 messages (increased from 500)
                if len(data["conversations"]) > 1000:
                    data["conversations"] = data["conversations"][-1000:]
                
                # Save the updated data back to the file with proper locking
                self.save_data(data)
                
                # Update memory cache for quick access
                self.conversations = data["conversations"]
                    
            except Exception as e:
                self.logger.error(f"Error adding conversation: {e}")
                # Don't create a new file here - just log the error
    
    def get_recent_conversations(self, limit=50) -> List:
        """
        Get recent conversations up to the specified limit.
        Added error handling to prevent returning empty data.
        """
        try:
            data = self.load_data()
            
            # Safety check - if conversations is empty despite having data previously, 
            # attempt recovery from backup
            if not data.get("conversations") and hasattr(self, 'conversations') and self.conversations:
                self.logger.warning("Found empty conversations in file but have cached conversations - using cached data")
                return self.conversations[-limit:]
                
            # Cache the conversations for backup
            self.conversations = data.get("conversations", [])
            
            # Return the requested number of recent conversations
            if data.get("conversations"):
                return data["conversations"][-limit:]
            return []
            
        except Exception as e:
            self.logger.error(f"Error getting recent conversations: {e}")
            # Fallback to cached conversations if available
            if hasattr(self, 'conversations') and self.conversations:
                self.logger.warning("Falling back to cached conversations due to error")
                return self.conversations[-limit:]
            return []
    
    def get_user_history(self, user_id: str) -> List:
        data = self.load_data()
        return [msg for msg in data["conversations"] 
                if msg.get("user_id") == user_id]
    
    def add_web_content(self, content: Dict):
        """
        Add web content to storage. This now uses the dedicated WebStorage 
        for persistence and the shared_memory for compatibility.
        """
        # Add timestamp if not present
        if 'timestamp' not in content:
            content['timestamp'] = time.time()
        
        # First, add to the dedicated web content storage
        self.web_content_storage.add_content(content)
        
        # Also maintain in shared_memory.json for backward compatibility
        # but keep smaller subset in main shared memory file
        try:
            data = self.load_data()
            # Add to the shared memory's web_content array
            data["web_content"].append(content)
            # Keep only the last N items in shared memory
            if len(data["web_content"]) > self.max_web_content:
                data["web_content"] = data["web_content"][-self.max_web_content:]
            # Save data back to shared memory file
            self.save_data(data)
            
            # Update memory container for quick access
            self.web_content = data["web_content"]
            
            self.logger.info(f"Added web content to both dedicated storage and shared memory: {content.get('query', 'Unknown query')} ({content.get('source', 'unknown')})")
        except Exception as e:
            self.logger.error(f"Error adding web content to shared memory: {e}")
    
    def get_recent_web_content(self, limit=50) -> List:
        """
        Get recent web content with limit.
        This prioritizes dedicated WebStorage but falls back to shared memory if needed.
        """
        try:
            # First try to get from WebStorage
            content_from_storage = self.web_content_storage.get_recent_content(limit)
            
            if content_from_storage:
                # Log successful retrieval
                self.logger.info(f"Retrieved {len(content_from_storage)} items from dedicated web content storage")
                return content_from_storage
            
            # If nothing from dedicated storage, use shared memory as fallback
            self.logger.warning("No content found in dedicated storage, falling back to shared memory")
            data = self.load_data()
            return data["web_content"][-limit:]
            
        except Exception as e:
            # Log error and fall back to shared memory
            self.logger.error(f"Error retrieving from web content storage: {e}, falling back to shared memory")
            data = self.load_data()
            return data["web_content"][-limit:]
    
    def get_web_content_by_topic(self, topic_query, max_age_hours=3, limit=5) -> List:
        """
        Get web content related to a specific topic.
        
        Args:
            topic_query: The topic or query to search for
            max_age_hours: Maximum age of content in hours (reduced from 24 to 3)
            limit: Maximum number of results to return
            
        Returns:
            List of matching content items
        """
        try:
            # Try to get from dedicated storage
            return self.web_content_storage.search_content(topic_query, hours=max_age_hours)[:limit]
        except Exception as e:
            self.logger.error(f"Error getting content by topic from dedicated storage: {e}, falling back to shared memory")
            # Fallback to basic filtering from shared memory
            data = self.load_data()
            current_time = time.time()
            max_age_seconds = max_age_hours * 3600
            
            matching_content = []
            for content in data["web_content"]:
                # Check age
                if current_time - content.get('timestamp', 0) > max_age_seconds:
                    continue
                    
                # Check for query match (basic)
                content_query = content.get('query', '').lower()
                if topic_query.lower() in content_query:
                    matching_content.append(content)
            
            # Sort by timestamp (newest first) and return limited results
            matching_content.sort(key=lambda x: x.get('timestamp', 0), reverse=True)
            return matching_content[:limit]
    
    def update_user_data(self, user_id: str, update_data: Dict):
        data = self.load_data()
        if user_id not in data["user_data"]:
            data["user_data"][user_id] = {}
        data["user_data"][user_id].update(update_data)
        self.save_data(data)
    
    def get_user_data(self, user_id: str) -> Dict:
        data = self.load_data()
        return data["user_data"].get(user_id, {})
    
    def add_bot_topic(self, bot_id, topic, content_summary):
        """
        Track topics that bots have recently covered to avoid repetition
        
        Args:
            bot_id: The ID of the bot that covered this topic
            topic: A short description of the topic (e.g. "Bitcoin price", "Solana update")
            content_summary: Brief summary of what was covered about this topic
        """
        data = self.load_data()
        
        # Ensure the field exists
        if "recent_bot_topics" not in data:
            data["recent_bot_topics"] = []
            
        # Add the new topic
        data["recent_bot_topics"].insert(0, {
            "bot_id": bot_id,
            "topic": topic,
            "content_summary": content_summary,
            "timestamp": time.time()
        })
        
        # Trim to max size
        if len(data["recent_bot_topics"]) > self.max_topics:
            data["recent_bot_topics"] = data["recent_bot_topics"][:self.max_topics]
        
        # Save data
        self.save_data(data)
    
    def get_recent_bot_topics(self, hours=3):
        """
        Get topics covered by bots in the last specified hours
        
        Args:
            hours: How many hours back to check (default 3, reduced from 24)
            
        Returns:
            List of recent topic dictionaries, each with bot_id, topic, content_summary, timestamp
        """
        data = self.load_data()
        topics = data.get("recent_bot_topics", [])
        
        cutoff_time = time.time() - (hours * 3600)
        recent_topics = [
            topic for topic in topics
            if topic["timestamp"] > cutoff_time
        ]
        return recent_topics
    
    def has_topic_been_covered(self, topic_query, hours=1, similarity_threshold=0.7):
        """
        Check if a topic has been recently covered by any bot
        
        Args:
            topic_query: The topic to check
            hours: How many hours back to check (reduced from 6 to 1)
            similarity_threshold: Threshold for considering topics as similar (0-1)
            
        Returns:
            Tuple of (bool, dict) where the boolean indicates if the topic has been covered
            and the dict contains the most similar previous topic entry (or None)
        """
        # Get topics from recent hours
        recent_topics = self.get_recent_bot_topics(hours=hours)
        
        if not recent_topics:
            return False, None
            
        # Lowercase for comparison
        topic_query_lower = topic_query.lower()
        
        # Check for similar topics
        best_match = None
        highest_similarity = 0
        
        for topic_entry in recent_topics:
            topic_text = topic_entry["topic"].lower()
            
            # Calculate similarity
            similarity = SequenceMatcher(None, topic_query_lower, topic_text).ratio()
            
            if similarity > highest_similarity:
                highest_similarity = similarity
                best_match = topic_entry
        
        if highest_similarity >= similarity_threshold:
            return True, best_match
        
        return False, best_match

    def get_recent_search_topics(self, hours=2):
        """
        Get recent search topics with their age in hours
        
        Args:
            hours: Maximum age of searches to return (default 2 hours, reduced from 8)
            
        Returns:
            List of tuples with (search_query, hours_ago)
        """
        try:
            # First try to get the list from WebStorage
            return self.web_content_storage.get_recent_queries(hours=hours)
            
        except Exception as e:
            # Fall back to shared memory
            self.logger.error(f"Error getting recent search topics from dedicated storage: {e}, falling back to shared memory")
            
            data = self.load_data()
            web_content = data.get("web_content", [])
            
            current_time = time.time()
            cutoff_time = current_time - (hours * 3600)
            
            # Get recent searches with their age
            result = []
            for item in web_content:
                if item.get("timestamp", 0) > cutoff_time and "query" in item:
                    hours_ago = (current_time - item.get("timestamp", 0)) / 3600
                    result.append((item["query"], hours_ago))
            
            # Sort by recency (newest first)
            result.sort(key=lambda x: x[1])
            
            return result
            
    def set_system_setting(self, key: str, value: Any) -> bool:
        """
        Store a system-wide setting in the shared memory file
        
        Args:
            key: Setting name/key
            value: Setting value (must be JSON serializable)
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Get current data
            data = self.load_data()
            
            # Ensure system_settings exists
            if "system_settings" not in data:
                data["system_settings"] = {}
                
            # Update the setting
            data["system_settings"][key] = value
            
            # Save back to file
            self.save_data(data)
            
            self.logger.info(f"System setting updated: {key} = {value}")
            return True
        except Exception as e:
            self.logger.error(f"Error setting system setting {key}: {e}")
            return False
            
    def get_system_setting(self, key: str, default_value: Any = None) -> Any:
        """
        Retrieve a system-wide setting from shared memory
        
        Args:
            key: Setting name/key to retrieve
            default_value: Default value to return if setting doesn't exist
            
        Returns:
            Setting value or default_value if not found
        """
        try:
            # Get current data
            data = self.load_data()
            
            # Check if system_settings exists
            if "system_settings" not in data:
                return default_value
                
            # Return the setting value or default
            return data["system_settings"].get(key, default_value)
        except Exception as e:
            self.logger.error(f"Error getting system setting {key}: {e}")
            return default_value

    # ADDED: Methods for persistent tracking of recently used topics
    def add_recently_used_topic(self, bot_id: str, topic_query: str, current_time: float = None):
        """
        Add a topic to the list of recently used topics for a specific bot.
        This persists across bot restarts.
        
        Args:
            bot_id: The ID of the bot
            topic_query: The topic query or content that was used
            current_time: Timestamp when the topic was used (defaults to current time)
        """
        if current_time is None:
            current_time = time.time()
            
        try:
            # Get current data
            data = self.load_data()
            
            # Ensure recent_topics exists
            if "recent_topics" not in data:
                data["recent_topics"] = {}
                
            # Ensure bot_id exists in recent_topics
            if bot_id not in data["recent_topics"]:
                data["recent_topics"][bot_id] = []
                
            # Add topic to the list
            data["recent_topics"][bot_id].append({
                "query": topic_query,
                "time": current_time
            })
            
            # Keep only the most recent 50 topics per bot
            if len(data["recent_topics"][bot_id]) > 50:
                data["recent_topics"][bot_id] = data["recent_topics"][bot_id][-50:]
                
            # Save data back to file
            self.save_data(data)
            self.logger.info(f"Added topic '{topic_query}' to recently used list for bot {bot_id}")
            
        except Exception as e:
            self.logger.error(f"Error adding recently used topic: {e}")
    
    def get_recently_used_topics(self, minutes: int = 10):
        """
        Get a dictionary of topics recently used by all bots within the specified time window.
        
        Args:
            minutes: Time window in minutes (default: 10 minutes)
            
        Returns:
            Dictionary mapping bot_ids to lists of recently used topic entries
        """
        try:
            # Get current data
            data = self.load_data()
            
            # Check if recent_topics exists
            if "recent_topics" not in data:
                return {}
                
            result = {}
            current_time = time.time()
            cutoff_time = current_time - (minutes * 60)
            
            # Process each bot's topics
            for bot_id, topics in data["recent_topics"].items():
                # Filter to only include recent topics
                recent_topics = [
                    topic for topic in topics
                    if topic.get("time", 0) > cutoff_time
                ]
                
                if recent_topics:
                    result[bot_id] = recent_topics
                    
            return result
            
        except Exception as e:
            self.logger.error(f"Error getting recently used topics: {e}")
            return {}
    
    def is_topic_recently_used(self, topic_query: str, minutes: int = 10):
        """
        Check if a topic has been recently used by any bot.
        
        Args:
            topic_query: The topic to check
            minutes: Time window in minutes (default: 10 minutes)
            
        Returns:
            Tuple of (bool, dict) indicating if the topic was used and by which bot
        """
        try:
            recently_used = self.get_recently_used_topics(minutes=minutes)
            
            # Normalize query for comparison
            query_lower = topic_query.lower()
            
            # Check all bots' recent topics
            for bot_id, topics in recently_used.items():
                for topic in topics:
                    used_query = topic.get("query", "").lower()
                    
                    # Check for exact match or high similarity
                    if used_query == query_lower or (
                        len(query_lower) > 10 and (
                            used_query in query_lower or query_lower in used_query
                        )
                    ):
                        return True, {"bot_id": bot_id, "topic": used_query, "time": topic.get("time", 0)}
            
            # No match found
            return False, None
            
        except Exception as e:
            self.logger.error(f"Error checking if topic is recently used: {e}")
            return False, None
        
    def cleanup_old_topics(self, hours: int = 3):
        """
        Clean up old topic entries to prevent the file from growing too large.
        
        Args:
            hours: Remove topics older than this many hours (default: 3 hours, reduced from 24)
        """
        try:
            # Get current data
            data = self.load_data()
            
            # Check if recent_topics exists
            if "recent_topics" not in data:
                return
                
            current_time = time.time()
            cutoff_time = current_time - (hours * 3600)
            
            # Process each bot's topics
            modified = False
            for bot_id, topics in data["recent_topics"].items():
                # Filter to only include topics newer than cutoff
                recent_topics = [
                    topic for topic in topics
                    if topic.get("time", 0) > cutoff_time
                ]
                
                # Check if we removed any topics
                if len(recent_topics) < len(topics):
                    data["recent_topics"][bot_id] = recent_topics
                    modified = True
            
            # While we're at it, also clean up recent_bot_topics
            if "recent_bot_topics" in data:
                old_count = len(data["recent_bot_topics"])
                data["recent_bot_topics"] = [
                    topic for topic in data["recent_bot_topics"]
                    if topic.get("timestamp", 0) > cutoff_time
                ]
                if len(data["recent_bot_topics"]) < old_count:
                    modified = True
                    
            # Save data if modified
            if modified:
                self.save_data(data)
                self.logger.info(f"Cleaned up old topic entries older than {hours} hours")
                
        except Exception as e:
            self.logger.error(f"Error cleaning up old topics: {e}")

    # ADD NEW METHOD: Cleanup old backups
    def cleanup_old_backups(self, max_backups=10):
        """Keep only the most recent backups and delete the rest."""
        try:
            import os
            import glob
            
            # Get all backup files in the backups directory
            backup_pattern = f"backups/{os.path.basename(self.file_path)}.backup.*"
            backup_files = glob.glob(backup_pattern)
            
            # If we don't have too many backups yet, no need to clean up
            if len(backup_files) <= max_backups:
                return
                
            # Sort by modification time (newest first)
            backup_files.sort(key=os.path.getmtime, reverse=True)
            
            # Delete older files beyond the max limit
            files_to_delete = backup_files[max_backups:]
            deleted_count = 0
            for old_file in files_to_delete:
                try:
                    os.remove(old_file)
                    deleted_count += 1
                except Exception as e:
                    self.logger.error(f"Failed to delete backup {old_file}: {e}")
                    
            if deleted_count > 0:
                self.logger.info(f"Backup cleanup: Deleted {deleted_count} old backups, kept {min(max_backups, len(backup_files)-deleted_count)} most recent")
        except Exception as e:
            self.logger.error(f"Error during backup cleanup: {e}") 
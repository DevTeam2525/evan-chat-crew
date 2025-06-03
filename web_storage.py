import json
import os
import time
import logging
import fcntl  # Add import for file locking
import threading  # Add import for threading lock
from typing import Dict, List, Any

class WebContentStorage:
    """Class dedicated to storing and retrieving web search content."""
    
    def __init__(self, file_path="web_content.json"):
        """Initialize the web content storage."""
        self.file_path = file_path
        
        # Setup logging
        self.logger = logging.getLogger("WebContentStorage")
        
        # Initialize the threading lock
        self.file_lock = threading.RLock()  # Using RLock instead of Lock for reentrant locking
        
        self.ensure_file_exists()
        
        # Constants
        self.max_content_items = 100  # Maximum items to store
        
        # Retention periods in hours - REDUCED from 24 to 3 hours
        self.default_retention_hours = 3.0  # Reduced from 24 to 3 hours
        self.duplicate_check_hours = 1.0    # Reduced from 8 to 1 hour
        
        # Schedule automatic cleanup to run periodically
        self._schedule_cleanup()
        
    def _schedule_cleanup(self):
        """
        Schedule periodic cleanup of old content. 
        This is called during initialization.
        """
        # We'll use a simple timestamp-based approach
        self.next_cleanup_time = time.time() + (60 * 15)  # 15 minutes
        
    def ensure_file_exists(self):
        """Ensure the storage file exists with proper structure."""
        if not os.path.exists(self.file_path):
            # File doesn't exist, create it with default structure
            self.logger.info(f"Creating new web content file at {self.file_path}")
            with open(self.file_path, 'w') as f:
                try:
                    fcntl.flock(f, fcntl.LOCK_EX)  # Exclusive lock for writing
                    json.dump({
                        "web_content": [],
                        "last_update": time.time()
                    }, f, indent=2)
                finally:
                    fcntl.flock(f, fcntl.LOCK_UN)  # Release the lock
        else:
            # Verify file structure
            try:
                with open(self.file_path, 'r') as f:
                    try:
                        fcntl.flock(f, fcntl.LOCK_SH)  # Shared lock for reading
                        data = json.load(f)
                    finally:
                        fcntl.flock(f, fcntl.LOCK_UN)
                
                # Ensure required fields exist
                modified = False
                if "web_content" not in data:
                    data["web_content"] = []
                    modified = True
                if "last_update" not in data:
                    data["last_update"] = time.time()
                    modified = True
                
                # Save if modifications were made
                if modified:
                    with open(self.file_path, 'w') as f:
                        try:
                            fcntl.flock(f, fcntl.LOCK_EX)  # Exclusive lock for writing
                            json.dump(data, f, indent=2)
                        finally:
                            fcntl.flock(f, fcntl.LOCK_UN)
                    
            except (json.JSONDecodeError, FileNotFoundError) as e:
                # File exists but is corrupted
                self.logger.error(f"Web content file corrupted: {e}")
                
                # Create backup of corrupted file
                import datetime
                backup_path = f"{self.file_path}.corrupted.{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}"
                try:
                    import shutil
                    shutil.copy2(self.file_path, backup_path)
                    self.logger.warning(f"Created backup of corrupted file at {backup_path}")
                except Exception as backup_error:
                    self.logger.error(f"Failed to create backup: {backup_error}")
                
                # Create new file with default structure
                with open(self.file_path, 'w') as f:
                    try:
                        fcntl.flock(f, fcntl.LOCK_EX)  # Exclusive lock for writing
                        json.dump({
                            "web_content": [],
                            "last_update": time.time()
                        }, f, indent=2)
                    finally:
                        fcntl.flock(f, fcntl.LOCK_UN)
                self.logger.warning(f"Created new web content file due to corruption")
    
    def load_data(self) -> Dict:
        """Load data from the storage file with error handling."""
        # Check if cleanup is due
        if hasattr(self, 'next_cleanup_time') and time.time() > self.next_cleanup_time:
            self.cleanup_old_content()
            self.next_cleanup_time = time.time() + (60 * 15)  # Reset for 15 minutes
        
        try:
            with open(self.file_path, 'r') as f:
                try:
                    fcntl.flock(f, fcntl.LOCK_SH)  # Shared lock for reading
                    data = json.load(f)
                finally:
                    fcntl.flock(f, fcntl.LOCK_UN)
                return data
        except (json.JSONDecodeError, FileNotFoundError) as e:
            self.logger.error(f"Error loading web content file: {e}")
            self.ensure_file_exists()
            return {"web_content": [], "last_update": time.time()}
    
    def save_data(self, data: Dict):
        """Save data to the storage file with proper locking."""
        # Update last_update timestamp
        data["last_update"] = time.time()
        
        # FIXED: Use more targeted locking approach
        try:
            with open(self.file_path, 'w') as f:
                try:
                    fcntl.flock(f, fcntl.LOCK_EX)  # Exclusive lock for writing
                    json.dump(data, f, indent=2)
                finally:
                    fcntl.flock(f, fcntl.LOCK_UN)
                
            # Create a periodic backup (every 20 saves)
            if time.time() % 20 < 1:
                import datetime
                backup_path = f"{self.file_path}.backup.{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}"
                import shutil
                shutil.copy2(self.file_path, backup_path)
                self.logger.info(f"Created periodic backup at {backup_path}")
                
        except Exception as e:
            self.logger.error(f"Error saving web content file: {e}")
    
    def add_content(self, content: Dict):
        """Add a new web content item to storage."""
        # Use thread lock for thread safety
        with self.file_lock:
            data = self.load_data()
            
            # First, check if this is a duplicate of recent content
            if self.has_recent_search(content.get("query", ""), hours=self.duplicate_check_hours):
                self.logger.info(f"Skipping duplicate search for '{content.get('query', '')}'")
                return
                
            # Add timestamp if not present
            if 'timestamp' not in content:
                content['timestamp'] = time.time()
                
            # Add the content
            data["web_content"].append(content)
            
            # Keep only the most recent items
            if len(data["web_content"]) > self.max_content_items:
                data["web_content"] = data["web_content"][-self.max_content_items:]
                
            # Remove any content older than default_retention_hours
            current_time = time.time()
            cutoff_time = current_time - (self.default_retention_hours * 3600)
            data["web_content"] = [item for item in data["web_content"] if item.get('timestamp', 0) > cutoff_time]
            
            # Save the updated data
            self.save_data(data)
            self.logger.info(f"Added web content for query: {content.get('query', 'Unknown')}")
    
    def get_recent_content(self, limit=50) -> List:
        """Get the most recent web content items."""
        # Use thread lock for thread safety
        with self.file_lock:
            data = self.load_data()
            
            # Return up to the requested number of items, sorted by timestamp (newest first)
            content = data.get("web_content", [])
            content.sort(key=lambda x: x.get('timestamp', 0), reverse=True)
            
            return content[:limit]
    
    def search_content(self, query: str, hours=3.0) -> List:
        """Search for content matching the query within the given time window."""
        # Use thread lock for thread safety
        with self.file_lock:
            data = self.load_data()
            content = data.get("web_content", [])
            
            # Define time cutoff
            cutoff_time = time.time() - (hours * 3600)
            
            # Filter content by time and relevance
            query_lower = query.lower()
            results = []
            
            for item in content:
                # Skip old items
                if item.get('timestamp', 0) < cutoff_time:
                    continue
                    
                # Check item for query matches
                item_query = item.get('query', '').lower()
                
                # Direct query match
                if query_lower in item_query or item_query in query_lower:
                    results.append(item)
                    continue
                    
                # For content with text, check content
                if item.get('source') == 'perplexity' and isinstance(item.get('content'), str):
                    text = item.get('content', '').lower()
                    if query_lower in text:
                        results.append(item)
                        continue
                        
                # For tweets, check text of tweets
                if item.get('source') == 'twitter' and isinstance(item.get('content'), list):
                    for tweet in item.get('content', []):
                        if isinstance(tweet, dict) and query_lower in tweet.get('text', '').lower():
                            results.append(item)
                            break
            
            return results
    
    def has_recent_search(self, query: str, hours=1.0) -> bool:
        """Check if a similar search has been performed recently."""
        # Use thread lock for thread safety
        with self.file_lock:
            data = self.load_data()
            content = data.get("web_content", [])
            
            # Define time cutoff
            cutoff_time = time.time() - (hours * 3600)
            
            # Normalize query for comparison
            query_lower = query.lower()
            query_words = set(query_lower.split())
            
            for item in content:
                # Skip old items
                if item.get('timestamp', 0) < cutoff_time:
                    continue
                    
                # Check for similarity
                item_query = item.get('query', '').lower()
                
                # Direct match
                if query_lower == item_query:
                    return True
                    
                # Word overlap for queries with sufficient length
                if len(query_words) >= 2 and len(item_query.split()) >= 2:
                    item_words = set(item_query.split())
                    common_words = query_words.intersection(item_words)
                    
                    # If 75% or more words match, consider it a duplicate
                    if len(common_words) / min(len(query_words), len(item_words)) >= 0.75:
                        return True
            
            return False
    
    def get_recent_queries(self, hours=1.0) -> List:
        """Get a list of recent search queries with timestamps."""
        # Use thread lock for thread safety
        with self.file_lock:
            data = self.load_data()
            content = data.get("web_content", [])
            
            # Define time cutoff
            cutoff_time = time.time() - (hours * 3600)
            
            # Extract queries and times
            queries = []
            for item in content:
                timestamp = item.get('timestamp', 0)
                if timestamp >= cutoff_time:
                    query = item.get('query', '')
                    if query:
                        hours_ago = (time.time() - timestamp) / 3600
                        queries.append((query, hours_ago))
            
            # Sort by recency
            queries.sort(key=lambda x: x[1])
            
            return queries
    
    def cleanup_old_content(self):
        """
        Remove content older than the default retention period.
        This helps keep the storage file from growing too large.
        """
        try:
            data = self.load_data()
            content = data.get("web_content", [])
            
            # Calculate cutoff time
            current_time = time.time()
            cutoff_time = current_time - (self.default_retention_hours * 3600)
            
            # Filter out old content
            filtered_content = [item for item in content if item.get("timestamp", 0) > cutoff_time]
            
            # If we removed items, save the updated data
            if len(filtered_content) < len(content):
                data["web_content"] = filtered_content
                self.save_data(data)
                self.logger.info(f"Cleaned up {len(content) - len(filtered_content)} old web content items")
                
            return True
        except Exception as e:
            self.logger.error(f"Error during content cleanup: {e}")
            return False 
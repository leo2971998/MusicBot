import asyncio
import logging
import time
from typing import Dict, Set
import discord
from config import HEALTH_CHECK_INTERVAL, MEMORY_CLEANUP_INTERVAL, MAX_GUILD_DATA_AGE

logger = logging.getLogger(__name__)

class HealthMonitor:
    """Background health monitoring and cleanup system"""
    
    def __init__(self, client, player_manager, queue_manager, data_manager):
        self.client = client
        self.player_manager = player_manager
        self.queue_manager = queue_manager
        self.data_manager = data_manager
        self.health_task = None
        self.memory_task = None
        self.running = False
        
    async def start(self):
        """Start the health monitoring background tasks"""
        if self.running:
            logger.warning("Health monitor already running")
            return
            
        self.running = True
        logger.info("Starting health monitoring background tasks")
        
        # Start periodic health checks
        self.health_task = asyncio.create_task(self._health_check_loop())
        self.memory_task = asyncio.create_task(self._memory_cleanup_loop())
        
    async def stop(self):
        """Stop the health monitoring background tasks"""
        if not self.running:
            return
            
        self.running = False
        logger.info("Stopping health monitoring background tasks")
        
        if self.health_task:
            self.health_task.cancel()
            try:
                await self.health_task
            except asyncio.CancelledError:
                pass
                
        if self.memory_task:
            self.memory_task.cancel()
            try:
                await self.memory_task
            except asyncio.CancelledError:
                pass
                
    async def _health_check_loop(self):
        """Periodic health check for voice clients and connections"""
        try:
            await asyncio.sleep(30)  # Initial delay to let bot fully initialize
            
            while self.running:
                try:
                    await self._perform_health_check()
                except Exception:
                    logger.exception("Error in health check loop")
                
                await asyncio.sleep(HEALTH_CHECK_INTERVAL)
                
        except asyncio.CancelledError:
            logger.info("Health check loop cancelled")
            
    async def _memory_cleanup_loop(self):
        """Periodic memory cleanup for old data and inactive guilds"""
        try:
            await asyncio.sleep(60)  # Initial delay
            
            while self.running:
                try:
                    await self._perform_memory_cleanup()
                except Exception:
                    logger.exception("Error in memory cleanup loop")
                
                await asyncio.sleep(MEMORY_CLEANUP_INTERVAL)
                
        except asyncio.CancelledError:
            logger.info("Memory cleanup loop cancelled")
            
    async def _perform_health_check(self):
        """Perform comprehensive health check"""
        logger.debug("Performing health check")
        
        # Check voice client health
        health_status = await self.player_manager.health_check()
        unhealthy_guilds = [guild_id for guild_id, healthy in health_status.items() if not healthy]
        
        # Clean up unhealthy voice clients
        for guild_id in unhealthy_guilds:
            logger.warning(f"Cleaning up unhealthy voice client for guild {guild_id}")
            try:
                await self.player_manager.disconnect_voice_client(guild_id, cleanup_tasks=True)
            except Exception:
                logger.exception(f"Error cleaning up unhealthy voice client for guild {guild_id}")
                
        # Check for orphaned tasks
        await self._cleanup_orphaned_tasks()
        
        # Validate guild data integrity
        await self._validate_guild_data()
        
        logger.debug(f"Health check completed. Cleaned up {len(unhealthy_guilds)} unhealthy clients")
        
    async def _cleanup_orphaned_tasks(self):
        """Clean up completed or orphaned async tasks"""
        total_cleaned = 0
        
        for guild_id, tasks in list(self.player_manager.active_tasks.items()):
            cleaned_tasks = []
            
            for task_name, task in list(tasks.items()):
                if task.done():
                    # Task is completed, remove it
                    tasks.pop(task_name, None)
                    cleaned_tasks.append(task_name)
                    total_cleaned += 1
                    
            if cleaned_tasks:
                logger.debug(f"Cleaned up {len(cleaned_tasks)} completed tasks for guild {guild_id}: {cleaned_tasks}")
                
            # If no tasks remain for guild, remove the guild entry
            if not tasks:
                self.player_manager.active_tasks.pop(guild_id, None)
                
        if total_cleaned > 0:
            logger.info(f"Cleaned up {total_cleaned} completed tasks")
            
    async def _validate_guild_data(self):
        """Validate and clean up guild data for non-existent guilds"""
        invalid_guilds = []
        current_time = time.time()
        
        for guild_id in list(self.client.guilds_data.keys()):
            try:
                # Check if guild still exists
                if not guild_id.isdigit():
                    invalid_guilds.append(guild_id)
                    continue
                    
                guild = self.client.get_guild(int(guild_id))
                if not guild:
                    invalid_guilds.append(guild_id)
                    continue
                    
                # Check if guild data is too old (inactive)
                guild_data = self.client.guilds_data[guild_id]
                last_activity = guild_data.get('last_activity', current_time)
                
                if current_time - last_activity > MAX_GUILD_DATA_AGE:
                    # Guild has been inactive for too long
                    voice_client = self.player_manager.voice_clients.get(guild_id)
                    if not voice_client or not voice_client.is_connected():
                        invalid_guilds.append(guild_id)
                        logger.info(f"Marking inactive guild {guild_id} for cleanup (inactive for {(current_time - last_activity) / 3600:.1f} hours)")
                        
            except Exception as e:
                logger.warning(f"Error validating guild {guild_id}: {e}")
                invalid_guilds.append(guild_id)
                
        # Clean up invalid guilds
        for guild_id in invalid_guilds:
            try:
                await self._cleanup_guild(guild_id)
            except Exception:
                logger.exception(f"Error cleaning up guild {guild_id}")
                
        if invalid_guilds:
            logger.info(f"Cleaned up {len(invalid_guilds)} invalid/inactive guilds")
            
    async def _cleanup_guild(self, guild_id: str):
        """Clean up all data for a specific guild"""
        logger.debug(f"Cleaning up guild {guild_id}")
        
        # Disconnect voice client
        await self.player_manager.disconnect_voice_client(guild_id, cleanup_tasks=True)
        
        # Clean up guild data
        self.client.guilds_data.pop(guild_id, None)
        self.client.playback_modes.pop(guild_id, None)
        
        # Clean up queue
        self.queue_manager.cleanup_guild(guild_id)
        
        # Save updated data
        await self.data_manager.save_guilds_data(self.client)
        
    async def _perform_memory_cleanup(self):
        """Perform memory cleanup operations"""
        logger.debug("Performing memory cleanup")
        
        # Update last activity timestamps for active guilds
        current_time = time.time()
        for guild_id in self.client.guilds_data:
            voice_client = self.player_manager.voice_clients.get(guild_id)
            if voice_client and voice_client.is_connected():
                self.client.guilds_data[guild_id]['last_activity'] = current_time
        
        # Clean up expired search cache entries
        try:
            from utils.search_cache import search_cache
            expired_count = search_cache.clear_expired()
            if expired_count > 0:
                logger.debug(f"Cleaned up {expired_count} expired search cache entries")
        except Exception as e:
            logger.warning(f"Error cleaning up search cache: {e}")
                
        # Force garbage collection for Python objects
        import gc
        before_count = len(gc.get_objects())
        collected = gc.collect()
        after_count = len(gc.get_objects())
        
        logger.debug(f"Memory cleanup: collected {collected} objects, {before_count} -> {after_count} objects")
        
        # Log memory statistics
        await self._log_memory_stats()
        
    async def _log_memory_stats(self):
        """Log current memory and resource usage statistics"""
        try:
            import psutil
            import os
            
            # Get process memory info
            process = psutil.Process(os.getpid())
            memory_info = process.memory_info()
            
            # Get system memory info
            system_memory = psutil.virtual_memory()
            
            # Count our resources
            voice_clients = len(self.player_manager.voice_clients)
            active_tasks = sum(len(tasks) for tasks in self.player_manager.active_tasks.values())
            guild_data_count = len(self.client.guilds_data)
            total_queue_size = sum(len(queue) for queue in self.queue_manager.queues.values())
            
            # Get search cache stats
            cache_stats = {"active_entries": 0, "memory_usage": "0B"}
            try:
                from utils.search_cache import search_cache
                cache_stats = search_cache.get_stats()
            except Exception as e:
                logger.debug(f"Could not get cache stats: {e}")
            
            logger.info(f"Memory stats - Process: {memory_info.rss / 1024 / 1024:.1f}MB, "
                       f"System: {system_memory.percent:.1f}% used, "
                       f"Voice clients: {voice_clients}, "
                       f"Active tasks: {active_tasks}, "
                       f"Guild data: {guild_data_count}, "
                       f"Queue items: {total_queue_size}, "
                       f"Cache entries: {cache_stats['active_entries']} ({cache_stats['memory_usage']})")
                       
        except ImportError:
            # psutil not available, just log basic stats
            voice_clients = len(self.player_manager.voice_clients)
            active_tasks = sum(len(tasks) for tasks in self.player_manager.active_tasks.values())
            guild_data_count = len(self.client.guilds_data)
            
            logger.debug(f"Resource stats - Voice clients: {voice_clients}, "
                        f"Active tasks: {active_tasks}, "
                        f"Guild data: {guild_data_count}")
                        
        except Exception as e:
            logger.warning(f"Could not retrieve memory stats: {e}")
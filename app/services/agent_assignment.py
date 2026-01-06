"""
Agent Assignment Service
Handles automatic assignment of agents to properties and inquiries with pincode-based notifications
"""

import asyncio
import uuid
from typing import Dict, List, Optional, Any
from ..db.supabase_client import db
import datetime as dt

class AgentAssignmentService:
    """Service for managing agent assignments to properties and inquiries"""
    
    @staticmethod
    async def assign_agent_to_property(property_id: str, agent_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Assign an agent to a property with pincode-based notification system.
        If no agent_id is provided, automatically assign based on pincode proximity.
        """
        try:
            # Get property details
            properties = await db.select("properties", filters={"id": property_id})
            if not properties:
                return {"success": False, "error": "Property not found"}
            
            property_data = properties[0]
            
            # If property already has an agent, return current assignment
            if property_data.get("agent_id"):
                return {
                    "success": True, 
                    "message": "Property already has an assigned agent",
                    "agent_id": property_data["agent_id"]
                }
            
            # If specific agent requested, assign that agent
            if agent_id:
                # Verify agent exists and is active
                agents = await db.select("users", filters={"id": agent_id, "user_type": "agent", "status": "active"})
                if not agents:
                    return {"success": False, "error": "Agent not found or inactive"}
                
                # Assign the specific agent
                await db.update("properties", {"agent_id": agent_id}, {"id": property_id})
                return {
                    "success": True,
                    "message": f"Agent {agent_id} assigned to property",
                    "agent_id": agent_id
                }
            
            # Auto-assign based on pincode proximity
            assignment_result = await AgentAssignmentService._assign_agent_by_pincode(property_data)
            return assignment_result
            
        except Exception as e:
            print(f"[AGENT_ASSIGNMENT] Error assigning agent to property: {e}")
            return {"success": False, "error": str(e)}
    
    @staticmethod
    async def _assign_agent_by_pincode(property_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Assign agent based on pincode proximity with notification rounds
        """
        try:
            property_id = property_data["id"]
            zip_code = property_data.get("zip_code")
            
            if not zip_code:
                return {"success": False, "error": "Property has no zip code"}
            
            # Check if property is already in notification rounds
            notification_rounds = await AgentAssignmentService._get_property_notification_rounds(property_id)
            
            if notification_rounds >= 3:
                # Move to property pool after 3 rounds
                await AgentAssignmentService._move_to_property_pool(property_id)
                return {
                    "success": True,
                    "message": "Property moved to pool after 3 notification rounds",
                    "in_pool": True
                }
            
            # Get agents in the same pincode area
            agents_in_area = await AgentAssignmentService._get_agents_by_pincode(zip_code)
            
            if not agents_in_area:
                # If no agents in same pincode, get agents from nearby areas
                agents_in_area = await AgentAssignmentService._get_agents_by_nearby_pincodes(zip_code)
            
            if not agents_in_area:
                return {"success": False, "error": "No agents available in the area"}
            
            # Send notifications to agents in rounds
            notification_result = await AgentAssignmentService._send_property_notifications(
                property_id, agents_in_area, notification_rounds
            )
            
            return notification_result
            
        except Exception as e:
            print(f"[AGENT_ASSIGNMENT] Error in pincode assignment: {e}")
            return {"success": False, "error": str(e)}
    
    @staticmethod
    async def _get_property_notification_rounds(property_id: str) -> int:
        """Get the current notification round for a property"""
        try:
            notifications = await db.select("notifications", filters={
                "entity_type": "property",
                "entity_id": property_id,
                "type": "property_assignment"
            })
            return len(notifications)
        except Exception as e:
            print(f"[AGENT_ASSIGNMENT] Error getting notification rounds: {e}")
            return 0
    
    @staticmethod
    async def _get_agents_by_pincode(zip_code: str) -> List[Dict[str, Any]]:
        """Get agents in the same pincode area"""
        try:
            # Get agents with same zip code
            agents = await db.select("users", filters={
                "user_type": "agent",
                "status": "active",
                "zip_code": zip_code
            })
            return agents
        except Exception as e:
            print(f"[AGENT_ASSIGNMENT] Error getting agents by pincode: {e}")
            return []
    
    @staticmethod
    async def _get_agents_by_nearby_pincodes(zip_code: str) -> List[Dict[str, Any]]:
        """Get agents from nearby pincode areas"""
        try:
            # For now, get all active agents as fallback
            # In a real implementation, you'd have a pincode proximity service
            agents = await db.select("users", filters={
                "user_type": "agent",
                "status": "active"
            })
            return agents[:5]  # Limit to 5 agents
        except Exception as e:
            print(f"[AGENT_ASSIGNMENT] Error getting nearby agents: {e}")
            return []
    
    @staticmethod
    async def _send_property_notifications(property_id: str, agents: List[Dict[str, Any]], current_round: int) -> Dict[str, Any]:
        """Send property assignment notifications to agents"""
        try:
            # Get property details for notification
            properties = await db.select("properties", filters={"id": property_id})
            if not properties:
                return {"success": False, "error": "Property not found"}
            
            property_data = properties[0]
            
            # Create notifications for each agent
            notifications_created = []
            for agent in agents:
                notification_data = {
                    "id": str(uuid.uuid4()),  # Use UUID instead of timestamp
                    "title": f"New Property Assignment - Round {current_round + 1}",
                    "message": f"New property '{property_data.get('title', 'Untitled')}' in {property_data.get('city', 'Unknown City')} needs your attention.",
                    "type": "property_assignment",
                    "entity_type": "property",
                    "entity_id": property_id,
                    "user_id": agent["id"],
                    "read": False,
                    "created_at": dt.datetime.utcnow().isoformat()
                }
                
                await db.insert("notifications", notification_data)
                notifications_created.append(agent["id"])
            
            # Update property with notification round
            # Note: Only update notification_round if column exists in schema
            # last_notification_sent column removed as it doesn't exist in properties table
            try:
                await db.update("properties", {
                    "notification_round": current_round + 1
                }, {"id": property_id})
            except Exception as update_error:
                # If notification_round doesn't exist either, just log and continue
                print(f"[AGENT_ASSIGNMENT] Could not update notification_round: {update_error}")
                # Notification was still sent, so this is non-critical
            
            return {
                "success": True,
                "message": f"Notifications sent to {len(notifications_created)} agents (Round {current_round + 1})",
                "notifications_sent": len(notifications_created),
                "round": current_round + 1
            }
            
        except Exception as e:
            print(f"[AGENT_ASSIGNMENT] Error sending notifications: {e}")
            return {"success": False, "error": str(e)}
    
    @staticmethod
    async def _move_to_property_pool(property_id: str) -> None:
        """Move property to pool after 3 notification rounds"""
        try:
            await db.update("properties", {
                "in_pool": True,
                "pool_date": dt.datetime.utcnow().isoformat(),
                "status": "pool"
            }, {"id": property_id})
            
            # Create admin notification about pool
            admin_notification = {
                "id": str(uuid.uuid4()),  # Use UUID instead of timestamp
                "title": "Property Moved to Pool",
                "message": f"Property {property_id} has been moved to the pool after 3 notification rounds.",
                "type": "admin_alert",
                "entity_type": "property",
                "entity_id": property_id,
                "user_id": None,  # Admin notification
                "read": False,
                "created_at": dt.datetime.utcnow().isoformat()
            }
            
            await db.insert("notifications", admin_notification)
            
        except Exception as e:
            print(f"[AGENT_ASSIGNMENT] Error moving to pool: {e}")
    
    @staticmethod
    async def accept_property_assignment(property_id: str, agent_id: str) -> Dict[str, Any]:
        """Agent accepts property assignment"""
        try:
            # Verify agent exists and is active
            agents = await db.select("users", filters={"id": agent_id, "user_type": "agent", "status": "active"})
            if not agents:
                return {"success": False, "error": "Agent not found or inactive"}
            
            # Assign property to agent
            await db.update("properties", {"agent_id": agent_id}, {"id": property_id})
            
            # Mark agent's notification as read
            await db.update("notifications", {"read": True}, {
                "entity_type": "property",
                "entity_id": property_id,
                "user_id": agent_id,
                "type": "property_assignment"
            })
            
            # Cancel other agents' notifications for this property
            await db.update("notifications", {"read": True, "cancelled": True}, {
                "entity_type": "property",
                "entity_id": property_id,
                "type": "property_assignment",
                "user_id": {"!=": agent_id}
            })
            
            agent_name = f"{agents[0]['first_name']} {agents[0]['last_name']}"
            return {
                "success": True,
                "message": f"Property assigned to {agent_name}",
                "agent_id": agent_id,
                "agent_name": agent_name
            }
            
        except Exception as e:
            print(f"[AGENT_ASSIGNMENT] Error accepting assignment: {e}")
            return {"success": False, "error": str(e)}
    
    @staticmethod
    async def reject_property_assignment(property_id: str, agent_id: str, reason: str = "") -> Dict[str, Any]:
        """Agent rejects property assignment"""
        try:
            # Mark agent's notification as read and rejected
            await db.update("notifications", {
                "read": True,
                "rejected": True,
                "rejection_reason": reason
            }, {
                "entity_type": "property",
                "entity_id": property_id,
                "user_id": agent_id,
                "type": "property_assignment"
            })
            
            # Check if all agents have rejected, then move to next round
            notifications = await db.select("notifications", filters={
                "entity_type": "property",
                "entity_id": property_id,
                "type": "property_assignment"
            })
            
            rejected_count = len([n for n in notifications if n.get("rejected")])
            total_notifications = len(notifications)
            
            if rejected_count >= total_notifications:
                # All agents rejected, move to next round
                await AgentAssignmentService._assign_agent_to_property(property_id)
            
            return {
                "success": True,
                "message": "Property assignment rejected",
                "next_round": rejected_count >= total_notifications
            }
            
        except Exception as e:
            print(f"[AGENT_ASSIGNMENT] Error rejecting assignment: {e}")
            return {"success": False, "error": str(e)}
    
    @staticmethod
    async def assign_agent_to_inquiry(inquiry_id: str, property_id: str) -> Dict[str, Any]:
        """
        Assign an agent to an inquiry based on the property's assigned agent
        """
        try:
            # Get property details to find assigned agent
            properties = await db.select("properties", filters={"id": property_id})
            if not properties:
                return {"success": False, "error": "Property not found"}
            
            property_data = properties[0]
            agent_id = property_data.get("agent_id")
            
            if not agent_id:
                return {"success": False, "error": "Property has no assigned agent"}
            
            # Update inquiry with assigned agent
            await db.update("inquiries", {"assigned_agent_id": agent_id}, {"id": inquiry_id})
            
            # Get agent details for response
            agents = await db.select("users", filters={"id": agent_id})
            agent_name = f"{agents[0]['first_name']} {agents[0]['last_name']}" if agents else "Unknown Agent"
            
            return {
                "success": True,
                "message": f"Agent {agent_name} assigned to inquiry",
                "agent_id": agent_id,
                "agent_name": agent_name
            }
            
        except Exception as e:
            print(f"[AGENT_ASSIGNMENT] Error assigning agent to inquiry: {e}")
            return {"success": False, "error": str(e)}
    
    @staticmethod
    async def get_agent_properties(agent_id: str) -> List[Dict[str, Any]]:
        """Get all properties assigned to a specific agent"""
        try:
            properties = await db.select("properties", filters={"agent_id": agent_id})
            return properties
        except Exception as e:
            print(f"[AGENT_ASSIGNMENT] Error getting agent properties: {e}")
            return []
    
    @staticmethod
    async def get_agent_inquiries(agent_id: str) -> List[Dict[str, Any]]:
        """Get all inquiries assigned to a specific agent"""
        try:
            inquiries = await db.select("inquiries", filters={"assigned_agent_id": agent_id})
            return inquiries
        except Exception as e:
            print(f"[AGENT_ASSIGNMENT] Error getting agent inquiries: {e}")
            return []
    
    @staticmethod
    async def reassign_property(property_id: str, new_agent_id: str) -> Dict[str, Any]:
        """Reassign a property to a different agent"""
        try:
            # Verify new agent exists and is active
            agents = await db.select("users", filters={"id": new_agent_id, "user_type": "agent", "status": "active"})
            if not agents:
                return {"success": False, "error": "Agent not found or inactive"}
            
            # Update property assignment
            await db.update("properties", {"agent_id": new_agent_id}, {"id": property_id})
            
            # Also reassign any pending inquiries for this property
            inquiries = await db.select("inquiries", filters={"property_id": property_id, "status": "new"})
            for inquiry in inquiries:
                await db.update("inquiries", {"assigned_agent_id": new_agent_id}, {"id": inquiry["id"]})
            
            agent_name = f"{agents[0]['first_name']} {agents[0]['last_name']}"
            return {
                "success": True,
                "message": f"Property reassigned to {agent_name}",
                "agent_id": new_agent_id,
                "agent_name": agent_name
            }
            
        except Exception as e:
            print(f"[AGENT_ASSIGNMENT] Error reassigning property: {e}")
            return {"success": False, "error": str(e)}
    
    @staticmethod
    async def get_available_agents() -> List[Dict[str, Any]]:
        """Get all available agents"""
        try:
            agents = await db.select("users", filters={"user_type": "agent", "status": "active"})
            return agents
        except Exception as e:
            print(f"[AGENT_ASSIGNMENT] Error getting available agents: {e}")
            return []
    
    @staticmethod
    async def get_unassigned_properties() -> List[Dict[str, Any]]:
        """Get all properties without assigned agents"""
        try:
            properties = await db.select("properties", filters={"agent_id": None})
            return properties
        except Exception as e:
            print(f"[AGENT_ASSIGNMENT] Error getting unassigned properties: {e}")
            return []
